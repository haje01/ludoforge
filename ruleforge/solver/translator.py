"""번역기(S4): 스키마 검증을 통과한 IR을 Z3 제약식으로 변환한다.

표현식은 `ast.parse(mode="eval")` 후 화이트리스트 노드만 Z3에 매핑한다(D2).
`eval`은 절대 쓰지 않으며, 허용 외 노드는 명시적 TranslationError를 던진다.

산출물(Translation):
- z3_vars:           변수명 → Z3 정수 변수
- domain_constraints: 선언 범위(min/max, enum 범위) 제약 목록
- rule_constraints:  rule_id → 룰 제약(`when`이면 Implies(when, then))
- enum_encoding:     enum 변수명 → {값: 정수}

assert_and_track(Solver 작업)은 여기서 하지 않는다 — 검사 단계(S5)의 책임이다.

enum 인코딩: 값을 0,1,2... 정수로 매핑하고 변수는 [0, n-1] 범위의 Int로 둔다.
1차에서는 서로 다른 enum 변수가 같은 값 이름을 쓰는 경우를 지원하지 않는다
(표현식의 enum 값을 전역 이름으로 해석하기 때문). 필요해지면 그때 한정한다.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

import z3

from ruleforge.dsl.ir import RuleSet


class TranslationError(Exception):
    """IR → Z3 번역 실패(허용 외 표현식 요소 등). 메시지에 위치를 담는다."""


@dataclass(frozen=True)
class Translation:
    z3_vars: dict[str, Any]
    domain_constraints: list[Any]
    rule_constraints: dict[str, Any]
    enum_encoding: dict[str, dict[str, int]]


# ast 비교 연산자 → (좌, 우) → Z3 식
_COMPARE_OPS: dict[type[ast.cmpop], Any] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}

# ast 이항 산술 연산자 → Z3 식
_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
}


def translate(ruleset: RuleSet) -> Translation:
    """검증된 RuleSet을 Z3 제약식으로 번역한다."""
    z3_vars, domain_constraints, enum_encoding = _build_domain(ruleset)

    # 표현식 번역용 심볼표: 변수명 → Z3 변수, enum 값 이름 → 정수.
    symbols: dict[str, Any] = dict(z3_vars)
    for encoding in enum_encoding.values():
        for value, code in encoding.items():
            symbols[value] = code

    rule_constraints: dict[str, Any] = {}
    for rule in ruleset.rules:
        try:
            then_expr = _translate_expr(_parse(rule.then), symbols)
            if rule.when is not None:
                when_expr = _translate_expr(_parse(rule.when), symbols)
                rule_constraints[rule.id] = z3.Implies(when_expr, then_expr)
            else:
                rule_constraints[rule.id] = then_expr
        except TranslationError as e:
            raise TranslationError(f"룰 '{rule.id}': {e}") from e

    return Translation(
        z3_vars=z3_vars,
        domain_constraints=domain_constraints,
        rule_constraints=rule_constraints,
        enum_encoding=enum_encoding,
    )


def _build_domain(
    ruleset: RuleSet,
) -> tuple[dict[str, Any], list[Any], dict[str, dict[str, int]]]:
    z3_vars: dict[str, Any] = {}
    domain_constraints: list[Any] = []
    enum_encoding: dict[str, dict[str, int]] = {}

    for v in ruleset.variables:
        if v.type == "bool":
            # 불리언 상태(D6): z3.Bool. 자유 True/False라 도메인 제약은 없다.
            z3_vars[v.name] = z3.Bool(v.name)
            continue

        var = z3.Int(v.name)
        z3_vars[v.name] = var
        if v.type == "int":
            if v.min is not None:
                domain_constraints.append(var >= v.min)
            if v.max is not None:
                domain_constraints.append(var <= v.max)
        else:  # enum: 0..n-1 정수 인코딩
            encoding = {value: i for i, value in enumerate(v.values)}
            enum_encoding[v.name] = encoding
            domain_constraints.append(var >= 0)
            domain_constraints.append(var <= len(v.values) - 1)

    return z3_vars, domain_constraints, enum_encoding


def _parse(expr: str) -> ast.expr:
    """표현식을 ast로 파싱한다(스키마 검증을 통과했으므로 정상 가정)."""
    return ast.parse(expr, mode="eval").body


def _translate_expr(node: ast.AST, symbols: dict[str, Any]) -> Any:
    """화이트리스트 노드만 Z3 식으로 재귀 변환한다. 그 외는 TranslationError."""
    if isinstance(node, ast.BoolOp):
        parts = [_translate_expr(v, symbols) for v in node.values]
        if isinstance(node.op, ast.And):
            return z3.And(*parts)
        if isinstance(node.op, ast.Or):
            return z3.Or(*parts)
        raise TranslationError("지원하지 않는 불리언 연산자")

    if isinstance(node, ast.UnaryOp):
        operand = _translate_expr(node.operand, symbols)
        if isinstance(node.op, ast.Not):
            return z3.Not(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        raise TranslationError("지원하지 않는 단항 연산자")

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise TranslationError(f"지원하지 않는 산술 연산자: {type(node.op).__name__}")
        return op(_translate_expr(node.left, symbols), _translate_expr(node.right, symbols))

    if isinstance(node, ast.Compare):
        return _translate_compare(node, symbols)

    if isinstance(node, ast.Name):
        if node.id not in symbols:
            raise TranslationError(f"미정의 심볼: '{node.id}'")
        return symbols[node.id]

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return z3.BoolVal(node.value)  # 불리언 리터럴(D6)
        if not isinstance(node.value, int):
            raise TranslationError(f"지원하지 않는 상수: {node.value!r} (정수/불리언만 허용)")
        return node.value

    raise TranslationError(f"지원하지 않는 표현식 요소: {type(node).__name__}")


def _translate_compare(node: ast.Compare, symbols: dict[str, Any]) -> Any:
    """단일/연쇄 비교를 And로 묶어 번역한다 (예: 1 <= x <= 3 → x>=1 ∧ x<=3)."""
    operands = [_translate_expr(node.left, symbols)]
    operands.extend(_translate_expr(c, symbols) for c in node.comparators)

    comparisons = []
    for i, op in enumerate(node.ops):
        fn = _COMPARE_OPS.get(type(op))
        if fn is None:
            raise TranslationError(f"지원하지 않는 비교 연산자: {type(op).__name__}")
        comparisons.append(fn(operands[i], operands[i + 1]))

    return comparisons[0] if len(comparisons) == 1 else z3.And(*comparisons)
