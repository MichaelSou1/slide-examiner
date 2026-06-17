"""Build the expanded Part 1 base corpus (12 clean decks).

Richer than the 6-deck pilot corpus: 12 decks with varied slide counts and
bullet density (better G3-G6 / S4 targets), a recurring glossary term per deck
written into the body text and recorded in deck metadata (so S3 terminology
injection actually has something to swap), and explicit required_sections (so
S5 missing-section injection is meaningful).
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from slide_examiner.generator import deck_from_content_json
from slide_examiner.ingest import save_deck_json

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "part1" / "decks"

# (deck_id, scenario, term, sections, [(title, [bullets])...]) -- term recurs in
# the body so terminology injection can swap it; sections drive S5.
THEMES = [
    ("cloud_migration", "full_proposal", "the Platform",
     ["context", "approach", "plan", "validation", "ask"],
     ["Why the Platform must move now", "A phased migration approach",
      "Twelve-month delivery roadmap", "How we validate each cutover", "What we need to proceed"]),
    ("retail_analytics", "full_proposal", "DemandSense",
     ["problem", "solution", "evidence", "rollout", "next"],
     ["Stores fly blind on stock", "DemandSense senses demand hourly",
      "DemandSense beat the baseline", "Scaling DemandSense to the fleet", "Decisions for this quarter"]),
    ("security_program", "full_proposal", "ZeroTrust",
     ["risk", "strategy", "controls", "metrics", "investment"],
     ["Our exposure is growing fast", "A ZeroTrust strategy",
      "The ZeroTrust controls we deploy", "How we measure ZeroTrust health", "The investment we request"]),
    ("product_launch", "launch", "Onboard",
     ["market", "product", "gtm", "metrics", "timeline"],
     ["The market opportunity is real", "Onboard launches self-serve setup",
      "Our go-to-market motion for Onboard", "Onboard launch success metrics", "Path to general availability"]),
    ("ops_efficiency", "client_intro", "RouteOpt",
     ["baseline", "diagnosis", "levers", "impact", "plan"],
     ["Where operating cost sits today", "Root causes behind the cost",
      "RouteOpt is the first lever", "Expected impact of RouteOpt", "A pragmatic ninety-day plan"]),
    ("data_platform", "full_proposal", "Lakehouse",
     ["pain", "vision", "architecture", "governance", "roadmap"],
     ["Data is trapped in silos", "One trusted Lakehouse",
      "The Lakehouse architecture", "Lakehouse governance and trust", "Lakehouse delivery roadmap"]),
    ("payments_modernization", "full_proposal", "PayCore",
     ["context", "gaps", "design", "risks", "ask"],
     ["Legacy payments are fragile", "Gaps in the current stack",
      "The PayCore design", "PayCore risks and mitigations", "What PayCore needs to launch"]),
    ("customer_support_ai", "client_intro", "HelpBot",
     ["problem", "approach", "pilot", "scale", "next"],
     ["Support queues keep growing", "HelpBot deflects routine tickets",
      "HelpBot pilot results", "Scaling HelpBot safely", "Next steps for HelpBot"]),
    ("supply_chain", "full_proposal", "FlowNet",
     ["context", "diagnosis", "solution", "impact", "plan"],
     ["Supply shocks hit margins", "Why FlowNet visibility is missing",
      "FlowNet connects the network", "FlowNet impact on service levels", "FlowNet rollout plan"]),
    ("marketing_attribution", "full_proposal", "Attrib",
     ["problem", "method", "evidence", "rollout", "ask"],
     ["Spend is hard to attribute", "How Attrib models touchpoints",
      "Attrib evidence from the pilot", "Rolling Attrib out by channel", "What Attrib needs next"]),
    ("hr_analytics", "client_intro", "PeoplePulse",
     ["context", "insight", "action", "impact", "plan"],
     ["Attrition is rising quietly", "PeoplePulse surfaces early signals",
      "Actions PeoplePulse recommends", "Impact PeoplePulse can drive", "PeoplePulse rollout plan"]),
    ("fraud_detection", "full_proposal", "GuardML",
     ["risk", "approach", "model", "metrics", "investment"],
     ["Fraud losses are climbing", "GuardML scores every transaction",
      "Inside the GuardML model", "GuardML detection metrics", "The GuardML investment ask"]),
]

# Bullet templates of varied length/density; index by slide to vary the deck.
BULLETS = [
    ["{t} is saturated at peak demand", "A refresh is due within two quarters", "Competitors already ship weekly"],
    ["Phase 1 stabilizes {t}", "Phase 2 replatforms the data tier", "Phase 3 refactors the core", "Phase 4 hardens {t} for scale", "Phase 5 hands off to operations"],
    ["Q1 foundation for {t}", "Q2 first production workloads", "Q3 migration and cutover"],
    ["Shadow traffic before switching {t}", "Automated rollback within five minutes", "Cost and latency dashboards per service"],
    ["Approve the phase 1 budget for {t}", "Assign two platform engineers", "Confirm the cutover freeze window"],
    ["{t} reduces toil by a third", "Teams adopt {t} daily", "Payback under twelve months"],
]


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for di, (name, scenario, term, sections, titles) in enumerate(THEMES):
        slides = []
        for si, title in enumerate(titles):
            bullets = [b.format(t=term) for b in BULLETS[(di + si) % len(BULLETS)]]
            slides.append({"title": title, "bullets": bullets, "section": sections[si % len(sections)]})
        content = {"deck_id": f"part1_{name}", "scenario": scenario, "required_sections": sections, "slides": slides}
        deck = deck_from_content_json(content)
        deck = replace(deck, metadata={
            **deck.metadata,
            "canonical_term": term,
            "variant_term": term + "X",
            "project_glossary": {term: [term + "X", term.lower()]},
        })
        path = OUT_DIR / f"{deck.deck_id}.json"
        save_deck_json(deck, path)
        written.append((deck.deck_id, len(deck.slides)))
    print(json.dumps({"decks": written, "out_dir": str(OUT_DIR), "count": len(written)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
