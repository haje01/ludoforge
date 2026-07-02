"""Phase 4: sim ↔ PRISM 오라클 교차검증(D19).

sim은 *추정*이고 PRISM은 *증명*이다. 소형 DTMC 모델에서 둘이 일치하면 추정기에 신뢰가
생긴다(D13의 "표집은 증명이 아니다" 반론을 건설적으로 무력화). PRISM 미설치 시 skip.

핵심: 같은 DTMC를 PRISM에 넣으면 Pmax=Pmin=정확값이라, sim의 직업별 승률 추정이 그
정확값을 신뢰구간 안에 담아야 한다. 또 sim의 constraints 파생(win_gold)도 함께 검증한다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.loader import load_rule_file
from core.schema import validate
from prob.prism_gen import generate
from prob.runner import find_prism, run_prism
from sim.aggregate import ProportionResult
from sim.engine import enum_constants, initial_state
from sim.runner import run_sim

# 오라클 DTMC는 사용자 예제가 아니라 테스트 픽스처다(D23 — PRISM은 테스트 전용 오라클).
ORACLE = Path(__file__).parent / "fixtures" / "oracle_dungeon.lf"
_ROLES = ("fighter", "rogue", "wizard")


def test_constraint_derivation_sets_win_gold() -> None:
    # role로부터 win_gold가 constraints로 파생돼 초기 상태에 채워진다(PRISM init 인코딩 대응).
    rs = load_rule_file(ORACLE)
    constants = enum_constants(rs)
    assert initial_state(rs, constants, {"role": "fighter"})["win_gold"] == 6
    assert initial_state(rs, constants, {"role": "rogue"})["win_gold"] == 4
    assert initial_state(rs, constants, {"role": "wizard"})["win_gold"] == 8


def test_oracle_dtmc_sweeps_roles() -> None:
    # 오라클 던전판은 DTMC라 sim이 끝까지 돈다(DtmcViolation 없음), 직업별로 sweep된다.
    rs = load_rule_file(ORACLE)
    report = run_sim(rs, samples=1000, horizon=300, seed=1)
    roles = {cfg.config["role"] for cfg in report.configs}
    assert roles == set(_ROLES)
    for cfg in report.configs:
        assert cfg.truncated == 0  # 흡수 상태로 모두 자연 종료(절단 없음)


@pytest.mark.skipif(find_prism() is None, reason="prism 바이너리 미설치")
def test_sim_win_rates_match_prism_oracle() -> None:
    rs = load_rule_file(ORACLE)
    validate(rs)
    report = run_sim(rs, samples=8000, horizon=300, seed=1, workers=2)
    sim_by_role = {
        cfg.config["role"]: {r.check_id: r for r in cfg.checks} for cfg in report.configs
    }

    for role in _ROLES:
        # role을 고정해 단일 초기 상태로 만들면 PRISM Pmax=정확값(DTMC라 Pmax=Pmin).
        pinned = replace(rs, init=f"({rs.init}) and role == {role}")
        prism = run_prism(generate(pinned))
        winnable = next(o for o in prism.outcomes if o.prop_id == "winnable")
        assert winnable.result is not None
        exact = float(winnable.result.split()[0])  # 값 뒤 반복법 오차추정 텍스트 제거

        sim_win = sim_by_role[role]["winnable"]
        assert isinstance(sim_win, ProportionResult)
        # PRISM 정확값이 sim의 95% 신뢰구간 안에 있어야 한다(추정기 신뢰).
        assert sim_win.ci[0] <= exact <= sim_win.ci[1], (
            f"{role}: PRISM={exact} ∉ sim CI {sim_win.ci} (P̂={sim_win.p_hat})"
        )
        # 보수적 허용오차로도 확인(시드 고정 — 비플레이키).
        assert abs(exact - sim_win.p_hat) < 0.02


# ---------- 상태 의존 weight(D26) 오라클 ----------

URN = Path(__file__).parent / "fixtures" / "urn.lf"
_URN_EXACT = 2 / 3  # 닫힌형: 마지막 공은 3개 중 균등, 그중 2개가 빨강


def test_urn_prism_model_renders_ratio_weights() -> None:
    # 상태 의존 weight는 비율형 (w_i)/(Σw)로 렌더 — 합=1 구성적 보장(D26).
    rs = load_rule_file(URN)
    model = generate(rs).model
    assert "/((red / (red + blue))+(blue / (red + blue)))" in model


@pytest.mark.skipif(find_prism() is None, reason="prism 바이너리 미설치")
def test_urn_sim_matches_prism_oracle() -> None:
    """비복원 추출(D26): PRISM 정확값 = 닫힌형 2/3 이고 sim 95% CI가 그 값을 담는다."""
    rs = load_rule_file(URN)
    validate(rs)
    prism = run_prism(generate(rs))
    ends_red = next(o for o in prism.outcomes if o.prop_id == "ends_red")
    assert ends_red.result is not None
    exact = float(ends_red.result.split()[0])
    assert abs(exact - _URN_EXACT) < 1e-6  # PRISM이 비율 weight를 정확히 푼다

    report = run_sim(rs, samples=8000, horizon=20, seed=1)
    (cfg,) = report.configs  # 자유변수 없음 — 단일 설정
    sim_red = next(r for r in cfg.checks if r.check_id == "ends_red")
    assert isinstance(sim_red, ProportionResult)
    assert sim_red.ci[0] <= exact <= sim_red.ci[1], (
        f"PRISM={exact} ∉ sim CI {sim_red.ci} (P̂={sim_red.p_hat})"
    )


# ---------- 동적 색인(D28) 오라클 ----------

DYN = Path(__file__).parent / "fixtures" / "dyn_index.lf"


@pytest.mark.skipif(find_prism() is None, reason="prism 바이너리 미설치")
def test_dyn_index_sim_matches_prism_oracle() -> None:
    """동적 색인 가드(D28)의 DTMC: PRISM 정확값(ternary 렌더)이 sim 95% CI 안에 있다."""
    rs = load_rule_file(DYN)
    validate(rs)
    prism = run_prism(generate(rs))
    full = next(o for o in prism.outcomes if o.prop_id == "p1_full")
    assert full.result is not None
    exact = float(full.result.split()[0])

    report = run_sim(rs, samples=8000, horizon=50, seed=1)
    (cfg,) = report.configs
    sim_full = next(r for r in cfg.checks if r.check_id == "p1_full")
    assert isinstance(sim_full, ProportionResult)
    assert sim_full.ci[0] <= exact <= sim_full.ci[1], (
        f"PRISM={exact} ∉ sim CI {sim_full.ci} (P̂={sim_full.p_hat})"
    )
