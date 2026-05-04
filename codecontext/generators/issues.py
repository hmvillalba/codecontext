"""CI issues generator - outputs issues.json compatible with GitHub Actions, GitLab CI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from codecontext.models import ProjectIndex, Risk


def generate_issues_json(index: ProjectIndex, output_path: Path, fail_on: str = "high"):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    issues = _build_issues(index)
    output_path.write_text(
        json.dumps(issues, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    severity_order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    fail_level = severity_order.get(fail_on, 1)

    critical_count = sum(1 for i in issues["issues"] if severity_order.get(i["severity"], 3) <= fail_level)

    return {
        "total_issues": len(issues["issues"]),
        "blocking_issues": critical_count,
        "should_fail": critical_count > 0,
        "path": str(output_path),
    }


def _build_issues(index: ProjectIndex) -> dict:
    issues = []

    for risk in index.risks:
        issues.append({
            "rule_id": risk.category,
            "severity": risk.severity,
            "message": risk.message,
            "location": risk.location,
            "detail": risk.detail,
            "type": _classify_risk(risk.category),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": index.root_path,
        "total_files": len(index.files),
        "total_loc": sum(f.lines_of_code for f in index.files),
        "issues_count": len(issues),
        "summary": {
            "critical": sum(1 for i in issues if i["severity"] == "critical"),
            "high": sum(1 for i in issues if i["severity"] == "high"),
            "warning": sum(1 for i in issues if i["severity"] == "warning"),
            "info": sum(1 for i in issues if i["severity"] == "info"),
        },
        "issues": issues,
    }


def _classify_risk(category: str) -> str:
    if "gap" in category:
        return "coverage"
    if category in ("god-class", "large-file", "duplicate-method"):
        return "quality"
    if category in ("unauthed-route", "missing-validation"):
        return "security"
    if category in ("missing-index",):
        return "performance"
    return "analysis"
