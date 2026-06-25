"""BMC 백엔드(Phase 3): 전이 시스템(D12)을 k 스텝 언롤링해 Z3로 검사한다.

의미론은 decisions.md D15:
- **프레임 = 미변경 유지**: 전이 outcome이 `next.X`로 건드리지 않은 변수는 다음 상태에서
  값이 유지된다(`next.y == y`). PRISM 갱신 의미와 일치 → 확률 백엔드와 모델 공유.
- **정적 constraints = 모든 상태 불변식**: constraints와 domain min/max를 매 스텝 s_i에 적용한다.
- **확률 가중치 무시(weight-erasure)**: outcome들을 비결정 분기(Or)로 본다.
- **반복 심화**: 깊이 j=0..k마다 `init ∧ T_0..T_{j-1} ∧ φ(s_j)`를 따로 풀어 가장 짧은
  반례를 찾는다. 데드락으로 경로가 끊겨도 자연히 처리된다.

검사 kind(D12): reachable / invariant / no_deadlock. prob는 확률 백엔드 전용이라 건너뛴다.
"k까지 유지/미도달"은 증명이 아니라 **유계 결과**임을 리포트에 명시한다(k-bound 정직성).
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass
from typing import Any

import z3

from core.ir import Constraint, RuleSet
from logic.solver.translator import translate_expression

# enum sort 라벨을 프로세스 단위로 유일하게(같은 이름 재선언 시 z3가 예외, translator와 동일).
_sort_seq = itertools.count()

# `next.X`(다음 상태 참조)를 Name으로 치환할 때 쓰는 키 접두사. 식별자에 안 나올 sentinel을
# 써서 실제 변수명과 충돌하지 않게 한다(D15 — `next`는 전이 표현식의 예약어이기도 함).
_NEXT = "§next§"


def _next_key(var: str) -> str:
    return f"{_NEXT}{var}"


# ---------- 결과 자료구조 ----------


@dataclass(frozen=True)
class Step:
    """경로의 한 스텝 상태: 변수명 → 값(문자열화)."""

    values: dict[str, str]


@dataclass(frozen=True)
class Trace:
    """반례/도달 경로. `actions[i]`는 s_i→s_{i+1}에서 발생한 전이 id(len = steps-1)."""

    steps: tuple[Step, ...]
    actions: tuple[str, ...]


@dataclass(frozen=True)
class PropertyResult:
    """한 속성의 BMC 결과.

    status:
    - reachable:    "reachable"(+trace) | "unreachable_within_k" | "unknown"
    - invariant:    "holds_up_to_k" | "violated"(+trace) | "unknown"
    - no_deadlock:  "no_deadlock_up_to_k" | "deadlock"(+trace) | "unknown"
    """

    prop_id: str
    kind: str
    desc: str | None
    status: str
    depth: int | None = None
    trace: Trace | None = None
    detail: str | None = None


@dataclass(frozen=True)
class BmcReport:
    k: int
    results: tuple[PropertyResult, ...]
    skipped_other: tuple[str, ...]

    @property
    def has_violation(self) -> bool:
        """증명된 문제(불변식 위반 / 데드락)가 있는가 — 종료코드 1."""
        return any(r.status in ("violated", "deadlock") for r in self.results)

    @property
    def has_unconfirmed(self) -> bool:
        """k 한계로 미확인이거나 unknown인 속성이 있는가 — 종료코드 3."""
        return any(r.status in ("unreachable_within_k", "unknown") for r in self.results)


# ---------- BMC 엔진 ----------


def run_bmc(ruleset: RuleSet, k: int) -> BmcReport:
    """전이 시스템의 checks를 깊이 k까지 BMC로 검사한다."""
    return _Bmc(ruleset, k).run()


class _Bmc:
    def __init__(self, ruleset: RuleSet, k: int) -> None:
        self.rs = ruleset
        self.k = k
        self.vars = ruleset.variables
        self.transitions = ruleset.transitions

        # enum sort + 값 인코딩(스텝 무관, 한 번만).
        self.sorts: dict[str, tuple[Any, dict[str, Any]]] = {}
        for v in self.vars:
            if v.type == "enum":
                label = f"{v.name}__bmc{next(_sort_seq)}"
                sort, consts = z3.EnumSort(label, list(v.values))
                self.sorts[v.name] = (sort, dict(zip(v.values, consts, strict=True)))

        # 전역 유일 enum 값 → const(비교 밖 bare 값 해석용, translator와 동일 처리).
        counts: dict[str, int] = {}
        for _, enc in self.sorts.values():
            for val in enc:
                counts[val] = counts.get(val, 0) + 1
        self.unique_values: dict[str, Any] = {
            val: const
            for _, enc in self.sorts.values()
            for val, const in enc.items()
            if counts[val] == 1
        }

        # 스텝별 변수(0..k)와 action 변수(0..k-1)를 미리 만든다.
        self.svars: list[dict[str, Any]] = [self._make_step_vars(i) for i in range(k + 1)]
        self.actions: list[Any] = [z3.Int(f"action@{i}") for i in range(k)]

        # 미리 계산: 스텝별 상태 제약(0..k), init(스텝0), 전이 관계(0..k-1).
        self.state_cons: list[list[Any]] = [self._state_constraints(i) for i in range(k + 1)]
        self.init_con: Any | None = (
            translate_expression(_parse(ruleset.init), *self._state_ctx(0))
            if ruleset.init is not None
            else None
        )
        self.relations: list[Any] = [self._relation(i) for i in range(k)]

    # --- 변수·문맥 구성 ---

    def _make_step_vars(self, i: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for v in self.vars:
            name = f"{v.name}@{i}"
            if v.type == "int":
                out[v.name] = z3.Int(name)
            elif v.type == "real":
                out[v.name] = z3.Real(name)
            elif v.type == "bool":
                out[v.name] = z3.Bool(name)
            else:  # enum
                out[v.name] = z3.Const(name, self.sorts[v.name][0])
        return out

    def _enums_base(self) -> dict[str, dict[str, Any]]:
        return {name: enc for name, (_, enc) in self.sorts.items()}

    def _state_ctx(self, i: int) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """스텝 i의 단일 상태 표현식용 (symbols, enums)."""
        symbols: dict[str, Any] = {**self.svars[i], **self.unique_values}
        return symbols, self._enums_base()

    def _trans_ctx(self, i: int) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """스텝 i→i+1 전이 표현식용. next.X(치환된 Name)를 다음 스텝 변수로 잇는다."""
        symbols, enums = self._state_ctx(i)
        symbols = dict(symbols)
        enums = dict(enums)
        for v in self.vars:
            symbols[_next_key(v.name)] = self.svars[i + 1][v.name]
        for name in self.sorts:
            enums[_next_key(name)] = self.sorts[name][1]
        return symbols, enums

    # --- 제약 구성 ---

    def _state_constraints(self, i: int) -> list[Any]:
        """스텝 i가 합법 상태이기 위한 제약: domain 경계 + 모든 constraints(D15)."""
        cons: list[Any] = []
        for v in self.vars:
            zv = self.svars[i][v.name]
            if v.type in ("int", "real"):
                if v.min is not None:
                    cons.append(zv >= v.min)
                if v.max is not None:
                    cons.append(zv <= v.max)
        symbols, enums = self._state_ctx(i)
        for constraint in self.rs.constraints:
            cons.append(_rule_constraint(constraint, symbols, enums))
        return cons

    def _guards(self, i: int) -> list[Any]:
        """스텝 i에서 각 전이 가드의 진리값(현재 상태 기준)."""
        symbols, enums = self._state_ctx(i)
        out: list[Any] = []
        for t in self.transitions:
            out.append(
                translate_expression(_parse(t.when), symbols, enums)
                if t.when is not None
                else z3.BoolVal(True)
            )
        return out

    def _relation(self, i: int) -> Any:
        """스텝 i→i+1 전이 관계. action@i로 어느 전이가 발생했는지 인코딩(D15)."""
        guards = self._guards(i)
        tsym, tenums = self._trans_ctx(i)
        disj: list[Any] = []
        for idx, t in enumerate(self.transitions):
            outcome_terms: list[Any] = []
            for oc in t.outcomes:
                then_node = _NextRewriter().visit(_parse(oc.then))
                then_c = translate_expression(then_node, tsym, tenums)
                frame = self._frame(oc.then, i)
                outcome_terms.append(z3.And(then_c, *frame) if frame else then_c)
            oc_or = outcome_terms[0] if len(outcome_terms) == 1 else z3.Or(*outcome_terms)
            disj.append(z3.And(self.actions[i] == idx, guards[idx], oc_or))
        return z3.Or(*disj) if disj else z3.BoolVal(False)

    def _frame(self, then_expr: str, i: int) -> list[Any]:
        """outcome이 건드리지 않은 변수는 유지: next.y == y(D15)."""
        touched = _next_vars(then_expr)
        return [
            self.svars[i + 1][v.name] == self.svars[i][v.name]
            for v in self.vars
            if v.name not in touched
        ]

    # --- 풀이 ---

    def _solver_to_depth(self, j: int) -> z3.Solver:
        """init ∧ (상태제약 0..j) ∧ (전이 0..j-1)를 담은 solver."""
        s = z3.Solver()
        for i in range(j + 1):
            for c in self.state_cons[i]:
                s.add(c)
        if self.init_con is not None:
            s.add(self.init_con)
        for i in range(j):
            s.add(self.relations[i])
        return s

    def _check_reachable(self, that: str) -> PropertyResult | tuple[str, int, Trace]:
        for j in range(self.k + 1):
            s = self._solver_to_depth(j)
            s.add(translate_expression(_parse(that), *self._state_ctx(j)))
            r = s.check()
            if r == z3.sat:
                return "reachable", j, self._trace(s.model(), j)
            if r == z3.unknown:
                return _unknown(f"깊이 {j}에서 unknown")
        return _status("unreachable_within_k")

    def _check_invariant(self, that: str) -> PropertyResult | tuple[str, int, Trace]:
        for j in range(self.k + 1):
            s = self._solver_to_depth(j)
            s.add(z3.Not(translate_expression(_parse(that), *self._state_ctx(j))))
            r = s.check()
            if r == z3.sat:
                return "violated", j, self._trace(s.model(), j)
            if r == z3.unknown:
                return _unknown(f"깊이 {j}에서 unknown")
        return _status("holds_up_to_k")

    def _check_no_deadlock(self) -> PropertyResult | tuple[str, int, Trace]:
        for j in range(self.k + 1):
            guards = self._guards(j)
            enabled = z3.Or(*guards) if guards else z3.BoolVal(False)
            s = self._solver_to_depth(j)
            s.add(z3.Not(enabled))
            r = s.check()
            if r == z3.sat:
                return "deadlock", j, self._trace(s.model(), j)
            if r == z3.unknown:
                return _unknown(f"깊이 {j}에서 unknown")
        return _status("no_deadlock_up_to_k")

    def _trace(self, model: Any, j: int) -> Trace:
        steps = tuple(
            Step(
                {
                    v.name: str(model.eval(self.svars[i][v.name], model_completion=True))
                    for v in self.vars
                }
            )
            for i in range(j + 1)
        )
        actions = tuple(
            self.transitions[model.eval(self.actions[i], model_completion=True).as_long()].id
            for i in range(j)
        )
        return Trace(steps=steps, actions=actions)

    # --- 실행 ---

    def run(self) -> BmcReport:
        results: list[PropertyResult] = []
        skipped: list[str] = []
        for c in self.rs.checks:
            if c.kind == "distribution":
                skipped.append(c.id)  # distribution=sim 전용(D19)
                continue
            if c.kind == "reachable":
                outcome = self._check_reachable(c.that or "")
            elif c.kind == "invariant":
                outcome = self._check_invariant(c.that or "")
            else:  # no_deadlock
                outcome = self._check_no_deadlock()
            results.append(_result(c.id, c.kind, c.desc, outcome))
        return BmcReport(k=self.k, results=tuple(results), skipped_other=tuple(skipped))


# ---------- 헬퍼 ----------


def _parse(expr: str) -> ast.expr:
    return ast.parse(expr, mode="eval").body


def _rule_constraint(
    constraint: Constraint, symbols: dict[str, Any], enums: dict[str, dict[str, Any]]
) -> Any:
    then = translate_expression(_parse(constraint.then), symbols, enums)
    if constraint.when is not None:
        return z3.Implies(translate_expression(_parse(constraint.when), symbols, enums), then)
    return then


def _next_vars(expr: str) -> set[str]:
    """표현식이 `next.X`로 제약하는 변수명 집합."""
    return {
        n.attr
        for n in ast.walk(_parse(expr))
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "next"
    }


class _NextRewriter(ast.NodeTransformer):
    """`next.X`(Attribute)를 Name(_next_key(X))으로 치환해 번역기가 다룰 수 있게 한다."""

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        if isinstance(node.value, ast.Name) and node.value.id == "next":
            return ast.copy_location(ast.Name(id=_next_key(node.attr), ctx=ast.Load()), node)
        return self.generic_visit(node)


# 검사 메서드는 (status, depth, trace) 또는 PropertyResult(unknown/단순 status)를 돌려준다.
# 아래 헬퍼들이 그것을 최종 PropertyResult로 정규화한다.


def _status(status: str) -> PropertyResult:
    return PropertyResult(prop_id="", kind="", desc=None, status=status)


def _unknown(detail: str) -> PropertyResult:
    return PropertyResult(prop_id="", kind="", desc=None, status="unknown", detail=detail)


def _result(
    pid: str, kind: str, desc: str | None, outcome: PropertyResult | tuple[str, int, Trace]
) -> PropertyResult:
    if isinstance(outcome, tuple):
        status, depth, trace = outcome
        return PropertyResult(
            prop_id=pid, kind=kind, desc=desc, status=status, depth=depth, trace=trace
        )
    return PropertyResult(
        prop_id=pid, kind=kind, desc=desc, status=outcome.status, detail=outcome.detail
    )


# ---------- 리포트 ----------


def format_bmc_report(report: BmcReport) -> str:
    """BmcReport를 한국어 리포트로 변환한다(k-bound 정직성 명시, D15)."""
    lines: list[str] = [f"BMC 검사 (깊이 한계 k={report.k})", ""]
    if not report.results and not report.skipped_other:
        lines.append("검사할 항목(checks)이 없습니다.")
        return "\n".join(lines)

    for i, r in enumerate(report.results, start=1):
        lines.append(_format_result(i, r))
    if report.skipped_other:
        lines.append("")
        lines.append(
            "ℹ️ 다른 백엔드 전용 검사라 건너뜀(distribution=sim): "
            + ", ".join(report.skipped_other)
        )
    return "\n".join(lines)


_LABEL: dict[str, str] = {
    "reachable": "✅ 도달 가능",
    "unreachable_within_k": "⚠️ k까지 도달 불가(미확인)",
    "holds_up_to_k": "✅ k까지 위반 없음",
    "violated": "❌ 불변식 위반",
    "no_deadlock_up_to_k": "✅ k까지 데드락 없음",
    "deadlock": "❌ 데드락 도달",
    "unknown": "⚠️ 판단 불가(unknown)",
}

_KBOUND_NOTE: dict[str, str] = {
    "unreachable_within_k": "    (k 한계 — 더 깊은 곳은 미검증. 진짜 도달 불가 증명 아님.)",
    "holds_up_to_k": "    (k 한계 — k 스텝까지만 보장. 무한 지평 증명 아님.)",
    "no_deadlock_up_to_k": "    (k 한계 — k 스텝까지만 보장.)",
}


def _format_result(index: int, r: PropertyResult) -> str:
    desc = f" — {r.desc}" if r.desc else ""
    head = f"[{index}] 검사 '{r.prop_id}' ({r.kind}){desc}: {_LABEL.get(r.status, r.status)}"
    parts = [head]
    if r.depth is not None:
        parts[0] += f" (깊이 {r.depth})"
    if r.status in _KBOUND_NOTE:
        parts.append(_KBOUND_NOTE[r.status])
    if r.detail:
        parts.append(f"    {r.detail}")
    if r.trace is not None:
        parts.append(_format_trace(r.trace))
    return "\n".join(parts)


def _format_trace(trace: Trace) -> str:
    lines: list[str] = ["    경로:"]
    for i, step in enumerate(trace.steps):
        state = ", ".join(f"{n}={v}" for n, v in step.values.items())
        lines.append(f"      s{i}: {state}")
        if i < len(trace.actions):
            lines.append(f"        --[{trace.actions[i]}]-->")
    return "\n".join(lines)
