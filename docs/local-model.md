# Running a local model (e.g. Raspberry Pi 5 with Gemma)

> Status: **note, not the recommended default.** The pipeline runs in production
> against an API provider (default `anthropic:claude-opus-4-8`). This document records
> whether and how a local model would work — in case someone needs it later (e.g. a
> privacy-sensitive environment). For non-sensitive, public administrative sources
> there is no reason to deviate from the API provider.

## Is it possible at all?

Technically yes. Provider and model come exclusively from the environment
(`src/tessera/extract.py`): `TESSERA_MODEL` is a pydantic-ai model string, and there is
no hard Anthropic dependency in the code. `pydantic-ai` also speaks OpenAI-compatible
endpoints, and a local [Ollama](https://ollama.com) server exposes exactly such an
endpoint. The rough path:

```bash
# On the Pi: ollama serve; ollama pull gemma3:4b
export TESSERA_MODEL=openai:gemma3:4b
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama        # A dummy is enough — Ollama does not check it;
                                    # the key check in extract.py only requires that
                                    # the variable is set.
```

**Possible small code change:** Currently only the model string is passed to `Agent()`,
no `base_url`. If pydantic-ai does not pick up `OPENAI_BASE_URL` on its own, the
provider has to be constructed explicitly with `base_url` (a few lines in
`extract.py`). This change is deliberately **not** made — it will only be built when a
local model is actually needed.

## The real catch: the task, not the hardware

Tessera demands two things that small, quantized models on a Pi 5 (CPU inference,
limited RAM) deliver poorly:

1. **Strict structured output** — the entire `XProcess` Pydantic graph in one shot,
   valid. Small Gemma variants often break the schema.
2. **Character-faithful `source_quote`** — the grounding gate
   ("provability over self-assessment", see `CLAUDE.md`) discards every step whose
   quote does not appear **verbatim** in the source text. Small models paraphrase
   instead of copying exactly — which is precisely what gets dropped here.

The reassuring part: a weak local model produces **no wrong output**, just **little or
none**. The grounding gate and the Pydantic validator catch hallucinations; the
cardinal rule "link, don't assert" stays intact. So it is not a *security* problem but
a *usability* one: on the Pi with Gemma 4B, expect many flagged/discarded steps and
slow runs (long Markdown context on CPU).

## A more realistic variant, should local ever become necessary

The Pi 5 as an **orchestrator** — crawling, validation and PR creation already run
locally and need no large model. Only send the pure extraction call to a stronger
model: either still the API provider, or a larger local model on a GPU-equipped
machine on the same network (same `OPENAI_BASE_URL` mechanism).
