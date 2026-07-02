"""sim 엔진(Phase 1, D19): IR 전이 시스템을 표집으로 시뮬레이션한다.

공유 IR은 이미 guarded-command 전이 시스템(D12)이라, sim은 그 *인터프리터*다. 의미론은
BMC(D15)와 같은 골격을 공유하되 해석만 다르다:

- **프레임 = 미변경 유지(D15):** outcome이 `next.X`로 건드리지 않은 변수는 다음 상태에서
  값이 유지된다(`apply_outcome`가 현재 상태를 복사 후 touched 변수만 덮어쓴다).
- **비결정 해소(D19→D20):** 도달 상태에 enabled 전이가 2개 이상이면, 모든 전이가 `pref`
  (플레이어 선호도)를 **명시한 경우에만** enabled끼리 정규화해 무작위 정책으로 표집한다
  (D20). 하나라도 미선언(None)이 섞이면 의도치 않은 가드 중첩으로 보고 `DtmcViolation`으로
  **명시적 거부**한다(그 비결정의 최선/최악은 BMC `ludoforge bmc` 몫). enabled가
  1개면 선택이 없어 rng를 소비하지 않는다(기존 DTMC 모델의 재현성·비트 동일 보존).
- **2단 표집:** ① enabled 전이를 `pref`로 골라(정책) → ② 그 전이의 outcome을 weight로
  표집한다(환경 우연, 합이 1이 아니면 정규화). weight는 D12 의미, `pref`는 D20 의미로 구분.

표현식은 `ast.parse(mode="eval")` 후 화이트리스트 노드만 **파이썬 값으로 평가**한다 — Z3
번역(translator)·PRISM 렌더(prism_gen)와 달리 *평가기*이지만 `eval`은 절대 쓰지 않는다(§7).
enum 값은 불투명 문자열로 다룬다(변수=문자열, bare 값 이름=자기 문자열 → 등식 비교).

Phase 1 범위: 1 run 표집과 DTMC 게이트만. 집계·신뢰구간(aggregate)·multiprocessing
(runner)·초기 자유변수 sweep은 후속 Phase다. 현재는 init이 **모든 변수를 고정**해야 한다.
"""

from __future__ import annotations

import ast
import itertools
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from core.ir import RuleSet, Transition

# 상태: 변수명 → 값. int=파이썬 int, real=float, bool=bool, enum=값 문자열.
State = dict[str, Any]


class SupportsRandom(Protocol):
    """rng 추상 — `random()`만 요구한다. stdlib random.Random·numpy Generator 모두 만족."""

    def random(self) -> float: ...


class SimError(Exception):
    """sim 실행 실패의 기반 예외. 메시지에 위치·원인을 담는다(예외를 삼키지 않는다, §7)."""


class DtmcViolation(SimError):
    """도달 상태에서 enabled 전이가 2개 이상 — DTMC 위배(D19). 사람이 읽는 안내를 담는다."""


class EvalError(SimError):
    """표현식 평가 실패(허용 외 노드·미정의 이름 등)."""


@dataclass(frozen=True)
class RunResult:
    """1회 시뮬레이션 결과.

    - states:     방문 상태열 s0..s_n (n = 스텝 수).
    - actions:    각 스텝에서 발생한 전이 id (len = len(states) - 1).
    - terminated: 자연 종료했는가 — enabled 전이가 0개(막다른 상태)이거나 **흡수 상태**
      (유일 전이의 모든 outcome이 상태를 그대로 두는 fixpoint, 예 won_absorb)에 도달.
    - truncated:  자연 종료 전에 지평 H에 걸려 잘렸는가(절단 — 추정 편향 보고용, D19).
    """

    states: tuple[State, ...]
    actions: tuple[str, ...]
    terminated: bool
    truncated: bool


# ---------- 표현식 평가기 (화이트리스트, eval 미사용) ----------

_CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

# 허용 함수 호출 → 파이썬 내장(가변 인자). 효과 전용 제한은 schema가 강제한다(generic + gate).
_FUNCS: dict[str, Callable[..., Any]] = {"min": min, "max": max}


