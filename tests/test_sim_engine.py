"""Phase 1: sim 엔진(D19) 테스트.

전이 시스템을 표집으로 1회 시뮬레이션한다. 검증 포인트:
- 표현식 평가기(화이트리스트, eval 미사용)가 산술·비교·불리언·enum 등식을 맞게 푼다.
- run_once가 같은 seed에서 결정적으로 재현된다(D19 재현성).
- DTMC 게이트가 enabled>1 모델을 친절히 거부한다(D19).
- 미고정 init은 Phase 2 sweep 안내와 함께 거부한다(Phase 경계).
"""

from __future__ import annotations

import ast
import random
from pathlib import Path
from typing import Any

import pytest

from core.loader import load_rule_file
from sim.engine import (
    DtmcViolation,
    EvalError,
    SimError,
    apply_outcome,
    enum_constants,
    evaluate,
    initial_state,
    run_once,
)

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def _eval(expr: str, env: dict[str, Any]) -> Any:
    return evaluate(ast.parse(expr, mode="eval").body, env)


# ---------- 표현식 평가기 ----------


def test_eval_arithmetic_and_comparison() -> None:
    env = {"gold": 7, "cap": 10}
    assert _eval("gold + 3", env) == 10
    assert _eval("gold * 2 - 1", env) == 13
    assert _eval("gold <= cap", env) is True
    assert _eval("gold > cap", env) is False


def test_eval_chained_comparison() -> None:
    assert _eval("1 <= x <= 3", {"x": 2}) is True
    assert _eval("1 <= x <= 3", {"x": 5}) is False


def test_eval_bool_and_not() -> None:
    env = {"a": True, "b": False}
    assert _eval("a and not b", env) is True
    assert _eval("a and b", env) is False
    assert _eval("a or b", env) is True


def test_eval_enum_equality_via_constants() -> None:
    # enum 변수는 문자열, bare 값 이름도 자기 문자열 → 등식 비교.
    env = {"role": "rogue", "rogue": "rogue", "wizard": "wizard"}
    assert _eval("role == rogue", env) is True
    assert _eval("role == wizard", env) is False
    assert _eval("role != wizard", env) is True


def test_eval_undefined_symbol_raises() -> None:
    with pytest.raises(EvalError, match="미정의 심볼"):
        _eval("ghost + 1", {"gold": 1})


def test_eval_rejects_non_whitelisted_node() -> None:
    with pytest.raises(EvalError, match="지원하지 않는"):
        _eval("gold ** 2", {"gold": 3})  # 거듭제곱은 화이트리스트 밖


# ---------- 초기 상태 ----------


def test_initial_state_from_pinned_init() -> None:
    rs = load_rule_file(FIXTURES / "coin.rule")
    state = initial_state(rs, enum_constants(rs))
    assert state == {"gold": 0, "flips": 0, "status": "playing"}


def test_initial_state_rejects_free_var_without_overrides() -> None:
    # 던전!은 role(enum)·win_gold(int)를 init에서 고정하지 않는다 → overrides 없이는 거부.
    rs = load_rule_file(EXAMPLES / "dungeon.rule")
    with pytest.raises(SimError, match="고정하지 않습니다"):
        initial_state(rs, enum_constants(rs))


# ---------- outcome 적용(프레임) ----------


def test_apply_outcome_keeps_unchanged_vars() -> None:
    rs = load_rule_file(FIXTURES / "coin.rule")
    constants = enum_constants(rs)
    state = {"gold": 2, "flips": 1, "status": "playing"}
    # 앞면 outcome: gold+1, flips+1. status는 건드리지 않으니 유지(프레임, D15).
    new = apply_outcome("next.gold == gold + 1 and next.flips == flips + 1", state, constants)
    assert new == {"gold": 3, "flips": 2, "status": "playing"}
    assert state["gold"] == 2  # 원본 불변(순수 함수)


# ---------- run_once: 재현성·구조 ----------


def test_run_once_is_deterministic_for_same_seed() -> None:
    rs = load_rule_file(FIXTURES / "coin.rule")
    r1 = run_once(rs, random.Random(42), horizon=10)
    r2 = run_once(rs, random.Random(42), horizon=10)
    assert r1 == r2  # 같은 seed → 동일 궤적(D19 재현성)


def test_run_once_trajectory_structure() -> None:
    rs = load_rule_file(FIXTURES / "coin.rule")
    r = run_once(rs, random.Random(7), horizon=20)
    # flips<5 동안 flip만, flips==5에서 finish, status=done 도달 → done_absorb는 흡수라
    # 자연 종료(stutter 안 펼침).
    assert r.actions == ("flip", "flip", "flip", "flip", "flip", "finish")
    assert r.terminated is True
    assert r.truncated is False
    assert r.states[-1]["status"] == "done"
    assert 0 <= r.states[-1]["gold"] <= 5


def test_run_once_different_seeds_can_differ() -> None:
    rs = load_rule_file(FIXTURES / "coin.rule")
    golds = {run_once(rs, random.Random(s), horizon=10).states[-1]["gold"] for s in range(20)}
    assert len(golds) > 1  # 표집이라 seed에 따라 최종 gold가 달라진다


# ---------- DTMC 게이트 ----------


def test_dtmc_violation_rejected_with_friendly_message() -> None:
    rs = load_rule_file(FIXTURES / "nondet.rule")
    with pytest.raises(DtmcViolation) as exc:
        run_once(rs, random.Random(0), horizon=10)
    msg = str(exc.value)
    assert "DTMC 위배" in msg
    assert "a" in msg and "b" in msg  # 동시 enabled 전이 id를 짚는다
    assert "ludoforge bmc" in msg  # 대안 백엔드 안내
