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
base가 k까지 통과하면 **k-귀납**(D25: init 없는 합법 상태열에서 φ(s_0..s_{j-1}) ∧ ¬φ(s_j)가
unsat)으로 무한 지평 증명을 시도한다 — 성공 시 증명으로 승격, 비귀납/unknown이면 유계 결과
유지(증명으로 뭉개지 않음).
"""

from __future__ import annotations

import ast
import itertools
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import z3

from core.ghost import erase_ghosts, ghost_names
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
    - reachable:    "reachable"(+trace) | "unreachable"(도달 불가 확정, D25)
                    | "unreachable_within_k" | "unknown"
    - invariant:    "holds"(무한 지평 증명, D25) | "holds_up_to_k" | "violated"(+trace)
                    | "unknown"
    - no_deadlock:  "no_deadlock"(무한 지평 증명, D25) | "no_deadlock_up_to_k"
                    | "deadlock"(+trace) | "unknown"
    """

    prop_id: str
    kind: str
    desc: str | None
    status: str
    depth: int | None = None
    trace: Trace | None = None
    detail: str | None = None


# 상태 → 종료코드 분할의 단일 소스(has_violation·has_unconfirmed·counts가 공유).
_VIOLATION_STATUSES = frozenset({"violated", "deadlock", "unreachable"})
_UNCONFIRMED_STATUSES = frozenset({"unreachable_within_k", "unknown"})


@dataclass(frozen=True)
class BmcReport:
    k: int
    results: tuple[PropertyResult, ...]
    skipped_other: tuple[str, ...]
    # ghost 서술 변수(D31) — 상태공간에서 제거하고 검사했음을 각주로 명시(조용히 숨기지 않음).
    erased_ghosts: tuple[str, ...] = ()

    @property
    def has_violation(self) -> bool:
        """증명된 문제(불변식 위반 / 데드락 / 도달 불가 확정)가 있는가 — 종료코드 1.

        `unreachable`은 reachable 검사의 **실패 확정**(어떤 깊이에서도 불가, D25 비준)이라
        "아직 k가 작아 미도달"(미확인, 종료코드 3)과 구분해 위반으로 취급한다."""
        return any(r.status in _VIOLATION_STATUSES for r in self.results)

    @property
    def has_unconfirmed(self) -> bool:
        """k 한계로 미확인이거나 unknown인 속성이 있는가 — 종료코드 3."""
        return any(r.status in _UNCONFIRMED_STATUSES for r in self.results)

    def counts(self) -> dict[str, int]:
        """상태별 개수(요약 라벨용) — 종료코드 분할과 동일 기준: 위반/미확인/그 외(=증명·통과).
        skipped는 다른 백엔드 전용이라 건너뛴 검사 수다(증명 대상 아님)."""
        violated = sum(1 for r in self.results if r.status in _VIOLATION_STATUSES)
        unconfirmed = sum(1 for r in self.results if r.status in _UNCONFIRMED_STATUSES)
        return {
            "proven": len(self.results) - violated - unconfirmed,
            "violated": violated,
            "unconfirmed": unconfirmed,
            "skipped": len(self.skipped_other),
        }


# ---------- BMC 엔진 ----------


