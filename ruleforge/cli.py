"""RuleForge CLI 진입점.

S0 단계에서는 골격만 둔다. 실제 파이프라인(로드→스키마→번역→검사→리포트)은
이후 단계(S2~S7)에서 채운다.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="MMORPG 룰 정합성 검증기")


@app.callback()
def main() -> None:
    """MMORPG 룰 정합성 검증기. 하위 명령으로 동작한다."""


@app.command()
def check(rules_dir: str = typer.Argument(..., help="검사할 .rule 파일이 있는 디렉토리")) -> None:
    """룰셋의 정합성을 검사한다 (S2~S7에서 구현 예정)."""
    typer.echo(f"[미구현] '{rules_dir}' 검사는 이후 단계에서 구현됩니다.")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
