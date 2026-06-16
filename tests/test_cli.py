"""S7: CLI 통합 테스트. ruleforge check <path> 파이프라인 + 종료코드.

종료코드: 0=정합, 1=모순, 2=로드/검증 오류, 3=unknown(판단 불가).
교차 검사: 디렉토리의 .rule 파일들을 병합해 검사한다(여러 기획자 파일 간 모순 탐지).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ruleforge.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


def test_contradiction_file_exits_1_and_reports() -> None:
    result = runner.invoke(app, ["check", str(FIXTURES / "warrior_hp.rule")])
    assert result.exit_code == 1
    assert "모순" in result.output
    assert "level" in result.output


def test_consistent_file_exits_0(tmp_path: Path) -> None:
    f = tmp_path / "ok.rule"
    f.write_text(
        "domain:\n"
        "  variables:\n"
        "    level: { type: int, min: 1, max: 100 }\n"
        "    hp: { type: int, min: 0 }\n"
        "    role: { type: enum, values: [warrior, mage] }\n"
        "rules:\n"
        "  - id: warrior_hp\n    when: 'role == warrior'\n    then: 'hp == level * 100'\n"
        "  - id: hp_cap\n    then: 'hp <= 10000'\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(f)])
    assert result.exit_code == 0
    assert "✅" in result.output


def test_schema_error_exits_2(tmp_path: Path) -> None:
    f = tmp_path / "bad.rule"
    f.write_text(
        "domain:\n  variables:\n    hp: { type: int }\n"
        "rules:\n  - id: r1\n    then: 'mana <= 100'\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(f)])
    assert result.exit_code == 2


def test_missing_path_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path / "nope.rule")])
    assert result.exit_code == 2


def test_directory_merges_files_for_cross_file_contradiction(tmp_path: Path) -> None:
    # 기획자 A: 도메인 + 전사 공식. 기획자 B: HP 상한. 따로 보면 정상, 합치면 모순.
    (tmp_path / "a.rule").write_text(
        "domain:\n"
        "  variables:\n"
        "    level: { type: int, min: 1, max: 100 }\n"
        "    hp: { type: int, min: 0 }\n"
        "    role: { type: enum, values: [warrior, mage] }\n"
        "rules:\n  - id: warrior_hp\n    when: 'role == warrior'\n    then: 'hp == level * 100'\n",
        encoding="utf-8",
    )
    (tmp_path / "b.rule").write_text(
        "rules:\n  - id: global_hp_cap\n    then: 'hp <= 5000'\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 1
    assert "warrior_hp" in result.output and "global_hp_cap" in result.output
