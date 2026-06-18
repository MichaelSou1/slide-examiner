# Part 1 — S3 routed out of the examiner: symbolic term-consistency linter

Head-to-head on the frozen S3 subset. The VLM (any size/channel/framing) tops out at ~0.69 balanced accuracy and forced-choice does not rescue it; the symbolic linter — extract terms → occurrence table → near-duplicate cluster, **no image** — is exact.

| detector | recall | specificity | balanced accuracy |
|---|---|---|---|
| **term_consistency linter** | 1.00 (8/8) | 1.00 (40/40) | **1.000** |
| 30B VLM, best channel (B′ pointwise) | — | — | 0.688 |
| 30B VLM, forced-choice (robust) | — | — | 0.25 |

- Negatives include the 24 clean deck controls **and** the S2/S5 deck defectives (must not trip S3): 0 false positives.
- Caveat: the synthetic injector uses a clean `…X`-suffix variant, so pure edit-distance clustering suffices. Real-world drift (`K8s`/`Kubernetes`/`kube`) is not edit-distance close — there the same occurrence table is handed to a text-LLM instead of the clusterer (`build_term_occurrences` is the shared input; `--glossary` supports the corporate-term-sheet variant).
- CLI: `python -m slide_examiner.cli lint-deck <deck.json> [--glossary T1 T2 ...]`.

