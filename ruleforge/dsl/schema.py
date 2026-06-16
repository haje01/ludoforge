"""스키마·참조 검증(S3): 로더 통과 후 Z3 이전의 게이트.

검사하는 것(CLAUDE.md §3.3 — 형식/참조 무결성):
- 중복 rule id
- 표현식 구문 오류(파싱 불가)
- 미정의 심볼 참조(선언 안 된 변수명 / enum 값 오타)
- int 변수의 min > max

여기서 실패하면 Z3 단계로 넘어가지 않는다. 모든 문제를 모아 SchemaError로 보고한다.

참고: '순환 의존'은 현 DSL에선 룰·변수가 서로를 참조하지 않아 해당 없음.
파생 변수나 룰 간 참조가 도입되면 그때 검사를 추가한다.

표현식의 '미정의 심볼' 검사를 위해 ast로 식별자(Name)만 추출한다. 허용 노드
화이트리스트 강제와 Z3 매핑은 번역기(S4)의 책임이며 여기서는 하지 않는다.
"""

from __future__ import annotations

import ast

from ruleforge.dsl.ir import Rule, RuleSet


class SchemaError(Exception):
    """스키마·참조 검증 실패. 메시지에 발견된 모든 문제를 담는다."""


def validate(ruleset: RuleSet) -> None:
    """룰셋의 참조 무결성을 검사한다. 문제가 있으면 SchemaError를 던진다."""
    errors: list[str] = []
    errors.extend(_check_variable_bounds(ruleset))
    errors.extend(_check_duplicate_rule_ids(ruleset))
    errors.extend(_check_references(ruleset))

    if errors:
        raise SchemaError("스키마 검증 실패:\n" + "\n".join(f"- {e}" for e in errors))


def _check_variable_bounds(ruleset: RuleSet) -> list[str]:
    errors: list[str] = []
    for v in ruleset.variables:
        if v.type == "int" and v.min is not None and v.max is not None and v.min > v.max:
            errors.append(f"변수 '{v.name}': min({v.min}) > max({v.max})")
    return errors


def _check_duplicate_rule_ids(ruleset: RuleSet) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for r in ruleset.rules:
        if r.id in seen and r.id not in dups:
            dups.append(r.id)
        seen.add(r.id)
    return [f"중복된 rule id: '{d}'" for d in dups]


def _check_references(ruleset: RuleSet) -> list[str]:
    """표현식이 참조하는 심볼이 모두 정의돼 있는지 검사한다.

    유효 심볼 = 선언된 변수명 ∪ 모든 enum 값. (enum 값이 어느 변수 소속인지까지는
    1차에서 따지지 않는다 — 오타 탐지가 목적.)
    """
    known: set[str] = {v.name for v in ruleset.variables}
    for v in ruleset.variables:
        known.update(v.values)

    errors: list[str] = []
    for rule in ruleset.rules:
        for clause, expr in (("when", rule.when), ("then", rule.then)):
            if expr is None:
                continue
            errors.extend(_check_expr_references(rule, clause, expr, known))
    return errors


def _check_expr_references(rule: Rule, clause: str, expr: str, known: set[str]) -> list[str]:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return [f"룰 '{rule.id}'의 {clause} 표현식 구문 오류: {expr!r} ({e.msg})"]

    errors: list[str] = []
    for name in sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}):
        if name not in known:
            errors.append(f"룰 '{rule.id}'의 {clause}가 미정의 심볼을 참조: '{name}'")
    return errors
