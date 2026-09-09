"""Resolve user generation boundaries and enforce them through the Lifecycle."""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator

from figure_tools.provenance import hash_json

SELECTION_SCHEMA = {
    'type': 'array', 'minItems': 1,
    'items': {
        'type': 'object', 'additionalProperties': False,
        'required': ['unit_id', 'method', 'scope'],
        'properties': {
            'unit_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'},
            'method': {'enum': ['auto', 'image_model', 'vector', 'hybrid']},
            'scope': {'enum': ['figure', 'panel', 'module']},
            'panel_id': {'type': 'string', 'minLength': 1},
            'members': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': {'type': 'string', 'minLength': 1}},
            'ownership': {'type': 'object', 'additionalProperties': {'enum': ['image_model', 'vector']}},
            'background': {'enum': ['preserve', 'transparent']},
            'provenance': {'enum': ['user', 'automatic']},
            'candidate_count': {'type': 'integer', 'minimum': 1, 'maximum': 4},
            'parameters': {'type': 'object'},
        },
    },
}


class GenerationIntentError(ValueError):
    """A recoverable mismatch between an instruction and the proposed production."""


def _elements(request: Mapping[str, Any]) -> dict[str, tuple[str | None, dict]]:
    result: dict[str, tuple[str | None, dict]] = {}
    for panel in request.get('panels', []):
        for element in panel.get('elements', []):
            key = element['element_id']
            if key in result:
                raise GenerationIntentError(f'duplicate element ID: {key}')
            result[key] = (panel['panel_id'], element)
    for label in request.get('labels', []):
        key = label['element_id']
        if key in result:
            raise GenerationIntentError(f'duplicate element ID: {key}')
        result[key] = (label.get('panel_id'), label)
    return result


