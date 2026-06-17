"""PRISM 실행·결과 파싱(D16). `prism` 바이너리가 있을 때만 동작(graceful).

번역(prism_gen)과 분리한다 — 모델 생성은 PRISM 없이 검증 가능하고, 여기서는 바이너리를
PATH나 `PRISM` 환경변수로 찾아 실행한다. 없으면 available=False로 모델만 안내한다.
PRISM은 속성마다 `Result: <값>` 한 줄을 순서대로 출력한다 — 이를 파싱해 매핑한다.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from probforge.prism_gen import PrismProgram

_RESULT_RE = re.compile(r"^Result:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PropOutcome:
    prop_id: str
    kind: str
    desc: str | None
    pctl: str
    result: str | None  # PRISM "Result:" 값. 파싱 실패/미실행이면 None.


@dataclass(frozen=True)
class ProbReport:
    available: bool  # prism을 찾아 실행했는가
    program: PrismProgram
    outcomes: tuple[PropOutcome, ...] = ()
    raw: str | None = None  # prism 원시 출력(실행 시) 또는 안내 메시지
    error: str | None = None
    timed_out: bool = False


def find_prism() -> str | None:
    """`PRISM` 환경변수(바이너리 경로) 또는 PATH에서 prism을 찾는다."""
    env = os.environ.get("PRISM")
    if env and Path(env).exists():
        return env
    return shutil.which("prism")


def run_prism(
    program: PrismProgram, *, prism: str | None = None, timeout: float = 120.0
) -> ProbReport:
    """PRISM 모델·속성을 실행해 결과를 파싱한다. 바이너리가 없으면 available=False."""
    binary = prism or find_prism()
    if binary is None:
        return ProbReport(
            available=False,
            program=program,
            error="PRISM 바이너리를 찾지 못했습니다(PATH 또는 PRISM 환경변수).",
        )

    with tempfile.TemporaryDirectory() as tmp:
        model_path = Path(tmp) / "model.prism"
        props_path = Path(tmp) / "model.props"
        model_path.write_text(program.model, encoding="utf-8")
        props_path.write_text(
            "\n".join(p.pctl for p in program.properties) + "\n", encoding="utf-8"
        )
        try:
            proc = subprocess.run(
                [binary, str(model_path), str(props_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ProbReport(
                available=True,
                program=program,
                error=f"PRISM 실행이 {timeout}s를 초과했습니다.",
                timed_out=True,
            )

    return _parse(program, proc.stdout, proc.returncode)


def _parse(program: PrismProgram, stdout: str, returncode: int) -> ProbReport:
    results = _RESULT_RE.findall(stdout)
    outcomes: list[PropOutcome] = []
    for i, p in enumerate(program.properties):
        outcomes.append(
            PropOutcome(
                prop_id=p.prop_id,
                kind=p.kind,
                desc=p.desc,
                pctl=p.pctl,
                result=results[i] if i < len(results) else None,
            )
        )
    error = None
    if returncode != 0:
        error = f"PRISM 종료코드 {returncode}"
    elif len(results) != len(program.properties):
        error = f"결과 수({len(results)})가 속성 수({len(program.properties)})와 다릅니다."
    return ProbReport(
        available=True,
        program=program,
        outcomes=tuple(outcomes),
        raw=stdout,
        error=error,
    )


def format_prob_report(report: ProbReport) -> str:
    """ProbReport를 한국어 리포트로. 미설치면 생성 모델과 안내를 출력한다."""
    lines: list[str] = []
    if not report.available:
        lines.append("⚠️ PRISM 미설치 — 모델만 생성했습니다(확률 계산은 PRISM 필요).")
        if report.error:
            lines.append(f"    {report.error}")
        lines.append("")
        lines.append("설치 후 다시 실행하거나, 아래 생성 모델을 직접 PRISM에 넣으세요.")
        lines.append("")
        lines.append(_format_program(report.program))
        return "\n".join(lines)

    lines.append("ProbForge (PRISM) 결과")
    if report.timed_out or report.error:
        lines.append(f"⚠️ {report.error}")
    lines.append("")
    for i, o in enumerate(report.outcomes, start=1):
        desc = f" — {o.desc}" if o.desc else ""
        value = o.result if o.result is not None else "(파싱 실패)"
        lines.append(f"[{i}] 속성 '{o.prop_id}' ({o.kind}){desc}: {value}")
        lines.append(f"    {o.pctl}")
    return "\n".join(lines)


def _format_program(program: PrismProgram) -> str:
    out = ["--- PRISM 모델 ---", program.model.rstrip()]
    out.append("")
    out.append("--- 속성(.props) ---")
    out.extend(f"{p.pctl}    // {p.prop_id} ({p.kind})" for p in program.properties)
    return "\n".join(out)
