"""Phase 5: real·고차원 스케일 시연(D19).

PRISM(망라적 증명)이 못 푸는 모델을 sim(표집 추정)이 분포로 답함을 보인다:
- real(연속) 변수 → PRISM 유한상태 게이트(D13)가 즉시 거부.
- sim은 상태공간을 빌드하지 않으므로 real·고차원을 그대로 표집한다(증명 아님, CI 동반).
연속 분포는 distinct 값이 많아 히스토그램이 넘쳐 평균/CI만 정직하게 보고한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ir import RuleSet
from core.loader import load_rule_file
from core.schema import SchemaError, validate
from prob.prism_gen import generate
from sim.aggregate import DistributionResult, ProportionResult
from sim.runner import run_sim

EXAMPLES = Path(__file__).parent.parent / "examples"


def _market() -> RuleSet:
    return load_rule_file(EXAMPLES / "market_sim.rule")


def test_prism_rejects_real_model() -> None:
    # PRISM은 real 변수를 유한상태 게이트에서 거부한다 — 이 모델은 망라적 증명 대상이 아님.
    rs = _market()
    with pytest.raises(SchemaError, match="실수 변수"):
        generate(rs)


def test_sim_estimates_real_model_that_prism_cannot() -> None:
    rs = _market()
    validate(rs)  # backend-agnostic 검증은 통과(real 허용)
    report = run_sim(rs, samples=8000, horizon=60, seed=1, workers=2)
    assert len(report.configs) == 1  # 자유변수 없음 → 단일 설정
    cfg = report.configs[0]
    assert cfg.truncated == 0  # 30라운드 후 흡수 → 모두 자연 종료
    by_id = {r.check_id: r for r in cfg.checks}

    # 연속 자산 분포: 복리라 평균 > 1(성장), distinct 多 → 백분위 생략(평균/CI만).
    gold = by_id["final_gold"]
    assert isinstance(gold, DistributionResult)
    assert gold.mean > 1.0
    assert gold.percentiles is None  # 연속 → 히스토그램 넘침(정직한 degradation)
    assert gold.ci[0] < gold.mean < gold.ci[1]

    # 도달성 추정(0~1 사이의 실제 확률).
    doubles = by_id["gold_doubles"]
    assert isinstance(doubles, ProportionResult)
    assert 0.0 < doubles.p_hat < 1.0


def test_sim_real_invariant_uses_rule_of_three() -> None:
    # 곱셈 복리라 자산은 항상 양수 → 위반 0/N → 불가능 단정 대신 rule-of-three 상한.
    rs = _market()
    report = run_sim(rs, samples=4000, horizon=60, seed=2)
    inv = {r.check_id: r for r in report.configs[0].checks}["portfolio_positive"]
    assert isinstance(inv, ProportionResult)
    assert inv.successes == 0  # 위반 미관측
    assert inv.rule_of_three == 3.0 / 4000
