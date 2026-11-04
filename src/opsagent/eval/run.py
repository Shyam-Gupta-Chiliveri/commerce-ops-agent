from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from opsagent.agent.copilot import review_ticket
from opsagent.fixture_io import load_json
from opsagent.settings import Settings


@dataclass
class EvalReport:
    drafter: str
    passed: int
    total: int
    violations: int
    checks_passed: int
    checks_total: int
    mean_latency_ms: float
    cost_eur: float
    failures: list[str] = field(default_factory=list)


def evaluate(db_path: Path, settings: Settings, drafter: str) -> EvalReport:
    cases = load_json("eval_cases.json")
    failures: list[str] = []
    passed = 0
    violations = 0
    checks_passed = 0
    checks_total = 0
    latency = 0.0
    cost = 0.0
    for case in cases:
        result = review_ticket(db_path, case["ticket_id"], settings, drafter=drafter)
        latency += result.latency_ms
        cost += result.cost_eur
        case_ok = True
        checks = [("intent", result.intent == case["expect_intent"], result.intent)]
        checks.append(("actions", result.actions == case["expect_actions"], ",".join(result.actions)))
        for needle in case["must_include"]:
            checks.append((f"include {needle}", needle in result.reply_de, ""))
        for needle in case["must_not_include"]:
            hit = needle in result.reply_de
            checks.append((f"exclude {needle}", not hit, ""))
            if hit:
                violations += 1
        checks.append(("critic", result.critic == [], ",".join(result.critic)))
        if result.critic:
            violations += len(result.critic)
        if result.executed_writes:
            checks.append(("no writes", False, ",".join(result.executed_writes)))
            violations += 1
        else:
            checks.append(("no writes", True, ""))
        for name, ok, detail in checks:
            checks_total += 1
            if ok:
                checks_passed += 1
            else:
                case_ok = False
                failures.append(f"{case['ticket_id']} {name} {detail}".rstrip())
        if case_ok:
            passed += 1
    total = len(cases)
    return EvalReport(
        drafter=drafter,
        passed=passed,
        total=total,
        violations=violations,
        checks_passed=checks_passed,
        checks_total=checks_total,
        mean_latency_ms=latency / total if total else 0.0,
        cost_eur=cost,
        failures=failures,
    )


def format_eval(report: EvalReport) -> str:
    lines = [
        f"{report.drafter}: {report.passed}/{report.total} tickets, "
        f"{report.checks_passed}/{report.checks_total} checks, "
        f"{report.violations} policy violations, "
        f"{report.mean_latency_ms:.1f} ms mean, model cost EUR {report.cost_eur:.4f}",
    ]
    for failure in report.failures:
        lines.append(f"  - {failure}")
    return "\n".join(lines)


def write_eval_json(path: Path, reports: list[EvalReport]) -> None:
    payload = [
        {
            "drafter": report.drafter,
            "passed": report.passed,
            "total": report.total,
            "violations": report.violations,
            "checks_passed": report.checks_passed,
            "checks_total": report.checks_total,
            "mean_latency_ms": round(report.mean_latency_ms, 3),
            "cost_eur": report.cost_eur,
            "failures": report.failures,
        }
        for report in reports
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
