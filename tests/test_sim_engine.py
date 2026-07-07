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

from core.ir import Outcome, RuleSet, Transition, Variable
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


def test_eval_min_max_saturate() -> None:
    # 포화/클램프: min(gold + 10, 30)은 상한 30에서 포화, max는 하한 선택.
    assert _eval("min(gold + 10, 30)", {"gold": 25}) == 30
    assert _eval("min(gold + 10, 30)", {"gold": 5}) == 15
    assert _eval("max(gold, 5)", {"gold": 3}) == 5
    assert _eval("min(a, b, c)", {"a": 9, "b": 4, "c": 7}) == 4  # 가변 인자


def test_eval_disallowed_function_raises() -> None:
    with pytest.raises(EvalError, match="지원하지 않는 함수 호출"):
        _eval("abs(gold)", {"gold": -3})


def test_eval_min_requires_two_args() -> None:
    with pytest.raises(EvalError, match="2개 이상"):
        _eval("min(gold)", {"gold": 3})


def test_apply_outcome_saturates_gold() -> None:
    # 효과 RHS의 min(…, 30)이 다음 상태에서 포화되는지(누적 오버플로 가드 대체).
    new = apply_outcome("next.gold == min(gold + 10, 30)", {"gold": 25}, {})
    assert new["gold"] == 30
    new2 = apply_outcome("next.gold == min(gold + 10, 30)", {"gold": 5}, {})
    assert new2["gold"] == 15


# ---------- 초기 상태 ----------


def test_initial_state_from_pinned_init() -> None:
    rs = load_rule_file(FIXTURES / "coin.lf")
    state = initial_state(rs, enum_constants(rs))
    assert state == {"gold": 0, "flips": 0, "status": "playing"}


def test_initial_state_rejects_free_var_without_overrides() -> None:
    # 던전!은 role(enum)·win_gold(int)를 init에서 고정하지 않는다 → overrides 없이는 거부.
    rs = load_rule_file(EXAMPLES / "dungeon.lf")
    with pytest.raises(SimError, match="고정하지 않습니다"):
        initial_state(rs, enum_constants(rs))


# ---------- outcome 적용(프레임) ----------


def test_apply_outcome_keeps_unchanged_vars() -> None:
    rs = load_rule_file(FIXTURES / "coin.lf")
    constants = enum_constants(rs)
    state = {"gold": 2, "flips": 1, "status": "playing"}
    # 앞면 outcome: gold+1, flips+1. status는 건드리지 않으니 유지(프레임, D15).
    new = apply_outcome("next.gold == gold + 1 and next.flips == flips + 1", state, constants)
    assert new == {"gold": 3, "flips": 2, "status": "playing"}
    assert state["gold"] == 2  # 원본 불변(순수 함수)


# ---------- run_once: 재현성·구조 ----------


def test_run_once_is_deterministic_for_same_seed() -> None:
    rs = load_rule_file(FIXTURES / "coin.lf")
    r1 = run_once(rs, random.Random(42), horizon=10)
    r2 = run_once(rs, random.Random(42), horizon=10)
    assert r1 == r2  # 같은 seed → 동일 궤적(D19 재현성)


def test_run_once_trajectory_structure() -> None:
    rs = load_rule_file(FIXTURES / "coin.lf")
    r = run_once(rs, random.Random(7), horizon=20)
    # flips<5 동안 flip만, flips==5에서 finish, status=done 도달 → done_absorb는 흡수라
    # 자연 종료(stutter 안 펼침).
    assert r.actions == ("flip", "flip", "flip", "flip", "flip", "finish")
    assert r.terminated is True
    assert r.truncated is False
    assert r.states[-1]["status"] == "done"
    assert 0 <= r.states[-1]["gold"] <= 5


def test_run_once_different_seeds_can_differ() -> None:
    rs = load_rule_file(FIXTURES / "coin.lf")
    golds = {run_once(rs, random.Random(s), horizon=10).states[-1]["gold"] for s in range(20)}
    assert len(golds) > 1  # 표집이라 seed에 따라 최종 gold가 달라진다


# ---------- DTMC 게이트 ----------


