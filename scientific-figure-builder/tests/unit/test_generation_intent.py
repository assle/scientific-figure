"""Generation choices enforced through the public Lifecycle boundary."""
import json
import pytest

from figure_tools.orchestrator import FigureOrchestrator
from tests.unit.test_lifecycle_orchestrator import _orchestrator as _scenario, _request

def _orchestrator(*args, **kwargs):
    return _scenario(*args, auto_continue_summary=False, **kwargs)


def diagram_request(**updates):
    request = _request()
    request.update({
        'description': 'Complete workflow: Start → Finish. White background.',
        'panels': [{'panel_id': 'a', 'bbox': [0, 0, 1, 1], 'physical_size': [140, 90],
                    'elements': [{'element_id': 'start', 'type': 'text', 'content': 'Start'},
                                 {'element_id': 'finish', 'type': 'text', 'content': 'Finish'}]}],
        'labels': [],
        'generation_intent': [{'unit_id': 'diagram', 'method': 'image_model', 'scope': 'figure'}],
    })
    request.update(updates)
    return request


def test_whole_flowchart_returns_summary_before_any_image_call(tmp_path):
    orch, run, client = _orchestrator(tmp_path, diagram_request())
    result = orch.advance('start')
    assert result['phase'] == 'planning'
    assert result['next_action'] == 'resume'
    assert 'diagram' in result['generation_summary']
    assert client.state.calls_used('generation') == 0
    plan = json.loads((run / 'plans/figure_plan.json').read_text())
    assert [(a['asset_id'], a['routing']) for a in plan['assets']] == [('diagram', 'image_model')]
    assert plan['generation_units'][0]['members'] == ['finish', 'start']
    assert plan['generation_summary'] == result['generation_summary']


def test_whole_flowchart_conditions_allow_text_and_preserve_background(tmp_path):
    orch, run, client = _orchestrator(tmp_path, diagram_request())
    orch.advance('start')
    condition = json.loads((run / 'plans/generation_conditions.json').read_text())['conditions'][0]
    assert 'no text' not in condition['negative_constraints']
    assert 'no symbols' not in condition['negative_constraints']
    assert 'transparent background' not in condition['prompt']
    assert condition['parameters']['preserve_background'] is True
    assert condition['generation_unit']['unit_id'] == 'diagram'


def test_internal_graph_is_preserved_but_not_drawn_over_image(tmp_path):
    graph = {'ports': [{'port_id': 's-out', 'node_id': 'start', 'side': 'right'},
                       {'port_id': 'f-in', 'node_id': 'finish', 'side': 'left'}],
             'typed_edges': [{'edge_id': 'flow', 'source_port': 's-out', 'target_port': 'f-in',
                              'semantic_type': 'sequence', 'direction': 'forward'}],
             'groups': [], 'labels': [], 'constraints': []}
    orch, run, _ = _orchestrator(tmp_path, diagram_request(figure_graph=graph))
    assert orch.advance('start')['next_action'] == 'resume'
    semantic = json.loads((run / 'plans/semantic_graph.json').read_text())
    rendered = json.loads((run / 'plans/figure_graph.json').read_text())
    assert [e['edge_id'] for e in semantic['typed_edges']] == ['flow']
    assert rendered['typed_edges'] == []
    assert [n['node_id'] for n in rendered['nodes']] == ['diagram']


def test_image_unit_requires_specific_review_evidence(tmp_path):
    orch, run, client = _orchestrator(tmp_path, diagram_request())
    orch.advance('start')
    result = orch.advance('resume')
    assert client.state.calls_used('generation') == 1
    report = json.loads((run / 'validation/final.json').read_text())
    required = [check for check in report['checks'] if check['check_id'].startswith('generation_unit_diagram_')]
    assert len(required) == 3
    assert all(check['status'] == 'fail' for check in required)
    assert not (run / 'exports/figure.png').exists()


def test_public_entry_accepts_generation_choice(tmp_path, monkeypatch):
    from tests.unit.test_server import _rpc, _use_offline_runtime
    _use_offline_runtime(monkeypatch, tmp_path)
    result = _rpc(monkeypatch, {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'advance_figure_workflow', 'arguments': {
            'project_dir': str(tmp_path), 'run_dir': str(tmp_path / 'run'), 'request': diagram_request()}}}, continue_summaries=False)[0]
    assert 'result' in result
    data = json.loads(result['result']['content'][0]['text'])
    assert data['next_action'] == 'resume'
    assert 'diagram' in data['generation_summary']