def evaluate(node: ast.AST, env: dict[str, Any]) -> Any:
    """화이트리스트 ast 노드를 파이썬 값으로 평가한다. 그 외는 EvalError.

    env는 변수 현재값 + enum 값 상수(값 이름 → 자기 문자열)를 합친 심볼표다.
    """
    if isinstance(node, ast.BoolOp):
        parts = (evaluate(v, env) for v in node.values)
        if isinstance(node.op, ast.And):
            return all(parts)
        if isinstance(node.op, ast.Or):
            return any(parts)
        raise EvalError("지원하지 않는 불리언 연산자")

    if isinstance(node, ast.UnaryOp):
        operand = evaluate(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise EvalError("지원하지 않는 단항 연산자")

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise EvalError(f"지원하지 않는 산술 연산자: {type(node.op).__name__}")
        return op(evaluate(node.left, env), evaluate(node.right, env))

    if isinstance(node, ast.Compare):
        left = evaluate(node.left, env)
        for op_node, comp in zip(node.ops, node.comparators, strict=True):
            fn = _CMP_OPS.get(type(op_node))
            if fn is None:
                raise EvalError(f"지원하지 않는 비교 연산자: {type(op_node).__name__}")
            right = evaluate(comp, env)
            if not fn(left, right):
                return False
            left = right  # 연쇄 비교(1 <= x <= 3)
        return True

    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Name) or func.id not in _FUNCS:
            raise EvalError(f"지원하지 않는 함수 호출: '{ast.unparse(node)}' (허용: min, max)")
        if node.keywords or len(node.args) < 2:
            raise EvalError(f"'{func.id}'은(는) 2개 이상의 위치 인자가 필요합니다")
        return _FUNCS[func.id](*(evaluate(a, env) for a in node.args))

    if isinstance(node, ast.Name):
        if node.id not in env:
            raise EvalError(f"미정의 심볼: '{node.id}'")
        return env[node.id]

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (bool, int, float)):
            return node.value
        raise EvalError(f"지원하지 않는 상수: {node.value!r} (정수/실수/불리언만)")

    raise EvalError(f"지원하지 않는 표현식 요소: {type(node).__name__}")


# ---------- 전이 시스템 인터프리터 ----------


def uses_policy(ruleset: RuleSet) -> bool:
    """모델이 무작위 정책(`pref`)으로 플레이어 선택을 해소하는가(D20).

    전이 하나라도 `pref`를 명시했으면 True — 리포트가 "주어진 정책 하의 추정 · Pmax 아님"
    라벨을 조건부로 띄울지 판단하는 신호다(선택 없는 순수 DTMC엔 정책 개념이 없다).
    """
    return any(t.pref is not None for t in ruleset.transitions)


def enum_constants(ruleset: RuleSet) -> dict[str, Any]:
    """enum 값 이름 → 자기 문자열 상수표. bare 값(`role == rogue`의 `rogue`) 해석용."""
    out: dict[str, Any] = {}
    for v in ruleset.variables:
        if v.type == "enum":
            for value in v.values:
                out[value] = value
    return out


def _pinned_state(ruleset: RuleSet, constants: dict[str, Any]) -> State:
    """init 술어가 고정하는 변수만 담은 부분 상태. 미고정 변수는 빠진다(검사 없음).

    init은 `var == 값` 등식의 and 결합만 지원한다. sim은 `constraints`(상태 불변식)를
    적용하지 않으므로, 던전!의 win_gold처럼 constraints로 파생되는 변수는 여기서 안 잡힌다
    (sim에선 init이나 sweep으로 직접 고정해야 한다 — constraints 연동은 Phase 4).
    """
    var_names = {v.name for v in ruleset.variables}
    state: State = {}
    if ruleset.init is not None:
        for conj in _conjuncts(_parse(ruleset.init)):
            name, rhs = _init_assignment(conj, var_names)
            state[name] = evaluate(rhs, constants)
    return state


def initial_state(
    ruleset: RuleSet, constants: dict[str, Any], overrides: dict[str, Any] | None = None
) -> State:
    """init + overrides(sweep) + constraints 전파에서 완전한 초기 상태를 도출한다.

    overrides는 sweep이 채우는 자유 enum/bool 값이다. 이어서 `constraints`(상태 불변식)로
    파생되는 변수(예 던전!의 `role==X → win_gold==V`)를 전파해 채운다(D19 Phase 4 — PRISM이
    constraints를 init에 인코딩하는 것과 대응). 적용 후에도 빠진 변수가 있으면 오류.
    """
    state = _pinned_state(ruleset, constants)
    if overrides:
        state.update(overrides)
    _propagate_constraints(ruleset, state, constants)
    missing = [v.name for v in ruleset.variables if v.name not in state]
    if missing:
        raise SimError(
            f"init이 변수 {missing}를 고정하지 않습니다 — enum/bool 자유변수는 sweep이 "
            f"채우고(simulate), int/real은 init이나 constraints로 고정해야 합니다(D19)."
        )
    return state


