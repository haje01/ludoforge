"""S7: CLI 통합 테스트. ludoforge check <path> 파이프라인 + 종료코드.

종료코드: 0=정합, 1=모순, 2=로드/검증 오류, 3=unknown(판단 불가).
교차 검사: 디렉토리의 .lf 파일들을 병합해 검사한다(여러 기획자 파일 간 모순 탐지).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ludoforge.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


def test_contradiction_file_exits_1_and_reports() -> None:
    result = runner.invoke(app, ["check", str(FIXTURES / "warrior_hp.lf")])
    assert result.exit_code == 1
    assert "모순" in result.output
    assert "level" in result.output


def test_consistent_file_exits_0(tmp_path: Path) -> None:
    f = tmp_path / "ok.lf"
    f.write_text(
        "domain {\n"
        "    level: int 1..100\n"
        "    hp:    int 0..\n"
        "    role:  enum { warrior, mage }\n"
        "}\n"
        "constraint warrior_hp:\n"
        "    when role == warrior\n"
        "    then hp == level * 100\n"
        "constraint hp_cap:\n"
        "    then hp <= 10000\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(f)])
    assert result.exit_code == 0
    assert "✅" in result.output


def test_schema_error_exits_2(tmp_path: Path) -> None:
    f = tmp_path / "bad.lf"
    f.write_text(
        "domain { hp: int 0.. }\nconstraint r1: then mana <= 100\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(f)])
    assert result.exit_code == 2


def test_missing_path_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path / "nope.lf")])
    assert result.exit_code == 2


def test_rules_only_file_alone_gives_directory_hint(tmp_path: Path) -> None:
    # constraints만 있는 파일을 단독 검사하면 디렉토리 검사를 안내한다.
    f = tmp_path / "planner_a.lf"
    f.write_text(
        "constraint warrior_hp:\n    when role == warrior\n    then hp == level * 100\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(f)])
    assert result.exit_code == 2
    assert "디렉토리" in result.output


def test_directory_merges_files_for_cross_file_contradiction(tmp_path: Path) -> None:
    # 기획자 A: 도메인 + 전사 공식. 기획자 B: HP 상한. 따로 보면 정상, 합치면 모순.
    (tmp_path / "a.lf").write_text(
        "domain {\n"
        "    level: int 1..100\n"
        "    hp:    int 0..\n"
        "    role:  enum { warrior, mage }\n"
        "}\n"
        "constraint warrior_hp:\n"
        "    when role == warrior\n"
        "    then hp == level * 100\n",
        encoding="utf-8",
    )
    (tmp_path / "b.lf").write_text(
        "constraint global_hp_cap:\n    then hp <= 5000\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 1
    assert "warrior_hp" in result.output and "global_hp_cap" in result.output
    # 범인 룰은 정의된 파일명과 함께 짚는다(id + (파일명)).
    assert "warrior_hp (a.lf)" in result.output
    assert "global_hp_cap (b.lf)" in result.output


def test_legacy_yaml_rule_exits_2_with_guidance(tmp_path: Path) -> None:
    # D32: YAML 프론트엔드 제거 — .lf로 안내하며 로드 오류(2)로 끝난다.
    f = tmp_path / "old.rule"
    f.write_text("domain:\n  variables:\n    hp: { type: int }\n", encoding="utf-8")
    result = runner.invoke(app, ["check", str(f)])
    assert result.exit_code == 2
    assert ".lf" in result.output
