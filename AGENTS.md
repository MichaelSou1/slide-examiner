# Project Memory

This repository tracks the Slide-Examiner research implementation against
`specs/SPEC_slide_examiner_attribution.md` and
`specs/EXAMINER_IO_CONTRACT.md`.

## Communication

- 用中文与用户交互（回复、说明、总结一律用中文）。

## Artifact Versioning

- 所有训练报告、评测报告和运行日志都必须加入 Git 追踪，不得仅保留在本地或远端机器上。
- 生成上述产物时，应将报告写入 `reports/`，将日志写入 `runs/` 或 `logs/` 下，并在同一任务中执行 `git add`；不得因其属于实验产物而忽略。
- 模型权重、检查点、渲染图片及其他大体积中间产物不受此规则影响，仍按 `.gitignore` 和外部归档约定处理。

## Remote Downloads

- 在 `huirui` 下载模型、数据集或 Python 包前，必须先确认本机代理
  `http://127.0.0.1:7890` 正在监听，并同时导出 `http_proxy`、
  `https_proxy`、`HTTP_PROXY`、`HTTPS_PROXY`；否则下载会非常慢。
- 下载前可用 `ss -lntp | grep 7890` 和带代理的 `curl` 做连通性检查。

## TODO Maintenance

- Treat `specs/todo.md` as the project-level execution checklist.
- When a task is completed, update its checkbox from `[ ]` to `[x]` in the same
  change or immediately after verification.
- When a task changes scope, split, rename, reorder, or rewrite the TODO item so
  the file stays faithful to the current plan.
- When a task is blocked, leave it unchecked and add a short blocker note with a
  date or artifact path when useful.
- Do not mark empirical research tasks complete unless the corresponding output
  artifact exists, such as a manifest, rendered image set, run JSONL, analysis
  summary, trained checkpoint, report, or panel file.
- Before starting substantial work, skim `specs/todo.md`; before finishing, check
  whether any TODO state needs updating.


## LaTex Suite Availability

- The LaTeX toolchain is available in the conda environment named "tex".