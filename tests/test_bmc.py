"""Phase 3: BMC 백엔드(D15) 테스트.

전이 시스템을 k 스텝 언롤링해 reachable/invariant/no_deadlock를 검사하고, 반례 경로와
k-bound 한계를 보고하는지 본다. 프레임=미변경 유지, constraints=상태 불변식, weight-erasure.
"""

from __future__ import annotations

from pathlib import Path

from core.loader import load_rule_file
from logic.solver.bmc import format_bmc_report, run_bmc

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def _by_id(report: object) -> dict[str, object]:
    return {r.prop_id: r for r in report.results}  # type: ignore[attr-defined]


# ---------- reachable ----------


def test_reachable_finds_shortest_trace() -> None:
    rs = load_rule_file(FIXTURES / "bmc_counter.lf")
    report = run_bmc(rs, k=10)
    r = _by_id(report)["reach3"]
    assert r.status == "reachable"  # type: ignore[attr-defined]
    assert r.depth == 3  # type: ignore[attr-defined]  # 0→1→2→3, 가장 짧은 경로
    # 경로의 마지막 상태가 목표를 만족
    assert r.trace.steps[-1].values["x"] == "3"  # type: ignore[attr-defined]
    # action 라벨이 전이 id로 채워짐
    assert r.trace.actions == ("inc", "inc", "inc")  # type: ignore[attr-defined]


def test_reachable_unconfirmed_within_small_k() -> None:
    rs = load_rule_file(FIXTURES / "bmc_counter.lf")
    report = run_bmc(rs, k=2)  # 깊이 3 필요한데 k=2
    r = _by_id(report)["reach3"]
    # 실제로는 도달 가능(깊이 3)이므로 ¬that 귀납은 실패해야 한다(건전성) — 미확인 유지
    assert r.status == "unreachable_within_k"  # type: ignore[attr-defined]
    assert report.has_unconfirmed


def test_reachable_proved_unreachable() -> None:
    """짝수만 도달하는 x에서 x==5는 ¬that 귀납(j=3)으로 도달 불가 확정(D25) — 종료코드 1."""
    rs = load_rule_file(FIXTURES / "bmc_induction.lf")
    report = run_bmc(rs, k=5)
    r = _by_id(report)["five"]
    assert r.status == "unreachable"  # type: ignore[attr-defined]
    assert "j=3" in r.detail  # type: ignore[attr-defined]
    assert report.has_violation  # 도달 불가 확정 = reachable 검사의 실패 확정(D25 비준)
    assert not report.has_unconfirmed


def test_reachable_stays_unconfirmed_when_k_below_induction_depth() -> None:
    """k=2는 도달 불가 확정에 필요한 귀납 깊이 3에 못 미침 — 미확인(3) 유지(D25 정직성)."""
    rs = load_rule_file(FIXTURES / "bmc_induction.lf")
    report = run_bmc(rs, k=2)
    r = _by_id(report)["five"]
    assert r.status == "unreachable_within_k"  # type: ignore[attr-defined]
    assert report.has_unconfirmed


# ---------- invariant ----------


def test_invariant_domain_implied_is_proved_immediately() -> None:
    """도메인 상한에서 직접 따라오는 불변식은 j=0 귀납으로 무한 지평 증명된다(D25)."""
    rs = load_rule_file(FIXTURES / "bmc_counter.lf")
    report = run_bmc(rs, k=10)
    r = _by_id(report)["le5"]
    assert r.status == "holds"  # type: ignore[attr-defined]
    assert "j=0" in r.detail  # type: ignore[attr-defined]
    assert not report.has_unconfirmed


def test_invariant_proved_at_min_induction_depth() -> None:
    """x+=2의 'x != 3'은 j=1 비귀납(반례는 도달 불가 상태), j=2에서 증명(D25)."""
    rs = load_rule_file(FIXTURES / "bmc_induction.lf")
    report = run_bmc(rs, k=5)
    r = _by_id(report)["odd3"]
    assert r.status == "holds"  # type: ignore[attr-defined]
    assert "j=2" in r.detail  # type: ignore[attr-defined]


def test_invariant_stays_bounded_when_k_below_induction_depth() -> None:
    """k=1은 귀납 깊이 2에 못 미침 — 증명으로 뭉개지 않고 유계 결과+사유 유지(D25 정직성)."""
    rs = load_rule_file(FIXTURES / "bmc_induction.lf")
    report = run_bmc(rs, k=1)
    r = _by_id(report)["odd3"]
    assert r.status == "holds_up_to_k"  # type: ignore[attr-defined]
    assert "귀납" in r.detail  # type: ignore[attr-defined]


def test_invariant_violation_gives_trace() -> None:
    rs = load_rule_file(FIXTURES / "bmc_counter.lf")
    report = run_bmc(rs, k=10)
    r = _by_id(report)["never4"]
    assert r.status == "violated"  # type: ignore[attr-defined]
    assert r.depth == 4  # type: ignore[attr-defined]  # x가 4에 처음 닿는 깊이
    assert r.trace.steps[-1].values["x"] == "4"  # type: ignore[attr-defined]
    assert report.has_violation


# ---------- no_deadlock ----------


def test_deadlock_detected() -> None:
    rs = load_rule_file(FIXTURES / "bmc_deadlock.lf")
    report = run_bmc(rs, k=10)
    r = _by_id(report)["live"]
    assert r.status == "deadlock"  # type: ignore[attr-defined]
    assert r.depth == 2  # type: ignore[attr-defined]  # x==2에서 전이 불가
    assert report.has_violation


