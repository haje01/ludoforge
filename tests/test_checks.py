"""S5: 검사 로직 테스트 (D3/D4 — Optimize 기반 도달성 검사).

모순 = "기획자가 합법이라 여기는 상태를 룰들이 봉쇄한다"(D3).
독립 변수(then에서 값이 결정되지 않는 자유 변수)의 선언 범위가 룰 하에서
도달 가능한지 Optimize로 확인하고(D4), 봉쇄되면 unsat core로 범인 룰을 짚는다.
"""

from __future__ import annotations

from pathlib import Path

from ruleforge.dsl.ir import Rule, RuleSet, Variable
from ruleforge.dsl.loader import load_rule_file
from ruleforge.solver.checks import check
from ruleforge.solver.translator import translate

FIXTURES = Path(__file__).parent / "fixtures"


def _check(rs: RuleSet):  # type: ignore[no-untyped-def]
    return check(rs, translate(rs))


def test_warrior_hp_contradiction_pins_level_and_culprits() -> None:
    rs = load_rule_file(FIXTURES / "warrior_hp.rule")
    report = _check(rs)

    assert report.has_contradiction
    # 독립 변수 level의 max만 잡혀야 하고, 종속 변수 hp(=level*100)는 거짓양성 없이 무시.
    assert len(report.violations) == 1
    v = report.violations[0]
    assert v.variable == "level"
    assert v.bound == "max"
    assert (v.declared, v.achievable) == (100, 50)
    assert v.enum_assignment == {"role": "warrior"}
    assert set(v.culprit_rules) == {"warrior_hp_formula", "global_hp_cap"}


def test_consistent_ruleset_has_no_contradiction() -> None:
    # hp 상한을 10000으로 두면 전사 레벨 100(hp=10000)도 도달 가능 → 모순 없음.
    rs = RuleSet(
        variables=(
            Variable(name="level", type="int", min=1, max=100),
            Variable(name="hp", type="int", min=0),
            Variable(name="role", type="enum", values=("warrior", "mage", "archer")),
        ),
        rules=(
            Rule(id="warrior_hp", when="role == warrior", then="hp == level * 100"),
            Rule(id="hp_cap", then="hp <= 10000"),
        ),
    )
    report = _check(rs)
    assert not report.has_contradiction
    assert report.violations == ()
    assert report.unreachable_enums == ()


def test_unreachable_enum_value_is_reported() -> None:
    # role==a 이면 x==5가 강제되는데 전역 룰 x>=8과 충돌 → role=a 자체가 도달 불가.
    rs = RuleSet(
        variables=(
            Variable(name="x", type="int", min=0, max=10),
            Variable(name="role", type="enum", values=("a", "b")),
        ),
        rules=(
            Rule(id="a_sets_x", when="role == a", then="x == 5"),
            Rule(id="x_floor", then="x >= 8"),
        ),
    )
    report = _check(rs)
    assert report.has_contradiction
    assert len(report.unreachable_enums) == 1
    ue = report.unreachable_enums[0]
    assert ue.enum_assignment == {"role": "a"}
    assert set(ue.culprit_rules) == {"a_sets_x", "x_floor"}


def test_no_unknowns_in_linear_cases() -> None:
    report = _check(load_rule_file(FIXTURES / "warrior_hp.rule"))
    assert report.unknowns == ()
