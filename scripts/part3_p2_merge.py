"""Merge sharded Protocol-2 partial JSONs into the final artifacts.

  synth:      part3_p2_merge.py synth  <out> <partial1> <partial2> ...
  slideaudit: part3_p2_merge.py sa     <out> <partial1> <partial2> ...

For synth, recomputes the linter-only / VLM-only / hybrid coverage over the union
of per-class cells (identical logic to part3_p2_eval.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.hybrid_critic import ROUTER, LINTER, LLM  # noqa: E402


def _routed_cell(d, cell):
    eng = ROUTER.get(d)
    if eng == LINTER:
        return cell.get("linter")
    if eng == LLM:
        return cell.get("llm")
    return cell.get("vlm_best") or cell.get("vlm_c0")


def merge_synth(out, parts):
    base = json.loads(Path(parts[0]).read_text())
    per_class = {}
    for p in parts:
        per_class.update(json.loads(Path(p).read_text()).get("per_class", {}))
    configs = {"linter_only": {}, "vlm_only": {}, "hybrid": {}}
    for d, cell in per_class.items():
        configs["linter_only"][d] = cell.get("linter")
        configs["vlm_only"][d] = cell.get("vlm_c0")
        configs["hybrid"][d] = _routed_cell(d, cell)

    def agg(cfg):
        cells = [c for c in cfg.values() if c]
        covered = [d for d, c in cfg.items() if c and c["bal_acc"] >= 0.70 and c["precision"] >= 0.70]
        return {"n_classes": len(cells),
                "mean_bal_acc": round(sum(c["bal_acc"] for c in cells) / len(cells), 3) if cells else None,
                "n_covered_0.70": len(covered), "covered_classes": covered}

    base["per_class"] = per_class
    base["config_per_class"] = configs
    base["coverage"] = {k: agg(v) for k, v in configs.items()}
    base["router"] = {d: ROUTER.get(d) for d in per_class}  # refresh to current routing
    base.pop("classes", None)
    Path(out).write_text(json.dumps(base, indent=2, ensure_ascii=False), encoding="utf-8")
    print("merged synth ->", out)
    print(json.dumps(base["coverage"], indent=2))


def merge_sa(out, parts):
    base = json.loads(Path(parts[0]).read_text())
    per_class = {}
    for p in parts:
        per_class.update(json.loads(Path(p).read_text()).get("per_class", {}))
    base["per_class"] = per_class
    Path(out).write_text(json.dumps(base, indent=2, ensure_ascii=False), encoding="utf-8")
    print("merged slideaudit ->", out, "classes:", list(per_class))


if __name__ == "__main__":
    mode, out, parts = sys.argv[1], sys.argv[2], sys.argv[3:]
    (merge_synth if mode == "synth" else merge_sa)(out, parts)
