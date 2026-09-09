"""Provider waiting through the Lifecycle entry point and real local HTTP."""
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from figure_tools.providers.client import ProviderClient
from figure_tools.providers.generic_transport import ProviderRouter
from figure_tools.providers.transport import ProviderError, RateLimitError
from figure_tools.phase_workers import ProviderPhaseWorker
from figure_tools.state import RunState
from tests.unit.test_lifecycle_orchestrator import _orchestrator, _request


@contextmanager
def provider_server(respond):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            try:
                respond(self, body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_GET(self):
            try:
                respond(self, None)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def workflow(tmp_path, url, policy=None):
    models = {'phase_reasoning': {'provider': 'local', 'model': 'local-test'}}
    router = ProviderRouter(models, {'local': {
        'type': 'openai', 'base_url': url, 'supports_responses_streaming': True,
        'request_policy': policy or {},
    }}, credentials={'local': 'local-secret'})
    state = RunState('waiting', budget={'phase_reasoning': 5})
    client = ProviderClient(models, router, state=state, output_dir=tmp_path)
    orch, _, _ = _orchestrator(tmp_path, _request(), run_dir=tmp_path,
                              state=state, worker=ProviderPhaseWorker(client))
    return orch, state


def test_lifecycle_read_timeout_is_not_rate_limit_or_retried(tmp_path):
    def stall(handler, body):
        time.sleep(.2)
        handler.send_response(200)
        handler.end_headers()
    with provider_server(stall) as (url, requests):
        orch, state = workflow(tmp_path, url, {'inactivity_timeout': .05})
        with pytest.raises(ProviderError) as caught:
            orch.advance('start')
        assert not isinstance(caught.value, RateLimitError)
        assert 'inactivity' in str(caught.value)
        assert len(requests) == 1
        assert state.calls_used('phase_reasoning') == 1
        persisted = RunState.load(tmp_path / 'run_state.json')
        assert persisted.calls_used('phase_reasoning') == 1
        assert persisted.to_dict()['provider_status']['phase_reasoning']['stop_reason'] == 'inactivity_timeout'


def event(handler, kind, response=None):
    value = {'type': kind}
    if response is not None:
        value['response'] = response
    handler.wfile.write(('data: ' + json.dumps(value) + '\n\n').encode())
    handler.wfile.flush()


def test_heartbeats_survive_checkpoints_without_resending(tmp_path):
    def respond(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        for _ in range(20):
            handler.wfile.write(b': keep-alive\n\n')
            handler.wfile.flush()
            time.sleep(.05)
        event(handler, 'response.failed', {'status': 'failed', 'error': {'code': 'test_stop'}})
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url, {'inactivity_timeout': .5, 'status_interval': .1})
        with pytest.raises(ProviderError, match='stream_failed'):
            orch.advance('start')
        assert len(requests) == 1
        assert requests[0]['stream'] is True
        assert state.calls_used('phase_reasoning') == 1
        snapshot = state.to_dict()['provider_status']['phase_reasoning']
        assert snapshot['elapsed_seconds'] > .8
        assert snapshot['checkpoint'] is True
        assert snapshot['stop_reason'] == 'stream_failed'


def test_heartbeats_do_not_reset_total_deadline(tmp_path):
    def respond(handler, body):
        handler.send_response(200)
        handler.end_headers()
        for _ in range(50):
            handler.wfile.write(b': keep-alive\n\n')
            handler.wfile.flush()
            time.sleep(.01)
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url, {'inactivity_timeout': .15, 'total_timeout': .2, 'status_interval': .03})
        with pytest.raises(ProviderError, match='deadline_exhausted'):
            orch.advance('start')
        assert len(requests) == 1
        assert state.to_dict()['provider_status']['phase_reasoning']['elapsed_seconds'] < .4


@pytest.mark.parametrize('code, count', [(429, 3), (500, 3), (502, 3), (503, 3), (504, 3), (401, 1), (400, 1), (501, 1)])
def test_http_errors_have_bounded_attempts_and_budget(tmp_path, code, count):
    def respond(handler, body):
        handler.send_response(code)
        handler.end_headers()
        handler.wfile.write(b'failure')
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url, {'backoff_base': 0, 'backoff_cap': 0})
        with pytest.raises(ProviderError):
            orch.advance('start')
        assert len(requests) == count
        assert state.calls_used('phase_reasoning') == count
        assert state.retries('phase_reasoning', 'transient') == count - 1


