"""검사 로직(S5): D3/D4 — Optimize 기반 도달성 검사.

모순 정의(D3): "기획자가 합법이라 여기는 상태를 룰들이 봉쇄한다."
검사 방법(D4): 각 enum 값 조합을 고정한 뒤, **독립 변수**(then에서 `var == ...`로
값이 결정되지 않는 자유 변수)의 선언 범위가 룰 하에서 도달 가능한지 Optimize로 확인.
달성 범위가 선언 범위보다 좁으면 모순으로 보고하고, 경계값을 assert_and_track 한
Solver의 unsat_core로 범인 룰을 추출한다.

종속 변수(예: hp == level*100의 hp)는 값이 공식으로 결정되므로 선언 범위 미달이
정상이다 — 거짓 양성을 피하려 검사 대상에서 제외한다(사용자 결정).

Z3가 unknown(타임아웃/비선형)을 반환하면 sat/unsat으로 뭉개지 않고 별도 보고한다
(CLAUDE.md §8).
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass, field
from typing import Any, Literal

import z3

from ruleforge.dsl.ir import RuleSet
from ruleforge.solver.translator import Translation


@dataclass(frozen=True)
class RangeViolation:
    """독립 변수의 선언 경계가 룰에 의해 도달 불가능해진 모순."""

    enum_assignment: dict[str, str]
    variable: str
    bound: Literal["min", "max"]
    declared: int
    achievable: int
    culprit_rules: tuple[str, ...]


@dataclass(frozen=True)
class UnreachableEnum:
    """특정 enum 값 조합 자체가 룰 하에서 도달 불가능한 모순."""

    enum_assignment: dict[str, str]
    culprit_rules: tuple[str, ...]


@dataclass(frozen=True)
class CheckReport:
    violations: tuple[RangeViolation, ...] = ()
    unreachable_enums: tuple[UnreachableEnum, ...] = ()
    unknowns: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_contradiction(self) -> bool:
        return bool(self.violations or self.unreachable_enums)


def check(ruleset: RuleSet, translation: Translation) -> CheckReport:
    """룰셋의 도달성 모순을 검사한다."""
    dependent = _dependent_variables(ruleset)
    target_vars = [v for v in ruleset.variables if v.type == "int" and v.name not in dependent]

    violations: list[RangeViolation] = []
    unreachable: list[UnreachableEnum] = []
    unknowns: list[str] = []

    for assignment in _enum_assignments(ruleset):
        enum_fix = [
            translation.z3_vars[name] == translation.enum_encoding[name][value]
            for name, value in assignment.items()
        ]

        status, core = _feasibility(translation, enum_fix)
        if status == "unknown":
            unknowns.append(f"{assignment or '전역'} 실행 가능성 검사에서 unknown")
            continue
        if status == "unsat":
            unreachable.append(UnreachableEnum(enum_assignment=assignment, culprit_rules=core))
            continue

        for var in target_vars:
            z3var = translation.z3_vars[var.name]
            bounds: tuple[tuple[Literal["min", "max"], int | None], ...] = (
                ("max", var.max),
                ("min", var.min),
            )
            for bound, declared in bounds:
                if declared is None:
                    continue
                v = _check_bound(
                    translation, enum_fix, assignment, var.name, z3var, bound, declared, unknowns
                )
                if v is not None:
                    violations.append(v)

    return CheckReport(
        violations=tuple(violations),
        unreachable_enums=tuple(unreachable),
        unknowns=tuple(unknowns),
    )


def _check_bound(
    translation: Translation,
    enum_fix: list[Any],
    assignment: dict[str, str],
    var_name: str,
    z3var: Any,
    bound: Literal["min", "max"],
    declared: int,
    unknowns: list[str],
) -> RangeViolation | None:
    """한 변수의 한 경계(min/max)가 도달 가능한지 검사한다."""
    status, achievable = _achievable(translation, enum_fix, z3var, maximize=(bound == "max"))
    if status == "unknown":
        unknowns.append(f"{assignment or '전역'} 변수 '{var_name}' {bound} 검사에서 unknown")
        return None
    if status != "ok" or achievable is None:
        return None

    violated = achievable < declared if bound == "max" else achievable > declared
    if not violated:
        return None

    core = _culprit(translation, enum_fix, z3var, declared)
    return RangeViolation(
        enum_assignment=assignment,
        variable=var_name,
        bound=bound,
        declared=declared,
        achievable=achievable,
        culprit_rules=core,
    )


def _dependent_variables(ruleset: RuleSet) -> set[str]:
    """then에서 `var == ...`로 값이 결정되는(종속) 변수 집합을 찾는다."""
    var_names = {v.name for v in ruleset.variables}
    dependent: set[str] = set()
    for rule in ruleset.rules:
        tree = ast.parse(rule.then, mode="eval")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Eq)
            ):
                for side in (node.left, node.comparators[0]):
                    if isinstance(side, ast.Name) and side.id in var_names:
                        dependent.add(side.id)
    return dependent


def _enum_assignments(ruleset: RuleSet) -> list[dict[str, str]]:
    """enum 변수들의 값 조합(데카르트 곱). enum이 없으면 빈 조합 하나."""
    enum_vars = [v for v in ruleset.variables if v.type == "enum"]
    if not enum_vars:
        return [{}]
    choices = [[(v.name, val) for val in v.values] for v in enum_vars]
    return [dict(combo) for combo in itertools.product(*choices)]


def _base(translation: Translation, enum_fix: list[Any]) -> list[Any]:
    return [*translation.domain_constraints, *enum_fix]


def _achievable(
    translation: Translation, enum_fix: list[Any], z3var: Any, *, maximize: bool
) -> tuple[Literal["ok", "unsat", "unknown"], int | None]:
    """룰 하에서 변수의 실제 달성 가능한 max/min을 Optimize로 구한다."""
    opt = z3.Optimize()
    for c in _base(translation, enum_fix):
        opt.add(c)
    for c in translation.rule_constraints.values():
        opt.add(c)
    if maximize:
        opt.maximize(z3var)
    else:
        opt.minimize(z3var)

    result = opt.check()
    if result == z3.unknown:
        return "unknown", None
    if result == z3.unsat:
        return "unsat", None
    value: int = opt.model().eval(z3var, model_completion=True).as_long()
    return "ok", value


def _feasibility(
    translation: Translation, enum_fix: list[Any]
) -> tuple[Literal["sat", "unsat", "unknown"], tuple[str, ...]]:
    """enum 조합이 룰 하에서 실행 가능한지(sat) 확인하고, 불가면 범인 룰을 추출한다."""
    solver = _tracked_solver(translation, enum_fix)
    result = solver.check()
    if result == z3.sat:
        return "sat", ()
    if result == z3.unknown:
        return "unknown", ()
    return "unsat", _core(solver)


def _culprit(
    translation: Translation, enum_fix: list[Any], z3var: Any, value: int
) -> tuple[str, ...]:
    """경계값(var == declared)을 assert_and_track 하고 unsat_core로 범인 룰을 추출한다."""
    solver = _tracked_solver(translation, enum_fix)
    solver.add(z3var == value)
    if solver.check() == z3.unsat:
        return _core(solver)
    return ()  # 모순 재현 실패(이론상 도달 가능) — 방어적 빈 core


def _tracked_solver(translation: Translation, enum_fix: list[Any]) -> Any:
    """룰만 assert_and_track 한 Solver. 도메인·enum 고정은 추적하지 않는 전제로 둔다."""
    solver = z3.Solver()
    for c in _base(translation, enum_fix):
        solver.add(c)
    for rule_id, constraint in translation.rule_constraints.items():
        solver.assert_and_track(constraint, rule_id)
    return solver


def _core(solver: Any) -> tuple[str, ...]:
    return tuple(sorted(str(c) for c in solver.unsat_core()))
