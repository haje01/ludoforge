"""S2: 로더 테스트. .rule(YAML) → IR(RuleSet).

로더는 구조적 파싱만 담당한다(YAML 형식, 필수 키, 필드 타입).
참조 무결성(미정의 심볼, 중복 id 등)은 S3 스키마 검증의 몫이다.
실패 시 어떤 파일/필드가 문제인지 명시한 LoaderError를 던진다(CLAUDE.md §7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ruleforge.dsl.ir import RuleSet
from ruleforge.dsl.loader import LoaderError, load_rule_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_section4_example() -> None:
    rs = load_rule_file(FIXTURES / "warrior_hp.rule")
    assert isinstance(rs, RuleSet)

    level = rs.variable("level")
    assert (level.type, level.min, level.max) == ("int", 1, 100)
    role = rs.variable("role")
    assert (role.type, role.values) == ("enum", ("warrior", "mage", "archer"))

    ids = [r.id for r in rs.rules]
    assert ids == ["warrior_hp_formula", "global_hp_cap"]
    warrior = rs.rules[0]
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
        "domain:\n  variables:\n    hp: { type: int }\nrules:\n  - id: r1\n    when: 'hp > 0'\n",
        encoding="utf-8",
    )
    with pytest.raises(LoaderError, match="r1"):
        load_rule_file(f)


def test_unknown_variable_type_names_the_variable(tmp_path: Path) -> None:
    f = tmp_path / "bad_type.rule"
    f.write_text(
        "domain:\n  variables:\n    hp: { type: float }\nrules: []\n",
        encoding="utf-8",
    )
    with pytest.raises(LoaderError, match="hp"):
        load_rule_file(f)


def test_loads_bool_variable(tmp_path: Path) -> None:
    f = tmp_path / "b.rule"
    f.write_text(
        "domain:\n  variables:\n    stealthed: { type: bool }\nrules: []\n",
        encoding="utf-8",
    )
    rs = load_rule_file(f)
    v = rs.variable("stealthed")
    assert (v.type, v.min, v.max, v.values) == ("bool", None, None, ())


def test_enum_without_values_names_the_variable(tmp_path: Path) -> None:
    f = tmp_path / "bad_enum.rule"
    f.write_text(
        "domain:\n  variables:\n    role: { type: enum }\nrules: []\n",
        encoding="utf-8",
    )
    with pytest.raises(LoaderError, match="role"):
        load_rule_file(f)