def test_stream_completion_produces_valid_intake_artifact(tmp_path):
    def respond(handler, body):
        prompt = body['input'][0]['content'][0]['text']
        shape = json.loads(prompt.split('Return ONLY one JSON object matching this output shape:\n')[1])
        handler.send_response(200)
        handler.end_headers()
        event(handler, 'response.created')
        event(handler, 'response.completed', {'status': 'completed', 'output_text': json.dumps(shape)})
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url)
        # Missing clarification holds the Lifecycle after Intake.
        orch.request['export_target'] = None
        result = orch.advance('start')
        assert result['status'] == 'paused'
        assert len(requests) == 1
        assert state.to_dict()['provider_status']['phase_reasoning']['state'] == 'completed'


def test_cancel_stops_stream_without_resubmission(tmp_path):
    started = threading.Event()
    def respond(handler, body):
        handler.send_response(200)
        handler.end_headers()
        started.set()
        time.sleep(.5)
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url)
        client = orch.worker.provider_client
        def cancel():
            assert started.wait(2)
            client.cancelled.set()
        thread = threading.Thread(target=cancel)
        thread.start()
        with pytest.raises(ProviderError, match='cancelled'):
            orch.advance('start')
        thread.join()
        assert len(requests) == 1
        assert state.to_dict()['provider_status']['phase_reasoning']['stop_reason'] == 'cancelled'


@pytest.mark.parametrize('wire, reason', [
    (b'data: {invalid}\n\n', 'invalid_response'),
    (b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n', 'stream_interrupted'),
    (b'data: {"type":"response.completed","response":{"status":"in_progress"}}\n\n', 'invalid_response'),
])
def test_partial_or_malformed_stream_cannot_complete_phase(tmp_path, wire, reason):
    def respond(handler, body):
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(wire)
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url)
        with pytest.raises(ProviderError, match=reason):
            orch.advance('start')
        assert len(requests) == 1
        assert state.artifact('figure_brief') is None


def test_retry_after_beyond_deadline_does_not_resubmit(tmp_path):
    def respond(handler, body):
        handler.send_response(429)
        handler.send_header('Retry-After', '100')
        handler.end_headers()
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url, {'total_timeout': 2})
        with pytest.raises(ProviderError, match='deadline_exhausted'):
            orch.advance('start')
        assert len(requests) == 1
        assert state.retries('phase_reasoning', 'transient') == 0


def test_mcp_progress_and_cancellation_during_header_wait(tmp_path, monkeypatch):
    import io
    import figure_tools.server as server
    from figure_tools.runtime_context import RuntimeContextFactory
    from figure_tools.providers.auth import MemorySecretStore
    started = threading.Event()
    def respond(handler, body):
        started.set()
        time.sleep(.4)
        handler.send_response(200)
        handler.end_headers()
    with provider_server(respond) as (url, requests):
        config = {'models': {'phase_reasoning': {'provider': 'live', 'model': 'test'}},
                  'providers': {'live': {'type': 'openai', 'base_url': url,
                    'supports_responses_streaming': True, 'credential_id': 'test',
                    'request_policy': {'status_interval': .02}}}}
        factory = RuntimeContextFactory(config_loader=lambda _: config,
                    secret_store=MemorySecretStore({'test': 'private-test-key'}),
                    environ={}, cache_dir=tmp_path / 'cache')
        monkeypatch.setattr(server, 'RuntimeContextFactory', lambda: factory)
        class Incoming:
            def __iter__(self):
                yield json.dumps({'id': 1, 'method': 'tools/call', 'params': {
                    'name': 'advance_figure_workflow', '_meta': {'progressToken': 'p'},
                    'arguments': {'request': _request(), 'run_dir': str(tmp_path / 'run')}}}) + '\n'
                assert started.wait(2)
                time.sleep(.08)
                yield json.dumps({'method': 'notifications/cancelled', 'params': {'requestId': 1}}) + '\n'
        output = io.StringIO()
        monkeypatch.setattr(server.sys, 'stdin', Incoming())
        monkeypatch.setattr(server.sys, 'stdout', output)
        assert server.serve_stdio() == 0
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        assert any(m.get('method') == 'notifications/progress' for m in messages)
        assert 'cancelled' in messages[-1]['error']['message']
        assert 'private-test-key' not in output.getvalue()
        assert len(requests) == 1
        persisted = RunState.load(tmp_path / 'run' / 'run_state.json')
        assert persisted.calls_used('phase_reasoning') == 1


def test_budget_stops_before_transient_retry(tmp_path):
    from figure_tools.state import BudgetExceeded
    def respond(handler, body):
        handler.send_response(429)
        handler.end_headers()
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url)
        state.budget['phase_reasoning'] = 1
        with pytest.raises(BudgetExceeded):
            orch.advance('start')
        assert len(requests) == 1
        assert state.retries('phase_reasoning', 'transient') == 0
        assert RunState.load(tmp_path / 'run_state.json').calls_used('phase_reasoning') == 1