def _propagate_constraints(ruleset: RuleSet, state: State, constants: dict[str, Any]) -> None:
    """constraints의 `when → then`을 fixpoint까지 전파해 파생 변수를 채운다.

    아직 평가 불가한(미설정 변수 참조) constraint는 다음 라운드로 미룬다. `then`이 `var == 값`
    등식이고 그 var가 미설정이면 값을 채운다(이미 설정됐는데 충돌하면 오류). 등식이 아닌
    then(부등식 등)은 초기값 파생에 못 쓰므로 건너뛴다(불변식 검사는 sim 범위 밖, 후속).
    """
    var_names = {v.name for v in ruleset.variables}
    changed = True
    while changed:
        changed = False
        for con in ruleset.constraints:
            if con.when is not None:
                try:
                    active = bool(evaluate(_parse(con.when), {**constants, **state}))
                except EvalError:
                    continue  # when이 미설정 변수를 참조 — 다음 라운드로
                if not active:
                    continue
            for conj in _conjuncts(_parse(con.then)):
                pair = _eq_pair(conj)
                if pair is None:
                    continue  # 등식 아님 → 파생 불가(건너뜀)
                target = _equality_target(pair, var_names)
                if target is None:
                    continue
                var, rhs = target
                try:
                    value = evaluate(rhs, {**constants, **state})
                except EvalError:
                    continue
                if var not in state:
                    state[var] = value
                    changed = True
                elif state[var] != value:
                    raise SimError(
                        f"constraint '{con.id}'가 초기값 충돌을 일으킵니다: "
                        f"{var}={state[var]} vs {value}."
                    )


def sweep_configs(ruleset: RuleSet, constants: dict[str, Any]) -> list[dict[str, Any]]:
    """init이 고정하지 않은 자유 enum/bool 변수의 데카르트 곱 설정 목록(D19 sweep).

    자유변수가 없으면 [{}](단일 설정). init이 고정하거나 constraints로 파생되는 변수는
    제외한다(파생 변수 예: win_gold). 남은 자유 int/real은 sweep 불가 — init 고정을 요구한다
    (이산 sweep만; 연속/큰 범위 초기값은 의미가 모호하다).
    """
    pinned = _pinned_state(ruleset, constants)
    derivable = _constraint_targets(ruleset)  # constraints로 채워지는 변수는 sweep 안 함
    domains: list[list[tuple[str, Any]]] = []
    for v in ruleset.variables:
        if v.name in pinned or v.name in derivable:
            continue
        if v.type == "enum":
            domains.append([(v.name, val) for val in v.values])
        elif v.type == "bool":
            domains.append([(v.name, True), (v.name, False)])
        else:
            raise SimError(
                f"자유 init 변수 '{v.name}'({v.type})는 sweep할 수 없습니다 — sweep은 "
                f"enum/bool만 지원합니다(D19). int/real은 init에서 고정하세요."
            )
    if not domains:
        return [{}]
    return [dict(combo) for combo in itertools.product(*domains)]


def eval_expr(expr: str, state: State, constants: dict[str, Any]) -> Any:
    """단일 표현식을 현재 상태에서 평가한다(집계가 체크 술어·수치식을 평가하는 진입점)."""
    return evaluate(_parse(expr), {**constants, **state})


def _constraint_targets(ruleset: RuleSet) -> set[str]:
    """constraints의 then 등식에서 값이 채워지는(파생되는) 변수명 집합(sweep 제외용)."""
    var_names = {v.name for v in ruleset.variables}
    targets: set[str] = set()
    for con in ruleset.constraints:
        for conj in _conjuncts(_parse(con.then)):
            pair = _eq_pair(conj)
            if pair is None:
                continue
            t = _equality_target(pair, var_names)
            if t is not None:
                targets.add(t[0])
    return targets


def enabled_transitions(
    ruleset: RuleSet, state: State, constants: dict[str, Any]
) -> list[Transition]:
    """현재 상태에서 가드(`when`)가 참인 전이 목록. 가드 없으면 항상 enabled."""
    env = {**constants, **state}
    return [t for t in ruleset.transitions if t.when is None or bool(evaluate(_parse(t.when), env))]