def test_phase_worker_cannot_silently_change_route(tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker
    class WrongRoute(StructuredPhaseWorker):
        def run(self, invocation):
            result = super().run(invocation)
            if invocation.phase == 'planning':
                result['asset_hints'] = [{
                    'asset_id': 'diagram', 'bbox': [0, 0, 1, 1],
                    'routing': 'svg',
                }]
            return result
    orch, run, client = _orchestrator(tmp_path, diagram_request(), worker=WrongRoute())
    result = orch.advance('start')
    assert result['next_action'] == 'resume'
    assert 'invalid Planning Advice' in result['error']
    assert client.state.calls_used('generation') == 0
    assert not (run / 'plans/figure_plan.json').exists()


def test_data_cannot_be_absorbed_into_image_unit(tmp_path):
    request = _request()
    request['generation_intent'] = [{'unit_id': 'whole', 'method': 'image_model', 'scope': 'figure'}]
    orch, _, client = _orchestrator(tmp_path, request)
    result = orch.advance('start')
    assert result['next_action'] == 'revise_generation_intent'
    assert 'measured data' in result['error']
    assert client.state.calls_used('generation') == 0


def test_explicit_revision_changes_route_without_reasking_and_keeps_budgets(tmp_path):
    request = diagram_request(generation_intent=[{'unit_id': 'diagram', 'method': 'vector', 'scope': 'figure'}])
    orch, run, client = _orchestrator(tmp_path, request)
    orch.advance('start')
    client.state.record_call('generation', 2)
    client.state.record_output_tokens('planning', 'local', 'model', 32768)
    result = orch.advance({'action': 'revise_generation_intent', 'reason': 'Use the image model for this whole flowchart',
                          'generation_intent': [{'unit_id': 'diagram', 'method': 'image_model', 'scope': 'figure'}]})
    assert result['next_action'] == 'resume'
    assert '生图模型' in result['generation_summary']
    assert client.state.calls_used('generation') == 2
    assert client.state.output_tokens_for('planning', 'local', 'model') == 32768
    plan = json.loads((run / 'plans/figure_plan.json').read_text())
    assert plan['revision'] == 2
    assert [asset['routing'] for asset in plan['assets']] == ['image_model']


def unit_transport():
    import io
    from PIL import Image, ImageDraw
    from figure_tools.providers.transport import MockProviderTransport
    class ReviewedDiagram(MockProviderTransport):
        def post(self, role, model, payload, image_paths=None):
            result = super().post(role, model, payload, image_paths)
            if role in ('generation', 'edits'):
                canvas = Image.new('RGB', (2048, 2048), 'white')
                ImageDraw.Draw(canvas).rectangle((100, 100, 900, 900), outline='black', width=5)
                buf = io.BytesIO(); canvas.save(buf, format='PNG'); result['image_bytes'] = buf.getvalue()
            if role in ('validations', 'final_validation'):
                result['checks'].extend({'check_id': item.split(' :: ')[0], 'status': 'pass', 'detail': 'synthetic test evidence'}
                    for item in payload.get('checks', []) if item.startswith('generation_unit_'))
            return result
    return ReviewedDiagram()


def test_complete_image_route_preserves_white_and_exports_with_review(tmp_path):
    from PIL import Image
    transport = unit_transport()
    orch, run, client = _orchestrator(tmp_path, diagram_request(), transport=transport)
    orch.advance('start')
    result = orch.advance('resume')
    assert result['status'] == 'completed', result
    assert client.state.calls_used('generation') == 1
    with Image.open(run / 'assets/diagram.png') as image:
        assert image.getpixel((0, 0)) == (255, 255, 255, 255)
    assert not list((run / 'vectors').glob('*.svg'))


def test_route_revision_preserves_unrelated_generated_panel(tmp_path):
    request = diagram_request()
    request['panels'] = [
        {'panel_id': 'a', 'bbox': [0, 0, .5, 1], 'physical_size': [70, 90],
         'elements': [{'element_id': 'start', 'type': 'text', 'content': 'Start'}]},
        {'panel_id': 'b', 'bbox': [.5, 0, .5, 1], 'physical_size': [70, 90],
         'elements': [{'element_id': 'finish', 'type': 'text', 'content': 'Finish'}]}]
    selections = [{'unit_id': 'left', 'method': 'image_model', 'scope': 'panel', 'panel_id': 'a'},
                  {'unit_id': 'right', 'method': 'image_model', 'scope': 'panel', 'panel_id': 'b'}]
    request['generation_intent'] = selections
    orch, run, client = _orchestrator(tmp_path, request, transport=unit_transport())
    orch.advance('start'); orch.advance('resume')
    original = (run / 'assets/right.png').read_bytes()
    calls = client.state.calls_used('generation')
    revised = [{**selections[0], 'method': 'vector'}, selections[1]]
    result = orch.advance({'action': 'revise_generation_intent', 'reason': 'Draw only the left panel locally', 'generation_intent': revised})
    assert result['next_action'] == 'resume'
    assert (run / 'assets/right.png').read_bytes() == original
    orch.advance('resume')
    assert client.state.calls_used('generation') == calls


def test_whole_unit_regeneration_does_not_switch_to_svg(tmp_path):
    class MissingFinalEvidence(type(unit_transport())):
        def post(self, role, model, payload, image_paths=None):
            result = super().post(role, model, payload, image_paths)
            if role == 'final_validation':
                result['checks'] = [item for item in result['checks'] if not item['check_id'].startswith('generation_unit_')]
            return result
    orch, run, client = _orchestrator(tmp_path, diagram_request(), transport=MissingFinalEvidence())
    orch.advance('start'); result = orch.advance('resume')
    assert result['next_action'] == 'repair_required'
    before = client.state.calls_used('generation')
    result = orch.advance({'action': 'apply_repair', 'repairs': [
        {'asset_id': 'diagram', 'route': 'image_model', 'prompt': 'Correct arrow direction while preserving the complete unit'}]})
    assert client.state.calls_used('generation') == before + 1
    plan = json.loads((run / 'plans/figure_plan.json').read_text())
    assert [a['routing'] for a in plan['assets']] == ['image_model']
    assert plan['generation_units'][0]['members'] == ['finish', 'start']
    assert not list((run / 'vectors').glob('*.svg'))


def test_unapproved_vector_repair_is_rejected_before_call(tmp_path):
    orch, run, client = _orchestrator(tmp_path, diagram_request())
    orch.advance('start'); orch.advance('resume')
    before = client.state.calls_used('generation')
    result = orch.advance({'action': 'apply_repair', 'repairs': [{'asset_id': 'diagram', 'route': 'svg', 'content': '<svg/>'}]})
    assert result['next_action'] == 'revise_generation_intent'
    assert client.state.calls_used('generation') == before
    assert client.state.retries('repair:diagram', 'quality') == 0


def test_module_and_hybrid_ownership_are_explicit(tmp_path):
    request = diagram_request(generation_intent=[{'unit_id': 'one-module', 'method': 'image_model', 'scope': 'module', 'panel_id': 'a', 'members': ['start']}])
    orch, run, _ = _orchestrator(tmp_path, request)
    assert orch.advance('start')['next_action'] == 'resume'
    plan = json.loads((run / 'plans/figure_plan.json').read_text())
    assert {a['asset_id']: a['routing'] for a in plan['assets']} == {'one-module': 'image_model', 'finish': 'svg'}
    other = diagram_request(generation_intent=[{'unit_id': 'mixed', 'method': 'hybrid', 'scope': 'figure',
                                              'ownership': {'start': 'vector', 'finish': 'vector'}}])
    second, _, _ = _orchestrator(tmp_path / 'second', other)
    summary = second.advance('start')['generation_summary']
    assert 'start由本地绘制' in summary and 'finish由本地绘制' in summary


def test_bad_scopes_and_editability_stop_before_generation(tmp_path):
    cases = [
        {'generation_intent': [{'unit_id': 'missing', 'method': 'image_model', 'scope': 'panel', 'panel_id': 'absent'}]},
        {'generation_intent': [{'unit_id': 'one', 'method': 'image_model', 'scope': 'figure'},
                               {'unit_id': 'two', 'method': 'vector', 'scope': 'panel', 'panel_id': 'a'}]},
        {'require_editable_objects': True},
    ]
    for index, change in enumerate(cases):
        orch, _, client = _orchestrator(tmp_path / str(index), diagram_request(**change))
        assert orch.advance('start')['next_action'] == 'revise_generation_intent'
        assert client.state.calls_used('generation') == 0


def test_intake_cannot_discard_explicit_selection(tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker
    class WrongIntake(StructuredPhaseWorker):
        def run(self, invocation):
            result = super().run(invocation)
            if invocation.phase == 'intake':
                result['request'].pop('generation_intent')
            return result
    orch, run, client = _orchestrator(tmp_path, diagram_request(), worker=WrongIntake())
    assert orch.advance('start')['next_action'] == 'resume'
    brief = json.loads((run / 'plans/figure_brief.json').read_text())
    assert brief['request']['generation_intent'][0]['unit_id'] == 'diagram'
    assert (run / 'plans/figure_plan.json').exists()
    assert client.state.calls_used('generation') == 0


def test_execution_rejects_replaced_plan_route(tmp_path):
    orch, run, client = _orchestrator(tmp_path, diagram_request())
    orch.advance('start')
    path = run / 'plans/figure_plan.json'
    plan = json.loads(path.read_text()); plan['assets'][0]['routing'] = 'svg'
    path.write_text(json.dumps(plan))
    result = orch.advance('resume')
    assert result['next_action'] == 'revise_generation_intent'
    assert client.state.calls_used('generation') == 0


def test_explicit_image_controls_reach_generation_conditions(tmp_path):
    request = diagram_request(generation_intent=[{'unit_id': 'diagram', 'method': 'image_model', 'scope': 'figure',
        'parameters': {'size': '2048x2048', 'seed': 123}, 'candidate_count': 2}])
    orch, run, _ = _orchestrator(tmp_path, request)
    orch.advance('start')
    condition = json.loads((run / 'plans/generation_conditions.json').read_text())['conditions'][0]
    assert condition['parameters']['size'] == '2048x2048'
    assert condition['parameters']['seed'] == 123
    plan = json.loads((run / 'plans/figure_plan.json').read_text())
    assert plan['estimated_paid_calls']['generation'] == 2


def test_hybrid_can_assign_a_semantic_component_to_the_image_model(tmp_path):
    request = diagram_request(generation_intent=[{'unit_id': 'mixed', 'method': 'hybrid', 'scope': 'figure',
                                                 'ownership': {'start': 'image_model', 'finish': 'vector'}}])
    orch, run, _ = _orchestrator(tmp_path, request)
    result = orch.advance('start')
    assert result['next_action'] == 'resume', result
    plan = json.loads((run / 'plans/figure_plan.json').read_text())
    assert {a['asset_id']: a['routing'] for a in plan['assets']} == {'start': 'image_model', 'finish': 'svg'}
    condition = json.loads((run / 'plans/generation_conditions.json').read_text())['conditions'][0]
    assert condition['generation_unit']['requirements']['labels'] == ['Start']
    assert 'no text' not in condition['negative_constraints']


def test_vector_member_cannot_disappear_from_worker_plan(tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker
    class DropMember(StructuredPhaseWorker):
        def run(self, invocation):
            result = super().run(invocation)
            if invocation.phase == 'planning':
                result['generation_units'] = []
            return result
    request = diagram_request(generation_intent=[{'unit_id': 'diagram', 'method': 'vector', 'scope': 'figure'}])
    orch, _, client = _orchestrator(tmp_path, request, worker=DropMember())
    result = orch.advance('start')
    assert result['next_action'] == 'resume'
    assert 'invalid Planning Advice' in result['error']
    assert client.state.calls_used('generation') == 0


@pytest.mark.parametrize("attempt", ["drop", "rewrite", "subdivide", "reroute"])
def test_planning_advice_cannot_take_generation_authority(tmp_path, attempt):
    from figure_tools.phase_workers import StructuredPhaseWorker

    class ConflictingAdvice(StructuredPhaseWorker):
        def run(self, invocation):
            result = dict(super().run(invocation))
            if invocation.phase != "planning":
                return result
            if attempt == "drop":
                result.pop("composition")
            elif attempt == "rewrite":
                result["generation_units"] = []
            elif attempt == "subdivide":
                result["assets"] = [{"asset_id": "start"}, {"asset_id": "finish"}]
            else:
                result["asset_hints"] = [{
                    "asset_id": "diagram", "bbox": [0, 0, 1, 1],
                    "routing": "svg",
                }]
            return result

    orch, run, client = _orchestrator(
        tmp_path, diagram_request(), worker=ConflictingAdvice(),
    )

    result = orch.advance("start")

    assert result["status"] == "paused"
    assert result["phase"] == "planning"
    assert "invalid Planning Advice" in result["error"]
    assert not (run / "plans/figure_plan.json").exists()
    assert client.state.calls_used("generation") == 0


def test_recorded_whole_figure_vector_shape_keeps_ten_members(tmp_path):
    elements = [
        {"element_id": f"member-{index}", "type": "text", "content": f"M{index}"}
        for index in range(10)
    ]
    request = diagram_request(
        panels=[{
            "panel_id": "a", "bbox": [0, 0, 1, 1],
            "physical_size": [140, 90], "elements": elements,
        }],
        generation_intent=[{
            "unit_id": "panorama", "method": "vector", "scope": "figure",
        }],
    )

    orch, run, _ = _orchestrator(tmp_path, request)
    assert orch.advance("start")["next_action"] == "resume"

    plan = json.loads((run / "plans/figure_plan.json").read_text())
    assert len(plan["generation_units"][0]["members"]) == 10
    assert len(plan["assets"]) == 10
    assert all(asset["generation_unit_id"] == "panorama" for asset in plan["assets"])


def test_recorded_whole_figure_image_shape_preserves_semantic_graph(tmp_path):
    elements = [
        {"element_id": f"node-{index}", "type": "text", "content": f"N{index}"}
        for index in range(28)
    ]
    ports = [
        {"port_id": f"node-{index}-out", "node_id": f"node-{index}", "side": "right"}
        for index in range(20)
    ] + [
        {"port_id": f"node-{index + 1}-in", "node_id": f"node-{index + 1}", "side": "left"}
        for index in range(20)
    ]
    edges = [{
        "edge_id": f"edge-{index}",
        "source_port": f"node-{index}-out",
        "target_port": f"node-{index + 1}-in",
        "direction": "forward",
        "semantic_type": "sequence",
    } for index in range(20)]
    request = diagram_request(
        panels=[{
            "panel_id": "a", "bbox": [0, 0, 1, 1],
            "physical_size": [140, 90], "elements": elements,
        }],
        figure_graph={
            "ports": ports, "typed_edges": edges, "groups": [],
            "labels": [], "constraints": [],
        },
        generation_intent=[{
            "unit_id": "panorama", "method": "image_model", "scope": "figure",
        }],
    )

    orch, run, _ = _orchestrator(tmp_path, request)
    assert orch.advance("start")["next_action"] == "resume"

    plan = json.loads((run / "plans/figure_plan.json").read_text())
    semantic = json.loads((run / "plans/semantic_graph.json").read_text())
    assert len(plan["generation_units"][0]["members"]) == 28
    assert [(asset["asset_id"], asset["routing"]) for asset in plan["assets"]] == [
        ("panorama", "image_model")
    ]
    assert len(semantic["nodes"]) == 28
    assert len(semantic["typed_edges"]) == 20


def test_inline_style_bible_is_normalized_and_used_end_to_end(tmp_path):
    style_bible = {
        "schema_version": "1.0",
        "palette": {"primary": "#2B176E", "accent": "#38BDF8"},
        "view": "flat 2D panoramic editorial scientific graphic",
        "projection": "orthographic front view",
        "lighting": "none",
        "material": "flat matte surfaces",
        "stroke_widths": {"thin": 0.75, "medium": 1.1},
        "fonts": {"family": "Arial", "sizes": {"label": 9}},
        "equation_style": "clean scientific typesetting",
        "background": "white",
        "shadow": "none",
        "forbidden_elements": ["isometric perspective", "glassmorphism"],
        "style_reference_hashes": [],
    }
    orch, run, _ = _orchestrator(
        tmp_path, diagram_request(style=style_bible),
    )

    result = orch.advance("start")

    assert result["next_action"] == "resume"
    brief = json.loads((run / "plans/figure_brief.json").read_text())
    assert brief["style"] == {"kind": "inline", "style_bible": style_bible}
    assert json.loads((run / "style_bible.json").read_text()) == style_bible
    plan = json.loads((run / "plans/figure_plan.json").read_text())
    assert plan["style_source"]["kind"] == "inline"
    assert plan["style_source"]["content_hash"].startswith("sha256:")
    assert "orthographic front view" in result["generation_summary"]
    assert "#2B176E" in result["generation_summary"]


def test_natural_language_style_compiles_without_default_fallback(tmp_path):
    description = (
        "flat indigo orthographic AI conference poster; white background; "
        "forbid isometric perspective and glassmorphism"
    )
    from figure_tools.phase_workers import StructuredPhaseWorker

    class FlatStyleWorker(StructuredPhaseWorker):
        def run(self, invocation):
            result = dict(super().run(invocation))
            if invocation.phase == "planning":
                result["style_bible"] = {
                    "schema_version": "1.0",
                    "palette": {"primary": "#2B176E", "background": "#FFFFFF"},
                    "view": "flat 2D panoramic scientific graphic",
                    "projection": "orthographic front view",
                    "lighting": "none", "material": "flat matte surfaces",
                    "stroke_widths": {"thin": 0.75},
                    "fonts": {"family": "Arial", "sizes": {"label": 9}},
                    "equation_style": "clean scientific typesetting",
                    "background": "white", "shadow": "none",
                    "forbidden_elements": ["isometric perspective", "glassmorphism"],
                    "style_reference_hashes": [],
                }
            return result

    orch, run, _ = _orchestrator(
        tmp_path, diagram_request(style=description), worker=FlatStyleWorker(),
    )

    result = orch.advance("start")

    assert result["next_action"] == "resume"
    brief = json.loads((run / "plans/figure_brief.json").read_text())
    assert brief["style"] == {"kind": "description", "description": description}
    resolved = json.loads((run / "style_bible.json").read_text())
    assert resolved["projection"] == "orthographic front view"
    assert resolved["view"] != "isometric"
    assert resolved["material"] != "matte with subtle specular highlights on glass"
    assert "isometric perspective" in resolved["forbidden_elements"]


def test_natural_language_style_can_resolve_to_isometric_glass(tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker

    class IsometricStyleWorker(StructuredPhaseWorker):
        def run(self, invocation):
            result = dict(super().run(invocation))
            if invocation.phase == "planning":
                result["style_bible"] = {
                    "schema_version": "1.0",
                    "palette": {"primary": "#111827", "accent": "#60A5FA"},
                    "view": "isometric scientific illustration",
                    "projection": "oblique isometric projection",
                    "lighting": "soft studio light",
                    "material": "translucent glass",
                    "stroke_widths": {"thin": 0.75},
                    "fonts": {"family": "Arial", "sizes": {"label": 9}},
                    "equation_style": "clean scientific typesetting",
                    "background": "black", "shadow": "soft",
                    "forbidden_elements": ["watermarks"],
                    "style_reference_hashes": [],
                }
            return result

    description = "isometric glass scientific illustration on black"
    orch, run, _ = _orchestrator(
        tmp_path, diagram_request(style=description), worker=IsometricStyleWorker(),
    )
    result = orch.advance("start")

    assert result["next_action"] == "resume"
    resolved = json.loads((run / "style_bible.json").read_text())
    assert resolved["projection"] == "oblique isometric projection"
    assert resolved["material"] == "translucent glass"
    assert resolved["background"] == "black"


def test_model_style_cannot_invert_explicit_flat_prohibitions(tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker

    class ContradictingStyleWorker(StructuredPhaseWorker):
        def run(self, invocation):
            result = dict(super().run(invocation))
            if invocation.phase == "planning":
                result["style_bible"] = {
                    "schema_version": "1.0", "palette": {"primary": "#111827"},
                    "view": "isometric illustration", "projection": "oblique",
                    "lighting": "studio", "material": "glassmorphism",
                    "stroke_widths": {"thin": 0.75},
                    "fonts": {"family": "Arial", "sizes": {"label": 9}},
                    "equation_style": "scientific", "background": "white",
                    "shadow": "none", "forbidden_elements": [],
                    "style_reference_hashes": [],
                }
            return result

    request = diagram_request(
        style="flat orthographic poster; forbid isometric, oblique and glassmorphism",
    )
    orch, run, client = _orchestrator(
        tmp_path, request, worker=ContradictingStyleWorker(),
    )

    result = orch.advance("start")

    assert result["status"] == "paused"
    assert "contradicts the style description" in result["error"]
    assert not (run / "style_bible.json").exists()
    assert client.state.calls_used("generation") == 0


def test_missing_style_file_pauses_before_plan_acceptance(tmp_path):
    missing = tmp_path / "missing-style.json"
    orch, run, client = _orchestrator(
        tmp_path, diagram_request(style=str(missing)),
    )

    result = orch.advance("start")

    assert result["status"] == "paused"
    assert result["phase"] == "planning"
    assert result["next_action"] == "resume"
    assert "Style Bible file is missing" in result["error"]
    assert not (run / "plans/figure_plan.json").exists()
    assert client.state.calls_used("generation") == 0


def test_invalid_model_style_advice_pauses_without_changing_brief(tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker

    class InvalidStyle(StructuredPhaseWorker):
        def run(self, invocation):
            result = dict(super().run(invocation))
            if invocation.phase == "planning":
                result["style_bible"] = {}
            return result

    description = "flat orthographic scientific graphic"
    orch, run, client = _orchestrator(
        tmp_path, diagram_request(style=description), worker=InvalidStyle(),
    )

    result = orch.advance("start")

    assert result["status"] == "paused"
    assert "style resolution failed" in result["error"]
    brief = json.loads((run / "plans/figure_brief.json").read_text())
    assert brief["style"] == {"kind": "description", "description": description}
    assert not (run / "plans/figure_plan.json").exists()
    assert client.state.calls_used("generation") == 0


def test_whole_figure_image_plan_exposes_asset_and_composition_blueprints(tmp_path):
    orch, run, _ = _orchestrator(tmp_path, diagram_request())

    result = orch.advance("start")

    assert result["next_action"] == "resume"
    plan = json.loads((run / "plans/figure_plan.json").read_text())
    assert plan["asset_blueprint_ref"]["artifact"] == "plans/asset_blueprint.svg"
    assert plan["composition_blueprint_ref"]["artifact"] == "plans/composition_blueprint.svg"
    assert plan["blueprint_ref"] == plan["composition_blueprint_ref"]
    asset_svg = (run / "plans/asset_blueprint.svg").read_text()
    composition_svg = (run / "plans/composition_blueprint.svg").read_text()
    assert set(part.split('"')[0] for part in asset_svg.split('data-node-id="')[1:]) == {
        "diagram"
    }
    assert composition_svg.count('data-region-id="') >= 2
    assert 'data-node-id="start"' in composition_svg
    assert 'data-node-id="finish"' in composition_svg
    client_calls = json.loads((run / "run_state.json").read_text())["calls"]["counts"]
    assert client_calls.get("generation", 0) == 0


def test_composition_blueprint_respects_forbidden_cards_and_box_arrows(tmp_path):
    style = {
        "schema_version": "1.0",
        "palette": {"primary": "#2B176E"},
        "view": "continuous panoramic field", "projection": "orthographic",
        "lighting": "none", "material": "flat matte",
        "stroke_widths": {"thin": 0.75},
        "fonts": {"family": "Arial", "sizes": {"label": 9}},
        "equation_style": "scientific", "background": "white", "shadow": "none",
        "forbidden_elements": ["card grid", "box-and-arrow flowchart"],
        "style_reference_hashes": [],
    }
    orch, run, _ = _orchestrator(tmp_path, diagram_request(style=style))
    assert orch.advance("start")["next_action"] == "resume"

    composition = (run / "plans/composition_blueprint.svg").read_text()
    assert 'data-region-id="' in composition
    assert '<rect' not in "\n".join(
        line for line in composition.splitlines() if 'data-region-id="' in line
    )
    assert "marker-end=" not in composition


def test_model_composition_cannot_drop_style_bible_prohibitions(tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker

    class IncompleteCompositionWorker(StructuredPhaseWorker):
        def run(self, invocation):
            result = dict(super().run(invocation))
            if invocation.phase == "planning":
                result["composition"]["forbidden_patterns"] = ["watermarks"]
            return result

    style = {
        "schema_version": "1.0", "palette": {"primary": "#2B176E"},
        "view": "continuous field", "projection": "orthographic",
        "lighting": "none", "material": "flat", "stroke_widths": {"thin": 0.75},
        "fonts": {"family": "Arial", "sizes": {"label": 9}},
        "equation_style": "scientific", "background": "white", "shadow": "none",
        "forbidden_elements": ["card grid", "box-and-arrow flowchart"],
        "style_reference_hashes": [],
    }
    orch, run, _ = _orchestrator(
        tmp_path, diagram_request(style=style), worker=IncompleteCompositionWorker(),
    )
    assert orch.advance("start")["next_action"] == "resume"

    plan = json.loads((run / "plans/figure_plan.json").read_text())
    assert set(plan["composition"]["forbidden_patterns"]) >= {
        "watermarks", "card grid", "box-and-arrow flowchart",
    }
    composition = (run / "plans/composition_blueprint.svg").read_text()
    assert "marker-end=" not in composition


def test_hybrid_top_level_label_can_be_image_owned_with_explicit_placement(tmp_path):
    request = diagram_request(labels=[{'element_id': 'caption', 'kind': 'label', 'content': 'Caption',
                                      'panel_id': 'a', 'bbox': [.05, .02, .2, .1]}],
        generation_intent=[{'unit_id': 'mixed', 'method': 'hybrid', 'scope': 'figure',
                            'ownership': {'start': 'vector', 'finish': 'vector', 'caption': 'image_model'}}])
    orch, run, _ = _orchestrator(tmp_path, request)
    result = orch.advance('start')
    assert result['next_action'] == 'resume', result
    plan = json.loads((run / 'plans/figure_plan.json').read_text())
    caption = next(a for a in plan['assets'] if a['asset_id'] == 'caption')
    assert caption['routing'] == 'image_model'
    assert caption['panel_id'] == 'a'
    assert caption['bbox'] == [.05, .02, .2, .1]
    assert not plan['text_elements']


def test_regeneration_rolls_back_image_and_conditions_on_global_regression(tmp_path):
    import io
    from PIL import Image, ImageDraw
    class Regression(type(unit_transport())):
        generated = 0
        reviews = 0
        def post(self, role, model, payload, image_paths=None):
            result = super().post(role, model, payload, image_paths)
            if role == 'generation':
                self.generated += 1
                if self.generated > 1:
                    with Image.open(io.BytesIO(result['image_bytes'])) as image:
                        ImageDraw.Draw(image).rectangle((200, 200, 400, 400), fill='red')
                        buf = io.BytesIO(); image.save(buf, format='PNG'); result['image_bytes'] = buf.getvalue()
            if role == 'final_validation':
                self.reviews += 1
                result['checks'].append({'check_id': 'generation_unit_diagram_connections' if self.reviews == 1 else 'new_global_failure',
                                         'status': 'fail', 'level': 'error', 'detail': 'controlled regression', 'element_ids': ['diagram']})
            return result
    orch, run, client = _orchestrator(tmp_path, diagram_request(), transport=Regression())
    orch.advance('start'); assert orch.advance('resume')['next_action'] == 'repair_required'
    original = (run / 'assets/diagram.png').read_bytes()
    before = json.loads((run / 'plans/generation_conditions.json').read_text())
    orch.advance({'action': 'apply_repair', 'repairs': [{'asset_id': 'diagram', 'route': 'image_model', 'prompt': 'Repair the connections'}]})
    assert (run / 'assets/diagram.png').read_bytes() == original
    assert json.loads((run / 'plans/generation_conditions.json').read_text()) == before
    assert client.state.calls_used('generation') == 2
