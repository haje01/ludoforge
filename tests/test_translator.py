"""S4: 표현식 번역기 테스트. IR → Z3 제약식 (D2: ast 화이트리스트).

번역기는 Z3 변수·도메인 경계·룰별 제약·enum 인코딩을 만든다.
assert_and_track(Solver 작업)은 S5의 몫이므로 여기서는 제약식만 검증한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import z3

from ruleforge.dsl.ir import Rule, RuleSet, Variable
from ruleforge.dsl.loader import load_rule_file
from ruleforge.solver.translator import Translation, TranslationError, translate

FIXTURES = Path(__file__).parent / "fixtures"


def _solver_with(t: Translation, *extra: Any) -> z3.Solver:
    s = z3.Solver()
    for c in t.domain_constraints:
        s.add(c)
    for c in t.rule_constraints.values():
        s.add(c)
    for e in extra:
        s.add(e)
    return s


def test_translate_produces_vars_and_rule_constraints() -> None:
    t = translate(load_rule_file(FIXTURES / "warrior_hp.rule"))
    assert isinstance(t, Translation)
    assert set(t.z3_vars) == {"level", "hp", "role"}
    assert set(t.rule_constraints) == {"warrior_hp_formula", "global_hp_cap"}


def test_enum_values_map_to_sort_constants() -> None:
    # D8: 정수 인코딩 대신 z3 EnumSort 상수로 매핑한다.
    t = translate(load_rule_file(FIXTURES / "warrior_hp.rule"))
    enc = t.enum_encoding["role"]
    assert set(enc) == {"warrior", "mage", "archer"}
    role = t.z3_vars["role"]
    assert z3.is_const(role) and not z3.is_int(role)  # EnumSort 상수(정수 인코딩 아님)
    assert all(c.sort() == role.sort() for c in enc.values())


def test_arithmetic_and_implies_semantics() -> None:
    # 전사(role==0), 레벨 51 → hp는 5100이어야 하고, 상한 5000과 모순이라 unsat.
    t = translate(load_rule_file(FIXTURES / "warrior_hp.rule"))
    warrior = t.enum_encoding["role"]["warrior"]
    s = _solver_with(t, t.z3_vars["role"] == warrior, t.z3_vars["level"] == 51)
    assert s.check() == z3.unsat


def test_when_clause_only_fires_for_matching_case() -> None:
    # 마법사(role==1)는 전사 공식의 영향을 받지 않는다 → 레벨 100에도 sat.
    t = translate(load_rule_file(FIXTURES / "warrior_hp.rule"))
    mage = t.enum_encoding["role"]["mage"]
    s = _solver_with(t, t.z3_vars["role"] == mage, t.z3_vars["level"] == 100)
    assert s.check() == z3.sat


def test_warrior_hp_is_forced_by_formula() -> None:
    # 전사 레벨 30 → hp는 정확히 3000으로 강제됨 (hp != 3000 이면 unsat).
    t = translate(load_rule_file(FIXTURES / "warrior_hp.rule"))
    warrior = t.enum_encoding["role"]["warrior"]
    s = _solver_with(
        t,
        t.z3_vars["role"] == warrior,
        t.z3_vars["level"] == 30,
        t.z3_vars["hp"] != 3000,
    )
    assert s.check() == z3.unsat


def test_bool_variable_translates_to_z3_bool() -> None:
    # 두 불리언 상태와 상호 배제 룰: 둘 다 True면 unsat (Not(And(...))).
    rs = RuleSet(
        variables=(
            Variable(name="stealthed", type="bool"),
            Variable(name="attacking", type="bool"),
        ),
        rules=(Rule(id="mutex", then="not (stealthed and attacking)"),),
    )
    t = translate(rs)
    assert set(t.z3_vars) == {"stealthed", "attacking"}
    assert z3.is_bool(t.z3_vars["stealthed"])
    s = _solver_with(t, t.z3_vars["stealthed"], t.z3_vars["attacking"])
    assert s.check() == z3.unsat


def test_bool_literal_constant_allowed() -> None:
    # True/False 리터럴은 bool 식에서 허용된다 (정수 화이트리스트의 예외).
    rs = RuleSet(
        variables=(Variable(name="stealthed", type="bool"),),
        rules=(Rule(id="force", then="stealthed == True"),),
    )
    t = translate(rs)
    s = _solver_with(t, z3.Not(t.z3_vars["stealthed"]))
    assert s.check() == z3.unsat


def test_real_variable_translates_to_z3_real_and_detects_over_constraint() -> None:
    # 확률 합=1인데 pa,pb 각각 0.6 이상이면 합 1.2 > 1 → 전역 unsat (LRA, D7).
    rs = RuleSet(
        variables=(
            Variable(name="pa", type="real", min=0.0, max=1.0),
            Variable(name="pb", type="real", min=0.0, max=1.0),
        ),
        rules=(
            Rule(id="sum_one", then="pa + pb == 1.0"),
            Rule(id="a_floor", then="pa >= 0.6"),
            Rule(id="b_floor", then="pb >= 0.6"),
        ),
    )
    t = translate(rs)
    assert z3.is_real(t.z3_vars["pa"])
    assert _solver_with(t).check() == z3.unsat


def test_constant_division_is_exact_rational() -> None:
    # 1/3은 z3 유리수로 정확히 표현되어야 한다(파이썬 float 0.333… 아님).
    rs = RuleSet(
        variables=(Variable(name="p", type="real", min=0.0, max=1.0),),
        rules=(Rule(id="third", then="p == 1 / 3"),),
    )
    t = translate(rs)
    s = _solver_with(t, t.z3_vars["p"] * 3 != 1)
    assert s.check() == z3.unsat


def test_variable_divisor_raises() -> None:
    # 변수 분모(a/b)는 비선형이라 거부한다(상수 분모만 허용, D7).
    rs = RuleSet(
        variables=(
            Variable(name="a", type="real", min=0.0, max=1.0),
            Variable(name="b", type="real", min=0.0, max=1.0),
        ),
        rules=(Rule(id="nonlinear", then="a / b == 1.0"),),
    )
    with pytest.raises(TranslationError, match="상수 분모"):
        translate(rs)


def test_duplicate_enum_value_names_resolved_by_context() -> None:
    # D8: 서로 다른 enum이 같은 값 이름(active/inactive)을 써도 비교 문맥으로 구분된다.
    rs = RuleSet(
        variables=(
            Variable(name="role", type="enum", values=("active", "inactive")),
            Variable(name="status", type="enum", values=("active", "inactive")),
        ),
        rules=(Rule(id="link", when="role == active", then="status == inactive"),),
    )
    t = translate(rs)
    ra = t.enum_encoding["role"]["active"]
    sa = t.enum_encoding["status"]["active"]
    si = t.enum_encoding["status"]["inactive"]
    assert ra.sort() != sa.sort()  # 별도 sort의 구별된 상수
    # role==active이면 status==inactive 강제 → status==active와 함께면 unsat
    assert _solver_with(t, t.z3_vars["role"] == ra, t.z3_vars["status"] == sa).check() == z3.unsat
    # role==active, status==inactive 는 sat
    assert _solver_with(t, t.z3_vars["role"] == ra, t.z3_vars["status"] == si).check() == z3.sat


def test_cross_enum_value_misuse_raises() -> None:
    # D8: 다른 enum의 값으로 비교하면 친절한 에러(원시 z3 sort 에러 아님).
    rs = RuleSet(
        variables=(
            Variable(name="role", type="enum", values=("warrior", "mage")),
            Variable(name="status", type="enum", values=("active", "idle")),
        ),
        rules=(Rule(id="bad", then="role == active"),),
    )
    with pytest.raises(TranslationError, match="active"):
        translate(rs)


def test_disallowed_function_call_raises() -> None:
    rs = RuleSet(
        variables=(Variable(name="hp", type="int", min=0),),
        rules=(Rule(id="bad_call", then="abs(hp) <= 5"),),
    )
    with pytest.raises(TranslationError, match="bad_call"):
        translate(rs)


def test_disallowed_attribute_raises() -> None:
    rs = RuleSet(
        variables=(Variable(name="hp", type="int", min=0),),
        rules=(Rule(id="bad_attr", then="hp.value <= 5"),),
    )
    with pytest.raises(TranslationError, match="bad_attr"):
        translate(rs)


def test_chained_comparison_supported() -> None:
    # 1 <= level <= 3 형태의 연쇄 비교를 And로 번역한다.
    rs = RuleSet(
        variables=(Variable(name="level", type="int"),),
        rules=(Rule(id="range", then="1 <= level <= 3"),),
    )
    t = translate(rs)
    s = _solver_with(t, t.z3_vars["level"] == 5)
    assert s.check() == z3.unsat
