# R5 G7 prevalence

Date: 2026-06-25

## AutoPresent slice

- Input: `data/part3/g7_autopresent/`
- Generation summary: `reports/part3/g7_autopresent_generation.json`
- Prevalence output: `reports/part3/g7_autopresent_prevalence.jsonl`
- Result: 14/20 decks generated; 8/14 generated decks had at least one G7 hit.
- Box-level incidence: 20/50 legal boxes = 40.0%.
- Hard G7: 4/50 legal boxes = 8.0%.

## Zenodo10K slice

- Input: `/home/gpus/datasets/zenodo10k/pptx`
- Prevalence output: `reports/part3/g7_zenodo93_prevalence.jsonl`
- Result: 81/93 scanned decks had at least one G7 hit.
- Box-level incidence: 857/3167 legal boxes = 27.1%.
- Hard G7: 495/3167 legal boxes = 15.6%.
- Scope note: this is a 93-deck slice. The earlier intended 298-deck scan did not materialize as a 298-deck
  artifact, so the paper reports the 93-deck result.

## PPTAgent smoke

- Input: `data/part3/tasks/test.jsonl` task `p3_05_full_proposal_v1`.
- Driver: `scripts/part3_g7_gen_pptagent.py`.
- Output: `data/part3/g7_pptagent/pptagent_000_p3_05_full_proposal_v1.pptx`.
- Generation summary: `reports/part3/g7_pptagent_smoke2.json`.
- Prevalence output: `reports/part3/g7_pptagent_prevalence.jsonl`.
- Smoke result: 1/1 deck generated; detector found 1/3 legal boxes with G7 hit (1 hard G7).

## Notes

- AutoPresent and PPTAgent both use mimo-compatible OpenAI endpoints.
- PPTAgent smoke used `mimo-v2.5-pro` for text and `mimo-v2.5` for vision.
- The R5 paper sentence uses the full G7 rate (all rendered containment overflow); the hard-G7 split is retained here as a conservative subset.
