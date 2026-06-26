"""Phase 2: sim 집계·sweep·리포트(D19) 테스트.

- 통계 헬퍼(Wilson 구간·rule-of-three)와 결합 가능한 집계(merge).
- arena(DTMC 클래스밸런스) sweep → 직업별 승률 추정 + 신뢰구간.
- 미관측 사건(progress>=4)은 rule-of-three 상한으로 보고(불가능이라 하지 않음).
- 분포(progress) 평균·백분위. 리포트에 "증명 아님" 라벨.
"""

from __future__ import annotations

from pathlib import Path

from core.loader import load_rule_file
from core.schema import validate
from sim.aggregate import (
    DistributionAggregate,
    DistributionResult,
    ProportionAggregate,
    ProportionResult,
    rule_of_three,
    simulate,
    wilson_interval,
)
from sim.engine import enum_constants, sweep_configs
from sim.report import format_sim_report

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def _by_id(cfg_result: object) -> dict[str, object]:
    return {r.check_id: r for r in cfg_result.checks}  # type: ignore[attr-defined]


# ---------- 통계 헬퍼 ----------


def test_wilson_interval_contains_phat() -> None:
    lo, hi = wilson_interval(50, 100)
    assert lo < 0.5 < hi
    assert lo >= 0.0 and hi <= 1.0


def test_rule_of_three() -> None:
    assert rule_of_three(1000) == 3.0 / 1000
    assert rule_of_three(0) == 1.0


# ---------- 결합 가능한 집계 ----------


def test_proportion_merge_matches_single() -> None:
    a, b = ProportionAggregate(), ProportionAggregate()
    for hit in [True, False, True]:
        a.update(hit)
    for hit in [True, True, False]:
        b.update(hit)
    a.merge(b)
    assert a.successes == 4
    assert a.n == 6


def test_distribution_merge_matches_single() -> None:
    data = [1.0, 2.0, 3.0, 4.0, 10.0]
    whole = DistributionAggregate()
    for x in data:
        whole.update(x)
    left, right = DistributionAggregate(), DistributionAggregate()
    for x in data[:2]:
        left.update(x)
    for x in data[2:]:
        right.update(x)
    left.merge(right)
    assert left.n == whole.n
    assert abs(left.mean - whole.mean) < 1e-9
    assert abs(left.stddev - whole.stddev) < 1e-9


def test_distribution_percentiles_discrete() -> None:
    agg = DistributionAggregate()
    for x in [0.0] * 10 + [3.0] * 90:
        agg.update(x)
    pct = agg.percentiles((5, 50, 95))
    assert pct is not None
    assert pct[50] == 3.0  # 90%가 3
    assert pct[5] == 0.0


def test_distribution_histogram_overflow_drops_percentiles() -> None:
    agg = DistributionAggregate()
    for x in range(2000):  # distinct > _HIST_CAP
        agg.update(float(x))
    assert agg.histogram_overflow is True
    assert agg.percentiles((50,)) is None
    assert agg.n == 2000  # 평균/분산은 여전히 유효


# ---------- sweep ----------


def test_sweep_enumerates_free_enum() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    configs = sweep_configs(rs, enum_constants(rs))
    roles = {c["role"] for c in configs}
    assert roles == {"fighter", "rogue", "wizard"}


# ---------- simulate: 클래스 밸런스 추정 ----------


def test_simulate_class_win_rates() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    validate(rs)
    report = simulate(rs, samples=5000, horizon=20, seed=1)
    by_role = {cfg.config["role"]: _by_id(cfg) for cfg in report.configs}

    # 승률 = win^3: fighter 0.729 · wizard 0.4219 · rogue 0.216.
    fighter = by_role["fighter"]["survives"]
    rogue = by_role["rogue"]["survives"]
    wizard = by_role["wizard"]["survives"]
    assert isinstance(fighter, ProportionResult)
    assert isinstance(rogue, ProportionResult)
    assert isinstance(wizard, ProportionResult)
    assert abs(fighter.p_hat - 0.729) < 0.03
    assert abs(rogue.p_hat - 0.216) < 0.03
    assert abs(wizard.p_hat - 0.4219) < 0.03
    # 클래스 밸런스 순서: fighter > wizard > rogue.
    assert fighter.p_hat > wizard.p_hat > rogue.p_hat
    # 신뢰구간이 추정값을 감싼다.
    assert fighter.ci[0] < fighter.p_hat < fighter.ci[1]


