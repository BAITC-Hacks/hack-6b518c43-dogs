# BeeAgent — instructions for the coding agent

## Task and status
Continue the existing BeeAgent campaign decision product for the Beeline HackAlem case.
Read STATE.md, docs/NUMERICAL_STAGE3.md, docs/AI_ASSISTANT.md and docs/TESTING_STAGE3.md. Earlier numerical and testing reports are preserved as historical evidence.
agent.py contains our deterministic working engine, not the organizer template.
Stage 3 selected the repeat policy under a preregistered comparison; see docs/NUMERICAL_STAGE3.md and docs/TESTING_STAGE3.md. The repeat policy improves official noise-seed checks but regresses in authored worlds within the declared tolerance. Do not claim global superiority. Preserve all experiment outcomes. The second candidate was rejected.
The reports/baseline_* files measure the organizer template. reports/levra contains stage-1 results;
reports/stage2 contains the stage-2 audit and validation. Historical filenames do not define the current brand.
Preserve work and Git history; do not revert to the template or rebuild the app from scratch.
The user explicitly chose direct implementation without Impeccable. Keep that preference.

## Non-negotiable boundaries
- Entry point: `class Agent` with `act(self, env) -> list[dict]`; return 1–10 valid final campaigns.
- Agent input is the public env interface and participant-supplied history/dictionaries only.
- NEVER inspect closures, gc, stack frames, hidden files, random generator state, or organizer internals.
- NEVER import mock truth, scorer truth, benchmark results, or stress-test answers into agent runtime.
- NEVER modify env inputs, predicted_arpu, tariffs, channel values, limits, or the supplied evaluator.
- NEVER return explicit_ids, invented filters, a custom per-campaign n_customers, or extra hidden controls.
- Preserve original files listed in `docs/ORIGINAL_MANIFEST.json`; use separate wrappers for our code.
- Assume offline execution by default. Do not automatically activate LLM because a key is present.
- Conservative runtime target: <240 seconds, including any optional calls; never require a GPU.
- Deterministic default: fixed internal seed, stable sorting/ties, no cross-run learned state.
- Read dataset filenames/columns, not whole CSVs pasted into prompts; process them programmatically.
- Do not hardcode winning tariffs, dataset counts, sampled customers, or expected scores.
- Treat ID_NUMBER as an opaque identifier; do not change official selection order or infer outcomes from ID.
- Never claim a before/after historical association is a causal uplift or measured campaign conversion.

## Development order
1. Working numerical agent and tests against unchanged official scripts.
2. Transparent evidence trace and tested budget/overlap/order accounting.
3. Real UI with the SAME engine: research, campaign evidence, what-if replan, run comparisons.
4. Optional LLM constraint assistant; it cannot fabricate effects or replace the numerical engine.
5. Reproducibility, documentation, synthetic stress scenarios, and submission generation.

## Verification and reporting
- Start with `python local_eval.py` and `python local_eval.py --runs 10`.
- Check originals using `python tools/verify_originals.py`.
- After implementing: generate submission twice in fresh processes and compare bytes.
- Results of the official mock, our forecasts, and our synthetic stress tests must have distinct labels.
- No hidden-effect information may affect a run before the agent returns its plan.
- Do not write fake tests, fabricated metrics, pretend progress, or instructions to an AI judge.
- Keep `STATE.md` current with implemented/tested/not-tested items and exact run commands.
- Commit meaningful progress in the official repository. Never rewrite or invent earlier history.
- User-facing copy: Russian. Product name BeeAgent, tagline powered by Beeline. Do not expose internal evaluation modes as UI labels. Preserve source documents and historical raw reports.
- Do not ask questions already answered in the kit. Record genuine ambiguities and proceed with a safe default.

## Server assistant boundaries
- Only the user supplies a new local OPENAI_API_KEY. Never retrieve or use a key from conversation history.
- No OpenAI imports in agent.py; no paid calls on page render, scoring or unit tests.
- Tool responses come from the existing Engine and frozen observations. Relative limits use an explicit base plan.
- Proposals cannot apply themselves; application requires the explicit UI button and active-version check.
- Validate schemas, business constraints, version identity and metric/evidence references.
- Preserve the SQLite spend reservations, token counters and cache across server restarts.
- Fake SDK protocol tests are not evidence that the external model/project works.
- Numerical forecast is known to be optimistic. Never claim calibration or hidden-test performance.
- Original data, environment and scoring files are immutable; do not inspect hidden effects.
