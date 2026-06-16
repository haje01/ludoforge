"""S1: 중간표현(IR) 데이터클래스 테스트.

IR은 불변(frozen)이어야 하고(CLAUDE.md §7), 1차 범위(LIA 수치공식 + enum)를
표현할 수 있어야 한다.
"""

from __future__ import annotations

import dataclasses

import pytest

from ruleforge.dsl.ir import Rule, RuleSet, Variable


def test_int_variable_holds_bounds() -> None:
    v = Variable(name="level", type="int", min=1, max=100)
    assert v.name == "level"
    assert v.type == "int"
    assert (v.min, v.max) == (1, 100)
    assert v.values == ()


def test_enum_variable_holds_values() -> None:
    v = Variable(name="role", type="enum", values=("warrior", "mage", "archer"))
    assert v.type == "enum"
    assert v.values == ("warrior", "mage", "archer")
    assert (v.min, v.max) == (None, None)


def test_rule_requires_id_and_then_then_optional_when() -> None:
    r = Rule(id="global_hp_cap", then="hp <= 5000")
    assert r.id == "global_hp_cap"
    assert r.then == "hp <= 5000"
    assert r.when is None

    r2 = Rule(
        id="warrior_hp_formula",
        then="hp == level * 100",
        when="role == warrior",
        author="planner_A",
        desc="전사 최대 HP는 레벨당 100",
    )
    assert r2.when == "role == warrior"
    assert r2.author == "planner_A"


def test_ruleset_groups_variables_and_rules() -> None:
    rs = RuleSet(
        variables=(Variable(name="level", type="int", min=1, max=100),),
        rules=(Rule(id="r1", then="level <= 100"),),
    )
    assert len(rs.variables) == 1
    assert len(rs.rules) == 1
    assert rs.variable("level").max == 100


def test_ruleset_variable_lookup_missing_raises_keyerror() -> None:
    rs = RuleSet(variables=(), rules=())
    with pytest.raises(KeyError):
        rs.variable("nope")


def test_ir_is_frozen() -> None:
    v = Variable(name="hp", type="int", min=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.min = 5  # type: ignore[misc]