def run_bmc(ruleset: RuleSet, k: int) -> BmcReport:
    """전이 시스템의 checks를 깊이 k까지 BMC로 검사한다.

    ghost 서술 변수(D31)는 상태공간에서 제거하고 검사한다(erase 후 소비 — 단방향 의존을
    schema가 보장하므로 비-ghost 의미는 비트 동일). 제거 사실은 리포트 각주로 남는다."""
    dropped = ghost_names(ruleset)
    report = _Bmc(erase_ghosts(ruleset), k).run()
    return replace(report, erased_ghosts=dropped) if dropped else report


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

    def _solver_span(self, j: int, anchored: bool = True) -> z3.Solver:
        """상태열 s_0..s_j의 제약을 담은 solver: (상태제약 0..j) ∧ (전이 0..j-1).

        anchored=True면 s_0에 init을 건다(기존 BMC base). False면 init 없는 임의 합법
        상태열 — k-귀납 스텝 검사용(D25)."""
        s = z3.Solver()
        for i in range(j + 1):
            for c in self.state_cons[i]:
                s.add(c)
        if anchored and self.init_con is not None:
            s.add(self.init_con)
        for i in range(j):
            s.add(self.relations[i])
        return s

    def _check_reachable(self, that: str) -> PropertyResult | tuple[str, int, Trace]:
        for j in range(self.k + 1):
            s = self._solver_span(j)
            s.add(translate_expression(_parse(that), *self._state_ctx(j)))
            r = s.check()
            if r == z3.sat:
                return "reachable", j, self._trace(s.model(), j)
            if r == z3.unknown:
                return _unknown(f"깊이 {j}에서 unknown")

        # k까지 미도달 → ¬that을 불변식으로 귀납해 성공하면 도달 불가 확정(D25).
        def not_that(i: int) -> Any:
            return z3.Not(translate_expression(_parse(that), *self._state_ctx(i)))

        return self._conclude_bounded(
            "unreachable",
            "unreachable_within_k",
            not_that,
            proved_note="¬that의 k-귀납으로 도달 불가 확정",
        )

    def _check_invariant(self, that: str) -> PropertyResult | tuple[str, int, Trace]:
        for j in range(self.k + 1):
            s = self._solver_span(j)
            s.add(z3.Not(translate_expression(_parse(that), *self._state_ctx(j))))
            r = s.check()
            if r == z3.sat:
                return "violated", j, self._trace(s.model(), j)
            if r == z3.unknown:
                return _unknown(f"깊이 {j}에서 unknown")

        def phi(i: int) -> Any:
            return translate_expression(_parse(that), *self._state_ctx(i))

        return self._conclude_bounded("holds", "holds_up_to_k", phi)

    def _induction(self, phi: Callable[[int], Any]) -> tuple[int | None, bool]:
        """k-귀납 스텝(D25): init 없는 합법 상태열 s_0..s_j에서 귀납 가설 φ(s_0..s_{j-1})
        하에 ¬φ(s_j)가 unsat인 최소 j를 찾는다(j=0은 가설 없이 모든 합법 상태 검사).

        반환: (증명된 귀납 깊이 j 또는 None, 스텝 검사 중 unknown 발생 여부)."""
        saw_unknown = False
        for j in range(self.k + 1):
            s = self._solver_span(j, anchored=False)
            for i in range(j):
                s.add(phi(i))
            s.add(z3.Not(phi(j)))
            r = s.check()
            if r == z3.unsat:
                return j, saw_unknown
            if r == z3.unknown:
                saw_unknown = True
        return None, saw_unknown

    def _conclude_bounded(
        self,
        proved_status: str,
        bounded_status: str,
        phi: Callable[[int], Any],
        proved_note: str = "k-귀납으로 증명",
    ) -> PropertyResult:
        """base가 k까지 통과한 속성을 k-귀납(D25)으로 무한 지평 증명 시도 후 결론짓는다.

        증명되면 proved_status(+최소 귀납 깊이), 비귀납/unknown이면 bounded_status에 사유를
        남긴다 — 절대 증명으로 승격하지 않는다(정직성)."""
        proved_j, saw_unknown = self._induction(phi)
        if proved_j is not None:
            return _status(proved_status, detail=f"{proved_note}(귀납 깊이 j={proved_j})")
        detail = "k-귀납 실패(k 내 비귀납) — 귀납 반례는 도달 가능성을 보장하지 않음"
        if saw_unknown:
            detail += " · 일부 스텝 검사 unknown"
        return _status(bounded_status, detail=detail)

    def _check_no_deadlock(self) -> PropertyResult | tuple[str, int, Trace]:
        for j in range(self.k + 1):
            guards = self._guards(j)
            enabled = z3.Or(*guards) if guards else z3.BoolVal(False)
            s = self._solver_span(j)
            s.add(z3.Not(enabled))
            r = s.check()
            if r == z3.sat:
                return "deadlock", j, self._trace(s.model(), j)
            if r == z3.unknown:
                return _unknown(f"깊이 {j}에서 unknown")

        # φ = "어떤 가드든 enabled". 전이 관계가 s_0..s_{j-1}의 발화를 강제하므로
        # ¬enabled(s_j) unsat 검사와 동형이다(D25).
        def enabled_phi(i: int) -> Any:
            guards = self._guards(i)
            return z3.Or(*guards) if guards else z3.BoolVal(False)

        return self._conclude_bounded("no_deadlock", "no_deadlock_up_to_k", enabled_phi)

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


def _status(status: str, detail: str | None = None) -> PropertyResult:
    return PropertyResult(prop_id="", kind="", desc=None, status=status, detail=detail)


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
            "ℹ️ 다른 백엔드 전용 검사라 건너뜀(distribution=sim): " + ", ".join(report.skipped_other)
        )
    if report.erased_ghosts:
        lines.append("")
        lines.append(
            "ℹ️ ghost 서술 변수는 상태공간에서 제거하고 검사했습니다(D31 — sim 전용 서술): "
            + ", ".join(report.erased_ghosts)
        )
    return "\n".join(lines)


_LABEL: dict[str, str] = {
    "reachable": "✅ 도달 가능",
    "unreachable": "❌ 도달 불가 확정(무한 지평, k-귀납)",
    "unreachable_within_k": "⚠️ k까지 도달 불가(미확인)",
    "holds": "✅ 불변식 증명(무한 지평, k-귀납)",
    "holds_up_to_k": "✅ k까지 위반 없음",
    "violated": "❌ 불변식 위반",
    "no_deadlock": "✅ 데드락 없음 증명(무한 지평, k-귀납)",
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
