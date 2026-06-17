"""번역기(S4): 스키마 검증을 통과한 IR을 Z3 제약식으로 변환한다.

표현식은 `ast.parse(mode="eval")` 후 화이트리스트 노드만 Z3에 매핑한다(D2).
`eval`은 절대 쓰지 않으며, 허용 외 노드는 명시적 TranslationError를 던진다.

산출물(Translation):
- z3_vars:           변수명 → Z3 변수(int/real/bool/enum sort 상수)
- domain_constraints: 선언 범위(int/real min/max) 제약 목록
- rule_constraints:  rule_id → 룰 제약(`when`이면 Implies(when, then))
- enum_encoding:     enum 변수명 → {값: z3 EnumSort 상수}

assert_and_track(Solver 작업)은 여기서 하지 않는다 — 검사 단계(S5)의 책임이다.

enum(D8): 각 enum 변수를 고유 z3 EnumSort로 만든다(상호 배타·유한이라 도메인 제약 불필요).
sort가 다르므로 서로 다른 enum이 같은 값 이름을 써도 안전하다. 표현식의 bare 값 이름은
비교 문맥에서 상대 변수의 enum sort로 해석한다(`_translate_compare`).
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass, field
from typing import Any

import z3

from core.ir import RuleSet

# z3는 전역 컨텍스트에서 같은 이름의 enum sort를 두 번 선언하면 예외를 던진다.
# translate()가 여러 번 호출돼도(테스트 등) 충돌하지 않도록 sort 라벨을 프로세스 단위로
# 유일하게 만든다. 라벨은 내부용이며 제약식의 의미(satisfiability)에는 영향이 없다(D8).
_enum_sort_seq = itertools.count()


class TranslationError(Exception):
    """IR → Z3 번역 실패(허용 외 표현식 요소 등). 메시지에 위치를 담는다."""


@dataclass(frozen=True)
class Translation:
    z3_vars: dict[str, Any]
    domain_constraints: list[Any]
    rule_constraints: dict[str, Any]
    enum_encoding: dict[str, dict[str, Any]]  # enum 변수명 → {값: z3 EnumSort 상수} (D8)
    expect_constraints: dict[str, Any] = field(default_factory=dict)  # expect_id → that 식 (D10)


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

    # 표현식 번역용 심볼표: 변수명 → Z3 변수. enum 값은 전역 유일한 것만 심볼로 둔다.
    # 중복 이름(서로 다른 enum이 같은 값)은 비교 문맥에서 상대 변수의 sort로 해석한다(D8).
    symbols: dict[str, Any] = dict(z3_vars)
    counts = _value_counts(enum_encoding)
    for encoding in enum_encoding.values():
        for value, const in encoding.items():
            if counts[value] == 1 and value not in symbols:
                symbols[value] = const

    rule_constraints: dict[str, Any] = {}
    for rule in ruleset.rules:
        try:
            then_expr = _translate_expr(_parse(rule.then), symbols, enum_encoding)
            if rule.when is not None:
                when_expr = _translate_expr(_parse(rule.when), symbols, enum_encoding)
                rule_constraints[rule.id] = z3.Implies(when_expr, then_expr)
            else:
                rule_constraints[rule.id] = then_expr
        except TranslationError as e:
            raise TranslationError(f"룰 '{rule.id}': {e}") from e

    expect_constraints: dict[str, Any] = {}
    for expect in ruleset.expects:
        try:
            expect_constraints[expect.id] = _translate_expr(
                _parse(expect.that), symbols, enum_encoding
            )
        except TranslationError as e:
            raise TranslationError(f"기대 '{expect.id}': {e}") from e

    return Translation(
        z3_vars=z3_vars,
        domain_constraints=domain_constraints,
        rule_constraints=rule_constraints,
        enum_encoding=enum_encoding,
        expect_constraints=expect_constraints,
    )


def translate_expression(
    node: ast.AST, symbols: dict[str, Any], enums: dict[str, dict[str, Any]]
) -> Any:
    """단일 표현식 ast 노드를 Z3 식으로 번역한다(BMC 등 외부 재사용 진입점, D15).

    화이트리스트 노드만 허용한다(`_translate_expr`와 동일 규칙). `next.<var>`(다음 상태)는
    여기서 처리하지 않는다 — 호출자가 Name으로 치환(mangle)해 넘긴다(bmc.py). `symbols`/
    `enums`에 현재·다음 스텝 변수를 함께 담아 호출하는 식이다.
    """
    return _translate_expr(node, symbols, enums)


def _build_domain(
    ruleset: RuleSet,
) -> tuple[dict[str, Any], list[Any], dict[str, dict[str, Any]]]:
    z3_vars: dict[str, Any] = {}
    domain_constraints: list[Any] = []
    enum_encoding: dict[str, dict[str, Any]] = {}

    for v in ruleset.variables:
        if v.type == "bool":
            # 불리언 상태(D6): z3.Bool. 자유 True/False라 도메인 제약은 없다.
            z3_vars[v.name] = z3.Bool(v.name)
            continue

        if v.type == "real":
            # 실수 변수(LRA, D7): z3.Real. 선언 min/max는 feasibility 제약으로 둔다.
            rvar = z3.Real(v.name)
            z3_vars[v.name] = rvar
            if v.min is not None:
                domain_constraints.append(rvar >= v.min)
            if v.max is not None:
                domain_constraints.append(rvar <= v.max)
            continue

        if v.type == "enum":
            # enum(D8): z3 EnumSort. 각 enum이 고유 sort라 값이 sort로 구별된다
            # (서로 다른 enum이 같은 값 이름을 써도 안전). 유한·상호 배타라 도메인 제약 불필요.
            sort_label = f"{v.name}__enum{next(_enum_sort_seq)}"
            sort, consts = z3.EnumSort(sort_label, list(v.values))
            z3_vars[v.name] = z3.Const(v.name, sort)
            enum_encoding[v.name] = dict(zip(v.values, consts, strict=True))
            continue

        var = z3.Int(v.name)
        z3_vars[v.name] = var
        if v.min is not None:
            domain_constraints.append(var >= v.min)
        if v.max is not None:
            domain_constraints.append(var <= v.max)

    return z3_vars, domain_constraints, enum_encoding


def _parse(expr: str) -> ast.expr:
    """표현식을 ast로 파싱한다(스키마 검증을 통과했으므로 정상 가정)."""
    return ast.parse(expr, mode="eval").body


def _value_counts(enum_encoding: dict[str, dict[str, Any]]) -> dict[str, int]:
    """enum 값 이름이 전체 enum에서 몇 번 등장하는지 센다(중복 이름 판별용, D8)."""
    counts: dict[str, int] = {}
    for encoding in enum_encoding.values():
        for value in encoding:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _translate_expr(
    node: ast.AST, symbols: dict[str, Any], enums: dict[str, dict[str, Any]]
) -> Any:
    """화이트리스트 노드만 Z3 식으로 재귀 변환한다. 그 외는 TranslationError."""
    if isinstance(node, ast.BoolOp):
        parts = [_translate_expr(v, symbols, enums) for v in node.values]
        if isinstance(node.op, ast.And):
            return z3.And(*parts)
        if isinstance(node.op, ast.Or):
            return z3.Or(*parts)
        raise TranslationError("지원하지 않는 불리언 연산자")

    if isinstance(node, ast.UnaryOp):
        operand = _translate_expr(node.operand, symbols, enums)
        if isinstance(node.op, ast.Not):
            return z3.Not(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        raise TranslationError("지원하지 않는 단항 연산자")

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Div):
            return _translate_div(node, symbols, enums)
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise TranslationError(f"지원하지 않는 산술 연산자: {type(node.op).__name__}")
        left = _translate_expr(node.left, symbols, enums)
        right = _translate_expr(node.right, symbols, enums)
        return op(left, right)

    if isinstance(node, ast.Compare):
        return _translate_compare(node, symbols, enums)

    if isinstance(node, ast.Name):
        if node.id not in symbols:
            raise TranslationError(f"미정의 심볼: '{node.id}'")
        return symbols[node.id]

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return z3.BoolVal(node.value)  # 불리언 리터럴(D6)
        if isinstance(node.value, float):
            return z3.RealVal(node.value)  # 실수 리터럴(LRA, D7)
        if not isinstance(node.value, int):
            raise TranslationError(f"지원하지 않는 상수: {node.value!r} (정수/실수/불리언만 허용)")
        return node.value

    raise TranslationError(f"지원하지 않는 표현식 요소: {type(node).__name__}")


def _translate_compare(
    node: ast.Compare, symbols: dict[str, Any], enums: dict[str, dict[str, Any]]
) -> Any:
    """단일/연쇄 비교를 And로 묶어 번역한다 (예: 1 <= x <= 3 → x>=1 ∧ x<=3).

    enum 비교는 문맥으로 값을 해석한다(D8): `role == warrior`에서 `warrior`는 상대
    피연산자 `role`의 enum sort 값으로 푼다. 서로 다른 enum의 같은 값 이름을 구별하고,
    다른 enum의 값을 잘못 쓰면 친절한 에러를 낸다.
    """
    operand_nodes = [node.left, *node.comparators]

    comparisons = []
    for i, op in enumerate(node.ops):
        fn = _COMPARE_OPS.get(type(op))
        if fn is None:
            raise TranslationError(f"지원하지 않는 비교 연산자: {type(op).__name__}")
        left, right = _resolve_compare_pair(operand_nodes[i], operand_nodes[i + 1], symbols, enums)
        comparisons.append(fn(left, right))

    return comparisons[0] if len(comparisons) == 1 else z3.And(*comparisons)


def _resolve_compare_pair(
    a_node: ast.expr, b_node: ast.expr, symbols: dict[str, Any], enums: dict[str, dict[str, Any]]
) -> tuple[Any, Any]:
    """비교 한 쌍을 번역하되, 한쪽이 enum 변수면 다른쪽 bare 값을 그 enum sort로 해석한다."""
    a_enum = a_node.id if isinstance(a_node, ast.Name) and a_node.id in enums else None
    b_enum = b_node.id if isinstance(b_node, ast.Name) and b_node.id in enums else None
    a = _resolve_operand(a_node, symbols, enums, hint=b_enum)
    b = _resolve_operand(b_node, symbols, enums, hint=a_enum)
    return a, b


def _resolve_operand(
    node: ast.expr, symbols: dict[str, Any], enums: dict[str, dict[str, Any]], hint: str | None
) -> Any:
    """hint(상대 enum 변수명)가 있으면 bare 값 이름을 그 enum의 sort 상수로 해석한다."""
    if hint is not None and isinstance(node, ast.Name) and node.id not in enums:
        hint_values = enums[hint]
        if node.id in hint_values:
            return hint_values[node.id]
        # 다른 enum의 값을 이 enum과 비교한 오용 → 친절한 에러(원시 z3 sort 에러 방지).
        if any(node.id in vals for vals in enums.values()):
            raise TranslationError(f"'{node.id}'은(는) enum '{hint}'의 값이 아닙니다")
    return _translate_expr(node, symbols, enums)


def _translate_div(
    node: ast.BinOp, symbols: dict[str, Any], enums: dict[str, dict[str, Any]]
) -> Any:
    """상수 분모 나눗셈만 허용한다(선형 LRA, D7).

    변수 분모(a/b)는 비선형(NIA/NRA)이라 거부한다. 분자는 Real로 올려 나눗셈을
    정확한 유리수로 다룬다(예: 1/3은 파이썬 float가 아닌 z3 유리수 1/3).
    """
    divisor = node.right
    if not _is_numeric_const(divisor):
        raise TranslationError(
            "나눗셈은 상수 분모만 허용합니다(변수 분모는 비선형). 곱셈/스케일링으로 우회하세요."
        )
    assert isinstance(divisor, ast.Constant)
    if divisor.value == 0:
        raise TranslationError("0으로 나눌 수 없습니다")
    numerator = _as_real(_translate_expr(node.left, symbols, enums))
    return numerator / z3.RealVal(divisor.value)


def _is_numeric_const(node: ast.AST) -> bool:
    if not isinstance(node, ast.Constant):
        return False
    return isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _as_real(value: Any) -> Any:
    """정수 리터럴/Int식을 Real로 올린다(나눗셈을 정확한 유리수로 다루기 위함)."""
    if isinstance(value, (int, float)):
        return z3.RealVal(value)
    if z3.is_int(value):
        return z3.ToReal(value)
    return value
