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

### 2. Adaptive steps (Score)
Prompt -> **Score** ("how visually complex is the scene", 4 levels) -> `level`
INT -> `ComfyMathExpression` (`4 + a * 4`) -> `KSampler.steps`.
Recording: a single-subject prompt renders at 4 steps, a crowded city at 16.
Shows a judgment driving a numeric parameter, not just a branch.

### 3. Prompt guard (Noul, Jev vs Laya)
Prompt -> **Yes/No** ("names a real celebrity or public figure?") -> `verdict`
-> `If/Else Switch` (true: safe fallback prompt, false: user prompt).
Recording: same graph, provider toggled on the Backend node. Laya misses
"Elon Musk"; Jev catches it. Needs `TYPESAFE_API_KEY`.

### 4. One switch, two models
Demo 1 with the Backend node flipped from `laya` to `jev`. Side-by-side clip of
the probability bars and `latency_ms` from `report`. Message: local and free vs
hosted and stronger, same graph.

### Known limitation (README, not a demo)
Korean prompts misroute on both Laya checkpoints. Translate first or use Jev.

## Recording pipeline
1. Start ComfyUI on a fixed port with the pack symlinked into `custom_nodes`.
2. Playwright (chromium, `recordVideo`, 1600x1000) loads the workflow from
   `examples/`, types each prompt, queues, waits on the `/history` entry.
3. `ffmpeg` trims and exports MP4 plus a 960px GIF for the README.
The script lives in `scripts/record_demo.ts` so any demo can be re-recorded.

## Blocked on
- An image checkpoint for demos 1-3 (none installed locally).
- `TYPESAFE_API_KEY` for demos 3-4.
- Permission to create the public GitHub repo.
