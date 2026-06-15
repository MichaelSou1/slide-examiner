from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_analysis_report(summary: dict[str, Any], path: str | Path, *, title: str = "SlideProbe Report") -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", "", f"Record count: {summary.get('record_count', 0)}", ""]
    lines.append("## Attribution")
    for item in summary.get("attribution", []):
        lines.append(
            "- {defect} ({template}): perception={p:.3f}, reasoning={r:.3f}, image_success={s:.3f}, n={n}".format(
                defect=item["defect_type"],
                template=item.get("template_condition") or "unknown",
                p=item["perception_bottleneck_rate"],
                r=item["reasoning_bottleneck_rate"],
                s=item["image_success_rate"],
                n=item["n"],
            )
        )
    lines.extend(["", "## Metrics"])
    for item in summary.get("metrics", []):
        lines.append(
            "- {modality}/{task}/{defect}: acc={acc:.3f}, f1={f1:.3f}, n={n}".format(
                modality=item["modality"],
                task=item["task"],
                defect=item["defect_type"],
                acc=item["accuracy"],
                f1=item["f1"],
                n=item["n"],
            )
        )
    lines.extend(["", "## Oracle Gaps"])
    for item in summary.get("oracle_gaps", []):
        lines.append(
            "- {model}/{defect}/{template}: {right}-{left} accuracy gap={gap:.3f}".format(
                model=item.get("model") or "unknown",
                defect=item["defect_type"],
                template=item.get("template_condition") or "unknown",
                right=item["right_modality"],
                left=item["left_modality"],
                gap=item["gap"],
            )
        )
    lines.extend(["", "## Caption Oracle Gaps"])
    for item in summary.get("caption_oracle_gaps", []):
        lines.append(
            "- {model}/{defect}/{template}: B-Bprime accuracy gap={gap:.3f}".format(
                model=item.get("model") or "unknown",
                defect=item["defect_type"],
                template=item.get("template_condition") or "unknown",
                gap=item["gap"],
            )
        )
    lines.extend(["", "## Template Collapse"])
    for item in summary.get("template_collapse", []):
        lines.append(
            "- {model}/{modality}/{defect}: relative error reduction={reduction:.3f}".format(
                model=item.get("model") or "unknown",
                modality=item["modality"],
                defect=item["defect_type"],
                reduction=item["relative_error_reduction"],
            )
        )
    lines.extend(["", "## Variance Gates"])
    for item in summary.get("variance_gates", []):
        lines.append(
            "- {model}/{defect}/{template}: effect={effect:.3f}, 2sigma={threshold:.3f}, {decision}".format(
                model=item.get("model") or "unknown",
                defect=item["defect_type"],
                template=item.get("template_condition") or "unknown",
                effect=item["effect"],
                threshold=item["threshold"],
                decision=item["decision"],
            )
        )
    lines.extend(["", "## Repair Pass Rates"])
    for item in summary.get("repair_pass_rates", []):
        lines.append(
            "- {model}/{defect}/{template}: repair pass={rate:.3f}, n={n}".format(
                model=item.get("model") or "unknown",
                defect=item["defect_type"],
                template=item.get("template_condition") or "unknown",
                rate=item["repair_pass_rate"],
                n=item["n"],
            )
        )
    lines.extend(["", "## Raw Summary", "", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```"])
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
