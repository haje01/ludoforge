"""검사 로직(S5): D3/D4 — Optimize 기반 도달성 검사.

모순 정의(D3): "기획자가 합법이라 여기는 상태를 룰들이 봉쇄한다."
검사 방법(D4): 각 enum 값 조합을 고정한 뒤, **독립 변수**(then에서 `var == ...`로
값이 결정되지 않는 자유 변수)의 선언 범위가 룰 하에서 도달 가능한지 Optimize로 확인.
달성 범위가 선언 범위보다 좁으면 모순으로 보고하고, 경계값을 assert_and_track 한
Solver의 unsat_core로 범인 룰을 추출한다. 조인트 조합 고정은 내부(int/real/bool) 변수
검사의 **문맥**일 뿐, 조합 셀이 unsat이어도 그 자체를 모순으로 보지 않는다 — 조건부
룰은 본래 일부 조합을 막기 때문이다(거짓 양성 회피).

enum 값의 도달성은 조인트 조합이 아니라 **값 단위 투영**으로 본다: 각 변수의 각 값이
어떤 배정으로든 도달 가능한지 확인하고(`domain ∧ rules ∧ var==value`), unsat이면 그 값이
봉쇄된 것으로 보고한다. 조합 단위 도달성 단언은 `expects:`(D10)로 명시한다.

종속 변수(예: hp == level*100의 hp)는 값이 공식으로 결정되므로 선언 범위 미달이
정상이다 — 거짓 양성을 피하려 검사 대상에서 제외한다(사용자 결정).

불리언 상태 변수(D6)도 같은 틀로 검사한다: 자유 bool의 True/False 각 상태가 룰 하에서
도달 가능한지 확인하고(상호 배제 등으로) 봉쇄되면 모순으로 보고한다. 무조건 강제로
값이 고정된 bool은 종속으로 보고 제외한다.

실수 변수(real, LRA, D7)는 feasibility에 참여해 "확률 합=1" 류 over-constraint/enum
조건부 모순을 잡는다. 더해 선언 min/max **끝점** 도달성을 검사한다(D9, A-i): `var ==
선언끝점`이 unsat이면 봉쇄로 보고한다. int(D4)과 달리 Optimize로 정확한 달성값을 구하지
않고 끝점 sat 여부만 본다(비-도달 상한 epsilon 문제 회피 — 정밀 gap은 후속 A-ii). 종속
real(공식으로 결정)은 끝점 미달이 정상이라 제외한다(D5 일관).

Z3가 unknown(타임아웃/비선형)을 반환하면 sat/unsat으로 뭉개지 않고 별도 보고한다
(CLAUDE.md §8).
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass, field
from typing import Any, Literal

import z3

from forge_core.ir import RuleSet
from ruleforge.solver.translator import Translation


@dataclass(frozen=True)
class RangeViolation:
    """독립 변수의 선언 경계가 룰에 의해 도달 불가능해진 모순."""

    assignment: dict[str, str]
    variable: str
    bound: Literal["min", "max"]
    declared: int
    achievable: int
    culprit_rules: tuple[str, ...]


@dataclass(frozen=True)
class UnreachableState:
    """특정 상태(enum 값 또는 자유 bool의 한 상태)가 룰 하에서 도달 불가능한 모순.

    enum은 값 단위 투영으로 검사하므로 assignment에 해당 변수=값 한 항목만 담긴다.
    자유 bool은 도달 가능한 enum 문맥 안에서 보므로 enum 문맥 + bool 상태가 함께 담긴다.
    """

    assignment: dict[str, str]
    culprit_rules: tuple[str, ...]


@dataclass(frozen=True)
class BoundUnreachable:
    """real 변수의 선언 경계(min/max) 끝점이 룰에 의해 도달 불가능한 모순(D9, 끝점 검사).

    int(D4)과 달리 정확한 달성값은 구하지 않는다 — 선언 끝점이 sat인지만 본다(A-i).
    """

    assignment: dict[str, str]
    variable: str
    bound: Literal["min", "max"]
    declared: float
    culprit_rules: tuple[str, ...]


@dataclass(frozen=True)
class UnmetExpectation:
    """기획자가 `expects:`로 단언한 도달성을 룰이 충족하지 못한 모순(D10).

    `rules ∧ that`가 unsat이면 기대 상태가 도달 불가 — 봉쇄한 룰을 unsat_core로 짚는다.
    """

    expect_id: str
    desc: str | None
    culprit_rules: tuple[str, ...]


@dataclass(frozen=True)
class CheckReport:
    violations: tuple[RangeViolation, ...] = ()
    unreachable_states: tuple[UnreachableState, ...] = ()
    bound_unreachables: tuple[BoundUnreachable, ...] = ()
    unmet_expectations: tuple[UnmetExpectation, ...] = ()
    unknowns: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_contradiction(self) -> bool:
        return bool(
            self.violations
            or self.unreachable_states
            or self.bound_unreachables
            or self.unmet_expectations
        )


def check(ruleset: RuleSet, translation: Translation) -> CheckReport:
    """룰셋의 도달성 모순을 검사한다."""
    dependent = _dependent_variables(ruleset)
    target_vars = [v for v in ruleset.variables if v.type == "int" and v.name not in dependent]
    real_targets = [v for v in ruleset.variables if v.type == "real" and v.name not in dependent]
    determined_bools = _determined_bools(ruleset)
    target_bools = [
        v for v in ruleset.variables if v.type == "bool" and v.name not in determined_bools
    ]

    violations: list[RangeViolation] = []
    unreachable: list[UnreachableState] = []
    bound_unreachables: list[BoundUnreachable] = []
    unknowns: list[str] = []

    # 전역 도달성: domain ∧ rules 자체가 unsat이면 어떤 상태로도 도달할 수 없는 전역
    # over-constraint다(예: 두 룰이 같은 변수를 다른 상수로 고정, 확률 합 과제약). enum
    # 조합과 무관한 모순이라 값 단위·내부 변수 검사 전에 먼저 본다. 전역 불가면 모든 하위
    # 검사가 자명히 불가라 노이즈만 늘므로 전역 모순 하나만 보고하고 멈춘다.
    global_status, global_core = _feasibility(translation, [])
    if global_status == "unsat":
        return CheckReport(
            unreachable_states=(UnreachableState(assignment={}, culprit_rules=global_core),)
        )
    if global_status == "unknown":
        unknowns.append("전역 실행 가능성 검사에서 unknown")

    for assignment in _enum_assignments(ruleset):
        enum_fix = [
            translation.z3_vars[name] == translation.enum_encoding[name][value]
            for name, value in assignment.items()
        ]

        status, _ = _feasibility(translation, enum_fix)
        if status == "unknown":
            unknowns.append(f"{assignment or '전역'} 실행 가능성 검사에서 unknown")
            continue
        if status == "unsat":
            # 조건부 룰(when→then)이 일부 조인트 조합을 막는 것은 의도된 배제이므로
            # 조합 셀 자체는 모순으로 보고하지 않는다(거짓 양성 회피). 내부 변수 검사만
            # 건너뛴다. enum 값의 도달성은 _check_enum_reachability에서 값 단위로 본다.
            continue

        # 자유 bool의 각 상태(True/False)가 룰 하에서 도달 가능한지 검사한다(D6).
        # int 경계 검사(D4)와 동형 — enum×bool 데카르트 곱 대신 변수별 도달성으로 본다.
        for bvar in target_bools:
            unreachable.extend(
                _check_bool_states(translation, enum_fix, assignment, bvar.name, unknowns)
            )

        for var in target_vars:
            z3var = translation.z3_vars[var.name]
            bounds: tuple[tuple[Literal["min", "max"], float | None], ...] = (
                ("max", var.max),
                ("min", var.min),
            )
            for bound, declared in bounds:
                if declared is None:
                    continue
                # int 변수의 경계는 정수다(real은 도달성 검사 비대상, D7). int로 좁혀 전달.
                v = _check_bound(
                    translation,
                    enum_fix,
                    assignment,
                    var.name,
                    z3var,
                    bound,
                    int(declared),
                    unknowns,
                )
                if v is not None:
                    violations.append(v)

        # real 변수(D9): 선언 min/max 끝점이 도달 가능한지 feasibility로 검사한다(A-i).
        # int 경계 검사와 대칭이되 달성값은 구하지 않고 끝점 sat 여부만 본다(epsilon 회피).
        for var in real_targets:
            z3rvar = translation.z3_vars[var.name]
            rbounds: tuple[tuple[Literal["min", "max"], float | None], ...] = (
                ("max", var.max),
                ("min", var.min),
            )
            for bound, declared in rbounds:
                if declared is None:
                    continue
                b = _check_real_bound(
                    translation, enum_fix, assignment, var.name, z3rvar, bound, declared, unknowns
                )
                if b is not None:
                    bound_unreachables.append(b)

    # enum 값 단위 도달성: 각 변수의 각 값이 어떤 배정으로든 도달 가능한지 본다(투영).
    # 조인트 조합 순회와 독립적인 전역 검사라 루프 밖에서 한 번씩 본다.
    unreachable.extend(_check_enum_reachability(ruleset, translation, unknowns))

    # 명시적 도달성 단언(D10): 룰과 무관한 전역 검사라 enum 조합 순회 밖에서 한 번씩 본다.
    unmet = _check_expects(ruleset, translation, unknowns)

    return CheckReport(
        violations=tuple(violations),
        unreachable_states=tuple(unreachable),
        bound_unreachables=tuple(bound_unreachables),
        unmet_expectations=tuple(unmet),
        unknowns=tuple(unknowns),
    )


def _check_expects(
    ruleset: RuleSet, translation: Translation, unknowns: list[str]
) -> list[UnmetExpectation]:
    """각 expect의 `that` 조건이 룰 하에서 도달 가능한지(sat) 검사한다(D10).

    `rules ∧ that`가 unsat이면 기대가 봉쇄된 것 — 범인 룰을 unsat_core로 짚는다.
    """
    results: list[UnmetExpectation] = []
    for expect in ruleset.expects:
        constraint = translation.expect_constraints[expect.id]
        status, core = _feasibility(translation, [constraint])
        if status == "unknown":
            unknowns.append(f"기대 '{expect.id}' 도달성 검사에서 unknown")
            continue
        if status == "unsat":
            results.append(
                UnmetExpectation(expect_id=expect.id, desc=expect.desc, culprit_rules=core)
            )
    return results


def _check_enum_reachability(
    ruleset: RuleSet, translation: Translation, unknowns: list[str]
) -> list[UnreachableState]:
    """각 enum 변수의 각 값이 룰 하에서 도달 가능한지 값 단위로 검사한다(투영).

    조인트 조합이 아니라 값 단위로 본다: `domain ∧ rules ∧ (var == value)`가 unsat이면
    그 값에 다른 변수의 어떤 배정으로도 도달할 수 없는 것 — 모순으로 보고한다. 조건부
    룰이 일부 조합만 막는 것(예: sky==night → lighting==night)은 정상이라 보고하지
    않는다(거짓 양성 회피). 조합 단위 도달성을 단언하려면 `expects:`(D10)를 쓴다. 무조건
    룰로 한 값에 핀된 enum은 다른 값이 도달 불가여도 정상이므로(D5 bool 처리와 동형)
    검사 대상에서 제외한다.
    """
    determined = _determined_enums(ruleset)
    found: list[UnreachableState] = []
    for var in (v for v in ruleset.variables if v.type == "enum" and v.name not in determined):
        z3var = translation.z3_vars[var.name]
        for value in var.values:
            fix = [z3var == translation.enum_encoding[var.name][value]]
            status, core = _feasibility(translation, fix)
            if status == "unknown":
                unknowns.append(f"'{var.name}'={value} 도달성 검사에서 unknown")
                continue
            if status == "unsat":
                found.append(
                    UnreachableState(assignment={var.name: value}, culprit_rules=core)
                )
    return found


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
        assignment=assignment,
        variable=var_name,
        bound=bound,
        declared=declared,
        achievable=achievable,
        culprit_rules=core,
    )


def _check_real_bound(
    translation: Translation,
    enum_fix: list[Any],
    assignment: dict[str, str],
    var_name: str,
    z3var: Any,
    bound: Literal["min", "max"],
    declared: float,
    unknowns: list[str],
) -> BoundUnreachable | None:
    """real 변수의 선언 끝점(var == declared)이 도달 가능한지 feasibility로 검사한다(D9, A-i).

    끝점이 unsat이면 봉쇄로 보고 범인 룰을 unsat_core로 짚는다. 달성값은 구하지 않는다.
    """
    status, core = _feasibility(translation, [*enum_fix, z3var == declared])
    if status == "unknown":
        unknowns.append(f"{assignment or '전역'} 변수 '{var_name}' {bound} 끝점 검사에서 unknown")
        return None
    if status != "unsat":
        return None
    return BoundUnreachable(
        assignment=assignment,
        variable=var_name,
        bound=bound,
        declared=declared,
        culprit_rules=core,
    )


def _check_bool_states(
    translation: Translation,
    enum_fix: list[Any],
    assignment: dict[str, str],
    bvar_name: str,
    unknowns: list[str],
) -> list[UnreachableState]:
    """한 자유 bool의 True/False 각각이 도달 가능한지 검사한다(D6).

    실행 가능한 enum 조합 안에서는 둘 중 최소 하나는 반드시 도달 가능하므로,
    봉쇄되는 상태는 많아야 하나다. 봉쇄되면 범인 룰을 unsat_core로 짚는다.
    """
    z3b = translation.z3_vars[bvar_name]
    found: list[UnreachableState] = []
    for value in (True, False):
        status, core = _feasibility(translation, [*enum_fix, z3b == z3.BoolVal(value)])
        label = "true" if value else "false"
        if status == "unknown":
            unknowns.append(
                f"{assignment or '전역'} 변수 '{bvar_name}'={label} 도달성 검사에서 unknown"
            )
            continue
        if status == "unsat":
            found.append(
                UnreachableState(assignment={**assignment, bvar_name: label}, culprit_rules=core)
            )
    return found


def _determined_bools(ruleset: RuleSet) -> set[str]:
    """무조건(`when` 없는) 룰로 상수 강제되는 bool 집합(종속).

    기획자가 명시적으로 값을 고정한 bool은 반대 상태가 도달 불가여도 정상이므로
    도달성 검사에서 제외한다(D5와 같은 거짓양성 회피). 조건부(`when`)로만 강제되는
    bool은 자유로 남겨, 그 강제가 상호 배제와 충돌해 상태를 봉쇄하면 모순으로 잡는다.
    """
    bool_names = {v.name for v in ruleset.variables if v.type == "bool"}
    determined: set[str] = set()
    for rule in ruleset.rules:
        if rule.when is not None:
            continue
        name = _forced_bool_atom(ast.parse(rule.then, mode="eval").body)
        if name in bool_names:
            determined.add(name)
    return determined


def _forced_bool_atom(node: ast.AST) -> str | None:
    """`then`이 bool을 상수로 고정하면 그 변수명을 돌려준다(아니면 None).

    인식 형태: bare atom(`x`), 부정(`not x`), 불리언 등식(`x == True`/`False == x`).
    """
    if isinstance(node, ast.Name):
        return node.id
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Name)
    ):
        return node.operand.id
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
        for a, b in ((node.left, node.comparators[0]), (node.comparators[0], node.left)):
            if isinstance(a, ast.Name) and _is_bool_const(b):
                return a.id
    return None


def _is_bool_const(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, bool)


def _determined_enums(ruleset: RuleSet) -> set[str]:
    """무조건(`when` 없는) 룰로 특정 값에 핀되는 enum 집합(종속).

    기획자가 명시적으로 한 값으로 고정한 enum은 나머지 값이 도달 불가여도 정상이므로
    값 단위 도달성 검사에서 제외한다(_determined_bools와 동형, D5 거짓양성 회피).
    """
    enum_names = {v.name for v in ruleset.variables if v.type == "enum"}
    var_names = {v.name for v in ruleset.variables}
    determined: set[str] = set()
    for rule in ruleset.rules:
        if rule.when is not None:
            continue
        name = _forced_enum_atom(ast.parse(rule.then, mode="eval").body, enum_names, var_names)
        if name is not None:
            determined.add(name)
    return determined


def _forced_enum_atom(node: ast.AST, enum_names: set[str], var_names: set[str]) -> str | None:
    """`then`이 enum을 상수 값으로 고정하면(`var == value`) 그 변수명을 돌려준다.

    한쪽이 enum 변수, 다른 쪽이 변수가 아닌 이름(enum 값)일 때만 핀으로 본다 —
    `sky == lighting` 같은 변수-변수 비교는 상수 고정이 아니라 제외한다.
    """
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
        for a, b in ((node.left, node.comparators[0]), (node.comparators[0], node.left)):
            if (
                isinstance(a, ast.Name)
                and a.id in enum_names
                and isinstance(b, ast.Name)
                and b.id not in var_names
            ):
                return a.id
    return None


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