@pytest.mark.parametrize('invalid', [{'max_attempts': 0}, {'total_timeout': float('nan')},
                                    {'inactivity_timeout': -1}, {'connect_timeout': True},
                                    {'backoff_base': 3, 'backoff_cap': 2}])
def test_invalid_policy_fails_before_sending(tmp_path, invalid):
    with provider_server(lambda *_: None) as (url, requests):
        with pytest.raises(ValueError):
            workflow(tmp_path, url, invalid)
        assert requests == []


def test_streamed_expansion_shares_budget_and_keeps_final_json(tmp_path):
    def respond(handler, body):
        handler.send_response(200)
        handler.end_headers()
        if body['max_output_tokens'] < 16384:
            event(handler, 'response.incomplete', {'status': 'incomplete',
                    'incomplete_details': {'reason': 'max_output_tokens'}})
        else:
            # Split UTF-8 and SSE framing at arbitrary byte boundaries.
            wire = ('data: ' + json.dumps({'type': 'response.completed', 'response': {
                    'status': 'completed', 'output_text': '{"label":"完成"}'}}, ensure_ascii=False) + '\n\n').encode()
            for part in [wire[:7], wire[7:-8], wire[-8:-7], wire[-7:]]:
                handler.wfile.write(part)
                handler.wfile.flush()
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url)
        client = orch.worker.provider_client
        result = client.run_phase_worker('intake', 'test', {}, [], {})
        assert result == {'label': '完成'}
        assert [req['max_output_tokens'] for req in requests] == [8192, 16384]
        assert state.calls_used('phase_reasoning') == 2
        assert state.retries('phase_reasoning', 'transient') == 0


def test_runtime_policy_role_overrides_provider(tmp_path):
    from figure_tools.runtime_context import RuntimeContextFactory
    from figure_tools.providers.auth import MemorySecretStore
    def respond(handler, body):
        handler.send_response(400)
        handler.end_headers()
    with provider_server(respond) as (url, requests):
        config = {'models': {'phase_reasoning': {'provider': 'p', 'model': 'test',
                    'request_policy': {'inactivity_timeout': 800}}},
                  'providers': {'p': {'type': 'openai', 'base_url': url, 'credential_id': 'k',
                    'request_policy': {'inactivity_timeout': 700, 'total_timeout': 2000}}}}
        context = RuntimeContextFactory(config_loader=lambda _: config,
            secret_store=MemorySecretStore({'k': 'test-key'}), environ={},
            cache_dir=tmp_path / 'cache').create(tmp_path, tmp_path / 'run')
        with pytest.raises(ProviderError):
            context.client.run_phase_worker('intake', 'test', {}, [], {})
        policy = context.state.to_dict()['provider_status']['phase_reasoning']['policy']
        assert policy['inactivity_timeout'] == 800
        assert policy['total_timeout'] == 2000
        assert policy['status_interval'] == 120
        assert 'stream' not in requests[0]  # Unrelated compatible hosts do not imply SSE.


def test_attempt_history_retains_errors_and_request_ids(tmp_path):
    codes = iter([429, 503, 400])
    def respond(handler, body):
        code = next(codes)
        handler.send_response(code)
        handler.send_header('x-request-id', f'id-{code}')
        handler.end_headers()
    with provider_server(respond) as (url, requests):
        orch, state = workflow(tmp_path, url, {'backoff_base': 0, 'backoff_cap': 0})
        with pytest.raises(ProviderError):
            orch.advance('start')
        history = [e['details'] for e in state.to_dict()['audit_log'] if e['event'] == 'provider_attempt_finished']
        assert [h['http_status'] for h in history] == [429, 503, 400]
        assert [h['request_id'] for h in history] == ['id-429', 'id-503', 'id-400']
        assert len({h['invocation_id'] for h in history}) == 1
        assert all(h['stop_reason'] != 'completed' for h in history)


def test_asset_download_follows_redirect_without_model_request():
    from figure_tools.providers.generic_transport import _request_bytes
    import urllib.request
    paths = []
    def respond(handler, body):
        paths.append(handler.path)
        if handler.path == '/redirect':
            handler.send_response(302)
            handler.send_header('Location', '/image')
            handler.end_headers()
        else:
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(b'asset-bytes')
    with provider_server(respond) as (url, requests):
        assert _request_bytes(url + '/redirect', opener=urllib.request.urlopen) == b'asset-bytes'
        assert paths == ['/redirect', '/image']
        assert requests == []
