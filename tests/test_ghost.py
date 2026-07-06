"""ghost 서술 변수(D31, 14차) — 단방향 의존 게이트·erase_ghosts·백엔드 배선 테스트.

핵심 불변식: "ghost 전부 제거 시 비-ghost 궤적 비트 동일". 픽스처 쌍(ghost_counter ↔
ghost_counter_plain)으로 bmc 지위·sim 추정의 동일성을 회귀로 고정한다(§8).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ghost import erase_ghosts, ghost_names
from core.loader import load_rule_file
from core.schema import SchemaError, check_finite_state, validate
from core.text_loader import parse_rule_text
from logic.solver.bmc import format_bmc_report, run_bmc
from prob.prism_gen import generate
from sim.aggregate import DistributionResult, ProportionResult, simulate
from sim.report import format_sim_report

FIXTURES = Path(__file__).parent / "fixtures"

_GHOST_MODEL = """
domain {
    ghost steps: int 0..
    gold: int 0..5
    status: enum { run, done }
}
init: gold == 0 and status == run and steps == 0
transition earn:
    when status == run and gold < 5
    outcomes:
        0.5 -> { gold = gold + 1; steps = steps + 1 }
        0.5 -> { steps = steps + 1 }
transition finish:
    when status == run and gold >= 5
    then status = done
