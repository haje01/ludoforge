"""S3: 스키마·참조 검증 테스트.

로더(S2) 통과 후 Z3(S4~) 이전의 게이트. 참조 무결성을 검사한다(CLAUDE.md §3.3):
중복 rule id, 표현식 구문 오류, 미정의 심볼 참조, int 변수 min>max.
실패 시 SchemaError에 모든 문제를 모아 보고한다(어떤 룰/필드인지 명시).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ir import Constraint, Expect, Outcome, RuleSet, Transition, Variable
from core.loader import load_rule_file
from core.schema import SchemaError, validate

FIXTURES = Path(__file__).parent / "fixtures"


def _domain() -> tuple[Variable, ...]:
    return (
        Variable(name="level", type="int", min=1, max=100),
        Variable(name="hp", type="int", min=0),
        Variable(name="role", type="enum", values=("warrior", "mage", "archer")),
    )


def test_valid_ruleset_passes() -> None:
    rs = load_rule_file(FIXTURES / "warrior_hp.rule")
    validate(rs)  # 예외 없이 통과해야 한다


def test_duplicate_rule_id_is_reported() -> None:
    rs = RuleSet(
        variables=_domain(),
        constraints=(
            Constraint(id="dup", then="hp <= 5000"),
            Constraint(id="dup", then="level <= 100"),
        ),
    )
    with pytest.raises(SchemaError, match="dup"):
        validate(rs)


def test_rules_without_any_domain_gives_directory_hint() -> None:
    # rules만 있고 domain 변수가 없으면(= rules-only 파일 단독 검사) 디렉토리 검사를 안내.
    rs = RuleSet(variables=(), constraints=(Constraint(id="r1", then="hp <= 5000"),))
    with pytest.raises(SchemaError, match="디렉토리"):
        validate(rs)


def test_undefined_variable_reference_is_reported() -> None:
    rs = RuleSet(
        variables=_domain(),
        constraints=(Constraint(id="r1", then="mana <= 100"),),
    )
    with pytest.raises(SchemaError, match="mana"):
        validate(rs)


def test_enum_value_typo_is_reported() -> None:
    rs = RuleSet(
        variables=_domain(),
        constraints=(Constraint(id="r1", when="role == wariror", then="hp <= 1"),),
    )
    with pytest.raises(SchemaError, match="wariror"):
        validate(rs)


def test_min_greater_than_max_is_reported() -> None:
    rs = RuleSet(
        variables=(Variable(name="level", type="int", min=100, max=1),),
        constraints=(),
    )
    with pytest.raises(SchemaError, match="level"):
        validate(rs)


def test_expression_syntax_error_names_the_rule() -> None:
    rs = RuleSet(
        variables=_domain(),
        constraints=(Constraint(id="broken", then="hp == * 100"),),
    )
    with pytest.raises(SchemaError, match="broken"):
        validate(rs)


def test_duplicate_expect_id_is_reported() -> None:
    rs = RuleSet(
        variables=_domain(),
        expects=(
            Expect(id="dup", that="level == 1"),
            Expect(id="dup", that="level == 2"),
        ),
    )
    with pytest.raises(SchemaError, match="dup"):
        validate(rs)


def test_undefined_symbol_in_expect_is_reported() -> None:
    rs = RuleSet(
        variables=_domain(),
        expects=(Expect(id="e1", that="mana == 1"),),
    )
    with pytest.raises(SchemaError, match="mana"):
        validate(rs)


def test_all_errors_collected_together() -> None:
    rs = RuleSet(
        variables=_domain(),
        constraints=(
            Constraint(id="r1", then="mana <= 100"),
            Constraint(id="r2", then="role == wariror"),
        ),
    )
    with pytest.raises(SchemaError) as exc:
        validate(rs)
    msg = str(exc.value)
    assert "mana" in msg and "wariror" in msg


# ── min/max는 효과(then/outcomes)에서만 — 술어에서 쓰면 거부(효과 전용) ──


def _effect(then: str, *, when: str | None = None) -> RuleSet:
    return RuleSet(
        variables=_domain(),
        transitions=(
            Transition(id="t", when=when, outcomes=(Outcome(then=then, weight=1.0),)),
        ),
    )


def test_min_in_effect_passes() -> None:
    # 효과 RHS의 포화(min)는 허용 — 함수명이 미정의 심볼로 오인되지 않는다.
    validate(_effect("next.hp == min(hp + 5, 50)"))  # 예외 없이 통과


def test_min_in_guard_is_rejected() -> None:
    # 가드(when)는 술어 — min() 금지(효과 전용).
    with pytest.raises(SchemaError, match="효과"):
        validate(_effect("next.hp == hp", when="min(level, 5) == 0"))


def test_min_in_constraint_then_is_rejected() -> None:
    # constraint의 then은 술어(같은 상태) — min() 금지.
    rs = RuleSet(
        variables=_domain(),
        constraints=(Constraint(id="c", then="hp == min(level, 50)"),),
    )
    with pytest.raises(SchemaError, match="효과"):
        validate(rs)


def test_disallowed_function_in_effect_is_reported() -> None:
    with pytest.raises(SchemaError, match="허용되지 않는 함수 호출"):
        validate(_effect("next.hp == abs(hp)"))


def test_min_one_arg_in_effect_is_reported() -> None:
    with pytest.raises(SchemaError, match="2개 이상"):
        validate(_effect("next.hp == min(hp)"))
