"""S2: 로더 진입점 테스트. 확장자 디스패치·디렉토리 병합(.lf 전용, D32).

구조적 파싱(문법·필드)은 text_loader의 몫이라 test_text_loader.py가 검증한다.
여기서는 진입점 책임만 본다: 파일/디렉토리 로드, YAML(.rule) 거부, 병합 규칙.
실패 시 어떤 파일/필드가 문제인지 명시한 LoaderError를 던진다(CLAUDE.md §7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ir import RuleSet
from core.loader import LoaderError, load_rule_file, load_rules

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_section4_example() -> None:
    rs = load_rule_file(FIXTURES / "warrior_hp.lf")
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
        load_rule_file(tmp_path / "nope.lf")


def test_yaml_rule_format_rejected(tmp_path: Path) -> None:
    # D32: YAML 프론트엔드 제거 — 조용한 무시가 아니라 .lf 안내와 함께 거부한다.
    legacy = tmp_path / "legacy.rule"
    legacy.write_text("domain:\n  variables:\n    hp: { type: int }\n", encoding="utf-8")
    with pytest.raises(LoaderError, match=r"\.lf"):
        load_rule_file(legacy)


def test_parse_error_reports_source_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.lf"
    bad.write_text("domain { hp: int 0.. \n", encoding="utf-8")  # 블록 미닫힘
    with pytest.raises(LoaderError):
        load_rule_file(bad)


def test_directory_without_lf_files_rejected(tmp_path: Path) -> None:
    with pytest.raises(LoaderError, match=r"\.lf"):
        load_rules(tmp_path)


def test_directory_merges_lf_files(tmp_path: Path) -> None:
    (tmp_path / "a.lf").write_text(
        "domain { hp: int 0..100 }\nconstraint cap: then hp <= 100\n", encoding="utf-8"
    )
    (tmp_path / "b.lf").write_text("constraint floor: then hp >= 0\n", encoding="utf-8")
    rs = load_rules(tmp_path)
    assert [c.id for c in rs.constraints] == ["cap", "floor"]
    assert [c.source for c in rs.constraints] == ["a.lf", "b.lf"]


def test_merge_conflicting_variable_declaration_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.lf").write_text("domain { hp: int 0..100 }\n", encoding="utf-8")
    (tmp_path / "b.lf").write_text("domain { hp: int 0..200 }\n", encoding="utf-8")
    with pytest.raises(LoaderError, match="hp"):
        load_rules(tmp_path)


def test_merge_duplicate_init_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.lf").write_text("domain { x: int 0..5 }\ninit: x == 0\n", encoding="utf-8")
    (tmp_path / "b.lf").write_text("init: x == 1\n", encoding="utf-8")
    with pytest.raises(LoaderError, match="init"):
        load_rules(tmp_path)