transition done_absorb: when status == done then status = done
check steps_dist distribution: steps
"""


# ── P1: 문법·IR·게이트 ──────────────────────────────────────────────────────────


def test_ghost_modifier_parsed_to_ir() -> None:
    rs = parse_rule_text(_GHOST_MODEL)
    by_name = {v.name: v for v in rs.variables}
    assert by_name["steps"].ghost is True
    assert by_name["gold"].ghost is False
    validate(rs)  # 합법 사용(ghost 대입 RHS·distribution·init 상수 고정) → 통과


def test_ghost_array_inherits_flag() -> None:
    rs = parse_rule_text(
        """
        domain {
            turn: enum { p1, p2 }
            ghost visits[p1, p2]: int 0..
        }
        init: turn == p1 and visits[p1] == 0 and visits[p2] == 0
        transition t: when turn == p1 then visits[p1] = visits[p1] + 1
        """
    )
    assert all(v.ghost for v in rs.variables if v.name.startswith("visits_"))


def _expect_gate_error(src: str, match: str) -> None:
    with pytest.raises(SchemaError, match=match):
        validate(parse_rule_text(src))


def test_ghost_in_guard_rejected() -> None:
    _expect_gate_error(
        """
        domain { ghost g: int 0..  x: int 0..5 }
        init: x == 0 and g == 0
        transition t: when g > 0 then x = x + 1
        """,
        "ghost",
    )


def test_ghost_in_constraint_rejected() -> None:
    _expect_gate_error(
        """
        domain { ghost g: int 0..  x: int 0..5 }
        init: x == 0 and g == 0
        constraint c: then g <= 5
        transition t: then g = g + 1
        """,
        "ghost",
    )


def test_ghost_in_weight_and_pref_rejected() -> None:
    _expect_gate_error(
        """
        domain { ghost g: int 1..  x: int 0..5 }
        init: x == 0 and g == 1
        transition t:
            outcomes:
                g / 10     -> x = x + 1
                1 - g / 10 -> x = x
        """,
        "ghost",
    )
    _expect_gate_error(
        """
        domain { ghost g: int 1..  x: int 0..5 }
        init: x == 0 and g == 1
        transition a: pref g then x = x + 1
        transition b: pref 1 then x = x
        """,
        "ghost",
    )


def test_ghost_in_nonghost_effect_rhs_rejected() -> None:
    _expect_gate_error(
        """
        domain { ghost g: int 0..  x: int 0..5 }
        init: x == 0 and g == 0
        transition t: then x = g
        """,
        "ghost",
    )


def test_ghost_in_reachable_that_rejected() -> None:
    _expect_gate_error(
        """
        domain { ghost g: int 0..  x: int 0..5 }
        init: x == 0 and g == 0
        transition t: then g = g + 1
        check c reachable: g >= 3
        """,
        "ghost",
    )


def test_ghost_init_must_pin_constant() -> None:
    # 파생(다른 변수 참조) 금지.
    _expect_gate_error(
        """
        domain { ghost g: int 0..  x: int 0..5 }
        init: x == 0 and g == x
        transition t: then g = g + 1
        """,
        "상수",
    )
    # 미고정(자유 sweep) 금지.
    _expect_gate_error(
        """
        domain { ghost g: int 0..  x: int 0..5 }
        init: x == 0
        transition t: then g = g + 1
        """,
        "고정",
    )


def test_ghost_assignment_may_read_everything() -> None:
    # ghost 대입의 RHS는 ghost·비-ghost 모두 읽을 수 있다(단방향의 허용 방향).
    rs = parse_rule_text(
        """
        domain { ghost g: int 0..  x: int 0..5 }
        init: x == 0 and g == 0
        transition t: then { x = x + 1; g = g + x }
        """
    )
    validate(rs)


# ── P2: erase_ghosts·백엔드 배선 ────────────────────────────────────────────────


def test_erase_ghosts_strips_decl_init_and_effects() -> None:
    rs = parse_rule_text(_GHOST_MODEL)
    erased = erase_ghosts(rs)
    assert ghost_names(rs) == ("steps",)
    assert all(not v.ghost for v in erased.variables)
    assert "steps" not in {v.name for v in erased.variables}
    assert erased.init is not None and "steps" not in erased.init
    earn = next(t for t in erased.transitions if t.id == "earn")
    assert "steps" not in earn.outcomes[0].then
    # 효과가 전부 ghost였던 분기는 `True`(프레임이 유지하는 자기 분기 — 분기 구조 보존).
    assert earn.outcomes[1].then == "True"
    # ghost 없는 모델은 무비용 경로(동일 객체).
    assert erase_ghosts(erased) is erased


def test_check_finite_state_skips_ghost() -> None:
    rs = parse_rule_text(_GHOST_MODEL)  # steps는 무한 int — erase 후 기준이라 통과해야
    check_finite_state(rs)


def test_bmc_status_identical_to_plain_twin() -> None:
    """ghost를 달아도 bmc 검사 지위가 손으로 걷어낸 쌍둥이와 동일하다(D31 핵심 회귀)."""
    ghost_rs = load_rule_file(FIXTURES / "ghost_counter.lf")
    plain_rs = load_rule_file(FIXTURES / "ghost_counter_plain.lf")
    validate(ghost_rs)
    g_report = run_bmc(ghost_rs, k=8)
    p_report = run_bmc(plain_rs, k=8)
    assert [(r.prop_id, r.status) for r in g_report.results] == [
        (r.prop_id, r.status) for r in p_report.results
    ]
    assert g_report.erased_ghosts == ("steps",)
    assert "ghost 서술 변수" in format_bmc_report(g_report)
    assert p_report.erased_ghosts == ()


def test_sim_nonghost_estimates_bit_identical_to_plain_twin() -> None:
    """sim은 원본을 실행하되 비-ghost 추정이 쌍둥이와 **비트 동일**해야 한다(rng 미소비)."""
    ghost_rs = load_rule_file(FIXTURES / "ghost_counter.lf")
    plain_rs = load_rule_file(FIXTURES / "ghost_counter_plain.lf")
    g_report = simulate(ghost_rs, samples=300, horizon=50, seed=7)
    p_report = simulate(plain_rs, samples=300, horizon=50, seed=7)
    (g_cfg,) = g_report.configs
    (p_cfg,) = p_report.configs
    g_props = [r for r in g_cfg.checks if isinstance(r, ProportionResult)]
    p_props = [r for r in p_cfg.checks if isinstance(r, ProportionResult)]
    assert g_props == p_props  # frozen dataclass — 완전 동등 = 비트 동일
    # ghost distribution은 ghost판에서만 추가로 동작하고 서술 변수 라벨을 단다.
    dist = next(r for r in g_cfg.checks if isinstance(r, DistributionResult))
    assert dist.check_id == "steps_dist" and dist.ghost_expr is True
    assert dist.n == 300 and dist.mean > 0
    assert "서술 변수(ghost — 논리 검증 제외)" in format_sim_report(g_report)


def test_prism_generate_erases_ghost() -> None:
    """PRISM 오라클도 erase 후 소비 — 모델 텍스트에 ghost가 없고 빈 갱신은 true."""
    rs = load_rule_file(FIXTURES / "ghost_counter.lf")
    model = generate(rs).model
    assert "steps" not in model
    assert "0.5:true" in model  # 전부-ghost 효과 분기 → PRISM 항등 갱신
