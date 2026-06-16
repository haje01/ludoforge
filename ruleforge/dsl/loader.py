"""로더: .rule(YAML) 파일을 IR(RuleSet)로 변환한다.

책임 경계: **구조적 파싱만** 한다 — YAML 형식, 필수 키 존재, 필드 타입.
참조 무결성(미정의 심볼 참조, 중복 rule id, 순환 의존)은 S3 스키마 검증의 몫이다.
파싱 실패 시 어떤 파일/필드가 문제인지 명시한 LoaderError를 던진다(CLAUDE.md §7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ruleforge.dsl.ir import Rule, RuleSet, Variable

_VALID_TYPES = ("int", "enum", "bool")


class LoaderError(Exception):
    """룰 파일 로딩 실패. 메시지에 문제 위치(파일/필드)를 담는다."""


def load_rules(path: str | Path) -> RuleSet:
    """경로를 로드한다. 파일이면 단일 RuleSet, 디렉토리면 모든 .rule을 병합한다.

    디렉토리 병합은 여러 기획자가 각자 파일에 쓴 룰을 함께 검사하기 위함이다
    (CLAUDE.md §1 — 파일 간 모순 탐지가 본 도구의 핵심 가치).
    """
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.rule"))
        if not files:
            raise LoaderError(f"디렉토리에 .rule 파일이 없습니다: {path}")
        return _merge([load_rule_file(f) for f in files])
    return load_rule_file(path)


def _merge(rulesets: list[RuleSet]) -> RuleSet:
    """여러 RuleSet을 병합한다. 변수는 이름으로 합치되 충돌(다른 선언)은 오류."""
    variables: dict[str, Variable] = {}
    rules: list[Rule] = []
    for rs in rulesets:
        for v in rs.variables:
            if v.name in variables and variables[v.name] != v:
                raise LoaderError(f"변수 '{v.name}'가 파일마다 다르게 선언되었습니다.")
            variables[v.name] = v
        rules.extend(rs.rules)
    return RuleSet(variables=tuple(variables.values()), rules=tuple(rules))


def load_rule_file(path: str | Path) -> RuleSet:
    """단일 .rule 파일을 읽어 RuleSet으로 변환한다."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise LoaderError(f"룰 파일을 찾을 수 없습니다: {path}") from e

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise LoaderError(f"{path}: YAML 파싱 실패 — {e}") from e

    if not isinstance(raw, dict):
        raise LoaderError(f"{path}: 최상위는 매핑이어야 합니다 (domain/rules 키).")

    variables = _parse_variables(raw.get("domain", {}), path)
    rules = _parse_rules(raw.get("rules", []), path)
    return RuleSet(variables=variables, rules=rules)


def _parse_variables(domain: Any, path: Path) -> tuple[Variable, ...]:
    if not isinstance(domain, dict):
        raise LoaderError(f"{path}: 'domain'은 매핑이어야 합니다.")
    var_specs = domain.get("variables", {})
    if not isinstance(var_specs, dict):
        raise LoaderError(f"{path}: 'domain.variables'는 변수명→스펙 매핑이어야 합니다.")

    variables: list[Variable] = []
    for name, spec in var_specs.items():
        variables.append(_parse_variable(str(name), spec, path))
    return tuple(variables)


def _parse_variable(name: str, spec: Any, path: Path) -> Variable:
    if not isinstance(spec, dict):
        raise LoaderError(f"{path}: 변수 '{name}' 스펙은 매핑이어야 합니다.")

    vtype = spec.get("type")
    if vtype not in _VALID_TYPES:
        raise LoaderError(
            f"{path}: 변수 '{name}'의 type이 잘못됨: {vtype!r} (허용: {_VALID_TYPES})"
        )

    if vtype == "int":
        return Variable(
            name=name,
            type="int",
            min=_parse_opt_int(spec.get("min"), name, "min", path),
            max=_parse_opt_int(spec.get("max"), name, "max", path),
        )

    if vtype == "bool":
        return Variable(name=name, type="bool")

    # enum
    values = spec.get("values")
    if not isinstance(values, list) or not values:
        raise LoaderError(
            f"{path}: 변수 '{name}'(enum)에는 비어있지 않은 values 목록이 필요합니다."
        )
    return Variable(name=name, type="enum", values=tuple(str(v) for v in values))


def _parse_opt_int(value: Any, var_name: str, field: str, path: Path) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise LoaderError(f"{path}: 변수 '{var_name}'의 {field}는 정수여야 합니다: {value!r}")
    return value


def _parse_rules(rules: Any, path: Path) -> tuple[Rule, ...]:
    if not isinstance(rules, list):
        raise LoaderError(f"{path}: 'rules'는 목록이어야 합니다.")

    parsed: list[Rule] = []
    for i, item in enumerate(rules):
        parsed.append(_parse_rule(item, i, path))
    return tuple(parsed)


def _parse_rule(item: Any, index: int, path: Path) -> Rule:
    if not isinstance(item, dict):
        raise LoaderError(f"{path}: rules[{index}]는 매핑이어야 합니다.")

    rule_id = item.get("id")
    if not isinstance(rule_id, str) or not rule_id:
        raise LoaderError(f"{path}: rules[{index}]에 문자열 'id'가 필요합니다.")

    then = item.get("then")
    if not isinstance(then, str) or not then:
        raise LoaderError(f"{path}: 룰 '{rule_id}'에 문자열 'then'이 필요합니다.")

    return Rule(
        id=rule_id,
        then=then,
        when=_parse_opt_str(item.get("when"), rule_id, "when", path),
        author=_parse_opt_str(item.get("author"), rule_id, "author", path),
        desc=_parse_opt_str(item.get("desc"), rule_id, "desc", path),
    )


def _parse_opt_str(value: Any, rule_id: str, field: str, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LoaderError(f"{path}: 룰 '{rule_id}'의 {field}는 문자열이어야 합니다: {value!r}")
    return value