def apply_outcome(then: str, state: State, constants: dict[str, Any]) -> State:
    """outcome.then(`next.X == 식`의 and 결합)을 적용한다. 프레임=미변경 유지(D15).

    RHS는 **현재 상태**에서 평가한다(`next.gold == gold + 1`의 gold는 현재값).
    """
    env = {**constants, **state}
    new_state: State = dict(state)  # 미제약 변수는 그대로 유지(프레임, D15)
    for conj in _conjuncts(_parse(then)):
        var, rhs = _next_assignment(conj)
        new_state[var] = evaluate(rhs, env)
    return new_state


def run_once(
    ruleset: RuleSet, rng: SupportsRandom, horizon: int, *, initial: State | None = None
) -> RunResult:
    """초기 상태에서 지평 H까지(또는 자연 종료까지) 1회 표집한다.

    매 스텝 enabled 전이를 모아 DTMC 게이트(enabled>1이면 거부)를 통과한 뒤, 단일 전이의
    outcome을 weight로 표집해 다음 상태로 간다. `initial`을 주면 그 상태에서 시작한다
    (sweep 설정별 시작 상태를 simulate가 미리 만들어 넘긴다).
    """
    constants = enum_constants(ruleset)
    state = initial if initial is not None else initial_state(ruleset, constants)
    states: list[State] = [state]
    actions: list[str] = []

    for _ in range(horizon):
        enabled = enabled_transitions(ruleset, state, constants)
        if not enabled:
            return RunResult(tuple(states), tuple(actions), terminated=True, truncated=False)
        t = _select_transition(enabled, state, constants, rng)
        if _is_absorbing(t, state, constants):
            # 흡수 상태(모든 outcome이 상태를 유지) — 더 펼쳐도 stutter뿐이라 자연 종료로 본다.
            return RunResult(tuple(states), tuple(actions), terminated=True, truncated=False)
        then = _sample_outcome(t, state, constants, rng)
        state = apply_outcome(then, state, constants)
        states.append(state)
        actions.append(t.id)

    return RunResult(tuple(states), tuple(actions), terminated=False, truncated=True)


# ---------- 내부 헬퍼 ----------


def _parse(expr: str) -> ast.expr:
    return ast.parse(expr, mode="eval").body


