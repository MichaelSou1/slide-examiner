"""Build the Part 1 pilot base corpus.

Generates a handful of clean, multi-slide consulting/proposal decks via the
project's structured-content -> Deck IR generator. These clean decks are the
base inputs for `build_synthetic_manifest`, which injects the pilot defect
types (G1/G2/S1 page-level, S2 deck-level) on top of them with controlled
severities.

Output: one Deck IR JSON per deck under data/pilot/decks/.
"""

from __future__ import annotations

import json
from pathlib import Path

from slide_examiner.generator import deck_from_content_json
from slide_examiner.ingest import save_deck_json

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "pilot" / "decks"

# Each deck is a coherent narrative: a fixed logical section order so that a
# narrative-order swap (S2) is a genuine defect, and real title/body text so
# title-body mismatch (S1) and text overflow (G1) have meaningful targets.
DECKS: list[dict] = [
    {
        "deck_id": "pilot_cloud_migration",
        "scenario": "full_proposal",
        "required_sections": ["context", "approach", "plan", "validation", "ask"],
        "slides": [
            {"section": "context", "title": "Why migrate to the cloud now",
             "bullets": ["On-prem capacity is saturated at peak hours",
                         "Hardware refresh is due within two quarters",
                         "Competitors already ship features weekly"]},
            {"section": "approach", "title": "A phased lift-and-shift approach",
             "bullets": ["Phase 1 rehost stateless services",
                         "Phase 2 replatform the data tier",
                         "Phase 3 refactor the billing monolith"]},
            {"section": "plan", "title": "Twelve-month delivery roadmap",
             "bullets": ["Q1 landing zone and networking",
                         "Q2 first production workloads",
                         "Q3 data migration and cutover"]},
            {"section": "validation", "title": "How we validate each cutover",
             "bullets": ["Shadow traffic before switching",
                         "Automated rollback within five minutes",
                         "Cost and latency dashboards per service"]},
            {"section": "ask", "title": "What we need to proceed",
             "bullets": ["Approve the phase 1 budget",
                         "Assign two platform engineers",
                         "Confirm the cutover freeze window"]},
        ],
    },
    {
        "deck_id": "pilot_retail_analytics",
        "scenario": "full_proposal",
        "required_sections": ["problem", "solution", "evidence", "rollout", "next"],
        "slides": [
            {"section": "problem", "title": "Store managers fly blind on stock",
             "bullets": ["Stockouts cost an estimated 4% of revenue",
                         "Replenishment is still a weekly spreadsheet",
                         "No store-level demand signal exists today"]},
            {"section": "solution", "title": "A demand-sensing analytics layer",
             "bullets": ["Ingest point-of-sale streams hourly",
                         "Forecast per SKU and per store",
                         "Push reorder nudges to the floor app"]},
            {"section": "evidence", "title": "Pilot stores beat the baseline",
             "bullets": ["Stockouts dropped 31% over eight weeks",
                         "Forecast error fell below 12% MAPE",
                         "Managers adopted the nudges daily"]},
            {"section": "rollout", "title": "Scaling to the full fleet",
             "bullets": ["Region-by-region in four waves",
                         "Train one champion per district",
                         "Integrate with the existing ERP"]},
            {"section": "next", "title": "Decisions for this quarter",
             "bullets": ["Fund the data pipeline build",
                         "Pick the first three rollout regions",
                         "Set the success metric thresholds"]},
        ],
    },
    {
        "deck_id": "pilot_security_program",
        "scenario": "full_proposal",
        "required_sections": ["risk", "strategy", "controls", "metrics", "investment"],
        "slides": [
            {"section": "risk", "title": "Our exposure is growing fast",
             "bullets": ["Phishing attempts up 60% year over year",
                         "Three near-miss incidents last quarter",
                         "Audit flagged stale access reviews"]},
            {"section": "strategy", "title": "A zero-trust security strategy",
             "bullets": ["Verify every request explicitly",
                         "Grant least-privilege access by default",
                         "Assume breach and segment blast radius"]},
            {"section": "controls", "title": "The controls we will deploy",
             "bullets": ["Hardware-backed multi-factor auth",
                         "Continuous device posture checks",
                         "Just-in-time privileged access"]},
            {"section": "metrics", "title": "How we measure security health",
             "bullets": ["Mean time to detect and respond",
                         "Coverage of MFA across the fleet",
                         "Percentage of access reviewed monthly"]},
            {"section": "investment", "title": "The investment we are requesting",
             "bullets": ["Two-year tooling and licensing budget",
                         "Three dedicated security engineers",
                         "Executive sponsorship for the rollout"]},
        ],
    },
    {
        "deck_id": "pilot_product_launch",
        "scenario": "launch",
        "required_sections": ["market", "product", "gtm", "metrics", "timeline"],
        "slides": [
            {"section": "market", "title": "The market opportunity is real",
             "bullets": ["Buyers want self-serve onboarding",
                         "Incumbents are slow and enterprise-only",
                         "A mid-market gap is wide open"]},
            {"section": "product", "title": "What we are launching",
             "bullets": ["A guided setup in under ten minutes",
                         "Usage-based pricing with a free tier",
                         "Native integrations with top tools"]},
            {"section": "gtm", "title": "Our go-to-market motion",
             "bullets": ["Product-led growth as the front door",
                         "Inside sales for expansion accounts",
                         "Community and content for awareness"]},
            {"section": "metrics", "title": "Launch success metrics",
             "bullets": ["Activation rate within first session",
                         "Week-four retention above forty percent",
                         "Payback period under twelve months"]},
            {"section": "timeline", "title": "Path to general availability",
             "bullets": ["Closed beta in four weeks",
                         "Open beta two weeks later",
                         "General availability end of quarter"]},
        ],
    },
    {
        "deck_id": "pilot_ops_efficiency",
        "scenario": "client_intro",
        "required_sections": ["baseline", "diagnosis", "levers", "impact", "plan"],
        "slides": [
            {"section": "baseline", "title": "Where operating cost sits today",
             "bullets": ["Logistics is the largest single line",
                         "Overtime spikes every month end",
                         "Manual handoffs slow every order"]},
            {"section": "diagnosis", "title": "Root causes behind the cost",
             "bullets": ["Routes are planned by hand",
                         "Inventory sits in the wrong nodes",
                         "Systems do not talk to each other"]},
            {"section": "levers", "title": "Three levers to pull",
             "bullets": ["Automate route optimization",
                         "Rebalance inventory placement",
                         "Connect the order and warehouse systems"]},
            {"section": "impact", "title": "Expected impact of the levers",
             "bullets": ["Eight to twelve percent cost reduction",
                         "Order cycle time cut by a third",
                         "Overtime normalized across the month"]},
            {"section": "plan", "title": "A pragmatic ninety-day plan",
             "bullets": ["Stand up the routing pilot first",
                         "Run an inventory rebalancing sprint",
                         "Sequence the systems integration"]},
        ],
    },
    {
        "deck_id": "pilot_data_platform",
        "scenario": "full_proposal",
        "required_sections": ["pain", "vision", "architecture", "governance", "roadmap"],
        "slides": [
            {"section": "pain", "title": "Data is trapped in silos",
             "bullets": ["Every team rebuilds the same metrics",
                         "Reports disagree across departments",
                         "Analysts spend days just finding data"]},
            {"section": "vision", "title": "One trusted data platform",
             "bullets": ["A single governed source of truth",
                         "Self-serve analytics for every team",
                         "Reusable, certified metric definitions"]},
            {"section": "architecture", "title": "The platform architecture",
             "bullets": ["Streaming and batch ingestion",
                         "A central lakehouse storage layer",
                         "A semantic layer over the warehouse"]},
            {"section": "governance", "title": "Governance and trust",
             "bullets": ["Clear ownership for every dataset",
                         "Automated data quality checks",
                         "Lineage tracked end to end"]},
            {"section": "roadmap", "title": "Delivery roadmap",
             "bullets": ["Foundation and ingestion first",
                         "Then the semantic and metrics layer",
                         "Finally self-serve enablement"]},
        ],
    },
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for content in DECKS:
        deck = deck_from_content_json(content)
        path = OUT_DIR / f"{deck.deck_id}.json"
        save_deck_json(deck, path)
        written.append((deck.deck_id, len(deck.slides), str(path)))
    print(json.dumps({"decks": written, "out_dir": str(OUT_DIR)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
