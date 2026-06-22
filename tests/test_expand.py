"""Tier 1 템플릿 확장(desugar) 테스트 — `for:`/`${param}` → 구체 항목 (D18).

로더가 파싱 직후 펼치므로 IR·백엔드는 구체 항목만 본다. 생성 id는 추적 가능해야 하고,
`${name}` 전체 치환은 값의 타입(숫자 weight 등)을 보존해야 한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.loader import LoaderError, load_rule_file

_DOM = "domain: {variables: {g: {type: int, min: 0, max: 9}, m: {type: enum, values: [a, b]}}}\n"


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "t.rule"
    p.write_text(_DOM + body, encoding="utf-8")
    return p


def test_records_form_expands_transitions(tmp_path: Path) -> None:
    body = (
        "transitions:\n"
        '  - id: "t_${k}"\n'
        "    for:\n"
        "      - { k: a, w: 0.7 }\n"
        "      - { k: b, w: 0.3 }\n"
        '    when: "m == ${k}"\n'
        "    outcomes:\n"
        '      - { weight: "${w}", then: "next.g == g" }\n'
    )
    rs = load_rule_file(_write(tmp_path, body))
    assert [t.id for t in rs.transitions] == ["t_a", "t_b"]
    assert rs.transitions[0].when == "m == a"
    # ${w} 전체 치환 → float 타입 보존
    assert rs.transitions[0].outcomes[0].weight == 0.7
    assert rs.transitions[1].outcomes[0].weight == 0.3


def test_product_form_cartesian(tmp_path: Path) -> None:
    body = (
        "transitions:\n"
        '  - id: "t_${x}_${y}"\n'
        "    for: { x: [a, b], y: [a, b] }\n"
        '    when: "m == ${x}"\n'
        '    then: "next.m == ${y}"\n'
    )
    rs = load_rule_file(_write(tmp_path, body))
    assert [t.id for t in rs.transitions] == ["t_a_a", "t_a_b", "t_b_a", "t_b_b"]


def test_interpolation_in_string(tmp_path: Path) -> None:
    body = (
        "constraints:\n"
        '  - id: "c_${k}"\n'
        "    for: [ { k: a, lim: 3 }, { k: b, lim: 5 } ]\n"
        '    when: "m == ${k}"\n'
        '    then: "g <= ${lim}"\n'
    )
    rs = load_rule_file(_write(tmp_path, body))
    assert [c.id for c in rs.constraints] == ["c_a", "c_b"]
    assert rs.constraints[1].then == "g <= 5"


def test_undefined_param_is_error(tmp_path: Path) -> None:
    body = (
        "transitions:\n"
        '  - id: "t_${k}"\n'
        "    for: [ { k: a } ]\n"
        '    when: "m == ${nope}"\n'
        '    then: "next.g == g"\n'
    )
    with pytest.raises(LoaderError, match="nope"):
        load_rule_file(_write(tmp_path, body))


def test_for_in_checks(tmp_path: Path) -> None:
    body = (
        "checks:\n"
        '  - id: "reach_${k}"\n'
        "    for: [ { k: a }, { k: b } ]\n"
        "    kind: reachable\n"
        '    that: "m == ${k}"\n'
    )
    rs = load_rule_file(_write(tmp_path, body))
    assert [c.id for c in rs.checks] == ["reach_a", "reach_b"]
    assert rs.checks[1].that == "m == b"


def test_no_for_is_passthrough(tmp_path: Path) -> None:
    body = 'transitions:\n  - id: plain\n    when: "m == a"\n    then: "next.g == g"\n'
    rs = load_rule_file(_write(tmp_path, body))
    assert [t.id for t in rs.transitions] == ["plain"]


def test_bad_for_shape_is_error(tmp_path: Path) -> None:
    body = (
        "transitions:\n"
        '  - id: "t_${k}"\n'
        "    for: 3\n"  # 리스트도 매핑도 아님
        '    then: "next.g == g"\n'
    )
    with pytest.raises(LoaderError, match="for"):
        load_rule_file(_write(tmp_path, body))
