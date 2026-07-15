## Elicitation cost / compute per slide

Token counts are per probed slide (paired-clean: a slide and its clean twin each count once). Estimated latency = completion_tokens / 40 tok·s⁻¹ + 1.2 s × calls (single-stream; concurrency hides most of it). `calls/slide` makes the compute budget explicit — C3 and the single-call C0 variants spend one call; **C0_rep** spends K (the deployed router's per-slide atomic-question count), so if C3 matches or beats C0_rep the recovery is not a test-time-compute effect.

| Model | Tag | Cond | calls/slide | input tok/slide | output tok/slide | total tok/slide | est. latency (s) |
|---|---|---|---|---|---|---|---|
| gemini-2.5-flash | G1 | C0 | 1 | 2370.4 | 59.4 | 2429.8 | 2.68 |
| gemini-2.5-flash | G1 | C0_full | 1 | 2907.4 | 75.8 | 2983.2 | 3.09 |
| gemini-2.5-flash | G1 | C0_rep | 10 | 23704 | 698 | 24402 | 29.45 |
| gemini-2.5-flash | G1 | C3 | 1 | 2001 | 29.2 | 2030.2 | 1.93 |
| gemini-2.5-flash | G7 | C0 | 1 | 2371.7 | 156.9 | 2528.6 | 5.12 |
| gemini-2.5-flash | G7 | C0_full | 1 | 2908.7 | 130.5 | 3039.2 | 4.46 |
| gemini-2.5-flash | G7 | C0_rep | 10 | 23716.7 | 1531.1 | 25247.8 | 50.28 |
| gemini-2.5-flash | G7 | C3 | 1 | 2024 | 37.5 | 2061.5 | 2.14 |
| gpt-5.1-nothinking | G1 | C0 | 1 | 1436.6 | 24.6 | 1461.2 | 1.81 |
| gpt-5.1-nothinking | G1 | C0_full | 1 | 1932.5 | 23 | 1955.5 | 1.77 |
| gpt-5.1-nothinking | G1 | C0_rep | 7.45 | 10702.3 | 188.3 | 10890.6 | 13.65 |
| gpt-5.1-nothinking | G1 | C3 | 1 | 1103 | 36.9 | 1139.9 | 2.12 |
| gpt-5.1-nothinking | G7 | C0 | 1 | 1435 | 45.9 | 1480.9 | 2.35 |
| gpt-5.1-nothinking | G7 | C0_full | 1 | 1931 | 61.5 | 1992.5 | 2.74 |
| gpt-5.1-nothinking | G7 | C0_rep | 8.544 | 12261.5 | 348.4 | 12609.9 | 18.96 |
| gpt-5.1-nothinking | G7 | C3 | 1 | 1123 | 40.5 | 1163.5 | 2.21 |
| qwen3-vl-plus | G1 | C0 | 1 | 2570.6 | 63.1 | 2633.7 | 2.78 |
| qwen3-vl-plus | G1 | C0_full | 1 | 3061.5 | 50.1 | 3111.6 | 2.45 |
| qwen3-vl-plus | G1 | C0_rep | 7.463 | 19182.8 | 373.7 | 19556.5 | 18.3 |
| qwen3-vl-plus | G1 | C3 | 1 | 2238 | 28 | 2266 | 1.9 |
| qwen3-vl-plus | G7 | C0 | 1 | 1411 | 121.6 | 1532.6 | 4.24 |
| qwen3-vl-plus | G7 | C0_full | 1 | 1902 | 134.6 | 2036.6 | 4.56 |
| qwen3-vl-plus | G7 | C0_rep | 8.372 | 11813.6 | 1083.6 | 12897.2 | 37.14 |
| qwen3-vl-plus | G7 | C3 | 1 | 1098 | 34.7 | 1132.7 | 2.07 |

### Compute multiplier (C0_rep vs C0)

| Model | Tag | C0 output tok | C0_rep output tok | C3 output tok | C0_rep/C0 calls | C3/C0 output |
|---|---|---|---|---|---|---|
| gemini-2.5-flash | G1 | 59.4 | 698 | 29.2 | 10.0× | 0.49 |
| gemini-2.5-flash | G7 | 156.9 | 1531.1 | 37.5 | 10.0× | 0.24 |
| gpt-5.1-nothinking | G1 | 24.6 | 188.3 | 36.9 | 7.5× | 1.5 |
| gpt-5.1-nothinking | G7 | 45.9 | 348.4 | 40.5 | 8.5× | 0.88 |
| qwen3-vl-plus | G1 | 63.1 | 373.7 | 28 | 7.5× | 0.44 |
| qwen3-vl-plus | G7 | 121.6 | 1083.6 | 34.7 | 8.4× | 0.29 |

> 64 run(s) predate the usage log and are omitted (AFC×12, AFC_clean×12, C0×12, C0_named×12, C0plus×4, C3×12); re-run a slice with `--resume` to top up their token counts.