def test_no_deadlock_proved_when_always_enabled() -> None:
    """무가드 전이가 있으면 모든 합법 상태가 enabled — j=0 귀납으로 데드락 없음 증명(D25)."""
    rs = load_rule_file(FIXTURES / "bmc_induction.lf")
    report = run_bmc(rs, k=3)
    r = _by_id(report)["live"]
    assert r.status == "no_deadlock"  # type: ignore[attr-defined]
    assert "j=0" in r.detail  # type: ignore[attr-defined]


def test_no_deadlock_stays_bounded_when_not_inductive() -> None:
    """bmc_deadlock은 깊이 2에 실제 데드락 — k=1이면 base 통과·비귀납 → 유계 유지(건전성)."""
    rs = load_rule_file(FIXTURES / "bmc_deadlock.lf")
    report = run_bmc(rs, k=1)
    r = _by_id(report)["live"]
    assert r.status == "no_deadlock_up_to_k"  # type: ignore[attr-defined]


# ---------- 던전! 통합 ----------


def test_dungeon_winnable_reachable() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.lf")
    report = run_bmc(rs, k=10)
    by = _by_id(report)
    # 전사(목표 10)는 몇 스텝 안에 보물을 모아 승리(status=won) 도달 가능
    assert by["winnable"].status == "reachable"  # type: ignore[attr-defined]
    # 불변식 3종은 k-귀납으로 무한 지평 증명으로 승격(D25)
    assert by["gold_nonneg"].status == "holds"  # type: ignore[attr-defined]
    assert by["no_monster_in_hall"].status == "holds"  # type: ignore[attr-defined]
    assert by["sound_victory"].status == "holds"  # type: ignore[attr-defined]
    # 모든 합법 상태에 후속 전이가 있음 — 데드락 없음도 증명으로 승격(D25)
    assert by["no_stuck"].status == "no_deadlock"  # type: ignore[attr-defined]


def test_dungeon_winning_trace_ends_at_hall_with_target_gold() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.lf")
    report = run_bmc(rs, k=10)
    trace = _by_id(report)["winnable"].trace  # type: ignore[attr-defined]
    last = trace.steps[-1].values
    assert last["status"] == "won"
    assert last["room"] == "hall"
    assert int(last["gold"]) >= int(last["win_gold"])


# ---------- 리포트 포맷 ----------


def test_report_mentions_k_bound_for_unproved() -> None:
    # k=2: never4(비귀납·위반은 깊이 4)와 reach3(깊이 3 필요)이 유계 결과로 남는다.
    rs = load_rule_file(FIXTURES / "bmc_counter.lf")
    text = format_bmc_report(run_bmc(rs, k=2))
    assert "k 한계" in text  # k-bound 정직성 명시(미증명 항목)
    assert "k=2" in text


def test_report_marks_proof_without_k_bound_note() -> None:
    # k=10: le5는 증명 승격 — 증명 항목에는 k-bound 각주가 붙지 않는다.
    rs = load_rule_file(FIXTURES / "bmc_counter.lf")
    text = format_bmc_report(run_bmc(rs, k=10))
    assert "무한 지평" in text
    assert "j=0" in text


def test_report_shows_violation_trace() -> None:
    rs = load_rule_file(FIXTURES / "bmc_counter.lf")
    text = format_bmc_report(run_bmc(rs, k=10))
    assert "불변식 위반" in text
    assert "경로:" in text
    assert "--[inc]-->" in text


# ---------- 상태 의존 weight(D26) — weight-erasure 무회귀 ----------


def test_bmc_erases_state_dependent_weights() -> None:
    """BMC는 weight가 식이어도 지우고(비결정 분기) 경로를 찾는다 — dialect 분리(D11·D26)."""
    rs = load_rule_file(FIXTURES / "urn.lf")
    report = run_bmc(rs, k=4)
    r = _by_id(report)["ends_red"]
    assert r.status == "reachable"  # type: ignore[attr-defined]
    assert r.depth == 3  # type: ignore[attr-defined]  # 공 3개를 다 뽑는 최단 경로


# ---------- 2인 레이스 던전(D27) — player 태그는 BMC에 주석 ----------


def test_race_dungeon_soundness() -> None:
    """레이스판: 양쪽 모두 이길 길이 존재하고(비결정 탐색 — 태그·pref 무시),
    건전성 불변식·데드락 없음은 k-귀납으로 무한 지평 증명된다."""
    rs = load_rule_file(EXAMPLES / "dungeon_race.lf")
    report = run_bmc(rs, k=12)
    by = _by_id(report)
    assert by["p1_wins"].status == "reachable"  # type: ignore[attr-defined]
    assert by["p1_wins"].depth == 11  # type: ignore[attr-defined]  # 선공 이점: p1 최단 승리
    assert by["p2_wins"].status == "reachable"  # type: ignore[attr-defined]
    assert by["p2_wins"].depth == 12  # type: ignore[attr-defined]  # 후공은 한 스텝 늦다
    assert by["win_needs_target_p1"].status == "holds"  # type: ignore[attr-defined]
    assert by["win_needs_target_p2"].status == "holds"  # type: ignore[attr-defined]
    assert by["no_stuck"].status == "no_deadlock"  # type: ignore[attr-defined]


def test_dynamic_index_guard_translates_to_z3_if() -> None:
    """동적 색인 가드(D28)가 z3.If로 번역돼 BMC 도달성이 동작한다."""
    rs = load_rule_file(FIXTURES / "dyn_index.lf")
    report = run_bmc(rs, k=8)
    r = _by_id(report)["p1_full"]
    assert r.status == "reachable"  # type: ignore[attr-defined]
    assert r.depth == 5  # type: ignore[attr-defined]  # p1 3득점 + p2 턴 2회 개재
