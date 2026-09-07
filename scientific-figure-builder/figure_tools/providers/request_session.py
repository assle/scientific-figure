"""One logical Provider invocation; context-local across concurrent figure work."""
from __future__ import annotations

import threading
import time
import random
from email.utils import parsedate_to_datetime
from contextvars import ContextVar
from dataclasses import dataclass, field
from collections.abc import Callable, Mapping
from typing import Any

from figure_tools.providers.request_policy import RequestPolicy
from figure_tools.providers.transport import RequestError


@dataclass
class RequestSession:
    policy: RequestPolicy
    dispatch: Callable[[], None] = lambda: None
    progress: Callable[[dict[str, Any]], None] = lambda status: None
    cancelled: threading.Event = field(default_factory=threading.Event)
    started: float = field(default_factory=time.monotonic)
    status: dict[str, Any] = field(default_factory=dict)
    output_usage: dict[str, int] | None = None

    def record_usage(self, response: Mapping[str, Any]) -> None:
        usage = response.get("usage")
        if not isinstance(usage, Mapping):
            return
        counts = {key: value for key in ("input_tokens", "output_tokens", "total_tokens")
                  if type(value := usage.get(key)) is int and value >= 0}
        details = usage.get("output_tokens_details")
        reasoning = details.get("reasoning_tokens") if isinstance(details, Mapping) else usage.get("reasoning_tokens")
        if type(reasoning) is int and reasoning >= 0:
            counts["reasoning_tokens"] = reasoning
        self.output_usage = counts or None

    @property
    def remaining(self) -> float:
        return self.policy.total_timeout - (time.monotonic() - self.started)

    def check(self) -> None:
        if self.cancelled.is_set():
            raise RequestError('request cancelled; remote outcome unknown', category='cancelled')
        if self.remaining <= 0:
            raise RequestError('logical invocation deadline exceeded; remote outcome unknown',
                               category='deadline_exhausted')

    def report(self, **details: Any) -> None:
        self.status.update(details)
        self.progress({**self.status, 'elapsed_seconds': time.monotonic() - self.started})


CURRENT_REQUEST: ContextVar[RequestSession | None] = ContextVar('provider_request', default=None)


def retry_delay(policy: RequestPolicy, retry_index: int, retry_after: str | None) -> float:
    ceiling = min(policy.backoff_cap, policy.backoff_base * (2 ** min(retry_index, 30)))
    delay = random.uniform(ceiling / 2, ceiling)
    if retry_after:
        try:
            server_delay = float(retry_after)
        except ValueError:
            try:
                server_delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
            except (ValueError, TypeError, OverflowError):
                server_delay = 0
        if server_delay > 0:
            delay = max(delay, server_delay)
    return delay
