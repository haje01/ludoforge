"""S2: 로더 테스트. .rule(YAML) → IR(RuleSet).

로더는 구조적 파싱만 담당한다(YAML 형식, 필수 키, 필드 타입).
참조 무결성(미정의 심볼, 중복 id 등)은 S3 스키마 검증의 몫이다.
실패 시 어떤 파일/필드가 문제인지 명시한 LoaderError를 던진다(CLAUDE.md §7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ir import RuleSet
from core.loader import LoaderError, load_rule_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_section4_example() -> None:
    rs = load_rule_file(FIXTURES / "warrior_hp.rule")
    assert isinstance(rs, RuleSet)

    level = rs.variable("level")
    assert (level.type, level.min, level.max) == ("int", 1, 100)
    role = rs.variable("role")
    assert (role.type, role.values) == ("enum", ("warrior", "mage", "archer"))

    ids = [r.id for r in rs.constraints]
    assert ids == ["warrior_hp_formula", "global_hp_cap"]
    warrior = rs.constraints[0]
    assert warrior.when == "role == warrior"
    assert warrior.then == "hp == level * 100"
    assert warrior.author == "planner_A"


def test_missing_file_raises_loader_error(tmp_path: Path) -> None:
    with pytest.raises(LoaderError, match="없"):
        load_rule_file(tmp_path / "nope.rule")


def test_malformed_yaml_raises_loader_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.rule"
    bad.write_text("domain: [unclosed\n", encoding="utf-8")
    with pytest.raises(LoaderError, match="YAML"):
        load_rule_file(bad)


def test_rule_without_then_names_the_rule(tmp_path: Path) -> None:
    f = tmp_path / "no_then.rule"
    f.write_text(
        "domain:\n  variables:\n    hp: { type: int }\n"
        "constraints:\n  - id: r1\n    when: 'hp > 0'\n",
        encoding="utf-8",
    )
    with pytest.raises(LoaderError, match="r1"):
        load_rule_file(f)


def test_unknown_variable_type_names_the_variable(tmp_path: Path) -> None:
    f = tmp_path / "bad_type.rule"
    f.write_text(
        "domain:\n  variables:\n    hp: { type: float }\nconstraints: []\n",
        encoding="utf-8",
    )
    with pytest.raises(LoaderError, match="hp"):
        load_rule_file(f)


def test_loads_bool_variable(tmp_path: Path) -> None:
    f = tmp_path / "b.rule"
    f.write_text(
        "domain:\n  variables:\n    stealthed: { type: bool }\nconstraints: []\n",
        encoding="utf-8",
    )
    rs = load_rule_file(f)
    v = rs.variable("stealthed")
    assert (v.type, v.min, v.max, v.values) == ("bool", None, None, ())


def test_loads_real_variable(tmp_path: Path) -> None:
    f = tmp_path / "r.rule"
    f.write_text(
        "domain:\n  variables:\n    prob: { type: real, min: 0, max: 1 }\nconstraints: []\n",
        encoding="utf-8",
    )
    rs = load_rule_file(f)
    v = rs.variable("prob")
    assert (v.type, v.min, v.max) == ("real", 0.0, 1.0)


def test_real_accepts_float_bounds(tmp_path: Path) -> None:
    f = tmp_path / "r2.rule"
    f.write_text(
        "domain:\n  variables:\n    drop: { type: real, min: 0.05, max: 0.5 }\nconstraints: []\n",
        encoding="utf-8",
    )
    v = load_rule_file(f).variable("drop")
    assert (v.min, v.max) == (0.05, 0.5)


def test_loads_expects_section(tmp_path: Path) -> None:
    f = tmp_path / "e.rule"
    f.write_text(
        "domain:\n  variables:\n    level: { type: int, min: 1, max: 100 }\n"
        "constraints: []\n"
        "expects:\n"
        "  - id: lvl_max\n    desc: '레벨 100 도달 가능'\n    that: 'level == 100'\n",
        encoding="utf-8",
    )
    rs = load_rule_file(f)
    assert len(rs.expects) == 1
    e = rs.expects[0]
    assert (e.id, e.that, e.desc) == ("lvl_max", "level == 100", "레벨 100 도달 가능")


def test_expect_without_that_names_it(tmp_path: Path) -> None:
    f = tmp_path / "bad_expect.rule"
    f.write_text(
        "domain:\n  variables:\n    level: { type: int }\nconstraints: []\n"
        "expects:\n  - id: e1\n    desc: '설명만 있음'\n",
        encoding="utf-8",
    )
    with pytest.raises(LoaderError, match="e1"):
        load_rule_file(f)


def test_enum_without_values_names_the_variable(tmp_path: Path) -> None:
    f = tmp_path / "bad_enum.rule"
    f.write_text(
        "domain:\n  variables:\n    role: { type: enum }\nconstraints: []\n",
        encoding="utf-8",
    )
    with pytest.raises(LoaderError, match="role"):
        load_rule_file(f)
