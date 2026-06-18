"""Build the Part 2 base corpus: ~28 clean business decks (~140 slides).

Wider than the 12-deck Part 1 corpus so the *semantic* training track (S1/S2/
S4/S5) sees enough distinct titles/bodies/sections to learn from instead of
re-rendering the same handful of slides. Same shape as part1_build_corpus.py:
each deck carries a recurring term, required_sections (for S5) and a glossary.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from slide_examiner.generator import deck_from_content_json
from slide_examiner.ingest import save_deck_json

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "part2" / "decks"

# (name, scenario, term, sections, [titles...])
THEMES = [
    ("cloud_migration", "full_proposal", "the Platform", ["context", "approach", "plan", "validation", "ask"],
     ["Why the Platform must move now", "A phased migration approach", "Twelve-month delivery roadmap",
      "How we validate each cutover", "What we need to proceed"]),
    ("retail_analytics", "full_proposal", "DemandSense", ["problem", "solution", "evidence", "rollout", "next"],
     ["Stores fly blind on stock", "DemandSense senses demand hourly", "DemandSense beat the baseline",
      "Scaling DemandSense to the fleet", "Decisions for this quarter"]),
    ("security_program", "full_proposal", "ZeroTrust", ["risk", "strategy", "controls", "metrics", "investment"],
     ["Our exposure is growing fast", "A ZeroTrust strategy", "The ZeroTrust controls we deploy",
      "How we measure ZeroTrust health", "The investment we request"]),
    ("product_launch", "launch", "Onboard", ["market", "product", "gtm", "metrics", "timeline"],
     ["The market opportunity is real", "Onboard launches self-serve setup", "Our go-to-market motion for Onboard",
      "Onboard launch success metrics", "Path to general availability"]),
    ("ops_efficiency", "client_intro", "RouteOpt", ["baseline", "diagnosis", "levers", "impact", "plan"],
     ["Where operating cost sits today", "Root causes behind the cost", "RouteOpt is the first lever",
      "Expected impact of RouteOpt", "A pragmatic ninety-day plan"]),
    ("data_platform", "full_proposal", "Lakehouse", ["pain", "vision", "architecture", "governance", "roadmap"],
     ["Data is trapped in silos", "One trusted Lakehouse", "The Lakehouse architecture",
      "Lakehouse governance and trust", "Lakehouse delivery roadmap"]),
    ("payments_modernization", "full_proposal", "PayCore", ["context", "gaps", "design", "risks", "ask"],
     ["Legacy payments are fragile", "Gaps in the current stack", "The PayCore design",
      "PayCore risks and mitigations", "What PayCore needs to launch"]),
    ("customer_support_ai", "client_intro", "HelpBot", ["problem", "approach", "pilot", "scale", "next"],
     ["Support queues keep growing", "HelpBot deflects routine tickets", "HelpBot pilot results",
      "Scaling HelpBot safely", "Next steps for HelpBot"]),
    ("supply_chain", "full_proposal", "FlowNet", ["context", "diagnosis", "solution", "impact", "plan"],
     ["Supply shocks hit margins", "Why FlowNet visibility is missing", "FlowNet connects the network",
      "FlowNet impact on service levels", "FlowNet rollout plan"]),
    ("marketing_attribution", "full_proposal", "Attrib", ["problem", "method", "evidence", "rollout", "ask"],
     ["Spend is hard to attribute", "How Attrib models touchpoints", "Attrib evidence from the pilot",
      "Rolling Attrib out by channel", "What Attrib needs next"]),
    ("hr_analytics", "client_intro", "PeoplePulse", ["context", "insight", "action", "impact", "plan"],
     ["Attrition is rising quietly", "PeoplePulse surfaces early signals", "Actions PeoplePulse recommends",
      "Impact PeoplePulse can drive", "PeoplePulse rollout plan"]),
    ("fraud_detection", "full_proposal", "GuardML", ["risk", "approach", "model", "metrics", "investment"],
     ["Fraud losses are climbing", "GuardML scores every transaction", "Inside the GuardML model",
      "GuardML detection metrics", "The GuardML investment ask"]),
    # --- new Part 2 themes ---
    ("inventory_optimization", "full_proposal", "StockIQ", ["problem", "approach", "evidence", "rollout", "ask"],
     ["Stockouts erode loyalty", "StockIQ rebalances inventory nightly", "StockIQ cut stockouts in the pilot",
      "Expanding StockIQ to all regions", "Funding the StockIQ rollout"]),
    ("clinical_triage", "client_intro", "TriageAI", ["context", "diagnosis", "solution", "impact", "plan"],
     ["ER wait times keep rising", "Why triage is the bottleneck", "TriageAI prioritizes acuity",
      "TriageAI impact on wait times", "A safe TriageAI pilot plan"]),
    ("energy_forecasting", "full_proposal", "GridCast", ["pain", "vision", "method", "validation", "roadmap"],
     ["Demand spikes strain the grid", "GridCast forecasts load early", "How GridCast models weather",
      "Validating GridCast against history", "The GridCast deployment roadmap"]),
    ("contract_review", "client_intro", "ClauseScan", ["problem", "approach", "pilot", "scale", "next"],
     ["Manual contract review is slow", "ClauseScan flags risky clauses", "ClauseScan pilot accuracy",
      "Scaling ClauseScan to legal", "Next steps for ClauseScan"]),
    ("warehouse_robotics", "full_proposal", "PickBot", ["baseline", "diagnosis", "levers", "impact", "plan"],
     ["Pick rates have plateaued", "Where manual picking stalls", "PickBot automates the long aisles",
      "Expected PickBot throughput gains", "A staged PickBot deployment"]),
    ("churn_prediction", "full_proposal", "RetainML", ["problem", "method", "evidence", "rollout", "ask"],
     ["Churn is quietly compounding", "How RetainML predicts churn", "RetainML lift over the baseline",
      "Rolling RetainML into CRM", "What RetainML needs to ship"]),
    ("doc_search", "client_intro", "FindFast", ["context", "insight", "action", "impact", "plan"],
     ["Teams cannot find documents", "FindFast indexes everything", "What FindFast changes day to day",
      "Impact FindFast drives on time saved", "The FindFast rollout plan"]),
    ("pricing_optimization", "full_proposal", "PriceWise", ["problem", "solution", "evidence", "rollout", "next"],
     ["Pricing leaves margin behind", "PriceWise optimizes per segment", "PriceWise results from the test",
      "Scaling PriceWise across SKUs", "Decisions for pricing this quarter"]),
    ("network_observability", "full_proposal", "TraceGrid", ["pain", "vision", "architecture", "governance", "roadmap"],
     ["Outages are hard to diagnose", "One pane with TraceGrid", "The TraceGrid architecture",
      "TraceGrid data governance", "The TraceGrid roadmap"]),
    ("field_service", "client_intro", "DispatchPro", ["baseline", "diagnosis", "levers", "impact", "plan"],
     ["Technician time is wasted", "Root causes of idle time", "DispatchPro routes smarter",
      "Impact DispatchPro can deliver", "A ninety-day DispatchPro plan"]),
    ("knowledge_assistant", "full_proposal", "SageDesk", ["problem", "approach", "pilot", "scale", "ask"],
     ["Agents repeat the same lookups", "SageDesk answers from the wiki", "SageDesk pilot deflection",
      "Scaling SageDesk to all teams", "What SageDesk needs next"]),
    ("quality_inspection", "full_proposal", "VisionQC", ["problem", "method", "evidence", "rollout", "ask"],
     ["Defects slip past manual QC", "VisionQC inspects every unit", "VisionQC catch-rate evidence",
      "Rolling VisionQC down the line", "Funding the VisionQC rollout"]),
    ("loan_underwriting", "full_proposal", "CreditLens", ["risk", "approach", "model", "metrics", "investment"],
     ["Underwriting is inconsistent", "CreditLens standardizes scoring", "Inside the CreditLens model",
      "CreditLens approval metrics", "The CreditLens investment ask"]),
    ("logistics_visibility", "client_intro", "ShipEye", ["context", "diagnosis", "solution", "impact", "plan"],
     ["Shipments go dark in transit", "Why visibility breaks down", "ShipEye tracks every leg",
      "ShipEye impact on on-time delivery", "A pragmatic ShipEye plan"]),
    ("content_moderation", "full_proposal", "SafeGuard", ["risk", "strategy", "controls", "metrics", "investment"],
     ["Harmful content slips through", "A SafeGuard moderation strategy", "The SafeGuard control stack",
      "How we measure SafeGuard quality", "The SafeGuard investment we request"]),
    ("demand_planning", "full_proposal", "PlanSync", ["problem", "solution", "evidence", "rollout", "next"],
     ["Forecasts and supply diverge", "PlanSync aligns the plan", "PlanSync accuracy in the trial",
      "Scaling PlanSync across plants", "Decisions for planning this quarter"]),
]

BULLETS = [
    ["{t} is saturated at peak demand", "A refresh is due within two quarters", "Competitors already ship weekly"],
    ["Phase 1 stabilizes {t}", "Phase 2 replatforms the data tier", "Phase 3 refactors the core",
     "Phase 4 hardens {t} for scale", "Phase 5 hands off to operations"],
    ["Q1 foundation for {t}", "Q2 first production workloads", "Q3 migration and cutover"],
    ["Shadow traffic before switching {t}", "Automated rollback within five minutes", "Cost and latency dashboards per service"],
    ["Approve the phase 1 budget for {t}", "Assign two platform engineers", "Confirm the cutover freeze window"],
    ["{t} reduces toil by a third", "Teams adopt {t} daily", "Payback under twelve months"],
    ["Current process is mostly manual", "{t} automates the repetitive work", "Error rates drop sharply"],
    ["The pilot covered three regions", "{t} beat the baseline by double digits", "Results held across segments"],
    ["{t} integrates with existing tools", "No data leaves the tenant", "Setup takes under a week"],
    ["Risks are tracked weekly", "{t} has a clear rollback path", "Compliance reviewed the design"],
    ["Adoption grew month over month", "{t} now handles most volume", "Support tickets fell steadily"],
    ["We need executive sponsorship", "{t} needs a small dedicated team", "A decision is needed this quarter"],
]


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for di, (name, scenario, term, sections, titles) in enumerate(THEMES):
        slides = []
        for si, title in enumerate(titles):
            bullets = [b.format(t=term) for b in BULLETS[(di + si) % len(BULLETS)]]
            slides.append({"title": title, "bullets": bullets, "section": sections[si % len(sections)]})
        content = {"deck_id": f"part2_{name}", "scenario": scenario, "required_sections": sections, "slides": slides}
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
    print(json.dumps({"decks": len(written), "slides": sum(n for _, n in written),
                      "out_dir": str(OUT_DIR)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
