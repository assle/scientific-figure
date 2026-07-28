# Routing rules

Element-to-engine routing for scientific-figure-builder (plan section 2).

## Responsibility boundaries

| Component | Responsibilities | Prohibited |
|---|---|---|
| OpenCode planning model | Understand requests, classify tasks, create plans, select tools, summarize validation | Invent scientific data; directly produce final raster figures |
| Ark multimodal analysis model | Analyze references, identify panels/objects, extract text candidates, report uncertainty | Decide whether numerical source data are correct |
| Ark multimodal validation model | Check semantic structure, object count, perspective, style consistency, unwanted text, final layout | Validate quantitative accuracy from pixels |
| Ark image-generation model | Generate/edit isolated, complex, non-quantitative visual assets | Generate data plots, axes, tick labels, exact numbers, equations, periodic arrays, or final compound figures |
| Python | Quantitative plots, precise geometry, file validation, composition, export, effective-DPI checks | Invent missing experimental values |
| SVG | Arrows, connectors, labels, equations, regular geometry, simple diagrams | Produce complex photorealistic equipment |
| PPTX | Optional editable text, shapes, final slide composition | Serve as the scientific computation engine |

## Worked examples

- Semi-realistic optical-fiber body -> Ark image model.
- Exact periodic grating -> Python or SVG.
- Beam and arrow -> SVG.
- Coupling-efficiency curve -> Python.
- Labels, angles, equations -> SVG or PPTX.
- Reference-figure decomposition -> Ark multimodal analysis model.
- Final assembly -> Python and SVG.

## Regular structures (Python or SVG only)

Periodic gratings/arrays, scales and ticks, neural-network nodes, repeated
geometry, exact angles and dimensions. Image generation is allowed only via an
explicit `visual_priority` override for non-quantitative drafts.
