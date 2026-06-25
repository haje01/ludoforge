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
