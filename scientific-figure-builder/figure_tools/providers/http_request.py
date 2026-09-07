"""Cancellable HTTP reads with independent inactivity and absolute deadlines."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from figure_tools.providers.request_policy import RequestPolicy
from figure_tools.providers.request_session import CURRENT_REQUEST, RequestSession, retry_delay
from figure_tools.providers.transport import RateLimitError, RequestError

MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_EVENT_BYTES = 8 * 1024 * 1024


def http_failure(status: int, detail: str, headers: Any) -> RequestError:
    kwargs: dict[str, Any] = dict(status=status, retry_after=headers.get('retry-after'),
                  request_id=headers.get('x-request-id') or headers.get('request-id'),
                  submission='submitted')
    if status == 429:
        return RateLimitError(f'provider HTTP {status}: {detail}', **kwargs)
    return RequestError(f'provider HTTP {status}: {detail}', category='server_error' if status >= 500 else 'http_error',
                        retryable=status in (500, 502, 503, 504), **kwargs)


class EventReader:
    """Bounded SSE framing; only terminal response objects become results."""

    def __init__(self, session: RequestSession) -> None:
        self.buffer = bytearray()
        self.data: list[bytes] = []
        self.event_size = 0
        self.session = session

    def feed(self, chunk: bytes) -> dict[str, Any] | None:
        self.buffer.extend(chunk)
        while b'\n' in self.buffer:
            line, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            line = line.rstrip(b'\r')
            self.event_size += len(line)
            if self.event_size > MAX_EVENT_BYTES:
                raise RequestError('SSE event exceeds size limit', category='invalid_response')
            if not line:
                result = self._event()
                self.event_size = 0
                if result is not None:
                    return result
            elif line.startswith(b'data:'):
                self.data.append(bytes(line[5:]).lstrip(b' '))
            elif line.startswith(b':'):
                if self.session.status.get('state') == 'awaiting_response':
                    self.session.status['state'] = 'connection_active_processing_unknown'
        if len(self.buffer) > MAX_EVENT_BYTES:
            raise RequestError('SSE line exceeds size limit', category='invalid_response')
        return None

    def _event(self) -> dict[str, Any] | None:
        if not self.data:
            return None
        payload = b'\n'.join(self.data)
        self.data.clear()
        try:
            event = json.loads(payload)
        except (ValueError, UnicodeError) as exc:
            raise RequestError('invalid SSE event', category='invalid_response') from exc
        if not isinstance(event, dict):
            raise RequestError('SSE event must be an object', category='invalid_response')
        kind = event.get('type')
        # Never retain raw reasoning or output deltas in progress diagnostics.
        if kind == 'response.created':
            self.session.status.update(state='connection_active_processing_unknown', last_event=kind)
        elif kind == 'response.in_progress':
            self.session.status.update(state='provider_processing', last_event=kind)
        elif isinstance(kind, str) and kind.startswith('response.') and kind.endswith('.delta'):
            self.session.status.update(state='receiving_output', last_event='response.delta')
        if kind in ('response.completed', 'response.incomplete', 'response.failed'):
            response = event.get('response')
            if not isinstance(response, dict):
                raise RequestError('terminal event missing response', category='invalid_response')
            expected = str(kind).split('.')[-1]
            if response.get('status') != expected:
                raise RequestError('terminal response status mismatch', category='invalid_response')
            self.session.status.update(last_event=kind)
            if kind == 'response.failed':
                # Failure after stream acceptance is never a safe HTTP retry.
                raise RequestError(f"provider stream failed: {response.get('error')}", category='stream_failed', submission='submitted')
            return response
        return None


async def _request(url: str, method: str, headers: dict[str, str], content: bytes | None,
                   stream: bool, session: RequestSession) -> bytes | dict[str, Any]:
    policy = session.policy
    last_activity: float | None = None
    next_checkpoint = time.monotonic() + policy.status_interval
    response_bytes = bytearray()
    reader = EventReader(session)
    session.status.update(state='awaiting_response', last_event=None, http_status=None, request_id=None)

    async def receive() -> bytes | dict[str, Any]:
        nonlocal last_activity
        timeout = httpx.Timeout(connect=min(policy.connect_timeout, session.remaining),
                                read=None, write=min(policy.connect_timeout, session.remaining), pool=policy.connect_timeout)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=(method == 'GET')) as client:
            # The caller already serialized and validated the request before dispatch.
            dispatched = False

            async def trace(name: str, info: dict[str, Any]) -> None:
                nonlocal dispatched, last_activity
                if method == 'POST' and name.endswith('send_request_headers.started') and not dispatched:
                    session.dispatch()
                    dispatched = True
                if name.endswith('send_request_body.complete'):
                    last_activity = time.monotonic()

            session.report(state='awaiting_response', request_kind='model' if method == 'POST' else 'asset_download')
            async with client.stream(method, url, headers=headers, content=content, extensions={'trace': trace}) as response:
                last_activity = time.monotonic()
                session.status.update(http_status=response.status_code,
                                      request_id=response.headers.get('x-request-id') or response.headers.get('request-id'))
                if response.status_code >= 300:
                    raise http_failure(response.status_code, '', response.headers)
                total = 0
                async for chunk in response.aiter_bytes():
                    session.check()
                    last_activity = time.monotonic()
                    session.status['last_activity_at'] = time.time()
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise RequestError('response exceeds size limit', category='invalid_response')
                    if stream:
                        result = reader.feed(chunk)
                        if result is not None:
                            return result
                    else:
                        response_bytes.extend(chunk)
                if stream:
                    raise RequestError('stream ended before terminal response; remote outcome unknown', category='stream_interrupted')
                return bytes(response_bytes)

    task = asyncio.create_task(receive())
    try:
        while True:
            session.check()
            now = time.monotonic()
            if last_activity is not None and now - last_activity >= policy.inactivity_timeout:
                raise RequestError('response inactivity timeout; remote outcome unknown', category='inactivity_timeout')
            if now >= next_checkpoint:
                session.report(checkpoint=True)
                next_checkpoint = now + policy.status_interval
            inactivity_remaining = policy.inactivity_timeout - (now - last_activity) if last_activity is not None else policy.inactivity_timeout
            delay = min(.1, session.remaining, inactivity_remaining, max(.001, next_checkpoint - now))
            done, _ = await asyncio.wait({task}, timeout=max(.001, delay))
            if done:
                session.check()
                return task.result()
    except httpx.ConnectError as exc:
        raise RequestError('provider connection establishment failed', category='connection_error', retryable=True, submission='not_submitted') from exc
    except httpx.ConnectTimeout as exc:
        raise RequestError('provider connection establishment timed out', category='connect_timeout', retryable=True, submission='not_submitted') from exc
    except httpx.HTTPError as exc:
        raise RequestError('provider connection interrupted; remote outcome unknown', category='connection_error') from exc
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def request(url: str, *, method: str, headers: dict[str, str], body: dict[str, Any] | None = None,
            stream: bool = False, timeout: float = 30) -> bytes | dict[str, Any]:
    content = json.dumps(body).encode('utf-8') if body is not None else None
    session = CURRENT_REQUEST.get() or RequestSession(RequestPolicy.resolve('generation', {'inactivity_timeout': timeout}))
    if method != 'GET':
        return asyncio.run(_request(url, method, headers, content, stream, session))
    for attempt in range(session.policy.max_attempts):
        session.check()
        try:
            session.report(request_kind='asset_download', download_attempt=attempt + 1)
            return asyncio.run(_request(url, method, headers, content, stream, session))
        except RequestError as exc:
            if not exc.retryable or attempt + 1 >= session.policy.max_attempts:
                exc.retryable = False
                raise
            delay = retry_delay(session.policy, attempt, exc.retry_after)
            if delay >= session.remaining:
                raise RequestError('asset download retry exceeds deadline', category='deadline_exhausted') from exc
            session.report(request_kind='asset_download', selected_delay=delay)
            if session.cancelled.wait(delay):
                session.check()
    raise AssertionError('unreachable')
