"""Phase output policy through real Provider requests and persisted Run State."""
import json

from figure_tools.providers.client import ProviderClient
from figure_tools.providers.generic_transport import ProviderRouter
from figure_tools.state import RunState
from tests.unit.test_provider_waiting import provider_server


def make_client(tmp_path, url, *, state=None, provider='local', model='test', output_tokens=None):
    route = {'provider': provider, 'model': model}
    if output_tokens is not None:
        route['output_tokens'] = output_tokens
    models = {'phase_reasoning': route}
    router = ProviderRouter(models, {provider: {'type': 'openai', 'base_url': url}}, credentials={provider: 'fake-test-key'})
    return ProviderClient(models, router, state=state or RunState('run', budget={'phase_reasoning': 10}), output_dir=tmp_path)


def reply(handler, body):
    handler.send_response(200)
    handler.end_headers()
    handler.wfile.write(json.dumps(body).encode())


def invoke(client, phase):
    return client.run_phase_worker(phase, 'test', {}, [], {})


def test_each_lifecycle_phase_starts_at_8192(tmp_path):
    def respond(handler, body):
        reply(handler, {'status': 'completed', 'output_text': '{"ok":true}'})
    with provider_server(respond) as (url, requests):
        client = make_client(tmp_path, url)
        for phase in ['intake', 'planning', 'review_and_repair']:
            assert invoke(client, phase) == {'ok': True}
        assert [r['max_output_tokens'] for r in requests] == [8192, 8192, 8192]


def test_resume_reuses_only_same_phase_provider_and_model(tmp_path):
    def respond(handler, body):
        if len(requests) == 1:
            reply(handler, {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}})
        else:
            reply(handler, {'status': 'completed', 'output_text': '{"ok":true}'})
    with provider_server(respond) as (url, requests):
        client = make_client(tmp_path, url)
        invoke(client, 'planning')
        saved = RunState.load(tmp_path / 'run_state.json')
        resumed = make_client(tmp_path, url, state=saved)
        invoke(resumed, 'planning')
        invoke(resumed, 'intake')
        invoke(make_client(tmp_path, url, state=saved, model='other'), 'planning')
        invoke(make_client(tmp_path, url, state=saved, provider='other'), 'planning')
        assert [r['max_output_tokens'] for r in requests] == [8192, 16384, 16384, 8192, 8192, 8192]


def test_usage_is_saved_for_incomplete_and_complete_without_reasoning_text(tmp_path):
    def respond(handler, body):
        if len(requests) == 1:
            response = {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
                        'usage': {'input_tokens': 100, 'output_tokens': 8192, 'output_tokens_details': {'reasoning_tokens': 7000}}}
        else:
            response = {'status': 'completed', 'output_text': '{"ok":true}',
                        'usage': {'input_tokens': 100, 'output_tokens': 9000, 'output_tokens_details': {'reasoning_tokens': 7500}}}
        response['output'] = [{'type': 'reasoning', 'content': [{'type': 'reasoning_text', 'text': 'PRIVATE REASONING'}]}]
        reply(handler, response)
    with provider_server(respond) as (url, requests):
        client = make_client(tmp_path, url)
        invoke(client, 'planning')
        saved = json.loads((tmp_path / 'run_state.json').read_text(encoding="utf-8"))
        history = [entry['details'] for entry in saved['audit_log'] if entry['event'] == 'provider_attempt_finished']
        assert [entry['output_usage']['output_tokens'] for entry in history] == [8192, 9000]
        assert [entry['output_usage']['reasoning_tokens'] for entry in history] == [7000, 7500]
        assert 'PRIVATE REASONING' not in json.dumps(saved)


def test_budget_does_not_remember_unsent_expansion(tmp_path):
    import pytest
    from figure_tools.state import BudgetExceeded
    def respond(handler, body):
        reply(handler, {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}})
    with provider_server(respond) as (url, requests):
        client = make_client(tmp_path, url, state=RunState('run', budget={'phase_reasoning': 1}))
        with pytest.raises(BudgetExceeded):
            invoke(client, 'planning')
        assert [r['max_output_tokens'] for r in requests] == [8192]
        history = json.loads((tmp_path / 'run_state.json').read_text(encoding="utf-8"))['output_token_limits']
        assert history == [{'phase': 'planning', 'provider': 'local', 'model': 'test', 'max_output_tokens': 8192}]


