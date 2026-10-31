# AI providers — what is real and what is simulated

The honesty rule is a **product feature**, not a comment: every job row carries
`simulated`, and the UI renders a visible badge for it. Nothing fabricated is
ever presented as real AI output.

| Provider (`AI_PROVIDER`) | Storyboard | Keyframes | `simulated` | Needs |
|---|---|---|---|---|
| `mock` (default) | fabricated locally from the prompt | gradient placeholders stamped **SIMULATED KEYFRAME (MOCK PROVIDER - NOT REAL AI)** | **true** | nothing — works offline, Termux/tests/CI |
| `zai_gateway` | real LLM JSON storyboard | real image-model renders (PNG/JPEG detected by magic bytes) | **false** | the `ai-gateway` sidecar running on 127.0.0.1:3030 |
| `openai_compatible` | real chat-completions JSON storyboard | real `images/generations` output | **false** | `OPENAI_BASE_URL` + `OPENAI_API_KEY` in `.env` (bring your own key) |
| `safety` | — | — | — | not a provider: it is the bookkeeping name used when the pre-filter rejects a prompt before any charge |

## Verified evidence (2026-10-31)

- **Real generation (`zai_gateway`):** prompt *"a slow cinematic dolly shot
  through a neon-lit rainy Tokyo alley at night"* → real LLM storyboard (2
  scenes), 2 real JPEG keyframes, real MP4 (2.59 MB, 10.5 s) — artifacts in the
  repo owner's evidence archive; pipeline wall-clock ≈126 s. `simulated=false`.
- **Simulated path (`mock`):** same flow fully offline, artifacts clearly
  stamped; used by the whole test suite (94 tests) and the browser E2E.
- **Failure path:** a provider exception produces `failed` + **full refund**
  (`refund_job_failed` ledger entry) — proven by `tests/test_pipeline.py`.

## Enabling real generation

```bash
# 1) start the sidecar (localhost only, optional shared token)
./scripts/dev.sh gateway            # node ai-gateway/index.mjs -> :3030

# 2) point the backend at it (backend/.env or repo .env)
AI_PROVIDER=zai_gateway
AI_GATEWAY_URL=http://127.0.0.1:3030
# AI_GATEWAY_TOKEN=<same value you export for the sidecar>   # optional

# 3) restart the backend; every new job now runs REAL generation
```

Or bring your own key:

```bash
AI_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://api.openai.com/v1     # or OpenRouter / local server
OPENAI_API_KEY=sk-...
```

## Design rules

1. **One abstraction** (`services/ai/base.py`): every provider implements
   `generate_storyboard()` and `generate_keyframe()`; the pipeline and the API
   are provider-agnostic.
2. **Secrets only via `.env`** — never in code, never in the DB, never logged.
3. **Image formats are detected from magic bytes** (`sniff_image_format`) —
   image APIs frequently return JPEG regardless of the requested type; the
   stored extension/content-type always match the real bytes.
4. **A failed provider call is a `failed` job, not a fake success** — the error
   message surfaces in the UI and the credits come back.
5. **The mock provider is a first-class provider**, not a hidden test shim —
   demos work without keys, and every artifact it fabricates says SIMULATED.
