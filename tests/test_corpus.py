"""S8: 알려진 모순/정합 코퍼스 + 거짓양성·거짓음성 회귀 잠금 (CLAUDE.md §8).

검증기의 신뢰성이 곧 제품 가치다. 의도적으로 모순/정합인 룰셋을 fixtures에 두고,
검사기가 정확히 그 결과를 내는지 잠근다. 한 번 잘못 잡은 케이스는 영구 회귀 테스트로
고정한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ruleforge.dsl.loader import load_rules
from ruleforge.dsl.schema import validate
from ruleforge.solver.checks import CheckReport, check
from ruleforge.solver.report import format_report
from ruleforge.solver.translator import translate

FIXTURES = Path(__file__).parent / "fixtures"
CONSISTENT = sorted((FIXTURES / "consistent").glob("*.rule"))
CONTRADICTION = sorted((FIXTURES / "contradiction").glob("*.rule"))


def _run(path: Path) -> CheckReport:
    rs = load_rules(path)
    validate(rs)
    return check(rs, translate(rs))


@pytest.mark.parametrize("rule_file", CONSISTENT, ids=lambda p: p.stem)
def test_consistent_corpus_has_no_contradiction(rule_file: Path) -> None:
    report = _run(rule_file)
    assert not report.has_contradiction, format_report(report)
    assert report.unknowns == ()


@pytest.mark.parametrize("rule_file", CONTRADICTION, ids=lambda p: p.stem)
def test_contradiction_corpus_is_detected(rule_file: Path) -> None:
    report = _run(rule_file)
    assert report.has_contradiction
    assert report.unknowns == ()


def test_corpus_directories_are_not_empty() -> None:
    # glob가 조용히 0건이면 위 parametrize가 통과처럼 보이는 함정을 막는다.
    assert CONSISTENT, "정합 코퍼스가 비어 있습니다"
    assert CONTRADICTION, "모순 코퍼스가 비어 있습니다"


def test_warrior_level_cap_pins_exact_culprits() -> None:
    report = _run(FIXTURES / "contradiction" / "warrior_level_cap.rule")
    assert len(report.violations) == 1
    v = report.violations[0]
    assert (v.variable, v.bound, v.declared, v.achievable) == ("level", "max", 100, 50)
    assert set(v.culprit_rules) == {"warrior_hp_formula", "global_hp_cap"}


def test_dependent_variable_not_flagged_regression() -> None:
    # D5 회귀: 종속 변수 hp(=level*100)는 hp=0 미달로 거짓양성 모순이 되면 안 된다.
    report = _run(FIXTURES / "contradiction" / "warrior_level_cap.rule")
    assert all(v.variable != "hp" for v in report.violations)


def test_unreachable_role_pins_culprits() -> None:
    report = _run(FIXTURES / "contradiction" / "unreachable_role.rule")
    assert len(report.unreachable_enums) == 1
    ue = report.unreachable_enums[0]
    assert ue.enum_assignment == {"role": "ghost"}
    assert set(ue.culprit_rules) == {"ghost_no_hp", "must_have_hp"}


def test_conflicting_constants_global_infeasibility() -> None:
    report = _run(FIXTURES / "contradiction" / "conflicting_constants.rule")
    assert len(report.unreachable_enums) == 1
    ue = report.unreachable_enums[0]
    assert ue.enum_assignment == {}  # enum 없음 → 전역 도달 불가
    assert set(ue.culprit_rules) == {"set_low", "set_high"}
