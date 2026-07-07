"""웹 MVP: FastAPI 앱 통합 테스트 (D32 P3).

LLM은 가짜 complete 주입으로 대체 — API 키 없이 전 경로(시트→번역→검증→규칙서→실행 잡)를
검증한다. 실행 결과의 종료코드 의미는 CLI와 동일해야 한다(0 정합 · 1 모순 · 2 오류).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from web.app import create_app
from web.config import WebConfig

_CONTRADICTION_LF = """domain {
    level: int 1..100
    hp:    int 0..
    role:  enum { warrior, mage }
}
constraint warrior_hp:
    when role == warrior
    then hp == level * 100
constraint hp_cap:
    then hp <= 5000
"""

_COIN_LF = """domain {
    gold:  int 0..5
    flips: int 0..5
}
init: gold == 0 and flips == 0
transition flip:
    when flips < 5
    outcomes:
        0.5 -> { gold = gold + 1; flips = flips + 1 }
        0.5 -> flips = flips + 1
check rich reachable: gold >= 4
check dist distribution: gold
"""


def _client(complete: Any = None) -> TestClient:
    cfg = WebConfig(bmc_k_max=12, sim_samples_max=500, sim_horizon_max=50)
    return TestClient(create_app(cfg, complete=complete))


def _wait_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.05)
    raise AssertionError("잡이 제시간에 끝나지 않았습니다.")


def test_index_serves_page() -> None:
    res = _client().get("/")
    assert res.status_code == 200
    assert "Ludoforge" in res.text


def test_sheet_endpoint_converts_and_reports_errors() -> None:
    client = _client()
    ok = client.post("/api/sheet", json={"name": "reward", "csv": "goblin,2\ndragon,10\n"})
    assert ok.status_code == 200
    assert ok.json()["table"] == "table reward { goblin: 2, dragon: 10 }"

    bad = client.post("/api/sheet", json={"name": "reward", "csv": "goblin,많이\n"})
    assert bad.status_code == 400
    assert "1행" in bad.json()["detail"]


def test_translate_endpoint_uses_injected_llm() -> None:
    def fake(system: str, messages: list[dict[str, str]]) -> str:
        return f"```\n{_CONTRADICTION_LF}```"

    client = _client(complete=fake)
    res = client.post("/api/translate", json={"prose": "전사 HP는 레벨당 100", "sheets": []})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] and "constraint warrior_hp" in data["lf"]


def test_translate_without_llm_returns_503(monkeypatch: Any) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = _client()  # complete 미주입 + 키 없음 → 명확한 안내와 503
    res = client.post("/api/translate", json={"prose": "아무거나", "sheets": []})
    assert res.status_code == 503
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_validate_endpoint() -> None:
    client = _client()
    ok = client.post("/api/validate", json={"lf": _COIN_LF})
    assert ok.json() == {"ok": True, "error": None}

    bad_lf = "domain { hp: int 0.. }\nconstraint c: then mana <= 1\n"
    bad = client.post("/api/validate", json={"lf": bad_lf})
    data = bad.json()
    assert data["ok"] is False and "mana" in data["error"]


def test_doc_endpoint_returns_html() -> None:
    client = _client()
    res = client.post("/api/doc", json={"lf": _COIN_LF})
    assert res.status_code == 200
    assert "<html" in res.json()["html"].lower()

    bad = client.post("/api/doc", json={"lf": "domain {"})
    assert bad.status_code == 400


def test_run_check_job_reports_contradiction() -> None:
    client = _client()
    res = client.post("/api/run", json={"lf": _CONTRADICTION_LF, "backend": "check"})
    job = _wait_job(client, res.json()["job_id"])
    assert job["status"] == "done"
    assert job["result"]["exit"] == 1
    assert "모순" in job["result"]["text"]


def test_run_bmc_job_clamps_k_and_returns_html() -> None:
    client = _client()
    res = client.post("/api/run", json={"lf": _COIN_LF, "backend": "bmc", "k": 999})
    body = res.json()
    assert body["params"]["k"] == 12  # 상한 클램프
    job = _wait_job(client, body["job_id"])
    assert job["status"] == "done"
    assert job["result"]["exit"] in (0, 3)
    assert job["result"]["html"]


def test_run_sim_job_clamps_samples_and_returns_html() -> None:
    client = _client()
    res = client.post(
        "/api/run",
        json={"lf": _COIN_LF, "backend": "sim", "samples": 99999, "horizon": 20, "seed": 1},
    )
    body = res.json()
    assert body["params"]["samples"] == 500  # 상한 클램프
    job = _wait_job(client, body["job_id"])
    assert job["status"] == "done"
    assert job["result"]["exit"] == 0
    assert "증명" in job["result"]["text"]  # "증명 아님" 라벨(정직성)
    assert job["result"]["html"]


def test_run_unknown_backend_rejected() -> None:
    res = _client().post("/api/run", json={"lf": _COIN_LF, "backend": "prism"})
    assert res.status_code == 400


def test_unknown_job_404() -> None:
    assert _client().get("/api/jobs/nope").status_code == 404
