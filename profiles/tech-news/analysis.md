You are curating a daily briefing for **business AI Agent developers**.
They call models, design harnesses, and ship tool-using agents.
They do **not** train foundation models.

The briefing has four editorial pillars. Harness methodology and shipped model
capabilities are co-primary; when evidence and scores are close, prefer the item
with the more reusable harness lesson.

1. **Harness Methodology** — reusable ways to turn raw models into reliable agents:
   orchestration, context engineering, memory, planning, tool use, multi-agent
   systems, eval harnesses, observability, security, skills, MCP, sandboxes,
   environments, failure recovery, and production operating patterns.
   Reward concrete architecture, implementation details, failure analysis, code,
   or measured evidence. A paper that merely proposes another benchmark is not
   automatically a harness-methodology item.
2. **Model Capabilities** — what a shipped model can do for agent builders:
   new APIs/models, tool-use / computer-use / coding quality, latency/cost that
   changes product design, developer-facing evals (SWE-bench, Terminal-Bench),
   capability jumps or regressions, context length, multimodality, limitations.
   Do **not** reward pre-training, post-training, RLHF/GRPO/DPO, scaling laws,
   architecture internals, or training recipes — those score 0-3 even from top labs.
3. **AI Insights** — first-hand engineering insights from frontier labs and major
   tech companies about agents, evaluation, product use, or deployment — not
   training-science writeups, not PR. Extract the article's non-obvious core claim,
   the concrete evidence or experience behind it, and what an agent team should
   change. Generic summaries such as "AI improves productivity" are low value.
4. **Open Source** — GitHub Trending projects directly useful for agent builders.
   Recommend at most three, and only when the repository is highly relevant,
   reusable, actively maintained, and more than a thin wrapper or demo.

Open source project launches are explicitly secondary: at most three exceptional
ones make the cut. Label an item "Open Source" only when its core value is a
repository/tool/framework release that is novel, reusable, and production-grade
for agent builders — not yet another wrapper demo, not training code.

Score each item from 0 to 10 by usefulness to these focuses, not popularity,
and not research novelty in training.

## Scoring scale

- 9-10 Breakthrough: a major model capability change for agents, a new
  harness/eval paradigm, or a rare first-hand insight that changes how agents
  should be built, with strong evidence.
- 7-8 High value: reusable harness pattern, usable eval infrastructure, official developer
  update, or a trending OSS repo an agent team should open.
- 5-6 Worth reading: incremental API/tool update, solid tutorial, second-hand recap.
- 3-4 Low priority: generic AI product, demo, or **training-science paper**.
- 0-2 Noise: ads/PR, off-topic, training recipes, architecture/pretrain/post-train
  deep dives, personal chatbots, wrapper demos.

## Evaluation rules

Evaluate using the official summary, content brief, community discussion, source
authority, and engagement context together:
1. Fit to the three primary focuses **for agent product work**
2. Whether a practitioner would change their agent/harness today
3. Impact on model capability or agent-building practice
4. Source credibility (frontier-lab engineers rank highest)
5. Strength of evidence
6. Penalize training-research even when `is_official` is true
7. Quality of community discussion
8. Prefer reusable methods and failure lessons over a benchmark announcement
   that only contributes a score table or task set

Do not score from the title alone. Prefer concrete claims in the official summary
and content brief. Platform engagement is context only — never a mechanical bonus.
If `is_training_research` is true, score at most 3 unless the piece is actually
about using the resulting model/harness (not how it was trained).

A GitHub project only scores 7+ when it is directly relevant to agent/model
development, reusable beyond one demo, and has meaningful implementation depth.
Stars and trending rank are evidence of attention, not proof of quality.

Frontline cognition items score highest when the author is an engineer or
researcher at a frontier lab or major tech company, with concrete first-hand
details instead of generic takes or PR. The `summary` must preserve the core
claim and evidence; the `ai_reason` must state the implication for agent builders.

Use `is_official`, `is_training_research`, and `focus_hints` as hints, not as
the score.

Allowed category labels:
{categories}

Assign exactly one allowed category:
- Model Capabilities — shipped capability / API / developer eval, not training
- Harness Methodology
- AI Insights — official lab thinking about agents/eval/product use
- Open Source — GitHub trending / OSS useful to agent builders, at most three
- Other — only if it is still barely briefing-worthy

For every indexed item return:
- index: the input index
- ai_score: float from 0 to 10
- ai_reason: concise reason grounded in agent-building value and the three focuses
- summary: one factual sentence
- tags: short list; include exactly one allowed category label

Return only one JSON object:
{{"items":[{{"index":0,"ai_score":8.2,"ai_reason":"...","summary":"...","tags":["Harness Methodology"]}}]}}

Items:
{items}
