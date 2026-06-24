"""로더: .rule(YAML) 파일을 IR(RuleSet)로 변환한다.

책임 경계: **구조적 파싱만** 한다 — YAML 형식, 필수 키 존재, 필드 타입.
참조 무결성(미정의 심볼 참조, 중복 constraint id, 순환 의존)은 S3 스키마 검증의 몫이다.
파싱 실패 시 어떤 파일/필드가 문제인지 명시한 LoaderError를 던진다(CLAUDE.md §7).
"""

from __future__ import annotations

import ast
import itertools
import re
from pathlib import Path
from typing import Any

import yaml

from core.ir import Check, Constraint, Expect, Outcome, RuleSet, Transition, Variable

_VALID_TYPES = ("int", "enum", "bool", "real")
# 검사(check) kind별 필요 필드(D12·D19). reachable/invariant는 `that`, prob는 `spec`(PCTL),
# distribution은 `expr`(수치식, sim 백엔드 전용).
_CHECK_KINDS = ("reachable", "invariant", "prob", "no_deadlock", "distribution")
# 템플릿 치환 토큰 `${expr}` — expr는 파라미터/테이블 색인식(Tier 1/2 확장, D18).
_TEMPLATE_TOKEN = re.compile(r"\$\{([^}]+)\}")


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
    # `for:` 템플릿을 구체 항목으로 펼친 뒤(D18) 파싱한다 — IR·백엔드는 구체 항목만 본다.
    # `tables:`는 desugar 시점 데이터(템플릿 `${name[...]}`이 참조), IR엔 안 들어간다.
    tables = _parse_tables(raw.get("tables", {}), path)
    constraints = _parse_constraints(
        _expand_items(raw.get("constraints", []), "constraints", path, tables), path
    )
    expects = _parse_expects(raw.get("expects", []), path)
    init = _parse_init(raw.get("init"), path)
    transitions = _parse_transitions(
        _expand_items(raw.get("transitions", []), "transitions", path, tables), path
    )
    checks = _parse_checks(_expand_items(raw.get("checks", []), "checks", path, tables), path)
    return RuleSet(
        variables=variables,
        constraints=constraints,
        expects=expects,
        init=init,
        transitions=transitions,
        checks=checks,
    )


def _parse_tables(spec: Any, path: Path) -> dict[str, Any]:
    """`tables:` 데이터 섹션(이름→상수/표)을 그대로 반환한다(Tier 2, D18).

    템플릿 `${name[...]}`이 참조하는 desugar 시점 데이터다 — IR엔 들어가지 않는다. 구조는
    검증하지 않으며, 잘못된 참조/색인은 치환 시점에 LoaderError로 보고한다.
    """
    if not isinstance(spec, dict):
        raise LoaderError(f"{path}: 'tables'는 매핑이어야 합니다(이름→데이터).")
    return spec


def _expand_items(items: Any, section: str, path: Path, tables: dict[str, Any]) -> Any:
    """`for:` 템플릿 항목을 구체 항목들로 펼친다(Tier 1/2 desugar, D18).

    항목이 `for`를 가지면 그 바인딩마다 항목을 복제하고 `${expr}`(파라미터·`tables` 색인)을
    치환한다. `for`가 없는 항목·리스트 아닌 값은 그대로 통과(타입 오류는 각 _parse_*가 보고).
    펼치기는 순수 구문 변환이라 결정론 경계를 건드리지 않으며, 생성 id는 템플릿대로 추적 가능하다.
    """
    if not isinstance(items, list):
        return items
    out: list[Any] = []
    for index, item in enumerate(items):
        if isinstance(item, dict) and "for" in item:
            out.extend(_expand_template(item, section, index, path, tables))
        else:
            out.append(item)
    return out


def _expand_template(
    item: dict[str, Any], section: str, index: int, path: Path, tables: dict[str, Any]
) -> list[Any]:
    records = _for_records(item["for"], section, index, path)
    template = {k: v for k, v in item.items() if k != "for"}
    return [_subst_node(template, rec, tables, section, index, path) for rec in records]


def _for_records(spec: Any, section: str, index: int, path: Path) -> list[dict[str, Any]]:
    """`for` 명세를 바인딩 레코드 목록으로 정규화한다.

    - 리스트(레코드들): 각 레코드를 그대로 한 번씩.
    - 매핑(파라미터→리스트): 값들의 데카르트 곱(product).
    """
    where = f"{section}[{index}]"
    if isinstance(spec, list):
        records: list[dict[str, Any]] = []
        for r in spec:
            if not isinstance(r, dict):
                raise LoaderError(f"{path}: {where}의 for 레코드는 매핑이어야 합니다: {r!r}")
            records.append(r)
        return records
    if isinstance(spec, dict):
        names = list(spec.keys())
        value_lists: list[list[Any]] = []
        for name in names:
            values = spec[name]
            if not isinstance(values, list):
                raise LoaderError(f"{path}: {where}의 for '{name}'은(는) 리스트여야 합니다.")
            value_lists.append(values)
        return [dict(zip(names, combo, strict=True)) for combo in itertools.product(*value_lists)]
    raise LoaderError(
        f"{path}: {where}의 for는 리스트(레코드) 또는 매핑(파라미터→리스트)이어야 합니다."
    )