def test_configured_ceiling_stops_expansion_and_clamps_restored_limit(tmp_path):
    import pytest
    from figure_tools.providers.transport import RequestError
    def respond(handler, body):
        reply(handler, {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}})
    with provider_server(respond) as (url, requests):
        client = make_client(tmp_path, url, output_tokens={'max_tokens': 12000})
        with pytest.raises(RequestError, match='token ceiling'):
            invoke(client, 'planning')
        assert [r['max_output_tokens'] for r in requests] == [8192, 12000]
        saved = RunState.load(tmp_path / 'run_state.json')
        restricted = make_client(tmp_path, url, state=saved, output_tokens={'max_tokens': 6000})
        with pytest.raises(RequestError, match='token ceiling'):
            invoke(restricted, 'planning')
        assert requests[-1]['max_output_tokens'] == 6000


def test_phase_specific_config_and_old_state_without_history(tmp_path):
    def respond(handler, body):
        reply(handler, {'status': 'completed', 'output_text': '{"ok":true}'})
    old = RunState('run', budget={'phase_reasoning': 10}).to_dict()
    old.pop('output_token_limits')
    with provider_server(respond) as (url, requests):
        client = make_client(tmp_path, url, state=RunState.from_dict(old), output_tokens={
            'phase_initial_tokens': {'planning': 16384, 'review_and_repair': 12000}})
        for phase in ['intake', 'planning', 'review_and_repair']:
            invoke(client, phase)
        assert [r['max_output_tokens'] for r in requests] == [8192, 16384, 12000]


def test_anthropic_phase_allowance_expands_and_reports_usage(tmp_path):
    def respond(handler, body):
        limit = body['max_tokens']
        reply(handler, {'stop_reason': 'max_tokens' if limit == 8192 else 'end_turn',
             'content': [{'type': 'text', 'text': '{"ok":true}'}], 'usage': {'output_tokens': min(limit, 9000)}})
    with provider_server(respond) as (url, requests):
        models = {'phase_reasoning': {'provider': 'local', 'model': 'anthropic-test'}}
        router = ProviderRouter(models, {'local': {'type': 'anthropic', 'base_url': url}}, credentials={'local': 'test'})
        client = ProviderClient(models, router, state=RunState('run', budget={'phase_reasoning': 3}), output_dir=tmp_path)
        assert invoke(client, 'planning') == {'ok': True}
        assert [r['max_tokens'] for r in requests] == [8192, 16384]
        state = json.loads((tmp_path / 'run_state.json').read_text(encoding="utf-8"))
        assert state['provider_status']['phase_reasoning']['output_usage']['output_tokens'] == 9000


def test_stream_usage_and_token_ceiling_survive_terminal_event(tmp_path):
    import pytest
    from figure_tools.providers.transport import RequestError
    def respond(handler, body):
        handler.send_response(200)
        handler.end_headers()
        event = {'type': 'response.incomplete', 'response': {
            'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
            'usage': {'output_tokens': 8192, 'output_tokens_details': {'reasoning_tokens': 8000}}}}
        handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
    with provider_server(respond) as (url, requests):
        models = {'phase_reasoning': {'provider': 'local', 'model': 'test', 'output_tokens': {'max_tokens': 8192}}}
        router = ProviderRouter(models, {'local': {'type': 'openai', 'base_url': url, 'supports_responses_streaming': True}}, credentials={'local': 'test'})
        client = ProviderClient(models, router, state=RunState('run', budget={'phase_reasoning': 3}), output_dir=tmp_path)
        with pytest.raises(RequestError, match='token ceiling'):
            invoke(client, 'intake')
        status = RunState.load(tmp_path / 'run_state.json').provider_status['phase_reasoning']
        assert len(requests) == 1
        assert status['output_usage'] == {'output_tokens': 8192, 'reasoning_tokens': 8000}


def test_known_official_model_caps_config_without_network(tmp_path):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return b'{"status":"completed","output_text":"{\\"ok\\":true}"}'
    requests = []
    def opener(request, **kwargs):
        requests.append(json.loads(request.data))
        return Response()
    models = {'phase_reasoning': {'provider': 'deepseek', 'model': 'deepseek-v4-flash-vision-exp',
                                 'output_tokens': {'initial_tokens': 500000}}}
    router = ProviderRouter(models, {'deepseek': {'type': 'openai', 'base_url': 'https://api.deepseek.com'}},
                            credentials={'deepseek': 'fake'}, opener=opener)
    client = ProviderClient(models, router, state=RunState('run', budget={'phase_reasoning': 1}), output_dir=tmp_path)
    assert invoke(client, 'planning') == {'ok': True}
    assert requests[0]['max_output_tokens'] == 384000