def test_simulate_unobserved_event_uses_rule_of_three() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    report = simulate(rs, samples=2000, horizon=20, seed=1)
    impossible = _by_id(report.configs[0])["impossible_round"]
    assert isinstance(impossible, ProportionResult)
    assert impossible.successes == 0
    assert impossible.rule_of_three == 3.0 / 2000  # 0/N → 상한, 불가능 단정 안 함


def test_simulate_distribution_of_progress() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    report = simulate(rs, samples=3000, horizon=20, seed=2)
    fighter = next(c for c in report.configs if c.config["role"] == "fighter")
    final = _by_id(fighter)["final_progress"]
    assert isinstance(final, DistributionResult)
    assert final.vmin >= 0.0 and final.vmax <= 3.0
    assert final.percentiles is not None
    # fighter는 대부분 3까지 도달 → 중앙값 3.
    assert final.percentiles[50] == 3.0


def test_simulate_is_reproducible() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    r1 = simulate(rs, samples=1000, horizon=20, seed=7)
    r2 = simulate(rs, samples=1000, horizon=20, seed=7)
    p1 = [r.successes for cfg in r1.configs for r in cfg.checks if isinstance(r, ProportionResult)]
    p2 = [r.successes for cfg in r2.configs for r in cfg.checks if isinstance(r, ProportionResult)]
    assert p1 == p2  # 같은 seed → 동일 집계(D19 재현성)


# ---------- 리포트 ----------


def test_report_has_proof_disclaimer_and_estimates() -> None:
    rs = load_rule_file(FIXTURES / "arena.rule")
    report = simulate(rs, samples=1000, horizon=20, seed=1)
    text = format_sim_report(report)
    assert "증명 아님" in text
    assert "role=fighter" in text
    assert "rule of three" in text  # 미관측 사건 안내
    assert "95% CI" in text


def test_report_shows_policy_label_when_pref_used() -> None:
    """pref(무작위 정책, D20)를 쓰는 모델은 'Pmax 아님' 정책 라벨을 노출한다."""
    rs = load_rule_file(FIXTURES / "policy_choice.rule")
    report = simulate(rs, samples=500, horizon=10, seed=1)
    assert report.uses_policy is True
    text = format_sim_report(report)
    assert "최적(Pmax) 아님" in text
    assert "정책(pref)" in text


def test_report_omits_policy_label_without_pref() -> None:
    """pref 없는 순수 DTMC 모델은 정책 라벨을 띄우지 않는다(오해 방지·기존 출력 불변)."""
    rs = load_rule_file(FIXTURES / "arena.rule")
    report = simulate(rs, samples=500, horizon=20, seed=1)
    assert report.uses_policy is False
    assert "최적(Pmax) 아님" not in format_sim_report(report)


def test_dungeon_example_uses_policy() -> None:
    """통합 examples/dungeon.lf(pref 욕심/안전 정책)가 로드·검증·표집되고 정책 라벨을 단다."""
    rs = load_rule_file(EXAMPLES / "dungeon.lf")
    validate(rs)
    report = simulate(rs, samples=500, horizon=300, seed=1)
    assert report.uses_policy is True
    # role sweep → 직업별 config. rogue는 욕심내다 전멸(death) 위험이 실재한다(>0).
    rogue = next(c for c in report.configs if c.config["role"] == "rogue")
    results = _by_id(rogue)
    death = results["death_possible"]
    assert isinstance(death, ProportionResult)
    assert death.successes > 0
    assert isinstance(results["final_gold"], DistributionResult)
    assert "최적(Pmax) 아님" in format_sim_report(report)
