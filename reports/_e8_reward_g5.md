# E8 Row 4 (freeform, n=40) — reward audit on internal-chromatic G5

Paired preference accuracy P(reward(clean)>reward(defective)); 0.5=blind. Freeform-only (template excluded).

| Reward model | category | G5 pref-acc [95% CI] | (G3 offset pref-acc) |
|---|---|---|---|
| docreward | document | 0.725 [0.572-0.839] (n=40) | 0.450 |
| pickscore | general_mm | 0.700 [0.546-0.819] (n=40) | 0.425 |
| skywork-vl | general_mm | 0.575 [0.422-0.715] (n=40) | 0.525 |
| aesthetic | aesthetic | 0.775 [0.625-0.877] (n=40) | 0.525 |
| clip-iqa | aesthetic | 0.650 [0.495-0.779] (n=40) | 0.525 |

**Summary:** 5 scorers, G5 range 0.575-0.775, mean 0.685. All weakly>chance (chromatic = low-level signal every CLIP-based reward partly sees; no clean narrow-vs-general split). G3-offset column <0.5 = rewards BLIND to fine alignment (mildly prefer the offset) -> supports linter-routes-G3.
