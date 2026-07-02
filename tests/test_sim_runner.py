"""Phase 3: sim 러너·병렬·CLI(D19) 테스트.

핵심 성공 기준 = **워커 수 무관 재현성**: workers=1과 workers=N의 SimReport가 동일.
numpy SeedSequence로 청크별 독립 스트림을 만들고 청크 순서대로 합치므로 보장된다.
"""

from __future__ import annotations

from pathlib import Path

from core.loader import load_rule_file
from sim.aggregate import ProportionResult
from sim.report import format_sim_report
from sim.runner import _chunk_counts, run_sim

FIXTURES = Path(__file__).parent / "fixtures"


def test_chunk_counts_partition_evenly() -> None:
    assert _chunk_counts(10, 4) == [3, 3, 2, 2]
    assert sum(_chunk_counts(1000, 64)) == 1000
    assert _chunk_counts(3, 8) == [1, 1, 1, 0, 0, 0, 0, 0]


def test_run_sim_reproducible_same_seed() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    r1 = run_sim(rs, samples=2000, horizon=20, seed=5, workers=1)
    r2 = run_sim(rs, samples=2000, horizon=20, seed=5, workers=1)
    assert r1 == r2


def test_run_sim_identical_across_worker_counts() -> None:
    # 워커 1개와 4개의 결과가 비트 단위로 동일해야 한다(D19 — 청크 시드·병합 순서 고정).
    rs = load_rule_file(FIXTURES / "arena.rule")
    serial = run_sim(rs, samples=3000, horizon=20, seed=9, workers=1)
    parallel = run_sim(rs, samples=3000, horizon=20, seed=9, workers=4)
    assert serial == parallel


def test_run_sim_class_win_rates_match_theory() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    report = run_sim(rs, samples=5000, horizon=20, seed=1, workers=2)
    by_role = {cfg.config["role"]: {r.check_id: r for r in cfg.checks} for cfg in report.configs}
    fighter = by_role["fighter"]["survives"]
    rogue = by_role["rogue"]["survives"]
    assert isinstance(fighter, ProportionResult)
    assert isinstance(rogue, ProportionResult)
    assert abs(fighter.p_hat - 0.729) < 0.03  # win^3
    assert abs(rogue.p_hat - 0.216) < 0.03
    assert fighter.p_hat > rogue.p_hat


def test_cli_sim_runs_and_labels_estimate() -> None:
    from typer.testing import CliRunner

    from ludoforge.cli import app

    result = CliRunner().invoke(
        app, ["sim", str(FIXTURES / "arena.rule"), "--samples", "500", "--seed", "1"]
    )
    assert result.exit_code == 0
    assert "증명 아님" in result.stdout
    assert "role=fighter" in result.stdout


def test_cli_sim_rejects_nondeterministic_model() -> None:
    from typer.testing import CliRunner

    from ludoforge.cli import app

    result = CliRunner().invoke(app, ["sim", str(FIXTURES / "nondet.rule"), "--samples", "10"])
    assert result.exit_code == 2  # 미선언 비결정 → 친절한 거부
    assert "비결정" in result.stderr


def test_policy_label_names_players() -> None:
    """player 태그(D27)가 있으면 정책 라벨에 플레이어를 명시한다."""
    rs = load_rule_file(Path(__file__).parent.parent / "examples" / "dungeon_race.lf")
    report = run_sim(rs, samples=50, horizon=300, seed=1)
    assert report.policy_players == ("p1", "p2")
    text = format_sim_report(report)
    assert "플레이어 p1, p2의 정책" in text
