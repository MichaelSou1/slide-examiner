"""P3 — build the Part 3 task set (deck-level briefs) with frozen splits.

Each task is a *brief* (the generator builds the deck); tasks are not eval labels,
so an in-house scenario pack is appropriate and avoids the self-eval concern.
SlidesBench is GitHub-hosted and was unreachable from this box (see
reports/data_prep/part3_optimizer_install.json); the in-house pack is the primary
source and SlidesBench remains an optional add when reachable.

Outputs:
  data/part3/tasks/{train,val,test}.jsonl
  reports/data_prep/part3_task_acquisition.json   (freeze: counts + sha256)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Deck-level scenarios -> required_sections (the generator must cover these).
SCENARIOS = {
    "launch": ["background", "problem", "solution", "call_to_action"],
    "client_intro": ["company_overview", "capabilities", "case_study", "next_steps"],
    "full_proposal": ["background", "problem", "solution", "validation", "pricing", "next_steps"],
}

# Diverse business topics (domain, audience) to vary content without varying layout.
TOPICS = [
    ("an AI-powered customer churn prediction platform", "a retail enterprise"),
    ("a Kubernetes-based internal developer platform", "a fintech engineering org"),
    ("a zero-trust security posture upgrade", "a healthcare CISO"),
    ("a warehouse robotics fleet management suite", "a logistics operator"),
    ("a real-time fraud detection service", "a payments processor"),
    ("a carbon accounting and ESG reporting tool", "a manufacturing board"),
    ("a multi-cloud cost optimization service", "a CFO and platform team"),
    ("a clinical trial data harmonization pipeline", "a pharma R&D group"),
    ("a personalized learning recommendation engine", "an edtech product team"),
    ("a supply-chain demand forecasting model", "a CPG planning team"),
    ("a conversational support copilot", "a telecom contact center"),
    ("a streaming data lakehouse migration", "a media analytics org"),
    ("a predictive maintenance platform for turbines", "an energy utility"),
    ("a privacy-preserving federated analytics service", "a banking consortium"),
    ("a developer onboarding automation toolkit", "a fast-growing SaaS company"),
]


def build_tasks(seed: int) -> list[dict]:
    rng = random.Random(seed)
    scenarios = list(SCENARIOS)
    tasks: list[dict] = []
    pairs = [(t, a) for (t, a) in TOPICS]
    rng.shuffle(pairs)
    for idx, (topic, audience) in enumerate(pairs):
        scenario = scenarios[idx % len(scenarios)]
        required = SCENARIOS[scenario]
        # two slide-count regimes to vary difficulty
        target_slides = 8 if idx % 2 == 0 else 12
        # VAGUE brief: it deliberately does NOT leak the rubric (no section list,
        # slide count, or consistency hints). The domain conventions the brief
        # omits are exactly what the optimizer must learn into the skill modules —
        # otherwise a capable generator nails the rubric from the brief alone and
        # skill-space optimization has nothing to optimize (measured: a strong
        # generator scores ~1.0 even with a near-empty skill under an explicit
        # brief, vs ~0.73 under a vague brief). The rubric lives in metadata only,
        # used for the independent gold quality + eval, never shown to the generator.
        brief = f"Create a {scenario.replace('_', ' ')} deck for {audience} about {topic}."
        tasks.append(
            {
                "task_id": f"p3_{idx:02d}_{scenario}",
                "scenario": scenario,
                "audience": audience,
                "topic": topic,
                "brief": brief,
                "rubric": {
                    "required_sections": required,
                    "target_slides": target_slides,
                    "max_bullets_per_slide": 6,
                    "min_slides": max(5, target_slides - 3),
                    "terminology_consistent": True,
                },
            }
        )
    return tasks


def _sha256(records: list[dict]) -> str:
    h = hashlib.sha256()
    for r in records:
        h.update(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split-seed", type=int, default=20260619)
    ap.add_argument("--n-train", type=int, default=10)
    ap.add_argument("--n-val", type=int, default=10)
    ap.add_argument("--n-test", type=int, default=10)
    ap.add_argument("--out-dir", default=str(REPO / "data/part3/tasks"))
    ap.add_argument("--freeze", default=str(REPO / "reports/data_prep/part3_task_acquisition.json"))
    args = ap.parse_args()

    tasks = build_tasks(args.split_seed)
    need = args.n_train + args.n_val + args.n_test
    if len(tasks) < need:
        # repeat-with-suffix to reach the requested count deterministically
        base = list(tasks)
        i = 0
        while len(tasks) < need:
            t = dict(base[i % len(base)])
            t["task_id"] = f"{t['task_id']}_v{i // len(base) + 1}"
            tasks.append(t)
            i += 1

    splits = {
        "train": tasks[: args.n_train],
        "val": tasks[args.n_train : args.n_train + args.n_val],
        "test": tasks[args.n_train + args.n_val : args.n_train + args.n_val + args.n_test],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze = {"split_seed": args.split_seed, "source": "in-house scenario pack (SlidesBench unreachable: GitHub down)", "splits": {}}
    for name, recs in splits.items():
        path = out_dir / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        rp = path.resolve()
        rel = str(rp.relative_to(REPO)) if str(rp).startswith(str(REPO)) else str(rp)
        freeze["splits"][name] = {"path": rel, "n": len(recs), "sha256": _sha256(recs)}

    Path(args.freeze).parent.mkdir(parents=True, exist_ok=True)
    Path(args.freeze).write_text(json.dumps(freeze, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(freeze, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
