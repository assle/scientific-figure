# Routing rules

Element-to-engine routing for scientific-figure-builder (plan section 2).

## Responsibility boundaries

| Component | Responsibilities | Prohibited |
|---|---|---|
| Calling Agent | Submit user input, approvals, and resume actions to the Orchestrator; present its next action | Own lifecycle sequencing or bypass phase gates |
| Orchestrator | Own Lifecycle phases, approvals, budgets, artifact handoffs, and next actions | Invent scientific data or replace deterministic routes |
| Phase worker | Perform isolated reasoning for one Lifecycle phase and return a schema-valid Phase artifact | Advance Run state, write arbitrary downstream artifacts, or use unallowed routes |
| Configured multimodal analysis model | Analyze references, identify panels/objects, extract text candidates, report uncertainty | Decide whether numerical source data are correct |
| Configured multimodal validation model | Check semantic structure, object count, perspective, style consistency, unwanted text, final layout | Validate quantitative accuracy from pixels |
| Configured image-generation model | Generate/edit isolated, complex, non-quantitative visual assets | Generate data plots, axes, tick labels, exact numbers, equations, periodic arrays, or final compound figures |
| Python | Quantitative plots, precise geometry, file validation, composition, export, effective-DPI checks | Invent missing experimental values |
| SVG | Arrows, connectors, labels, equations, regular geometry, simple diagrams | Produce complex photorealistic equipment |
| PPTX | Optional editable text, shapes, final slide composition | Serve as the scientific computation engine |

## Worked examples

- Semi-realistic optical-fiber body -> configured image-generation model.
- Exact periodic grating -> Python or SVG.
- Beam and arrow -> SVG.
- Coupling-efficiency curve -> Python.
- Labels, angles, equations -> SVG or PPTX.
- Reference-figure decomposition -> configured multimodal analysis model.
- Final assembly -> Python and SVG.
- Figure Graph connectors -> port-bound SVG arrows in the blueprint and final assembly.

## Regular structures (Python or SVG only)

Periodic gratings/arrays, scales and ticks, neural-network nodes, repeated
geometry, exact angles and dimensions. Image generation is allowed only via an
explicit `visual_priority` override for non-quantitative drafts.
