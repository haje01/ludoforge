"""S5: 검사 로직 테스트 (D3/D4 — Optimize 기반 도달성 검사).

모순 = "기획자가 합법이라 여기는 상태를 룰들이 봉쇄한다"(D3).
독립 변수(then에서 값이 결정되지 않는 자유 변수)의 선언 범위가 룰 하에서
도달 가능한지 Optimize로 확인하고(D4), 봉쇄되면 unsat core로 범인 룰을 짚는다.
"""

from __future__ import annotations

from pathlib import Path

from forge_core.ir import Expect, Rule, RuleSet, Variable
from forge_core.loader import load_rule_file
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
    assert v.assignment == {"role": "warrior"}
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
    assert report.unreachable_states == ()


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
    assert len(report.unreachable_states) == 1
    ue = report.unreachable_states[0]
    assert ue.assignment == {"role": "a"}
    assert set(ue.culprit_rules) == {"a_sets_x", "x_floor"}


def test_conditional_enum_exclusion_is_not_false_positive() -> None:
    # 거짓양성 회귀: 조건부 룰이 일부 조인트 조합만 막는 것은 모순이 아니다.
    # sky==night → lighting==night이면 (night, day)는 막히지만 모든 enum 값은 도달 가능.
    rs = RuleSet(
        variables=(
            Variable(name="sky", type="enum", values=("day", "night")),
            Variable(name="lighting", type="enum", values=("day", "night")),
        ),
        rules=(Rule(id="night_sky_needs_dark", when="sky == night", then="lighting == night"),),
    )
    report = _check(rs)
    assert not report.has_contradiction
    assert report.unreachable_states == ()
    assert report.unknowns == ()


def test_enum_value_unreachable_by_value_projection_not_per_cell() -> None:
    # 두 룰이 sky==night일 때 lighting을 day/night로 동시 강제 → sky=night 값 자체가 봉쇄.
    # 값 단위 투영이라 조인트 셀 둘이 아니라 sky=night 하나만 보고해야 한다.
    rs = RuleSet(
        variables=(
            Variable(name="sky", type="enum", values=("day", "night")),
            Variable(name="lighting", type="enum", values=("day", "night")),
        ),
        rules=(
            Rule(id="needs_dark", when="sky == night", then="lighting == night"),
            Rule(id="forces_day", when="sky == night", then="lighting == day"),
        ),
    )
    report = _check(rs)
    assert len(report.unreachable_states) == 1
    ue = report.unreachable_states[0]
    assert ue.assignment == {"sky": "night"}
    assert set(ue.culprit_rules) == {"needs_dark", "forces_day"}


def test_unconditionally_pinned_enum_is_not_false_positive() -> None:
    # D5 일관: 무조건 룰로 한 값에 핀된 enum은 나머지 값이 도달 불가여도 정상.
    rs = RuleSet(
        variables=(Variable(name="mode", type="enum", values=("easy", "normal", "hard")),),
        rules=(Rule(id="pin_normal", then="mode == normal"),),
    )
    report = _check(rs)
    assert not report.has_contradiction
    assert report.unreachable_states == ()
    assert report.unknowns == ()


def test_bool_state_blocked_by_mutex_is_reported() -> None:
    # D6: attacking이 항상 강제되고 상호 배제이므로 stealthed=true는 도달 불가.
    # attacking은 무조건 강제(종속)라 검사 대상에서 빠지고, 자유 bool인 stealthed만 잡힌다.
    rs = load_rule_file(FIXTURES / "contradiction" / "stealth_blocked.rule")
    report = _check(rs)
    assert report.has_contradiction
    assert len(report.unreachable_states) == 1
    ue = report.unreachable_states[0]
    assert ue.assignment == {"stealthed": "true"}
    assert set(ue.culprit_rules) == {"always_attacking", "stealth_mutex"}
    assert report.unknowns == ()


def test_free_bool_with_mutex_has_no_false_positive() -> None:
    # D6 거짓양성 회귀: 상호 배제만 있고 둘 다 자유면 각 상태가 도달 가능 → 모순 없음.
    rs = load_rule_file(FIXTURES / "consistent" / "stealth_mutex_ok.rule")
    report = _check(rs)
    assert not report.has_contradiction
    assert report.unknowns == ()


def test_real_probability_over_constraint_is_reported() -> None:
    # LRA(D7): 실수 확률 합=1과 두 하한(0.7)이 충돌 → 전역 도달 불가, 세 룰이 범인.
    rs = load_rule_file(FIXTURES / "contradiction" / "prob_sum.rule")
    report = _check(rs)
    assert report.has_contradiction
    assert len(report.unreachable_states) == 1
    ue = report.unreachable_states[0]
    assert ue.assignment == {}  # enum 없음 → 전역 over-constraint
    assert set(ue.culprit_rules) == {"prob_sum_one", "common_floor", "rare_floor"}
    assert report.unknowns == ()


