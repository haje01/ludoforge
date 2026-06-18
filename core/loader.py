"""로더: .rule(YAML) 파일을 IR(RuleSet)로 변환한다.

책임 경계: **구조적 파싱만** 한다 — YAML 형식, 필수 키 존재, 필드 타입.
참조 무결성(미정의 심볼 참조, 중복 constraint id, 순환 의존)은 S3 스키마 검증의 몫이다.
파싱 실패 시 어떤 파일/필드가 문제인지 명시한 LoaderError를 던진다(CLAUDE.md §7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.ir import Check, Constraint, Expect, Outcome, RuleSet, Transition, Variable

_VALID_TYPES = ("int", "enum", "bool", "real")
# 검사(check) kind별 필요 필드(D12). reachable/invariant는 `that`, prob는 `spec`(PCTL).
_CHECK_KINDS = ("reachable", "invariant", "prob", "no_deadlock")


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
    """여러 RuleSet을 병합한다. 변수는 이름으로 합치되 충돌(다른 선언)은 오류.

    전이 시스템(D12)도 병합한다: transitions/checks는 이어 붙이고, `init`은 전역
    초기 상태라 둘 이상의 파일이 선언하면 모호하므로 오류로 본다.
    """
    variables: dict[str, Variable] = {}
    constraints: list[Constraint] = []
    expects: list[Expect] = []
    transitions: list[Transition] = []
    checks: list[Check] = []
    init: str | None = None
    for rs in rulesets:
        for v in rs.variables:
            if v.name in variables and variables[v.name] != v:
                raise LoaderError(f"변수 '{v.name}'가 파일마다 다르게 선언되었습니다.")
            variables[v.name] = v
        constraints.extend(rs.constraints)
        expects.extend(rs.expects)
        transitions.extend(rs.transitions)
        checks.extend(rs.checks)
        if rs.init is not None:
            if init is not None:
                raise LoaderError("init(초기 상태)이 둘 이상의 파일에 선언되었습니다 (전역 1개).")
            init = rs.init
    return RuleSet(
        variables=tuple(variables.values()),
        constraints=tuple(constraints),
        expects=tuple(expects),
        init=init,
        transitions=tuple(transitions),
        checks=tuple(checks),
    )


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
        raise LoaderError(f"{path}: 최상위는 매핑이어야 합니다 (domain/constraints 키).")

    variables = _parse_variables(raw.get("domain", {}), path)
    constraints = _parse_constraints(raw.get("constraints", []), path)
    expects = _parse_expects(raw.get("expects", []), path)
    init = _parse_init(raw.get("init"), path)
    transitions = _parse_transitions(raw.get("transitions", []), path)
    checks = _parse_checks(raw.get("checks", []), path)
    return RuleSet(
        variables=variables,
        constraints=constraints,
        expects=expects,
        init=init,
        transitions=transitions,
        checks=checks,
    )


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

    if vtype == "real":
        return Variable(
            name=name,
            type="real",
            min=_parse_opt_float(spec.get("min"), name, "min", path),
            max=_parse_opt_float(spec.get("max"), name, "max", path),
        )

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


def _parse_opt_float(value: Any, var_name: str, field: str, path: Path) -> float | None:
    """real 변수의 경계. 정수/실수 모두 받아 float로 정규화한다(bool 제외)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LoaderError(f"{path}: 변수 '{var_name}'의 {field}는 실수여야 합니다: {value!r}")
    return float(value)


def _parse_constraints(constraints: Any, path: Path) -> tuple[Constraint, ...]:
    if not isinstance(constraints, list):
        raise LoaderError(f"{path}: 'constraints'는 목록이어야 합니다.")

    parsed: list[Constraint] = []
    for i, item in enumerate(constraints):
        parsed.append(_parse_constraint(item, i, path))
    return tuple(parsed)


def _parse_constraint(item: Any, index: int, path: Path) -> Constraint:
    if not isinstance(item, dict):
        raise LoaderError(f"{path}: constraints[{index}]는 매핑이어야 합니다.")

    cid = item.get("id")
    if not isinstance(cid, str) or not cid:
        raise LoaderError(f"{path}: constraints[{index}]에 문자열 'id'가 필요합니다.")

    then = item.get("then")
    if not isinstance(then, str) or not then:
        raise LoaderError(f"{path}: 제약 '{cid}'에 문자열 'then'이 필요합니다.")

    return Constraint(
        id=cid,
        then=then,
        when=_parse_opt_str(item.get("when"), cid, "when", path),
        author=_parse_opt_str(item.get("author"), cid, "author", path),
        desc=_parse_opt_str(item.get("desc"), cid, "desc", path),
        source=path.name,
    )


def _parse_expects(expects: Any, path: Path) -> tuple[Expect, ...]:
    if not isinstance(expects, list):
        raise LoaderError(f"{path}: 'expects'는 목록이어야 합니다.")

    parsed: list[Expect] = []
    for i, item in enumerate(expects):
        parsed.append(_parse_expect(item, i, path))
    return tuple(parsed)


def _parse_expect(item: Any, index: int, path: Path) -> Expect:
    if not isinstance(item, dict):
        raise LoaderError(f"{path}: expects[{index}]는 매핑이어야 합니다.")

    expect_id = item.get("id")
    if not isinstance(expect_id, str) or not expect_id:
        raise LoaderError(f"{path}: expects[{index}]에 문자열 'id'가 필요합니다.")

    that = item.get("that")
    if not isinstance(that, str) or not that:
        raise LoaderError(f"{path}: 기대 '{expect_id}'에 문자열 'that'(도달 조건)이 필요합니다.")

    desc = _parse_opt_str(item.get("desc"), expect_id, "desc", path)
    return Expect(id=expect_id, that=that, desc=desc)


