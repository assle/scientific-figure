# Real Provider regression verification

This is the current verification record for credential-backed Provider routes.
It contains no credentials, prompts, uploaded image data, or authorization
headers.

## Controlled live run

The 2026-09-05 macOS run enforced a total ceiling of 10 real Model calls at the
Provider Transport boundary. It used 6 calls and left 4 unused:

| Model role | Provider model | Calls | Result |
| --- | --- | ---: | --- |
| `vision_analyze` | `deepseek-v4-flash-vision-exp` | 1 | Complete five-panel reference analysis |
| `image_generate` | `qwen-image-3.0` | 1 | 1024 x 1024 RGBA asset generated |
| inherited `image_edit` | `qwen-image-3.0` | 1 | Structure retained and outer accent changed to blue |
| `phase_reasoning` | `deepseek-v4-flash-vision-exp` | 1 | Valid structured Phase artifact |
| `vision_validate` asset review | `deepseek-v4-flash-vision-exp` | 1 | Non-blocking result |
| `vision_validate` final review | `deepseek-v4-flash-vision-exp` | 1 | All requested checks passed |

The complex reference that had previously produced truncated JSON completed at
the initial 4096-token allowance. No Structured output expansion was needed in
this run; deterministic boundary tests cover 4096 to 8192 to 16384 expansion,
paid-call accounting, audit recording, and budget exhaustion.

## Local and browser verification

Playwright and Computer Use both loaded the generated and edited outputs as two
complete 1024 x 1024 images with no browser console errors. The checkerboard
background initially exposed internal transparent holes that were invisible on
white: the generated asset had 9.41% transparent pixels and the edited asset had
5.12% transparent pixels in the central 384 x 384 region. After restricting
corner-color chroma key to edge-connected background, replaying the retained RGB
pixels reduced both central transparency ratios to 0 while preserving the same
foreground bounding boxes.

The no-network suite completed with 572 passed and 3 explicitly skipped real
Provider or desktop tests. The opt-in PowerPoint test passed separately after
Microsoft 365 activation, including SVG insertion, conversion, and ungrouping.
