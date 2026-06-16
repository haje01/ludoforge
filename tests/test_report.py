"""S6: 리포터 테스트. CheckReport → 한국어 사람용 리포트.

리포트는 사람이 읽을 수 있어야 한다(CLAUDE.md §2.4): 어떤 enum 조건에서 어떤 변수가
어디까지만 도달 가능한지, 범인 룰이 무엇인지 제시한다. unknown은 숨기지 않는다(§10).
"""

from __future__ import annotations

from ruleforge.solver.checks import CheckReport, RangeViolation, UnreachableState
from ruleforge.solver.report import format_report


def test_no_contradiction_reports_success() -> None:
    text = format_report(CheckReport())
    assert "✅" in text
    assert "모순" in text


def test_range_violation_is_human_readable() -> None:
    report = CheckReport(
        violations=(
            RangeViolation(
                assignment={"role": "warrior"},
                variable="level",
                bound="max",
                declared=100,
                achievable=50,
                culprit_rules=("global_hp_cap", "warrior_hp_formula"),
            ),
        )
    )
    text = format_report(report)
    assert "❌" in text
    assert "role=warrior" in text
    assert "level" in text
    assert "50" in text and "100" in text
    assert "global_hp_cap" in text and "warrior_hp_formula" in text


def test_min_bound_violation_wording() -> None:
    report = CheckReport(
        violations=(
            RangeViolation(
                assignment={},
                variable="gold",
                bound="min",
                declared=0,
                achievable=10,
                culprit_rules=("min_gold",),
            ),
        )
    )
    text = format_report(report)
    assert "gold" in text
    assert "10" in text and "0" in text


def test_unreachable_enum_is_reported() -> None:
    report = CheckReport(
        unreachable_states=(
            UnreachableState(assignment={"role": "a"}, culprit_rules=("a_sets_x", "x_floor")),
        )
    )
    text = format_report(report)
    assert "role=a" in text
    assert "도달" in text
    assert "a_sets_x" in text and "x_floor" in text


def test_unknown_is_surfaced_not_hidden() -> None:
    report = CheckReport(unknowns=("role=warrior 변수 'level' max 검사에서 unknown",))
    text = format_report(report)
    assert "⚠️" in text
    assert "unknown" in text