def _parse_init(value: Any, path: Path) -> str | None:
    """전이 시스템의 초기 상태 술어(D12). 선택적 최상위 문자열."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise LoaderError(f"{path}: 'init'은 비어있지 않은 문자열(초기 상태 술어)이어야 합니다.")
    return value


def _parse_transitions(transitions: Any, path: Path) -> tuple[Transition, ...]:
    if not isinstance(transitions, list):
        raise LoaderError(f"{path}: 'transitions'는 목록이어야 합니다.")
    return tuple(_parse_transition(item, i, path) for i, item in enumerate(transitions))


def _parse_transition(item: Any, index: int, path: Path) -> Transition:
    if not isinstance(item, dict):
        raise LoaderError(f"{path}: transitions[{index}]는 매핑이어야 합니다.")

    tid = item.get("id")
    if not isinstance(tid, str) or not tid:
        raise LoaderError(f"{path}: transitions[{index}]에 문자열 'id'가 필요합니다.")

    has_then = "then" in item
    has_outcomes = "outcomes" in item
    if has_then and has_outcomes:
        raise LoaderError(f"{path}: 전이 '{tid}'는 'then'과 'outcomes' 중 하나만 가질 수 있습니다.")
    if not has_then and not has_outcomes:
        raise LoaderError(f"{path}: 전이 '{tid}'에 'then' 또는 'outcomes'가 필요합니다.")

    if has_then:
        then = item.get("then")
        if not isinstance(then, str) or not then:
            raise LoaderError(f"{path}: 전이 '{tid}'의 'then'은 비어있지 않은 문자열이어야 합니다.")
        # bare then은 weight=1.0 단일 Outcome으로 정규화한다(D12).
        outcomes: tuple[Outcome, ...] = (Outcome(then=then),)
    else:
        outcomes = _parse_outcomes(item.get("outcomes"), tid, path)

    return Transition(
        id=tid,
        outcomes=outcomes,
        when=_parse_opt_str(item.get("when"), tid, "when", path),
        desc=_parse_opt_str(item.get("desc"), tid, "desc", path),
        source=path.name,
    )


def _parse_outcomes(outcomes: Any, tid: str, path: Path) -> tuple[Outcome, ...]:
    if not isinstance(outcomes, list) or not outcomes:
        raise LoaderError(f"{path}: 전이 '{tid}'의 'outcomes'는 비어있지 않은 목록이어야 합니다.")
    parsed: list[Outcome] = []
    for i, item in enumerate(outcomes):
        if not isinstance(item, dict):
            raise LoaderError(f"{path}: 전이 '{tid}' outcomes[{i}]는 매핑이어야 합니다.")
        then = item.get("then")
        if not isinstance(then, str) or not then:
            raise LoaderError(f"{path}: 전이 '{tid}' outcomes[{i}]에 문자열 'then'이 필요합니다.")
        weight = _parse_weight(item.get("weight"), tid, i, path)
        parsed.append(Outcome(then=then, weight=weight))
    return tuple(parsed)


def _parse_weight(value: Any, tid: str, index: int, path: Path) -> float:
    """outcome 가중치. 생략 시 1.0. 음수는 거부(합 검증은 확률 백엔드 몫, D13)."""
    if value is None:
        return 1.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LoaderError(
            f"{path}: 전이 '{tid}' outcomes[{index}]의 weight는 실수여야 합니다: {value!r}"
        )
    if value < 0:
        raise LoaderError(
            f"{path}: 전이 '{tid}' outcomes[{index}]의 weight는 음수일 수 없습니다: {value}"
        )
    return float(value)


def _parse_checks(checks: Any, path: Path) -> tuple[Check, ...]:
    if not isinstance(checks, list):
        raise LoaderError(f"{path}: 'checks'는 목록이어야 합니다.")
    return tuple(_parse_check(item, i, path) for i, item in enumerate(checks))


def _parse_check(item: Any, index: int, path: Path) -> Check:
    if not isinstance(item, dict):
        raise LoaderError(f"{path}: checks[{index}]는 매핑이어야 합니다.")

    cid = item.get("id")
    if not isinstance(cid, str) or not cid:
        raise LoaderError(f"{path}: checks[{index}]에 문자열 'id'가 필요합니다.")

    kind = item.get("kind")
    if kind not in _CHECK_KINDS:
        raise LoaderError(f"{path}: 검사 '{cid}'의 kind가 잘못됨: {kind!r} (허용: {_CHECK_KINDS})")

    that = _parse_opt_str(item.get("that"), cid, "that", path)
    spec = _parse_opt_str(item.get("spec"), cid, "spec", path)

    # kind별 필요 필드 강제(D12): reachable/invariant는 that, prob는 spec.
    if kind in ("reachable", "invariant") and not that:
        raise LoaderError(
            f"{path}: 검사 '{cid}'(kind={kind})에 문자열 'that'(상태 술어)이 필요합니다."
        )
    if kind == "prob" and not spec:
        raise LoaderError(f"{path}: 검사 '{cid}'(kind=prob)에 문자열 'spec'(PCTL)이 필요합니다.")

    return Check(
        id=cid,
        kind=kind,
        that=that,
        spec=spec,
        desc=_parse_opt_str(item.get("desc"), cid, "desc", path),
        source=path.name,
    )


def _parse_opt_str(value: Any, rule_id: str, field: str, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LoaderError(f"{path}: 룰 '{rule_id}'의 {field}는 문자열이어야 합니다: {value!r}")
    return value