def resolve_units(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand selections into disjoint, stable semantic memberships."""
    elements = _elements(request)
    selections: Any = request.get('generation_intent')
    explicit = selections is not None
    if selections is None:
        selections = [{'unit_id': 'automatic', 'method': 'auto', 'scope': 'figure', 'provenance': 'automatic'}]
    errors = list(Draft202012Validator(SELECTION_SCHEMA).iter_errors(selections))
    if errors:
        raise GenerationIntentError('invalid generation_intent: ' + errors[0].message)
    panel_ids = {panel['panel_id'] for panel in request.get('panels', [])}
    units = []
    covered: set[str] = set()
    unit_ids: set[str] = set()
    for selection in selections:
        unit: dict[str, Any] = copy.deepcopy(dict(selection))
        ident, scope = unit['unit_id'], unit['scope']
        if ident in unit_ids:
            raise GenerationIntentError(f'duplicate Generation unit: {ident}')
        unit_ids.add(ident)
        panel_id = unit.get('panel_id')
        if scope != 'figure' and panel_id not in panel_ids:
            raise GenerationIntentError(f'{ident}: choose an existing panel_id')
        if scope == 'figure' and ('panel_id' in unit or 'members' in unit):
            raise GenerationIntentError(f'{ident}: figure scope cannot have a panel or partial membership')
        available = {key for key, (panel, _) in elements.items() if scope == 'figure' or panel == panel_id}
        if scope == 'module':
            members = set(unit.get('members', []))
            if not members or not members <= available:
                raise GenerationIntentError(f'{ident}: module members must identify existing elements/nodes in its panel')
        else:
            if scope == 'panel' and 'members' in unit:
                raise GenerationIntentError(f'{ident}: use module scope for partial panel membership')
            members = available
        if not members:
            raise GenerationIntentError(f'{ident}: generation scope is empty')
        if covered & members:
            raise GenerationIntentError(f'{ident}: overlapping generation selections require clarification')
        covered.update(members)
        method = unit['method']
        ownership: dict[str, str] = dict(unit.get('ownership', {}))
        if method not in ('hybrid', 'auto') and ownership:
            raise GenerationIntentError(f'{ident}: only hybrid/auto can divide content ownership')
        if ownership and set(ownership) != members:
            raise GenerationIntentError(f'{ident}: ownership must cover every member exactly once')
        if not ownership:
            ownership = {key: ('image_model' if elements[key][1].get('type') == 'image_asset' else 'vector') for key in members}
        if method in ('vector', 'image_model'):
            ownership = dict.fromkeys(members, method)
        for key in members:
            if ownership[key] == 'image_model' and elements[key][1].get('type') == 'data_plot':
                raise GenerationIntentError(f'{ident}: measured data plot {key} needs deterministic rendering; choose hybrid or a narrower scope')
            if ownership[key] == 'vector' and elements[key][1].get('type') == 'image_asset':
                raise GenerationIntentError(f'{ident}: vector ownership of {key} requires a deterministic source; revise that element')
        if request.get('require_editable_objects') and 'image_model' in ownership.values():
            raise GenerationIntentError(f'{ident}: image-generated content cannot guarantee independently editable objects')
        unit.update(members=sorted(members), ownership=dict(sorted(ownership.items())),
                    provenance=unit.get('provenance', 'user' if explicit else 'automatic'),
                    background=unit.get('background', 'preserve' if method == 'image_model' else 'transparent'))
        if method == 'image_model':
            originals = [elements[key][1] for key in sorted(members) if elements[key][1].get('type') == 'image_asset']
            controls = [dict(item.get('parameters') or {}) for item in originals]
            if 'parameters' not in unit and controls and any(item != controls[0] for item in controls):
                raise GenerationIntentError(f'{ident}: conflicting image controls; specify parameters for the whole unit')
            unit['parameters'] = copy.deepcopy(unit.get('parameters', controls[0] if controls else {}))
            unit['candidate_count'] = unit.get('candidate_count', originals[0].get('candidate_count', 1) if len(originals) == 1 else 1)
            ports = {port['port_id']: port.get('node_id') for port in (request.get('figure_graph') or {}).get('ports', [])}
            unit['requirements'] = {
                'labels': [str(elements[key][1].get('content', '')) for key in sorted(members)
                           if elements[key][1].get('type', elements[key][1].get('kind')) in ('text', 'label', 'annotation', 'equation')],
                'relations': [copy.deepcopy(edge) for edge in (request.get('figure_graph') or {}).get('typed_edges', [])
                              if ports.get(edge.get('source_port')) in members and ports.get(edge.get('target_port')) in members],
                'description': str(request.get('description', '')),
            }
        units.append(unit)
    # Unselected content keeps its existing automatic route; it is still summarized.
    remaining = set(elements) - covered
    for key in sorted(remaining):
        panel, element = elements[key]
        automatic_id = f'auto-{key}'
        while automatic_id in unit_ids:
            automatic_id += '-remaining'
        unit_ids.add(automatic_id)
        units.append({'unit_id': automatic_id, 'method': 'auto', 'scope': 'module',
                      'panel_id': panel, 'members': [key],
                      'ownership': {key: 'image_model' if element.get('type') == 'image_asset' else 'vector'},
                      'provenance': 'automatic', 'background': 'transparent'})
    return units


def _bounding_box(items: list[list[float]]) -> list[float]:
    x, y = min(b[0] for b in items), min(b[1] for b in items)
    return [x, y, max(b[0] + b[2] for b in items) - x, max(b[1] + b[3] for b in items) - y]


def production_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build production elements without changing the authoritative semantic request."""
    result = copy.deepcopy(dict(request))
    units = resolve_units(request)
    elements = _elements(request)
    owners = {member: unit for unit in units for member in unit['members']}
    result['generation_units'] = units
    result['generation_intent_hash'] = hash_json(units)
    panels = {panel['panel_id']: panel for panel in result['panels']}
    for unit in units:
        if unit['method'] != 'image_model':
            continue
        ident = unit['unit_id']
        if ident in elements and unit['members'] != [ident]:
            raise GenerationIntentError(f'{ident}: unit ID collides with an existing element')
        members = set(unit['members'])
        selected = [copy.deepcopy(elements[key][1]) for key in unit['members']]
        if unit['scope'] == 'figure':
            panel_id = '__figure_unit__'
            panel = {'panel_id': panel_id, 'bbox': [0, 0, 1, 1],
                     'physical_size': [float((request.get('canvas') or {}).get('width', 140)), float((request.get('canvas') or {}).get('height', 90))], 'elements': []}
            result['panels'] = [panel]
            result['labels'] = []
            bbox = None
        else:
            panel_id = unit['panel_id']
            panel = panels[panel_id]
            bbox = _bounding_box([list(elements[key][1].get('bbox', [0, 0, 1, 1])) for key in unit['members']]) if unit['scope'] == 'module' else None
        references = [ref for element in selected for ref in element.get('references', [])]
        for path in request.get('reference_figures', []):
            if not any(ref.get('path') == path for ref in references):
                from figure_tools.provenance import hash_file
                references.append({'path': path, 'role': 'content', 'strength': 1.0, 'content_hash': hash_file(path)})
        for item in selected:
            if item.get('type') == 'vector_element':
                from xml.etree import ElementTree
                try:
                    item['content'] = ' '.join(ElementTree.fromstring(item.get('content', '')).itertext())
                except ElementTree.ParseError:
                    pass
                item['type'] = 'semantic_reference'
        references = list({json.dumps(ref, sort_keys=True): ref for ref in references}.values())
        semantic = {'description': request.get('description', ''), 'elements': selected,
                    'internal_relations': unit.get('requirements', {}).get('relations', []), 'style': request.get('style', ''),
                    'unit': unit}
        element = {'element_id': ident, 'type': 'image_asset',
                   'prompt': 'Generate ONLY the selected Generation unit together, including its required text and internal arrows. The global description is context, not permission to draw unselected panels or external connectors.\n' + json.dumps(semantic, ensure_ascii=False),
                   'generation_unit_id': ident, 'generation_unit': unit,
                   'parameters': {**unit.get('parameters', {}), 'preserve_background': unit['background'] == 'preserve'},
                   'references': references, 'style_group': ident,
                   'candidate_count': unit.get('candidate_count', 1)}
        if bbox is not None:
            element['bbox'] = bbox
        panel['elements'] = [child for child in panel.get('elements', []) if child['element_id'] not in members]
        panel['elements'].append(element)
        result['labels'] = [label for label in result.get('labels', []) if label['element_id'] not in members]
    retained_labels = []
    for label in result.get('labels', []):
        owner = owners[label['element_id']]
        if owner['method'] == 'hybrid' and owner['ownership'][label['element_id']] == 'image_model':
            panel_id = label.get('panel_id')
            if panel_id not in panels or 'bbox' not in label:
                raise GenerationIntentError(f"{label['element_id']}: image-owned top-level labels need panel_id and bbox (or group the label into an image-model panel/module)")
            panels[panel_id]['elements'].append({**label, 'type': label.get('kind', 'text')})
        else:
            retained_labels.append(label)
    result['labels'] = retained_labels
    for panel in result['panels']:
        for element in panel.get('elements', []):
            if element['element_id'] in owners:
                owner = owners[element['element_id']]
                key = element['element_id']
                element['generation_unit_id'] = owner['unit_id']
                if owner['method'] == 'hybrid' and owner['ownership'][key] == 'image_model':
                    ports = {p['port_id']: p.get('node_id') for p in (request.get('figure_graph') or {}).get('ports', [])}
                    child = {'unit_id': key, 'method': 'image_model', 'scope': 'module',
                             'panel_id': panel['panel_id'], 'members': [key], 'ownership': {key: 'image_model'},
                             'provenance': owner['provenance'], 'background': owner['background'],
                             'parameters': dict(element.get('parameters') or {}),
                             'requirements': {'labels': [str(element['content'])] if element.get('content') else [],
                                 'description': str(element.get('prompt') or element.get('content') or ''),
                                 'relations': [copy.deepcopy(e) for e in (request.get('figure_graph') or {}).get('typed_edges', [])
                                               if ports.get(e.get('source_port')) == key and ports.get(e.get('target_port')) == key]}}
                    element['type'] = 'image_asset'
                    element['generation_unit'] = child
                    element['parameters'] = {**child['parameters'], 'preserve_background': child['background'] == 'preserve'}
                    element['prompt'] = 'Generate this declared hybrid component, including its owned labels: ' + json.dumps(child, ensure_ascii=False)
                    element.pop('content', None)
    for label in result.get('labels', []):
        label['generation_unit_id'] = owners[label['element_id']]['unit_id']
    return result


def validate_plan(request: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    expected = resolve_units(request)
    if plan.get('generation_intent_hash') != hash_json(expected) or plan.get('generation_units') != expected:
        raise GenerationIntentError('Planning changed or dropped generation method/scope; correct the plan to match the Figure brief')
    assets = plan.get('assets', [])
    asset_ids = [asset['asset_id'] for asset in assets]
    if len(asset_ids) != len(set(asset_ids)) or any(t['element_id'] not in asset_ids for t in plan.get('text_elements', [])):
        raise GenerationIntentError('Duplicate assets or unowned text would violate generation boundaries')
    expected_sources = {element['element_id']: element for panel in production_request(request)['panels'] for element in panel.get('elements', [])}
    asset_by_id = {asset['asset_id']: asset for asset in assets}
    if any(asset_by_id[t['element_id']].get('panel_id') or asset_by_id[t['element_id']].get('type') not in ('text', 'equation') for t in plan.get('text_elements', [])):
        raise GenerationIntentError('Text overlays must have their own declared deterministic assets')
    for unit in expected:
        owned = [asset for asset in assets if asset.get('generation_unit_id') == unit['unit_id']]
        if not owned:
            raise GenerationIntentError(f"{unit['unit_id']}: no planned assets own this generation scope")
        if unit['method'] == 'image_model':
            if len(owned) != 1 or owned[0].get('asset_id') != unit['unit_id'] or owned[0].get('routing') != 'image_model' or owned[0].get('type') != 'image_asset' or (owned[0].get('source') or {}).get('type') != 'image_asset':
                raise GenerationIntentError(f"{unit['unit_id']}: expected one whole image-model asset, not a split or vector substitute")
            if (owned[0].get('source') or {}).get('element_id') != unit['unit_id']:
                raise GenerationIntentError(f"{unit['unit_id']}: production source changed unit identity")
            if unit['scope'] != 'figure' and owned[0].get('panel_id') != unit['panel_id']:
                raise GenerationIntentError(f"{unit['unit_id']}: image was moved outside its selected panel")
            if unit['scope'] == 'figure' and (len(plan.get('panels', [])) != 1 or owned[0].get('bbox') != [0, 0, 1, 1]):
                raise GenerationIntentError(f"{unit['unit_id']}: whole-figure image must own the full canvas")
            if (owned[0].get('source') or {}).get('generation_unit') != unit:
                raise GenerationIntentError(f"{unit['unit_id']}: image asset lost its approved content ownership")
            if any(asset.get('asset_id') in unit['members'] and asset is not owned[0] for asset in assets):
                raise GenerationIntentError(f"{unit['unit_id']}: internal labels/elements must not be composed twice")
        else:
            represented: set[str] = set()
            for asset in owned:
                source = asset.get('source') or {}
                members = source.get('represented_members', [asset['asset_id']] if asset['asset_id'] in unit['members'] else [])
                if not isinstance(members, list) or not all(isinstance(member, str) for member in members) or not set(members) <= set(unit['members']):
                    raise GenerationIntentError(f"{unit['unit_id']}: invalid represented_members")
                if (not members and unit['method'] != 'auto') or represented.intersection(members):
                    raise GenerationIntentError(f"{unit['unit_id']}: duplicate or undeclared members in planned assets")
                represented.update(members)
                if unit['scope'] in ('panel', 'module') and asset.get('panel_id', source.get('panel_id')) != unit['panel_id']:
                    raise GenerationIntentError(f"{unit['unit_id']}: member moved outside its panel")
                child = (expected_sources.get(asset['asset_id']) or {}).get('generation_unit')
                if child and source.get('generation_unit') != child:
                    raise GenerationIntentError(f"{unit['unit_id']}: hybrid image content changed its member ownership")
                owner = 'vector' if unit['method'] == 'vector' else unit['ownership'].get(asset['asset_id'])
                if unit['method'] == 'hybrid' and owner is None:
                    raise GenerationIntentError(f"{unit['unit_id']}: hybrid content has undeclared ownership")
                if owner == 'vector' and (asset.get('routing') not in ('svg', 'python') or source.get('type') == 'image_asset' or asset.get('type') == 'image_asset'):
                    raise GenerationIntentError(f"{unit['unit_id']}: deterministic content changed to image generation")
                if owner == 'image_model' and (asset.get('routing') != 'image_model' or (asset.get('source') or {}).get('type') != 'image_asset'):
                    raise GenerationIntentError(f"{unit['unit_id']}: image content changed to a deterministic route")
            if represented != set(unit['members']):
                raise GenerationIntentError(f"{unit['unit_id']}: planned assets dropped declared members")
    known = {unit['unit_id'] for unit in expected}
    if any(asset.get('generation_unit_id') not in known for asset in assets):
        raise GenerationIntentError('Every planned asset must belong to a declared Generation unit')


def generation_summary(plan: Mapping[str, Any]) -> str:
    statements = []
    for unit in plan.get('generation_units', []):
        owned = [a for a in plan.get('assets', []) if a.get('generation_unit_id') == unit['unit_id']]
        scope = {'figure': '整图', 'panel': '子图 ' + str(unit.get('panel_id', '')), 'module': '模块 ' + ', '.join(unit['members'])}[unit['scope']]
        if unit['method'] == 'image_model':
            statements.append(f"{unit['unit_id']}（{scope}）：整体由生图模型生成，包含内部文字、箭头和配图。")
        else:
            parts = [f"{a['asset_id']}由{'生图模型' if a['routing'] == 'image_model' else '本地绘制'}生成" for a in owned]
            statements.append(f"{unit['unit_id']}（{scope}）：" + '；'.join(parts) + '。')
    summary = ' '.join(statements) + ' 各部分最终由本地排版合并；位图内容不会因此变成可逐项编辑的矢量。'
    if plan.get('style_summary'):
        summary += ' ' + str(plan['style_summary'])
    return summary


def projected_graphs(request: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[dict, dict]:
    """Retain semantic topology while projecting collapsed units for assembly."""
    from figure_tools.figure_graph import build_figure_graph

    semantic_assets = [{'asset_id': key, 'type': el.get('type', el.get('kind', 'text')),
                        'panel_id': panel, 'z_order': index}
                       for index, (key, (panel, el)) in enumerate(_elements(request).items(), 1)]
    semantic = build_figure_graph(request, {**plan, 'assets': semantic_assets})
    visible = {asset['asset_id'] for asset in plan['assets']}
    mapping = {key: key for key in visible}
    collapsed = set()
    for asset in plan['assets']:
        child = (asset.get('source') or {}).get('generation_unit')
        if child:
            collapsed.add(asset['asset_id'])
            mapping.update(dict.fromkeys(child['members'], asset['asset_id']))
    for unit in plan.get('generation_units', []):
        owned = [asset['asset_id'] for asset in plan['assets'] if asset.get('generation_unit_id') == unit['unit_id']]
        if unit['method'] == 'image_model' or len(owned) == 1:
            for member in unit['members']:
                if member not in visible or unit['method'] == 'image_model':
                    mapping[member] = owned[0]
                    collapsed.add(owned[0])
    graph = copy.deepcopy(semantic)
    for port in graph['ports']:
        if port['node_id'] not in mapping:
            raise GenerationIntentError(f"semantic node {port['node_id']} has no declared production owner")
        port['node_id'] = mapping[port['node_id']]
    port_nodes = {p['port_id']: p['node_id'] for p in graph['ports']}
    graph['typed_edges'] = [edge for edge in graph['typed_edges']
                            if not (port_nodes[edge['source_port']] == port_nodes[edge['target_port']]
                                    and port_nodes[edge['source_port']] in collapsed)]
    groups = []
    for group in graph['groups']:
        nodes = sorted({mapping.get(node, node) for node in group.get('node_ids', [])})
        if len(nodes) == 1 and nodes[0] in collapsed:
            continue
        groups.append({**group, 'node_ids': nodes})
    graph['groups'] = groups
    graph['labels'] = [label for label in graph['labels'] if label.get('node_id', label.get('target_id')) not in mapping
                       or mapping.get(label.get('node_id', label.get('target_id'))) not in collapsed]
    graph['constraints'] = [item for item in graph['constraints']
                            if all(mapping.get(node, node) == node for node in item.get('node_ids', []))]
    return semantic, build_figure_graph({'figure_graph': graph}, plan)


def image_review_requirements(plan: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    result = {}
    units = {unit['unit_id']: unit for unit in plan.get('generation_units', []) if unit['method'] == 'image_model'}
    for asset in plan.get('assets', []):
        child = (asset.get('source') or {}).get('generation_unit')
        if child:
            units[child['unit_id']] = child
    for unit in units.values():
        ident = unit['unit_id']
        facts = json.dumps(unit.get('requirements', {}), ensure_ascii=False)
        for aspect, question in (
            ('content', 'Verify every required node and exact label is present and correct'),
            ('connections', 'Verify connectivity, arrow directions and scientific relationships'),
            ('quality', 'Verify readability, clipping, background and coherent visual design'),
        ):
            result[f'generation_unit_{ident}_{aspect}'] = (ident, f'{question} for {ident}; required content: {facts}')
    return result
