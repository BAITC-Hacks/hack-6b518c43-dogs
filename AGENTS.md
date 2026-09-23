# LEVRA — instructions for the coding agent

## Task and status
Build LEVRA, a working campaign decision product for the Beeline HackAlem case.
Read `docs/BUILD_BRIEF.md`, `docs/DATA_AUDIT.md`, and `PARTICIPANT_GUIDE.md` first.
`agent.py` currently contains the UNCHANGED ORGANIZER TEMPLATE, not our algorithm.
The reports currently in `reports/` measure that template, not LEVRA.
Work in the team repository supplied by the organizer; preserve existing work and Git history.

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
- User-facing copy: Russian, with consistent English technical labels where needed.
- Do not ask questions already answered in the kit. Record genuine ambiguities and proceed with a safe default.