def test_dtmc_violation_rejected_with_friendly_message() -> None:
    rs = load_rule_file(FIXTURES / "nondet.lf")
    with pytest.raises(DtmcViolation) as exc:
        run_once(rs, random.Random(0), horizon=10)
    msg = str(exc.value)
    assert "비결정" in msg
    assert "a" in msg and "b" in msg  # 동시 enabled 전이 id를 짚는다
    assert "pref" in msg  # 의도된 선택이면 pref 선언 안내(D20)
    assert "ludoforge bmc" in msg  # 대안 백엔드 안내
    assert "ludoforge prob" not in msg  # 제거된 명령 안내 없음(D23)


# ---------- 무작위 정책: 선택 표집 (D20) ----------


def _build_choice_set(pref_a: float | None, pref_b: float | None) -> RuleSet:
    """init(x==0)에서 a·b 두 전이가 동시 enabled인 선택 집합 모델을 만든다."""
    return RuleSet(
        variables=(Variable(name="x", type="int", min=0, max=5),),
        init="x == 0",
        transitions=(
            Transition(id="a", when="x == 0", pref=pref_a, outcomes=(Outcome(then="next.x == 1"),)),
            Transition(id="b", when="x == 0", pref=pref_b, outcomes=(Outcome(then="next.x == 2"),)),
        ),
    )


def test_choice_sampling_matches_declared_pref() -> None:
    """모든 co-enabled가 pref 선언 시 enabled끼리 정규화 표집 — 도달 분포가 pref(0.3)에 수렴."""
    rs = load_rule_file(FIXTURES / "policy_choice.lf")
    n = 4000
    a_count = sum(
        1 for s in range(n) if run_once(rs, random.Random(s), horizon=10).states[-1]["pick"] == "a"
    )
    frac = a_count / n
    # 기댓값 0.3, 3σ≈0.022(n=4000) — 여유 있게 0.03 이내.
    assert abs(frac - 0.3) < 0.03


def test_choice_sampling_is_reproducible() -> None:
    """선택 표집도 같은 seed → 동일 궤적(D19 재현성, RNG 추가 draw 1회는 결정적)."""
    rs = load_rule_file(FIXTURES / "policy_choice.lf")
    r1 = run_once(rs, random.Random(123), horizon=10)
    r2 = run_once(rs, random.Random(123), horizon=10)
    assert r1 == r2


def test_choice_set_with_missing_pref_rejected() -> None:
    """co-enabled에 pref 미선언(None)이 섞이면 거부 — 의도치 않은 가드 중첩 안전망(D20)."""
    rs = _build_choice_set(pref_a=0.5, pref_b=None)
    with pytest.raises(DtmcViolation):
        run_once(rs, random.Random(0), horizon=10)


def test_choice_set_with_zero_pref_sum_rejected() -> None:
    """모두 pref=0이면 정규화 불가 — outcome weight 합 0과 동형으로 거부(D20)."""
    rs = _build_choice_set(pref_a=0.0, pref_b=0.0)
    with pytest.raises(SimError, match="pref"):
        run_once(rs, random.Random(0), horizon=10)


# ---------- 상태 의존 pref/weight (D26) ----------


def test_urn_without_replacement_converges_to_closed_form() -> None:
    """비복원 추출(상태 의존 weight): 마지막 공이 빨강일 확률의 닫힌형 2/3에 수렴."""
    rs = load_rule_file(FIXTURES / "urn.lf")
    n = 4000
    hits = sum(
        1 for s in range(n) if run_once(rs, random.Random(s), horizon=10).states[-1]["last"] == "r"
    )
    # 기댓값 2/3, 3σ≈0.022(n=4000) — 여유 있게 0.03 이내.
    assert abs(hits / n - 2 / 3) < 0.03


def test_adaptive_pref_converges_to_state_ratio() -> None:
    """상태 식 pref: x=3에서 pick_a 확률 = 3/10 = 0.3에 수렴."""
    rs = load_rule_file(FIXTURES / "policy_adaptive.lf")
    n = 4000
    hits = sum(
        1 for s in range(n) if run_once(rs, random.Random(s), horizon=5).states[-1]["done"] == "a"
    )
    assert abs(hits / n - 0.3) < 0.03