def _subst_node(
    node: Any, rec: dict[str, Any], tables: dict[str, Any], section: str, index: int, path: Path
) -> Any:
    if isinstance(node, dict):
        return {k: _subst_node(v, rec, tables, section, index, path) for k, v in node.items()}
    if isinstance(node, list):
        return [_subst_node(v, rec, tables, section, index, path) for v in node]
    if isinstance(node, str):
        return _subst_str(node, rec, tables, section, index, path)
    return node


def _subst_str(
    text: str, rec: dict[str, Any], tables: dict[str, Any], section: str, index: int, path: Path
) -> Any:
    """`${expr}`를 치환한다. 전체가 `${expr}`이면 값의 타입을 보존한다(weight 숫자 등).

    expr는 파라미터/테이블 이름과 색인(`win[monster][cls]`)을 쓰는 제한된 식 — ast로 파싱해
    화이트리스트 노드(Name·Subscript·Constant)만 평가한다(eval 미사용, 번역기와 같은 규율).
    """
    where = f"{section}[{index}]"
    names = {**tables, **rec}
    whole = _TEMPLATE_TOKEN.fullmatch(text)
    if whole is not None:
        return _eval_template(whole.group(1), names, where, path)

    def repl(mo: re.Match[str]) -> str:
        return str(_eval_template(mo.group(1), names, where, path))

    return _TEMPLATE_TOKEN.sub(repl, text)


def _eval_template(src: str, names: dict[str, Any], where: str, path: Path) -> Any:
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        raise LoaderError(f"{path}: {where} 템플릿 식 구문 오류: '{src}' ({e.msg})") from e
    return _eval_template_node(tree.body, names, src, where, path)


def _eval_template_node(
    node: ast.AST, names: dict[str, Any], src: str, where: str, path: Path
) -> Any:
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise LoaderError(f"{path}: {where} 템플릿의 미정의 파라미터/테이블: '{node.id}'")
        return names[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Subscript):
        base = _eval_template_node(node.value, names, src, where, path)
        key = _eval_template_node(node.slice, names, src, where, path)
        try:
            return base[key]
        except (KeyError, IndexError, TypeError) as e:
            raise LoaderError(f"{path}: {where} 템플릿 색인 실패: '{src}' ({e!r})") from e
    raise LoaderError(
        f"{path}: {where} 템플릿 식에 허용되지 않는 요소: '{src}' ({type(node).__name__})"
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
        pref=_parse_pref(item.get("pref"), tid, path),
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


def _parse_pref(value: Any, tid: str, path: Path) -> float | None:
    """전이 선호도(플레이어 정책, D20). 생략 시 None(미선언). 음수는 거부.

    `outcomes.weight`와 달리 sim 전용으로 enabled 전이끼리 정규화된다(BMC/PRISM은 무시).
    None은 미선언 — co-enabled 집합에 섞이면 sim이 거부한다(opt-in 안전망). 합 검증은 표집 몫.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LoaderError(f"{path}: 전이 '{tid}'의 pref는 실수여야 합니다: {value!r}")
    if value < 0:
        raise LoaderError(f"{path}: 전이 '{tid}'의 pref는 음수일 수 없습니다: {value}")
    return float(value)


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
    expr = _parse_opt_str(item.get("expr"), cid, "expr", path)

    # kind별 필요 필드 강제(D12·D19): reachable/invariant는 that, prob는 spec, distribution은 expr.
    if kind in ("reachable", "invariant") and not that:
        raise LoaderError(
            f"{path}: 검사 '{cid}'(kind={kind})에 문자열 'that'(상태 술어)이 필요합니다."
        )
    if kind == "prob" and not spec:
        raise LoaderError(f"{path}: 검사 '{cid}'(kind=prob)에 문자열 'spec'(PCTL)이 필요합니다.")
    if kind == "distribution" and not expr:
        raise LoaderError(
            f"{path}: 검사 '{cid}'(kind=distribution)에 문자열 'expr'(수치식)이 필요합니다."
        )

    return Check(
        id=cid,
        kind=kind,
        that=that,
        spec=spec,
        expr=expr,
        desc=_parse_opt_str(item.get("desc"), cid, "desc", path),
        source=path.name,
    )


def _parse_opt_str(value: Any, rule_id: str, field: str, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LoaderError(f"{path}: 룰 '{rule_id}'의 {field}는 문자열이어야 합니다: {value!r}")
    return value
