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
    rs = load_rule_file(FIXTURES / "warrior_hp.lf")
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
        transitions=(Transition(id="t", when=when, outcomes=(Outcome(then=then, weight=1.0),)),),
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


# ── constraint 등식으로 핀되는 변수는 transition에서 갱신 금지(bmc·sim 의미 불일치 차단) ──


def test_constraint_pinned_var_updated_in_transition_is_rejected() -> None:
    # win_gold는 constraint 등식으로 파생되는 상수(모든 상태 불변)다. 이를 transition 효과로
    # 갱신하면 bmc(매 스텝 불변식 강제)와 sim(init 파생만)의 의미가 갈라진다 — 정적 거부.
    rs = RuleSet(
        variables=(
            Variable(name="gold", type="int", min=0, max=30),
            Variable(name="win_gold", type="int", min=0, max=30),
            Variable(name="role", type="enum", values=("rogue", "wizard")),
        ),
        constraints=(Constraint(id="rogue_win", when="role == rogue", then="win_gold == 10"),),
        transitions=(
            Transition(
                id="bump",
                outcomes=(Outcome(then="next.win_gold == win_gold + 5", weight=1.0),),
            ),
        ),
    )
    with pytest.raises(SchemaError, match="win_gold"):
        validate(rs)


def test_constraint_pinned_var_in_multi_effect_is_rejected() -> None:
    # 병렬 대입(and 결합) 중 하나만 핀 변수를 건드려도 거부해야 한다.
    rs = RuleSet(
        variables=(
            Variable(name="gold", type="int", min=0, max=30),
            Variable(name="win_gold", type="int", min=0, max=30),
            Variable(name="role", type="enum", values=("rogue", "wizard")),
        ),
        constraints=(Constraint(id="rogue_win", when="role == rogue", then="win_gold == 10"),),
        transitions=(
            Transition(
                id="bump",
                outcomes=(
                    Outcome(then="next.gold == gold + 1 and next.win_gold == 20", weight=1.0),
                ),
            ),
        ),
    )
    with pytest.raises(SchemaError, match="win_gold"):
        validate(rs)


def test_relational_constraint_var_updated_in_transition_passes() -> None:
    # `<=` 류 관계형 불변식은 변수를 특정 값으로 핀하지 않는다 — 갱신과 공존 합법(좁게만 막는다).
    rs = RuleSet(
        variables=(Variable(name="hp", type="int", min=0, max=5000),),
        constraints=(Constraint(id="cap", then="hp <= 5000"),),
        transitions=(
            Transition(id="heal", outcomes=(Outcome(then="next.hp == hp + 10", weight=1.0),)),
        ),
    )
    validate(rs)  # 예외 없이 통과


def test_constraint_pinned_var_not_mutated_passes() -> None:
    # 핀 변수를 갱신하지 않으면(읽기만) 정상 — 던전! win_gold의 정상 용법.
    rs = RuleSet(
        variables=(
            Variable(name="gold", type="int", min=0, max=30),
            Variable(name="win_gold", type="int", min=0, max=30),
            Variable(name="role", type="enum", values=("rogue", "wizard")),
            Variable(name="status", type="enum", values=("exploring", "won")),
        ),
        constraints=(Constraint(id="rogue_win", when="role == rogue", then="win_gold == 10"),),
        transitions=(
            Transition(
                id="claim",
                when="gold >= win_gold",
                outcomes=(Outcome(then="next.status == won", weight=1.0),),
            ),
        ),
    )
    validate(rs)  # 예외 없이 통과


# ---------- 상태 의존 pref/weight (D26) ----------

_D26_VARS = (
    Variable(name="red", type="int", min=0, max=2),
    Variable(name="blue", type="int", min=0, max=1),
)


def test_weight_expr_undefined_symbol_is_reported() -> None:
    rs = RuleSet(
        variables=_D26_VARS,
        transitions=(
            Transition(
                id="draw",
                outcomes=(
                    Outcome(then="next.red == red - 1", weight="reed / (red + blue)"),
                    Outcome(then="next.blue == blue - 1", weight="blue / (red + blue)"),
                ),
            ),
        ),
    )
    with pytest.raises(SchemaError, match="미정의 심볼.*reed"):
        validate(rs)


def test_pref_expr_with_next_is_rejected() -> None:
    rs = RuleSet(
        variables=_D26_VARS,
        transitions=(
            Transition(
                id="a",
                outcomes=(Outcome(then="next.red == red", weight=1.0),),
                pref="next.red",
            ),
        ),
    )
    with pytest.raises(SchemaError, match="next\\..*전이 then에서만"):
        validate(rs)


def test_negative_constant_weight_is_rejected() -> None:
    rs = RuleSet(
        variables=_D26_VARS,
        transitions=(
            Transition(
                id="a",
                outcomes=(
                    Outcome(then="next.red == red", weight=-0.5),
                    Outcome(then="next.red == red", weight=1.0),
                ),
            ),
        ),
    )
    with pytest.raises(SchemaError, match="weight는 음수일 수 없습니다"):
        validate(rs)
