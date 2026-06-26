"""S8: 알려진 모순/정합 코퍼스 + 거짓양성·거짓음성 회귀 잠금 (CLAUDE.md §8).

검증기의 신뢰성이 곧 제품 가치다. 의도적으로 모순/정합인 룰셋을 fixtures에 두고,
검사기가 정확히 그 결과를 내는지 잠근다. 한 번 잘못 잡은 케이스는 영구 회귀 테스트로
고정한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.loader import load_rules
from core.schema import validate
from logic.solver.checks import CheckReport, check
from logic.solver.report import format_report
from logic.solver.translator import translate

FIXTURES = Path(__file__).parent / "fixtures"
CONSISTENT = sorted((FIXTURES / "consistent").glob("*.rule"))
CONTRADICTION = sorted((FIXTURES / "contradiction").glob("*.rule"))

# docs용 예제(examples/)도 회귀로 잠근다 — README/예제가 실제 동작과 어긋나지 않게.
EXAMPLES = Path(__file__).parent.parent / "examples"
EXAMPLE_EXPECTED = {
    "item_enchant": True,
    "loot_table": True,
    "starter_zone_drops": True,
    "stealth_combat": True,
    "drop_rates_real": True,
    "day_night_cycle": True,
    "crit_chance": True,
    "stat_budget": True,
    "balanced_stats": False,
    "balanced_build": False,
    "dungeon": False,  # 전이 시스템 예제 — 정적 check는 모순 없음(동역학은 ludoforge bmc)
    "market_sim": False,  # real·다변수 시연(sim 백엔드/D19) — 정적 check는 모순 없음
}


def _run(path: Path) -> CheckReport:
    rs = load_rules(path)
    validate(rs)
    return check(rs, translate(rs))


@pytest.mark.parametrize("rule_file", CONSISTENT, ids=lambda p: p.stem)
def test_consistent_corpus_has_no_contradiction(rule_file: Path) -> None:
    report = _run(rule_file)
    assert not report.has_contradiction, format_report(report)
    assert report.unknowns == ()


@pytest.mark.parametrize("rule_file", CONTRADICTION, ids=lambda p: p.stem)
def test_contradiction_corpus_is_detected(rule_file: Path) -> None:
    report = _run(rule_file)
    assert report.has_contradiction
    assert report.unknowns == ()


def test_corpus_directories_are_not_empty() -> None:
    # glob가 조용히 0건이면 위 parametrize가 통과처럼 보이는 함정을 막는다.
    assert CONSISTENT, "정합 코퍼스가 비어 있습니다"
    assert CONTRADICTION, "모순 코퍼스가 비어 있습니다"


def test_warrior_level_cap_pins_exact_culprits() -> None:
    report = _run(FIXTURES / "contradiction" / "warrior_level_cap.rule")
    assert len(report.violations) == 1
    v = report.violations[0]
    assert (v.variable, v.bound, v.declared, v.achievable) == ("level", "max", 100, 50)
    assert set(v.culprit_rules) == {"warrior_hp_formula", "global_hp_cap"}


def test_dependent_variable_not_flagged_regression() -> None:
    # D5 회귀: 종속 변수 hp(=level*100)는 hp=0 미달로 거짓양성 모순이 되면 안 된다.
    report = _run(FIXTURES / "contradiction" / "warrior_level_cap.rule")
    assert all(v.variable != "hp" for v in report.violations)


def test_unreachable_role_pins_culprits() -> None:
    report = _run(FIXTURES / "contradiction" / "unreachable_role.rule")
    assert len(report.unreachable_states) == 1
    ue = report.unreachable_states[0]
    assert ue.assignment == {"role": "ghost"}
    assert set(ue.culprit_rules) == {"ghost_no_hp", "must_have_hp"}


@pytest.mark.parametrize("stem,expect_contradiction", sorted(EXAMPLE_EXPECTED.items()))
def test_examples_match_documented_outcome(stem: str, expect_contradiction: bool) -> None:
    report = _run(EXAMPLES / f"{stem}.lf")
    assert report.has_contradiction is expect_contradiction, format_report(report)
    assert report.unknowns == ()


def test_examples_directory_matches_expected_set() -> None:
    # 예제 파일이 추가/삭제되면 기대표(EXAMPLE_EXPECTED)도 함께 갱신하도록 강제.
    actual = {p.stem for p in EXAMPLES.glob("*.lf")}
    assert actual == set(EXAMPLE_EXPECTED), f"examples/ 변경됨: {actual}"


def test_real_cap_blocks_declared_max() -> None:
    # D9: real 끝점 검사 — 선언 max=1.0이 룰(<=0.3)로 봉쇄됨을 정확히 짚는다.
    report = _run(FIXTURES / "contradiction" / "real_cap_blocks_max.rule")
    assert len(report.bound_unreachables) == 1
    b = report.bound_unreachables[0]
    assert (b.variable, b.bound, b.declared) == ("drop_rate", "max", 1.0)
    assert set(b.culprit_rules) == {"rate_capped"}


def test_conflicting_constants_global_infeasibility() -> None:
    report = _run(FIXTURES / "contradiction" / "conflicting_constants.rule")
    assert len(report.unreachable_states) == 1
    ue = report.unreachable_states[0]
    assert ue.assignment == {}  # enum 없음 → 전역 도달 불가
    assert set(ue.culprit_rules) == {"set_low", "set_high"}
