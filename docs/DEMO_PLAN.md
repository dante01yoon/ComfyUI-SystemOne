# ComfyUI-SystemOne demo plan

Each demo is one workflow JSON in `examples/`, one README section, and one
recording (MP4 for the release, GIF for the README). Every claim a demo makes
was observed on this machine; numbers come from the node's own `report` output.

## What the probe showed (Laya, 2026-10-02, MPS)

| Task | `laya` | `laya` multilingual |
| --- | --- | --- |
| Style choice, English prompt with an explicit style word (4 prompts) | 4/4, conf 0.83-0.99 | 4/4, conf 0.91-1.00 |
| Style choice, prompt with no style word | conf 0.26-0.34 | conf 0.31-0.37 |
| Style choice, Korean prompt ("수채화") | wrong (anime) | wrong (photo) |
| "Names a real public figure?" (Elon Musk, Taylor Swift) | 1 of 2 above 0.5 | 0 of 2 |
| Warm latency per call | 0.06-0.3 s | 0.06-0.3 s |

Demos lean on what worked. The failures become the honest Jev-vs-Laya segment
instead of being hidden.

## Demos

### 1. Style router (Laya, local, free)
Prompt -> **Choice** (`photo / anime / watercolor / render3d`, `min_confidence`
0.5, fallback `photo`) -> **Map** (label -> style suffix) -> `StringConcatenate`
-> `CLIPTextEncode` -> `KSampler`.
Recording: three prompts back to back. Watercolor and anime prompts route to
their styles; the ambiguous "a knight riding a dragon" drops below 0.5 and the
fallback kicks in. The on-node probability bars carry the story.

### 2. Kid-safe gate (Score, Laya)
Prompt -> **Score** ("how graphic or disturbing would the image be", 4 levels)
-> `ComfyMathExpression` (`a >= 2`) -> `If/Else Switch` (true: a kid-safe
replacement prompt, false: the user's prompt) -> `KSampler`.
Probe on 12 prompts: every safe prompt scored <= 1.39 (knight vs dragon,
pirate ship, cartoon pumpkin), every gore prompt >= 2.39, so a 2.0 cut is
12/12. The same question as a Noul was 11/12. Gore never renders: the swap
happens before sampling.
Replaced the earlier "adaptive steps" idea. Its scores were in the right order
but confidence was 0.12-0.15, and SDXL Turbo barely changes between 3 and 5
steps, so the demo showed nothing.

### 3. Real-person guard, Laya and Jev side by side (done)
Two Yes/No nodes, one per backend, on the same prompt. Stops before sampling so
no real person's likeness is rendered. Laya scored real people 0.33-0.47 and a
generic businessman 0.39 (no separating threshold); Jev scored 0.99 vs 0.03.

### 4. One dropdown, two models (done)
Demo 1's graph with prompts that imply a style through a reference. Korean
prompts were dropped from this demo because SDXL's CLIP cannot read Korean, so
even a correct route would not show the subject. On 8 implicit prompts Jev was
8/8 at confidence >= 0.99; Laya was 7/8 but routed only 3 past the 0.5 gate.

### Known limitation (README, not a demo)
Korean prompts misroute on both Laya checkpoints; Jev handled them.

## Recording pipeline
`scripts/record_demo.mjs` (Playwright, 1920x1080) lays out nodes from each
example's `_meta.layout`, types each prompt, clicks Run, and waits for
`execution_success`. `@node.widget=value` arguments change a widget between
runs. `scripts/make_media.sh` trims the start and writes the MP4 and README GIF.
