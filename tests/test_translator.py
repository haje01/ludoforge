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


def test_enum_encoding_maps_values_to_ints() -> None:
    t = translate(load_rule_file(FIXTURES / "warrior_hp.rule"))
    assert t.enum_encoding["role"] == {"warrior": 0, "mage": 1, "archer": 2}


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