def _conjuncts(node: ast.expr) -> list[ast.expr]:
    """and 결합을 펼쳐 conjunct 목록으로. and가 아니면 단일 원소."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return list(node.values)
    return [node]


def _eq_pair(node: ast.expr) -> tuple[ast.expr, ast.expr] | None:
    """단일 `a == b` 비교면 (a, b)를, 아니면 None을 돌려준다."""
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
        return node.left, node.comparators[0]
    return None


def _equality_target(
    pair: tuple[ast.expr, ast.expr], var_names: set[str]
) -> tuple[str, ast.expr] | None:
    """등식 (a, b)에서 한 변이 선언된 변수명이면 (변수명, 반대편 값 노드), 아니면 None."""
    left, right = pair
    if isinstance(left, ast.Name) and left.id in var_names:
        return left.id, right
    if isinstance(right, ast.Name) and right.id in var_names:
        return right.id, left
    return None


def _init_assignment(node: ast.expr, var_names: set[str]) -> tuple[str, ast.expr]:
    """init 등식 `var == 값`에서 (변수명, 값 노드). 변수는 var_names로 판별(enum 값과 구분)."""
    pair = _eq_pair(node)
    if pair is None:
        raise SimError("init 술어는 'var == 값' 등식의 and 결합만 지원합니다(Phase 1).")
    target = _equality_target(pair, var_names)
    if target is None:
        raise SimError("init 등식의 한 변은 선언된 변수명이어야 합니다.")
    return target


def _next_assignment(node: ast.expr) -> tuple[str, ast.expr]:
    """전이 then 등식 `next.X == 식`에서 (X, 식 노드)를 뽑는다."""
    pair = _eq_pair(node)
    if pair is None:
        raise EvalError("전이 then은 'next.X == 식' 등식(또는 그 and 결합)이어야 합니다.")
    for a, b in (pair, (pair[1], pair[0])):
        if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "next":
            return a.attr, b
    raise EvalError("전이 then의 한 변은 next.<변수>여야 합니다.")


def _is_absorbing(t: Transition, state: State, constants: dict[str, Any]) -> bool:
    """전이 t가 상태 s에서 흡수(모든 outcome이 s를 그대로 둠)인가 — fixpoint 종료 판정."""
    return all(apply_outcome(oc.then, state, constants) == state for oc in t.outcomes)


def _rate_value(value: float | str, env: dict[str, Any], what: str) -> float:
    """weight/pref 값을 수치로 만든다 — 상수는 그대로, 상태 식(str, D26)은 현재 상태에서 평가.

    음수는 모델 오류로 크게 실패한다. enabledness는 가드 단독이므로(D26) 음수·합0이 나오는
    상태는 가드로 배제하는 것이 모델러 책임이다.
    """
    if isinstance(value, str):
        result = evaluate(_parse(value), env)
        if isinstance(result, bool) or not isinstance(result, (int, float)):
            raise SimError(f"{what} 식 {value!r}이 수치가 아닌 값으로 평가됐습니다: {result!r}")
        value = float(result)
    if value < 0:
        raise SimError(f"{what}가 음수입니다: {value} — 그런 상태는 가드(when)로 배제하세요(D26).")
    return float(value)


def _select_transition(
    enabled: list[Transition], state: State, constants: dict[str, Any], rng: SupportsRandom
) -> Transition:
    """enabled 전이 중 하나를 고른다(무작위 정책, D20).

    - enabled 1개: 그 전이(선택 없음 → **rng 미소비**로 기존 DTMC 모델의 재현성·비트 동일 유지).
    - enabled 2개 이상: 모든 전이가 `pref`를 명시했으면 enabled끼리 정규화해 표집하고,
      하나라도 미선언(None)이 섞이면 의도치 않은 가드 중첩으로 보고 `DtmcViolation` 거부
      (명시적 opt-in 안전망). `pref` 합이 0이면 정규화 불가로 SimError.
    - 상태 식 pref(D26)는 현재 상태에서 평가한다(음수면 SimError).
    """
    if len(enabled) == 1:
        return enabled[0]
    if any(t.pref is None for t in enabled):
        raise _dtmc_violation(state, enabled)
    env = {**constants, **state}
    prefs = [
        _rate_value(t.pref, env, f"전이 '{t.id}'의 pref")
        for t in enabled
        if t.pref is not None  # 위에서 None 배제 — mypy 좁히기용
    ]
    total = sum(prefs)
    if total <= 0:
        ids = ", ".join(t.id for t in enabled)
        raise SimError(f"선택 집합 {{{ids}}}의 pref 합이 0입니다 — 정규화할 수 없습니다.")
    threshold = rng.random() * total
    acc = 0.0
    for t, p in zip(enabled, prefs, strict=True):
        acc += p
        if threshold < acc:
            return t
    return enabled[-1]  # 부동소수 오차 안전망


def _sample_outcome(
    t: Transition, state: State, constants: dict[str, Any], rng: SupportsRandom
) -> str:
    """단일 전이의 outcome을 weight로 표집해 then 문자열을 돌려준다(가중치 정규화).

    상태 식 weight(D26)는 전이 직전 상태에서 평가한다 — 남은 덱 구성에 비례하는 비복원
    추출 등. outcome이 1개면 표집이 없어 rng를 소비하지 않는다(재현성 보존).
    """
    if len(t.outcomes) == 1:
        return t.outcomes[0].then
    env = {**constants, **state}
    weights = [
        _rate_value(oc.weight, env, f"전이 '{t.id}' outcomes[{i}]의 weight")
        for i, oc in enumerate(t.outcomes)
    ]
    total = sum(weights)
    if total <= 0:
        raise SimError(
            f"전이 '{t.id}'의 weight 합이 0입니다 — 그런 상태는 가드(when)로 배제하세요(D26)."
        )
    threshold = rng.random() * total
    acc = 0.0
    for oc, w in zip(t.outcomes, weights, strict=True):
        acc += w
        if threshold < acc:
            return oc.then
    return t.outcomes[-1].then  # 부동소수 오차 안전망


def _dtmc_violation(state: State, enabled: list[Transition]) -> DtmcViolation:
    state_str = ", ".join(f"{k}={v}" for k, v in state.items())
    ids = ", ".join(t.id for t in enabled)
    return DtmcViolation(
        f"비결정(D19·D20): 상태 {{{state_str}}}에서 가드가 동시에 참인 전이가 "
        f"{len(enabled)}개입니다: {ids}. 가드를 상호배타로 만들거나, 의도된 플레이어 선택이면 "
        f"co-enabled 전이 *모두*에 pref를 선언하세요(무작위 정책, D20). 그 비결정의 최선/최악은 "
        f"BMC(ludoforge bmc)로 검사합니다."
    )
