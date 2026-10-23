# Results

The final evaluation, run as pre-registered in [eval-plan.md](eval-plan.md) (with amendments 1 to 4, all written before the held-out matches existed).

- **When:** 2026-10-23 20:13 to 21:39 UTC, one run, all four arms.
- **Code:** commit `b040ffb`, the code deployed to the live demo.
- **Model:** gpt-5-mini (2025-08-07) on Microsoft Foundry, for every arm.
- **Data:** the 80 held-out matches (seeds 9001-9080), generated for this run and never used before. They hold 328 VAR-reviewable incidents, 61 of them contested (the on-field call differs from the Law, or the incident is borderline).
- **Records:** every incident, arm, verdict, explanation, claim and timing is in [`results/held-out-20261023T2139Z.json`](../results/held-out-20261023T2139Z.json).

No arm recorded an error.

## The pre-registered test

Success required the full desk to beat the model alone on verdict accuracy **and** on the unsupported-claim rate, each 95% interval (paired bootstrap, 10,000 resamples) excluding zero.

| | Model alone | Ruling | Difference [95% CI] | |
|---|---|---|---|---|
| Verdict accuracy | 89.3% | 100% | +10.7 pts [+7.6, +14.0] | met |
| Unsupported-claim rate | 3.5% | 2.6% | −0.9 pts [−2.6, +0.8] | not met |

**The pre-registered success test is not met.** The desk gets every decision right and the model alone does not, but on unsupported claims the difference favours the desk and stays within noise. The development run had already suggested this, and amendment 3 said so before the held-out run.

## All arms

| Arm | Verdict | Contested (61) | Law clause | Unsupported claims | Explanations with any | Raw data in fan text | Planted errors: precision / recall | Median s | p90 s | $ per check |
|---|---|---|---|---|---|---|---|---|---|---|
| Model alone | 89.3% | 77.0% | 8.5% | 3.5% | 11.0% | 85.4% | 61.5% / 87.0% | 11.0 | 16.4 | 0.0036 |
| Ruling | **100%** | **100%** | **100%** | 2.6% | 4.6% | **0%** | **100% / 100%** | 18.4 | 37.6 | 0.0043 |
| Ruling without precedent | 100% | 100% | 100% | 2.7% | 5.2% | 0% | 100% / 100% | 16.7 | 36.0 | 0.0046 |
| Ruling without checker | 100% | 100% | 100% | 3.4% | 6.4% | 0% | 100% / 100% | 6.4 | 8.1 | 0.0007 |

Contested incidents: Ruling +23.0 pts over the model alone [+13.1, +34.4]. No stale-law citation appeared in any arm. Cost is at the gpt-5-mini list price ($0.25 and $2.00 per million input and output tokens); precedent embeddings are not counted.

## By category

| Category | Incidents | Verdict: model / Ruling | Law clause: model / Ruling | Unsupported claims: model / Ruling |
|---|---|---|---|---|
| Offside | 206 | 93.7% / 100% | 8.3% / 100% | 3.9% / 0.6% |
| Penalty claim | 60 | 78.3% / 100% | 10.0% / 100% | 3.6% / 6.8% |
| Handball | 23 | 78.3% / 100% | 21.7% / 100% | 2.8% / 3.0% |
| Handball before a goal | 19 | 78.9% / 100% | 0% / 100% | 0% / 2.8% |
| Possible red card | 20 | 100% / 100% | 0% / 100% | 4.2% / 6.4% |

## Planted on-field errors

46 of the 328 on-field calls were wrong.
- **Ruling** flagged exactly those 46.
- **The model alone** flagged 65. It was right on 40, missed 6, and **would have overturned 25 correct on-field decisions**.

## Where the model alone went wrong

It missed 35 of 328: 31 wrong decisions and 4 wrong cards. The misses cluster in a few situations:

| Situation | Model alone right |
|---|---|
| A penalty claim where the attacker initiated the contact | 0 of 7 |
| A tight onside call (it called offside) | 12 of 19 |
| A handball by the scorer just before the goal | 3 of 7 |
| An offside from a throw-in, goal kick or corner (no offence) | 8 of 11 |
| Marginal contact in the area | 4 of 7 |
| The ball off the defender's own body onto the arm | 4 of 6 |

The desk was right in every one of these situations.

## Edge cases

From the held-out run:

| Edge case | Incidents | Model alone | Ruling |
|---|---|---|---|
| Offside after a deflection off a defender (no reset) | 2 | 2 | 2 |
| Offside reset by a defender's deliberate play | 7 | 7 | 7 |
| Handball by the scorer immediately before the goal | 7 | 3 | 7 |
| A team-mate's accidental handball earlier in the move (goal stands) | 12 | 12 | 12 |
| DOGSO in the area | 0 | | |

