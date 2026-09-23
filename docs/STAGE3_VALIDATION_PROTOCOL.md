# Stage 3: protocol fixed before experiments

Registered 2026-09-23 10:42:59 UTC (15:42:59 Asia/Almaty), exact stamp in reports/stage3/registration.json. The original clock label was rounded incorrectly; its unchanged preregistration bytes are archived in reports/stage3/baseline/validation_protocol.md. Baseline: eb782330fb71796dc8cadc7a27eee6a64ff8e516. Exact agent and submission archived in reports/stage3/baseline. Numerical research stops after one 45–60 minute pass, no later than 17:30 local. No organizer files, effects or evaluator internals are inspected or changed.

## Candidates, fixed before outcomes

- baseline: stage-2 adaptive policy, unchanged.
- fixed: baseline fixed_pilots comparator (12 historical priorities, 100 contacts each).
- repeat: same posterior/solver, but reserve research resources: at most 20% total contacts and 20% total budget; retain final resources. From the fifth pilot, prioritize up to six confirmation pilots for a current material allocation (at least 10% positive predicted contribution or 10% total budget). Repeat once after its first observation when its advantage over an alternative is within two combined model SDs. Use up to 180 SMS contacts for transferable estimates, or up to 100 calls for the independent call estimate. Thresholds are heuristics, not calibrated probabilities. Re-evaluate material allocations after every public observation.
- revisit: repeat plus revisit untested historical hypotheses after at least three distinct observed directions: median negative innovation shrinks positive untested historical means toward zero, bounded to the original mean, and expands their variance to reflect disagreement. On every fourth pilot, probe an untested alternative on a large exposed/disputed cell by optimistic upper model score. No history-count exclusion; weak history remains a hypothesis. No more than these two candidate policies or subsequent threshold tuning in this pass.

## Development and one-time held-out comparison

Previously seen official seeds 0–19 and 42 are development, not independent validation. Run development seeds 0,1,2,3,4 for all four strategies. Then freeze candidate code hash before held-out outcomes. Official held-out seeds 100–109 (all four policies); these change pilot noise only, not the official effect world. Seed42 is only a final compatibility/diagnostic run and never a selection criterion.

Separate author-designed worlds use no organizer truth. Four families, 1,200 clients, 40,000 budget, 1,800 contacts, up to 20 pilots; identical resources for all policies. Historical direction c has +80% before/after association, others weakly negative. Families: history approximately right; best direction moved to d; effects weakened; adverse initial pilot observations. Development parameters: conversion .60, c effect .65, shifted d .80/others -.12, weakened scale .20, adverse first two observations -.25, high segment factor .80; seeds 60,61,62. Held-out parameters (not tuned after viewing): conversion .45, c effect .50, shifted d 1.05/others -.08, weakened scale .08, adverse first three observations -.30, high segment factor .65; seeds 160–164. New parameter settings and seeds are both held out. Worlds are distinct families and are never averaged as if their scales were interchangeable.

## Outcomes and acceptance

Save every row, including failures: measured net, forecast net/error, pilot cost/contacts/count, total resources, time, contract violations and plan. Per family/split/policy report median, minimum, negative fraction, mean absolute forecast error, mean pilot resources/time. No accurate loss probability or coverage claim.

A candidate is eligible only with zero contract violations, runtime <240s, official held-out median >=95% baseline, minimum no worse than baseline by more than 10% of |baseline median|, and no increased official negative fraction. In each held-out authored family its median must not regress by more than 10% of max(|baseline median|, 40,000); negative fraction must not worsen by >.20. It must improve official median by >=5% OR improve at least two authored family medians by >=10% of max(|baseline median|,40,000), and reduce official forecast MAE (no scalar correction using official results). Choose eligible candidate with highest official median; if within 2%, lower official MAE wins. If neither qualifies, retain baseline and document unsuccessful hypotheses. Fixed-pilot comparator contextualizes results, but is not silently promoted to a third candidate.

Run all preregistered outcomes once, without deleting unfavorable runs. Any rerun is explicitly labelled and cannot replace selection data. Final official local_eval, 10-seed script, fresh-process submission/key-invariance, originals, unit tests and browser checks follow selection.

## Recorded implementation limitations (after outcomes, no tuning)

The frozen harness supplies direct historical rows only for c. The phrase “others weakly negative” above described intent imprecisely: other targets actually use the baseline engine’s unobserved context priors, which can have either sign. Both candidates and all comparators used the same frozen history. Code/world hashes match the original registration. No outcomes were discarded or rerun for selection. The contact cap reserves final execution capacity; there is no hard sub-budget exclusively reserved for confirmation. Confirmations receive priority from step five while resources remain. Resource caps and repeat allocation changed together, so this experiment does not isolate their separate causal contributions.
