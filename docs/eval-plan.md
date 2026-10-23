# Evaluation plan (pre-registered)

Written on 2026-10-15, before any synthetic data, tools or prompts exist. Results will be reported against this plan as written. Any later change gets a dated amendment at the bottom, never a silent edit.

## Question

When VAR reviews an incident, does a desk that **computes** the evidence (geometry from tracking data), **retrieves** the applicable Law clause and similar precedent decisions, and **checks** every claim before publishing give better decisions and fewer unsupported claims than a language model reading the same raw data?

## Data

- **Source:** synthetic matches from Ruling's own generator, with fictional clubs and players. No real match data.
- **Held-out set:** 20 matches, seeds 9001-9020. They are never used for tuning prompts, thresholds or retrieval. Development uses seeds 5001-5020.
- **Target:** at least 300 VAR-reviewable incidents across these categories:
  - offside (including deflections and deliberate play by an opponent)
  - fouls in and around the penalty area
  - handball (including accidental handball by the scorer)
  - denying an obvious goal-scoring opportunity (DOGSO) and direct red cards
  - serious foul play
  - mistaken identity
  - ball out of play during the attacking phase before a goal
- **Ground truth:** each incident's correct outcome comes from the generator's encoding of the Laws of the Game.
- **On-field decisions:** errors are planted at fixed rates per category. Borderline incidents are included where the correct VAR outcome is "on-field decision stands: no clear and obvious error".
- **Precedent library:** a separate archive of 120 matches (seeds 1-120) that the precedent search may use. Held-out incidents are never in it.

## Arms

| Arm | Description |
|-----|-------------|
| A. Model only | gpt-5-mini receives the same raw incident data (events and freeze-frame positions as JSON) and is asked for the VAR outcome, the Law clause and a fan explanation. |
| B. Ruling | The full desk: evidence tools, Laws retrieval, precedent search, assessor, communicator, checker. |
| C1. Ruling without precedent | Ablation. |
| C2. Ruling without checker | Ablation. |

All arms use the same model deployment and the same incident data.

## Metrics

**Primary:** verdict accuracy, the share of incidents where the arm gives the correct VAR outcome ("stands" or "overturn to X"), with the correct restart and disciplinary sanction.

**Secondary:**
- Law clause accuracy: the cited clause is the one that governs the incident.
- Unsupported-claim rate: the share of factual claims in the fan explanation not backed by the computed evidence or the cited clause. Claims are extracted per sentence and checked against the evidence record; a sample of 50 is checked by hand.
- Planted-error detection: precision and recall for flagging the on-field errors planted in the data.
- Time to a ready draft (seconds) and cost per incident (USD).

## Analysis

- **Success:** Arm B beats Arm A on verdict accuracy **and** on unsupported-claim rate. The 95% confidence interval of each difference (paired bootstrap over incidents, 10,000 resamples) must exclude zero.
- Every metric is reported per category as well as overall, whatever the result.
- The ablations show how much each part contributes.

## Known limitations, stated up front

- **The ground truth is our own encoding of the Laws.** Arm B's tools compute the same geometry the generator used, so a win on factual calls (offside position, inside or outside the area) is expected by design. The claim being tested there is that facts should be computed, not generated. The informative results are the subjective categories and the unsupported-claim rate.
- **Synthetic incidents simplify real ones:** point positions and labelled attributes instead of video.
- **The Laws are paraphrased** with clause references, so a paraphrase error would affect both arms' scoring equally.

## Amendments

**1. 2026-10-15, before any data, tools or prompts exist.** The reference text is the Laws of the Game 2026/27 (in force from 1 July 2026). The unsupported-claim rate gains a named sub-metric, the **stale-law citation rate**: the share of explanations that rely on wording removed or changed in earlier editions. Examples:
- the handball "arm above shoulder level" criterion and its listed exceptions, removed in 2022/23;
- DOGSO considerations that omit the location and number of attackers, added in 2026/27;
- treating a second caution as never reviewable, when a clearly wrong one is reviewable from 2026/27.

**2. 2026-10-18, before any held-out match has been generated.**