def test_state_expr_run_is_reproducible() -> None:
    rs = load_rule_file(FIXTURES / "urn.lf")
    assert run_once(rs, random.Random(7), horizon=10) == run_once(rs, random.Random(7), horizon=10)


def _zero_sum_ruleset(weights: tuple[str, str]) -> RuleSet:
    """가드 없는 draw가 red=blue=0 상태에서도 enabled인 잘못된 모델(D26 가드 규율 위반)."""
    return RuleSet(
        variables=(
            Variable(name="red", type="int", min=0, max=2),
            Variable(name="blue", type="int", min=0, max=1),
        ),
        init="red == 0 and blue == 0",
        transitions=(
            Transition(
                id="draw",
                outcomes=(
                    Outcome(then="next.red == red - 1", weight=weights[0]),
                    Outcome(then="next.blue == blue - 1", weight=weights[1]),
                ),
            ),
        ),
    )


def test_weight_sum_zero_state_fails_loudly() -> None:
    """weight 합 0 상태 도달 = 가드 누락 — 조용히 덮지 않고 SimError(D26)."""
    rs = _zero_sum_ruleset(("red", "blue"))
    with pytest.raises(SimError, match="weight 합이 0"):
        run_once(rs, random.Random(0), horizon=5)


def test_negative_weight_evaluation_fails_loudly() -> None:
    rs = _zero_sum_ruleset(("red - 5", "blue + 1"))
    with pytest.raises(SimError, match="음수"):
        run_once(rs, random.Random(0), horizon=5)


# ---------- player 태그 소유 게이트 (D27) ----------

_TURN = Variable(name="turn", type="enum", values=("p1", "p2"))
_X = Variable(name="x", type="int", min=0, max=3)


def _race_ruleset(player_a: str | None, player_b: str | None) -> RuleSet:
    return RuleSet(
        variables=(_TURN, _X),
        init="turn == p1 and x == 0",
        transitions=(
            Transition(
                id="a",
                outcomes=(Outcome(then="next.x == 1"),),
                when="x == 0",
                pref=1.0,
                player=player_a,
            ),
            Transition(
                id="b",
                outcomes=(Outcome(then="next.x == 2"),),
                when="x == 0",
                pref=1.0,
                player=player_b,
            ),
        ),
    )


def test_mixed_ownership_choice_set_rejected() -> None:
    """서로 다른 플레이어의 전이가 co-enabled — 가드 실수이므로 명시 거부(D27)."""
    rs = _race_ruleset("p1", "p2")
    with pytest.raises(DtmcViolation, match="소유 혼성.*a\\(player=p1\\).*b\\(player=p2\\)"):
        run_once(rs, random.Random(0), horizon=5)


def test_tagged_and_untagged_mix_rejected() -> None:
    """태그 전이와 무소속 전이의 혼성도 모호하므로 거부(D27)."""
    rs = _race_ruleset("p1", None)
    with pytest.raises(DtmcViolation, match="소유 혼성.*무소속"):
        run_once(rs, random.Random(0), horizon=5)


def test_single_owner_choice_set_samples_as_before() -> None:
    """단일 소유 선택 집합은 기존 pref 표집과 동일하게 동작한다(D27 — 의미 불변)."""
    rs = _race_ruleset("p1", "p1")
    r = run_once(rs, random.Random(0), horizon=5)
    assert r.states[-1]["x"] in (1, 2)  # 정상 표집·거부 없음


def test_race_dungeon_greedy_beats_safe() -> None:
    """레이스 매치업(D27): 욕심(p1, 잠수 8:2)이 안전(p2, 2:8)을 이긴다 — 추정 답."""
    rs = load_rule_file(EXAMPLES / "dungeon_race.lf")
    n = 1500
    wins = {"p1": 0, "p2": 0}
    for s in range(n):
        r = run_once(rs, random.Random(s), horizon=300)
        w = r.states[-1]["winner"]
        if w in wins:
            wins[w] += 1
    assert wins["p1"] + wins["p2"] == n  # 항상 승자가 난다(흡수 종료)
    assert wins["p1"] / n > 0.55  # 기대 ~0.67 — 여유 있는 문턱(비플레이키)
    assert wins["p2"] / n > 0.20  # 기대 ~0.33 — 안전도 무시 못 할 승률
