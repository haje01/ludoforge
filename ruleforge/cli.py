"""RuleForge CLI 진입점.

`ruleforge check <path>` 한 줄로 파이프라인을 실행한다:
  로드 → 스키마·참조 검증 → Z3 번역 → 도달성 검사 → 한국어 리포트.

종료코드: 0=정합, 1=모순 발견, 2=로드/검증/번역 오류, 3=unknown(판단 불가).
"""

from __future__ import annotations

from pathlib import Path

import typer

from forge_core.loader import LoaderError, load_rules
from forge_core.schema import SchemaError, validate
from ruleforge.solver.bmc import format_bmc_report, run_bmc
from ruleforge.solver.checks import check as run_checks
from ruleforge.solver.report import format_report
from ruleforge.solver.translator import TranslationError, translate

app = typer.Typer(help="MMORPG 룰 정합성 검증기")

_EXIT_OK = 0
_EXIT_CONTRADICTION = 1
_EXIT_ERROR = 2
_EXIT_UNKNOWN = 3


@app.callback()
def main() -> None:
    """MMORPG 룰 정합성 검증기. 하위 명령으로 동작한다."""


@app.command()
def check(path: str = typer.Argument(..., help="검사할 .rule 파일 또는 디렉토리")) -> None:
    """룰셋의 정합성을 검사한다. 디렉토리면 모든 .rule을 병합해 함께 검사한다."""
    try:
        ruleset = load_rules(Path(path))
        validate(ruleset)
        translation = translate(ruleset)
    except (LoaderError, SchemaError, TranslationError) as e:
        typer.echo(f"검사를 진행할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    report = run_checks(ruleset, translation)
    rule_sources = {r.id: r.source for r in ruleset.rules if r.source}
    typer.echo(format_report(report, rule_sources))

    if report.has_contradiction:
        raise typer.Exit(_EXIT_CONTRADICTION)
    if report.unknowns:
        raise typer.Exit(_EXIT_UNKNOWN)
    raise typer.Exit(_EXIT_OK)


@app.command()
def bmc(
    path: str = typer.Argument(..., help="검사할 .rule 파일 또는 디렉토리"),
    k: int = typer.Option(10, "--k", help="BMC 언롤링 깊이 상한"),
) -> None:
    """전이 시스템(init/transitions/properties)을 깊이 k까지 BMC로 검사한다(D15).

    종료코드: 0=정상, 1=증명된 위반(불변식/데드락), 2=로드/검증 오류, 3=k 한계 미확인.
    """
    try:
        ruleset = load_rules(Path(path))
        validate(ruleset)
    except (LoaderError, SchemaError) as e:
        typer.echo(f"검사를 진행할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    if not ruleset.transitions:
        typer.echo(
            "전이(transitions)가 없어 BMC 대상이 아닙니다. 정적 검사는 'ruleforge check'를 쓰세요.",
            err=True,
        )
        raise typer.Exit(_EXIT_ERROR)

    try:
        report = run_bmc(ruleset, k)
    except TranslationError as e:
        typer.echo(f"번역 오류:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    typer.echo(format_bmc_report(report))

    if report.has_violation:
        raise typer.Exit(_EXIT_CONTRADICTION)
    if report.has_unconfirmed:
        raise typer.Exit(_EXIT_UNKNOWN)
    raise typer.Exit(_EXIT_OK)


if __name__ == "__main__":
    app()