def test_real_probability_consistent_has_no_contradiction() -> None:
    rs = load_rule_file(FIXTURES / "consistent" / "prob_ok.rule")
    report = _check(rs)
    assert not report.has_contradiction
    assert report.unknowns == ()


def test_duplicate_enum_names_contradiction_resolved_by_context() -> None:
    # D8: 두 enum이 같은 값 이름(on/off). gate==on이면 valve==off 강제인데 valve는 항상 on.
    # 비교 문맥으로 각 값을 제 sort로 풀어 gate==on 상태 봉쇄를 정확히 잡는다.
    rs = RuleSet(
        variables=(
            Variable(name="gate", type="enum", values=("on", "off")),
            Variable(name="valve", type="enum", values=("on", "off")),
        ),
        rules=(
            Rule(id="gate_closes_valve", when="gate == on", then="valve == off"),
            Rule(id="valve_forced_on", then="valve == on"),
        ),
    )
    report = _check(rs)
    assert report.has_contradiction
    assert report.unknowns == ()
    states = [ue.assignment for ue in report.unreachable_states]
    assert any(s.get("gate") == "on" for s in states)


def test_real_declared_max_blocked_is_reported() -> None:
    # D9: prob∈[0,1]인데 룰이 prob<=0.5로 막으면 선언 max=1.0 끝점에 도달 불가.
    rs = RuleSet(
        variables=(Variable(name="prob", type="real", min=0.0, max=1.0),),
        rules=(Rule(id="cap_half", then="prob <= 0.5"),),
    )
    report = _check(rs)
    assert report.has_contradiction
    assert len(report.bound_unreachables) == 1
    b = report.bound_unreachables[0]
    assert (b.variable, b.bound, b.declared) == ("prob", "max", 1.0)
    assert set(b.culprit_rules) == {"cap_half"}
    assert report.unknowns == ()


def test_real_declared_min_blocked_is_reported() -> None:
    # D9: 룰이 prob>=0.6이면 선언 min=0.0 끝점에 도달 불가.
    rs = RuleSet(
        variables=(Variable(name="prob", type="real", min=0.0, max=1.0),),
        rules=(Rule(id="floor", then="prob >= 0.6"),),
    )
    report = _check(rs)
    bounds = {(b.variable, b.bound) for b in report.bound_unreachables}
    assert ("prob", "min") in bounds
    assert all(set(b.culprit_rules) == {"floor"} for b in report.bound_unreachables)


def test_dependent_real_excluded_from_bound_check() -> None:
    # D9: 공식으로 값이 결정되는 종속 real은 끝점 미달이 정상 → 거짓양성 없음(D5 일관).
    rs = RuleSet(
        variables=(Variable(name="ratio", type="real", min=0.0, max=1.0),),
        rules=(Rule(id="fixed", then="ratio == 1"),),
    )
    report = _check(rs)
    assert report.bound_unreachables == ()


def test_real_endpoints_reachable_has_no_contradiction() -> None:
    # 합=1만 있으면 common은 0(rare=1)·1(rare=0) 양 끝점에 도달 가능 → 모순 없음.
    rs = RuleSet(
        variables=(
            Variable(name="common", type="real", min=0.0, max=1.0),
            Variable(name="rare", type="real", min=0.0, max=1.0),
        ),
        rules=(Rule(id="sum_one", then="common + rare == 1.0"),),
    )
    report = _check(rs)
    assert not report.has_contradiction
    assert report.unknowns == ()


def test_unmet_expectation_reports_culprits() -> None:
    # D10: 전사가 레벨 100에 도달 가능해야 한다고 단언했지만 hp 상한이 막는다.
    rs = RuleSet(
        variables=(
            Variable(name="level", type="int", min=1, max=100),
            Variable(name="hp", type="int", min=0),
            Variable(name="role", type="enum", values=("warrior", "mage")),
        ),
        rules=(
            Rule(id="warrior_hp", when="role == warrior", then="hp == level * 100"),
            Rule(id="hp_cap", then="hp <= 5000"),
        ),
        expects=(Expect(id="warrior_max_level", that="role == warrior and level == 100"),),
    )
    report = _check(rs)
    assert report.has_contradiction
    assert len(report.unmet_expectations) == 1
    u = report.unmet_expectations[0]
    assert u.expect_id == "warrior_max_level"
    assert set(u.culprit_rules) == {"warrior_hp", "hp_cap"}
    assert report.unknowns == ()


def test_met_expectation_has_no_contradiction() -> None:
    # D10: 도달 가능한 단언은 모순이 아니다.
    rs = RuleSet(
        variables=(Variable(name="level", type="int", min=1, max=100),),
        rules=(Rule(id="cap", then="level <= 100"),),
        expects=(Expect(id="reach_100", that="level == 100"),),
    )
    report = _check(rs)
    assert not report.has_contradiction
    assert report.unmet_expectations == ()


def test_no_unknowns_in_linear_cases() -> None:
    report = _check(load_rule_file(FIXTURES / "warrior_hp.rule"))
    assert report.unknowns == ()
