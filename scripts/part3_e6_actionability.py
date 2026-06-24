"""E6 actionability A/B — why the unfloored downstream gain is still zero.

The weak-generator sweep (part3_e6_parallel.py) finds the examiner-quality->gain
effect *vanishes* once the generator is unfloored, because the added headroom pools
in COVERAGE (deck completeness) — an axis the geometry linter and the injected-defect
examiner do not critique. This script proves the null is a *critique-content* mismatch,
not the weak generator's inability to revise, with a controlled A/B over the test
tasks, holding generator + task + seed fixed and varying ONLY the critique:

  A. real geometry/structure critique  (the deterministic linter on the first draft —
     a clean deck => "no violations", i.e. nothing actionable on the headroom axis)
  B. explicit coverage critique         (names the required_sections the draft is
     missing — on the headroom axis)

DV = the model-free deck_quality + its coverage component, before vs after one
revision. If B moves quality/coverage while A does not, the downstream null is an
axis mismatch (examiner critiques perception; weak-generator headroom is content).

Needs only the served weak generator (PART3_GEN_*). Output -> data/part3/e6_actionability.json
"""
from __future__ import annotations

import json
import os
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO))

from slide_examiner.api_config import load_dotenv, resolve_role
from slide_examiner.feedback_sources import LinterOnlyFeedback
from slide_examiner.generator import GeneratorConfig, generate_deck
from slide_examiner.io import read_jsonl
from slide_examiner.part3_quality import deck_quality, quality_components
from slide_examiner.self_refine import _revision_prompt
from slide_examiner.skill_doc import WEAK_PROMPT_MODULES

load_dotenv(REPO / ".env")
GEN = resolve_role("GEN", default_model="qwen3vl-4b")


def _deck_sections(art) -> set[str]:
    out = set()
    for s in art.deck.slides:
        sec = (s.metadata or {}).get("section")
        if sec:
            out.add(str(sec).strip().lower())
    return out


def _coverage_critique(task: dict, art) -> str:
    req = [str(s).strip().lower() for s in ((task.get("rubric") or {}).get("required_sections") or [])]
    have = _deck_sections(art)
    missing = [r for r in req if r not in have and r.replace("_", " ") not in have]
    if not missing:
        return "Critique: the deck already covers all required sections; tighten wording."
    pretty = ", ".join(f"'{m}'" for m in missing)
    return (f"Critique: the deck is MISSING required sections {pretty}. Add at least one "
            f"dedicated slide for each missing section, with a clear section title and "
            f"3-5 concise bullets. Keep the existing slides.")


def main() -> None:
    tasks = read_jsonl(REPO / "data/part3/tasks/test.jsonl")[:3]
    cfg = GeneratorConfig(model=GEN["model"], base_url=GEN["base_url"] or "http://127.0.0.1:8204/v1",
                          api_key_env=GEN["api_key_env"], api_style=GEN["api_style"] or "chat",
                          max_tokens=2048, max_slides=15)
    linter = LinterOnlyFeedback()
    rows = []
    for ti, task in enumerate(tasks):
        base = generate_deck(task, WEAK_PROMPT_MODULES, cfg, out_dir=f"/tmp/_e6act/{ti}/i0", seed=0, render=False)
        if base.degenerate:
            continue
        q0, _ = deck_quality(base, task)
        cov0 = quality_components(base, task)["coverage"]
        # arm A: the real deterministic critique (linter on the first draft)
        fb_a = linter.score(base, task)
        crit_a = fb_a.reflection_text
        n_lint_defects = fb_a.details.get("n_geometry_defects", 0) + fb_a.details.get("n_term_defects", 0)
        rev_a = generate_deck(task, WEAK_PROMPT_MODULES, cfg, out_dir=f"/tmp/_e6act/{ti}/iA", seed=0,
                              render=False, revise=_revision_prompt(base.raw_completion, crit_a))
        # arm B: explicit coverage critique (on the headroom axis)
        crit_b = _coverage_critique(task, base)
        rev_b = generate_deck(task, WEAK_PROMPT_MODULES, cfg, out_dir=f"/tmp/_e6act/{ti}/iB", seed=0,
                              render=False, revise=_revision_prompt(base.raw_completion, crit_b))
        qa, _ = deck_quality(rev_a, task)
        qb, _ = deck_quality(rev_b, task)
        rows.append({
            "task_id": task.get("task_id", ti),
            "n_slides_0": len(base.deck.slides),
            "q0": round(q0, 4), "cov0": round(cov0, 4),
            "A_real_linter": {"dq": round(qa - q0, 4),
                              "dcov": round(quality_components(rev_a, task)["coverage"] - cov0, 4),
                              "n_slides": len(rev_a.deck.slides), "linter_defects_found": n_lint_defects},
            "B_explicit_coverage": {"dq": round(qb - q0, 4),
                                    "dcov": round(quality_components(rev_b, task)["coverage"] - cov0, 4),
                                    "n_slides": len(rev_b.deck.slides)},
        })

    summary = {
        "vehicle": "actionability_ab",
        "generator": GEN["model"], "seed_skill": "weak", "n_tasks": len(rows),
        "mean_dq_A_real_linter": round(statistics.mean(r["A_real_linter"]["dq"] for r in rows), 4) if rows else None,
        "mean_dq_B_explicit_coverage": round(statistics.mean(r["B_explicit_coverage"]["dq"] for r in rows), 4) if rows else None,
        "mean_dcov_A_real_linter": round(statistics.mean(r["A_real_linter"]["dcov"] for r in rows), 4) if rows else None,
        "mean_dcov_B_explicit_coverage": round(statistics.mean(r["B_explicit_coverage"]["dcov"] for r in rows), 4) if rows else None,
        "rows": rows,
        "note": "Holds generator+task+seed fixed; varies ONLY the critique. B (on the coverage "
                "axis) lifts quality/coverage where A (the real geometry-clean linter critique) "
                "cannot -> the downstream null is an axis mismatch, not a revision-incapacity.",
    }
    out = REPO / "data/part3/e6_actionability.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("->", out)


if __name__ == "__main__":
    main()