Because some of these are rare, one of each was also run through the full desk with the same models after the evaluation. The rare ones came from the precedent archive, with the incident itself excluded from its own precedent; the demo-match ones ran on the live API. **All 6 decisions were right.**

The run also found one gap, fixed afterwards. For DOGSO in the area with a genuine attempt to play the ball, the decision (the yellow card stands) was right. But the evidence did not state that the offence was inside the penalty area, or that the defender tried to play the ball, the two facts that turn red into yellow. The writer could not explain the decision, and the checker held it. The evidence now states both, and the same check publishes: "Contact … was 6.2 m inside the area; Vasivic attempted to play the ball, so the decision is a yellow card." The held-out numbers above come from the code before this fix.

Mistaken identity, the ball going out of play before a goal, and two incidents in one passage of play are not generated, so they are not tested.

## Ablations

- **Precedent** changes no verdict, by design: precedent is advisory and the measured decision always stands. Without it, unsupported claims were 2.7% (vs 2.6%), and 8 checks were held instead of 4.
- **The checker** cuts unsupported claims from 3.4% to 2.6% (−0.9 pts [−2.1, +0.3]), and explanations with any unsupported claim from 6.4% to 4.6%. The direction is consistent, but this is not significant on its own. It adds about 12 seconds per check and multiplies the cost by six ($0.0043 against $0.0007).

## What the unsupported claims were

*This breakdown was not pre-registered; it explains the numbers above rather than replacing them.*

**Ruling.** The judge marked 16 of its 625 fact and law claims as not supported:
- 11 are the sentence "It was a close call", which the desk writes for borderline incidents. The judge's record has the measured facts but not the desk's borderline flag, so it cannot verify the phrase.
- 2 mention precedent, which the judge's record also lacks.
- 3 are genuine slips, for example naming the passer as the player who set the offside line.

These explain why Ruling's claim rate is higher than the model's on penalty claims and red cards, the categories with most borderline incidents.

**The model alone.** The judge marked 42 of its 1,202 claims as not supported, and 26 of them as contradicted. Most are wrong offside geometry, for example calling a tight onside "offside" with coordinates for the line. Ruling had 1 contradicted claim.

The product lesson: when the desk calls something close, it should state the measured reason as a fact that can be checked.

## The checker's holds

Ruling held 4 of 328 checks: the writer's drafts still failed the checker after two rewrites. In each case the checker was stricter than its own instructions, for example rejecting "VAR checked using tracking data". All 4 holding lines still stated the correct decision, for example "VAR check complete: no foul." No check reached the 90-second deadline; the slowest took 87.5 seconds.

## Groundedness (Microsoft Foundry, exploratory)

Microsoft Foundry's groundedness evaluator (azure-ai-evaluation 1.18.9, judged by gpt-5-mini) scored every fan explanation from 1 to 5. It used the same record as the claim audit: the raw check data, the measured facts and the Law summary. Both runs are logged in the Foundry project.

| | Model alone | Ruling |
|---|---|---|
| Mean groundedness (1-5) | 4.53 | 4.67 |
| Grounded (3 or more) | 86.9% | 89.9% |

Ruling minus the model alone: +0.14, 95% CI [+0.003, +0.284], a paired bootstrap over 328 pairs. The interval only just excludes zero, and this check was not pre-registered, so it is exploratory.

Unlike our claim audit, this evaluator also scores statements of the outcome ("the on-field decision stands"). The record cannot support those, because it holds no decision. The reasons it gives for low scores in both arms typically concern the stated outcome. Per-explanation scores and reasons: [`results/held-out-20261023T2139Z.groundedness-scores.json`](../results/held-out-20261023T2139Z.groundedness-scores.json).

## Hand check of the claim audit

50 fact and law claims were drawn at random (seed 20261024): 25 from the model alone and 25 from Ruling, shuffled together. Each was checked against the same record the judge saw, the raw check data, the measured facts and the Law summary. **The check was done by Claude Code, the AI coding assistant used to build Ruling, not by a person**, as amendment 4 states.

Agreement with the judge was **49 of 50**. The one disagreement was a model-only claim that the handball happened "1.53 m from goal". The judge accepted it, but 1.53 m is the distance the ball travelled before hitting the arm; the contact point was about 12 m from goal. So if anything the judge is lenient towards the model alone. The labels are in [`results/held-out-20261023T2139Z.hand-check.json`](../results/held-out-20261023T2139Z.hand-check.json).

## Limitations

- **The correct outcomes come from our own encoding of the Laws.** The desk computes the same geometry the generator used, so its edge on factual calls is expected by design. The subjective categories and the claims carry the information.
- **Synthetic incidents** use points and labelled attributes, not video, and on-field errors are planted at higher rates than in real matches.
- **The claim judge is a model** (gpt-5-mini at low effort, with a different prompt from the checker), so it can be wrong. The hand check suggests it is close but lenient.
