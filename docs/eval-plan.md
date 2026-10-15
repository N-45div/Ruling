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

None yet.
