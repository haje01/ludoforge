"""FastAPI 셸 — 산문/시트 → LLM 번역 → 사람 게이트 → check/bmc/sim 파이프라인의 웹 표면.

명령형 셸(§7): 판정·실행 로직은 전부 함수형 코어(web/runs·web/translate·core)가 하고,
여기는 HTTP 직렬화·잡 폴링·정적 페이지 서빙만 한다. `complete`(LLM 호출)는 주입 가능해
테스트가 API 키 없이 전 경로를 검증한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from core.docgen import render_doc_html
from core.schema import SchemaError, validate
from core.text_loader import TextLoaderError, parse_rule_text
from web.config import WebConfig, load_config
from web.jobs import JobStore
from web.runs import run_bmc_text, run_check_text, run_sim_text
from web.sheet_import import SheetImportError, csv_to_table
from web.translate import CompleteFn, anthropic_complete, make_reviewer, translate_prose

_STATIC = Path(__file__).resolve().parent / "static"


class SheetIn(BaseModel):
    name: str
    csv: str


class TranslateIn(BaseModel):
    prose: str
    sheets: list[SheetIn] = Field(default_factory=list)


class LfIn(BaseModel):
    lf: str


class RunIn(BaseModel):
    lf: str
    backend: str  # check | bmc | sim
    k: int = 10
    samples: int = 10_000
    horizon: int = 100
    seed: int = 0


def _sheets_to_tables(sheets: list[SheetIn]) -> str:
    """시트들을 table 절 텍스트로 — 실패는 400(어느 시트 몇 행인지 메시지에 담김)."""
    parts: list[str] = []
    for sheet in sheets:
        try:
            parts.append(csv_to_table(sheet.name, sheet.csv))
        except SheetImportError as e:
            raise HTTPException(status_code=400, detail=f"시트 '{sheet.name}': {e}") from e
    return "\n".join(parts)


def create_app(config: WebConfig | None = None, complete: CompleteFn | None = None) -> FastAPI:
    """앱 팩토리. complete를 주입하면 그걸 쓰고, 아니면 첫 번역 요청 때 Claude 클라이언트 생성."""
    cfg = config if config is not None else load_config()
    jobs = JobStore()
    app = FastAPI(title="Ludoforge Web", docs_url=None, redoc_url=None)
    llm: dict[str, CompleteFn] = {}
    if complete is not None:
        llm["fn"] = complete

    def get_complete() -> CompleteFn:
        if "fn" not in llm:
            try:
                llm["fn"] = anthropic_complete(cfg.model)
            except Exception as e:  # SDK 미설치·API 키 없음 등 — 명확히 안내
                raise HTTPException(
                    status_code=503,
                    detail=f"LLM 클라이언트를 준비할 수 없습니다({e}). "
                    "ANTHROPIC_API_KEY 환경변수를 설정하고 서버를 재시작하세요.",
                ) from e
        return llm["fn"]

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_STATIC / "index.html").read_text(encoding="utf-8")

    @app.post("/api/sheet")
    def sheet(body: SheetIn) -> dict[str, str]:
        """CSV 한 장을 table 절로 변환해 미리보기로 돌려준다(결정론 — LLM 불개입)."""
        try:
            return {"table": csv_to_table(body.name, body.csv)}
        except SheetImportError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.post("/api/translate")
    def translate(body: TranslateIn) -> dict[str, Any]:
        """산문(+시트) → `.lf`. ok=false여도 마지막 후보와 오류를 돌려준다(사람이 이어서 수정)."""
        tables_lf = _sheets_to_tables(body.sheets)
        try:
            comp = get_complete()
            result = translate_prose(
                body.prose,
                tables_lf=tables_lf,
                complete=comp,
                review=make_reviewer(comp) if cfg.review_translation else None,
                max_attempts=cfg.max_translate_attempts,
            )
        except HTTPException:
            raise
        except Exception as e:  # LLM 호출 실패(네트워크·인증 등) — 상태로 명확히 보고
            raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {e}") from e
        return {
            "ok": result.ok,
            "lf": result.lf_text,
            "attempts": [{"error": a.error} for a in result.attempts],
        }

    @app.post("/api/validate")
    def validate_lf(body: LfIn) -> dict[str, Any]:
        """로더·스키마 게이트만 통과시켜 본다(실행 전 빠른 확인)."""
        try:
            validate(parse_rule_text(body.lf, source="web-input.lf"))
        except (TextLoaderError, SchemaError) as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "error": None}

    @app.post("/api/doc")
    def doc(body: LfIn) -> dict[str, str]:
        """사람 게이트용 규칙서 미리보기 — 기획자는 `.lf` 대신 이 산문을 읽고 승인한다(D29·D32)."""
        try:
            validate(parse_rule_text(body.lf, source="web-input.lf"))
            html = render_doc_html(body.lf, "규칙서 미리보기", source="web-input.lf")
        except (TextLoaderError, SchemaError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"html": html}

    @app.post("/api/run")
    def run(body: RunIn) -> dict[str, Any]:
        """백엔드 실행 잡을 시작한다. 자원 상한을 넘는 파라미터는 클램프해 알려준다."""
        lf = body.lf
        if body.backend == "check":
            job_id = jobs.submit(lambda: run_check_text(lf))
            return {"job_id": job_id, "params": {}}
        if body.backend == "bmc":
            k = min(body.k, cfg.bmc_k_max)
            job_id = jobs.submit(lambda: run_bmc_text(lf, k))
            return {"job_id": job_id, "params": {"k": k}}
        if body.backend == "sim":
            samples = min(body.samples, cfg.sim_samples_max)
            horizon = min(body.horizon, cfg.sim_horizon_max)
            seed = body.seed
            workers = cfg.sim_workers
            job_id = jobs.submit(lambda: run_sim_text(lf, samples, horizon, seed, workers))
            return {"job_id": job_id, "params": {"samples": samples, "horizon": horizon}}
        raise HTTPException(status_code=400, detail=f"알 수 없는 backend: {body.backend!r}")

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다.")
        return {"status": job.status, "result": job.result, "error": job.error}

    return app