*Measured incident density.* The generator now plants five incident categories:
- offside checks on goals
- penalty claims
- handball claims
- handball before a goal
- possible red cards

On the development and precedent seeds only (5001-5020 and 1-120, 140 matches), it produces 4.09 VAR-reviewable incidents per match. Of those, 0.97 per match are contested: the on-field call differs from the Law, or the incident is borderline.

*Change 1: a larger held-out set.* 20 held-out matches would give about 82 incidents, short of the 300 targeted above. The held-out set therefore becomes **seeds 9001-9080 (80 matches, about 327 incidents expected)**. The seeds were chosen before generation, and no held-out match exists yet.

*Change 2: a contested breakdown.* Every metric will also be reported for the **contested subset**, because silent "check complete" incidents dominate the count and are easy for both arms.

*Disclosure: planted error rates.* On-field error rates are planted per scenario and are higher than in real matches (the generator gives about 0.74 VAR interventions per match), so that the evaluation sees enough contested decisions. This is a design choice for the test, not a claim about real refereeing.

**3. 2026-10-20, before any held-out match has been generated.**

*New secondary metric: readability.* The share of fan explanations that leak raw data: a raw player id (for example `MLA-11`), a data field name, a coordinate pair, or a bare true/false value. It is detected by pattern in `src/ruling/eval/readability.py`.

*Why it is added.* It was found on development data, so it is labelled as such. On the development seeds, the model alone leaked raw data in 65 of 79 fan explanations and Ruling in none. It is added now so that the held-out run tests it rather than the development run that suggested it.

*Disclosure: the unsupported-claim audit changed on development data before this point, and the held-out run uses the final version.*
- The judge now receives the club names.
- Statements about the VAR process count as decision statements.
- Claims the desk's checker lists must appear in the drafts.

*Development result on the final code (commit f8a8e08).* Unsupported claims were low for both arms: 1.0% for the model alone and 1.2% for Ruling. No advantage for Ruling on this metric is claimed from development data.

**4. 2026-10-24, before any held-out match has been generated.**

*Metric code completed.* The scoring code computed verdict accuracy, the unsupported-claim rate and the interval for the verdict difference, but not every metric this plan names. It now also computes, from the same per-incident records:
- the 95% interval of the unsupported-claim rate difference (paired bootstrap over incidents, 10,000 resamples, each rate recomputed on every resample), which the success test needs;
- planted-error detection. An arm flags an incident when its final decision differs from the on-field call. A planted error is an incident whose correct final decision differs from it. Precision and recall follow;
- cost per incident at the gpt-5-mini list price: $0.25 per million input tokens and $2.00 per million output tokens. The embedding calls for precedent are not counted;
- median and 90th-percentile time;
- every metric per category and for the contested subset. Until now only verdict accuracy had both.

The success test is computed from these intervals as written above.

*Desk changes since amendment 3.* All were made on development data and failure drills, while no held-out data existed:
- intake holds a check whose tracking misses a player the decision depends on;
- model calls have time limits (30 s for writing and 45 s for checking, per attempt), and each check has a 90-second deadline, after which only a holding line goes out;
- the checker's decision record states the on-field decision, what the VAR did and the final decision in words.

A held check keeps the verdict computed before it was held, so verdict accuracy is unaffected; its explanation is the holding line.

*Run conditions.* All four arms run on the held-out set in one run, at most 6 checks at a time, against the same Foundry deployment (gpt-5-mini, version 2025-08-07). The code is the commit recorded in the results file, the same code that runs the live demo.

*Hand check.* The 50-claim hand check is done by the AI coding assistant used to build Ruling (Claude Code), reading each claim against the evidence record, not by a person. Its agreement with the automated judge is reported as exactly that.

*Not pre-registered, reported as exploratory.* Azure AI Foundry's groundedness evaluator is run on the fan explanations of the model-only arm and the full desk, as an independent judge alongside our own claim audit.

*Categories not covered.* The generator does not produce serious foul play as a separate category (it is part of the possible red cards), mistaken identity, or the ball going out of play before a goal. Results are reported for the five categories in amendment 2 only.
