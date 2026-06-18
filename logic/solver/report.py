"""리포터(S6): CheckReport를 사람용 한국어 리포트 문자열로 변환한다.

순수 함수만 둔다 — 출력(IO)은 CLI(S7)의 책임이다.
리포트 원칙(CLAUDE.md §2.4, §10): 범인 룰과 깨지는 조건을 함께 제시하고,
unknown은 절대 숨기지 않는다.
"""

from __future__ import annotations

from logic.solver.checks import (
    BoundUnreachable,
    CheckReport,
    RangeViolation,
    UnmetExpectation,
    UnreachableState,
)


def format_report(report: CheckReport, rule_sources: dict[str, str] | None = None) -> str:
    """검사 결과를 한국어 리포트 문자열로 만든다.

    `rule_sources`(rule_id → 정의 파일명)가 주어지면 범인 룰을 `id (파일명)` 형식으로
    짚는다 — 디렉토리 병합 검사에서 어느 파일의 룰이 모순을 일으켰는지 드러내기 위함이다.
    """
    sources = rule_sources or {}
    lines: list[str] = []
    contradictions = (
        len(report.violations)
        + len(report.unreachable_states)
        + len(report.bound_unreachables)
        + len(report.unmet_expectations)
    )

    if contradictions == 0:
        lines.append("✅ 모순이 발견되지 않았습니다.")
    else:
        lines.append(f"❌ 모순 {contradictions}건이 발견되었습니다.")
        lines.append("")
        index = 1
        for ue in report.unreachable_states:
            lines.append(_format_unreachable(index, ue, sources))
            index += 1
        for v in report.violations:
            lines.append(_format_violation(index, v, sources))
            index += 1
        for bu in report.bound_unreachables:
            lines.append(_format_bound_unreachable(index, bu, sources))
            index += 1
        for um in report.unmet_expectations:
            lines.append(_format_unmet_expectation(index, um, sources))
            index += 1

    if report.unknowns:
        lines.append("")
        lines.append(f"⚠️ 판단 불가(unknown) {len(report.unknowns)}건 — 별도 확인이 필요합니다:")
        lines.extend(f"    - {u}" for u in report.unknowns)

    return "\n".join(lines)


def _format_assignment(assignment: dict[str, str]) -> str:
    if not assignment:
        return "모든 경우"
    return ", ".join(f"{name}={value}" for name, value in assignment.items())


def _format_culprit(rule_id: str, sources: dict[str, str]) -> str:
    """범인 룰을 `id (파일명)` 형식으로 짚는다. 파일명을 모르면 id만 출력한다."""
    source = sources.get(rule_id)
    return f"{rule_id} ({source})" if source else rule_id


def _format_culprits(culprit_rules: tuple[str, ...], sources: dict[str, str]) -> str:
    if not culprit_rules:
        return "    → 범인 룰을 특정하지 못했습니다(도메인 제약 단독 가능성)."
    return "    → 범인 룰: " + ", ".join(_format_culprit(r, sources) for r in culprit_rules)


def _format_violation(index: int, v: RangeViolation, sources: dict[str, str]) -> str:
    cond = _format_assignment(v.assignment)
    if v.bound == "max":
        detail = (
            f"'{v.variable}'은(는) 최대 {v.achievable}까지만 도달 가능합니다 "
            f"(선언 max={v.declared})."
        )
    else:
        detail = (
            f"'{v.variable}'은(는) 최소 {v.achievable} 이상만 가능합니다 (선언 min={v.declared})."
        )
    return f"[{index}] {cond}일 때 {detail}\n{_format_culprits(v.culprit_rules, sources)}"


def _format_unreachable(index: int, ue: UnreachableState, sources: dict[str, str]) -> str:
    cond = _format_assignment(ue.assignment)
    return (
        f"[{index}] {cond} 상태에 도달할 수 없습니다.\n"
        f"{_format_culprits(ue.culprit_rules, sources)}"
    )


def _format_bound_unreachable(index: int, bu: BoundUnreachable, sources: dict[str, str]) -> str:
    cond = _format_assignment(bu.assignment)
    label = "최대값" if bu.bound == "max" else "최소값"
    detail = f"'{bu.variable}'의 선언 {label} {bu.declared}에 도달할 수 없습니다."
    return f"[{index}] {cond}일 때 {detail}\n{_format_culprits(bu.culprit_rules, sources)}"


def _format_unmet_expectation(index: int, um: UnmetExpectation, sources: dict[str, str]) -> str:
    desc = f" — {um.desc}" if um.desc else ""
    detail = f"기대 '{um.expect_id}'{desc}가 충족되지 않습니다(도달 불가)."
    return f"[{index}] {detail}\n{_format_culprits(um.culprit_rules, sources)}"
