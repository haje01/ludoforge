"""sim 집계(Phase 2, D19): 표집 결과를 결합 가능한(mergeable) 집계로 모은다.

증명이 아니라 **추정**이므로 정직성이 핵심이다(프로젝트 DNA). 모든 추정에 신뢰구간을
붙이고, 한 번도 관측되지 않은 사건은 "불가능"이라 하지 않고 **rule-of-three 상한(≈3/N)**
으로 보고한다(존재 증명은 Z3/BMC 몫). 지평 H에 걸려 잘린 run 비율(절단)도 함께 보고한다.

집계는 **결합 가능**하게 설계한다 — 부분 집계를 `merge`로 합칠 수 있어야 Phase 3(분산/
multiprocessing)에서 워커별 부분합을 모을 수 있다. 따라서 전체 표본을 메모리에 들지 않고:
- 비율: (성공 수, 표본 수) 카운트 → Wilson 구간·rule-of-three.
- 분포: Welford(평균/분산) + 값→빈도 카운터(이산 정확 백분위, 상한 초과 시 평균만).

`simulate`는 sweep 설정마다 N회 표집해 체크별로 집계하고 SimReport를 돌려준다.
"""

from __future__ import annotations

import ast
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from core.ir import Check, RuleSet
from sim.engine import (
    RunResult,
    enum_constants,
    evaluate,
    initial_state,
    policy_players,
    run_once,
    sweep_configs,
    uses_policy,
)

# 95% 신뢰수준 정규근사 z값. Monte Carlo는 표본이 커 CLT 정규근사가 충분하다(t 미사용).
_Z95 = 1.96
# 분포 히스토그램의 distinct 값 상한. 초과하면(연속/넓은 범위) 카운트를 버리고 평균만 본다.
_HIST_CAP = 1000


# ---------- 통계 헬퍼 ----------


def wilson_interval(successes: int, n: int, z: float = _Z95) -> tuple[float, float]:
    """이항 비율의 Wilson 점수 신뢰구간. n=0이면 (0,1)."""
    if n == 0:
        return (0.0, 1.0)
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def rule_of_three(n: int) -> float:
    """0/N 관측 시 사건 확률의 ~95% 상한(≈3/N). n=0이면 1.0."""
    return 1.0 if n == 0 else 3.0 / n


# ---------- 결합 가능한 집계 ----------


@dataclass
class ProportionAggregate:
    """불리언 사건의 비율 집계(reachable 도달·invariant 위반). (성공 수, 표본 수)만 든다."""

    successes: int = 0
    n: int = 0

    def update(self, hit: bool) -> None:
        self.n += 1
        if hit:
            self.successes += 1

    def merge(self, other: ProportionAggregate) -> None:
        self.successes += other.successes
        self.n += other.n

    @property
    def p_hat(self) -> float:
        return self.successes / self.n if self.n else 0.0

    @property
    def ci(self) -> tuple[float, float]:
        return wilson_interval(self.successes, self.n)


@dataclass
class DistributionAggregate:
    """수치식의 분포 집계. Welford(평균/분산) + 값→빈도(이산 백분위). 둘 다 결합 가능."""

    n: int = 0
    mean: float = 0.0
    m2: float = 0.0  # Σ(x-mean)^2 누적(Welford)
    vmin: float = math.inf
    vmax: float = -math.inf
    counts: Counter[float] = field(default_factory=Counter)
    histogram_overflow: bool = False

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)
        self.vmin = min(self.vmin, x)
        self.vmax = max(self.vmax, x)
        if not self.histogram_overflow:
            self.counts[x] += 1
            if len(self.counts) > _HIST_CAP:
                self.histogram_overflow = True
                self.counts.clear()

    def merge(self, other: DistributionAggregate) -> None:
        if other.n == 0:
            return
        if self.n == 0:
            self.__dict__.update(other.__dict__)
            self.counts = Counter(other.counts)
            return
        n = self.n + other.n
        delta = other.mean - self.mean
        self.mean += delta * other.n / n
        self.m2 += other.m2 + delta * delta * self.n * other.n / n
        self.n = n
        self.vmin = min(self.vmin, other.vmin)
        self.vmax = max(self.vmax, other.vmax)
        if self.histogram_overflow or other.histogram_overflow:
            self.histogram_overflow = True
            self.counts.clear()
        else:
            self.counts.update(other.counts)
            if len(self.counts) > _HIST_CAP:
                self.histogram_overflow = True
                self.counts.clear()

    @property
    def stddev(self) -> float:
        return math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else 0.0

    @property
    def stderr(self) -> float:
        return self.stddev / math.sqrt(self.n) if self.n else 0.0

    @property
    def ci(self) -> tuple[float, float]:
        margin = _Z95 * self.stderr
        return (self.mean - margin, self.mean + margin)

    def percentiles(self, ps: tuple[int, ...]) -> dict[int, float] | None:
        """이산 백분위(nearest-rank). 히스토그램 초과 시 None."""
        if self.histogram_overflow or self.n == 0:
            return None
        ordered = sorted(self.counts.items())
        out: dict[int, float] = {}
        for p in ps:
            rank = max(1, math.ceil(p / 100 * self.n))
            cum = 0
            for value, cnt in ordered:
                cum += cnt
                if cum >= rank:
                    out[p] = value
                    break
        return out


# ---------- 결과 자료구조 ----------


@dataclass(frozen=True)
class ProportionResult:
    """reachable(도달)·invariant(위반) 체크의 추정 결과."""

    check_id: str
    kind: str
    desc: str | None
    event_label: str  # "도달" / "위반"
    successes: int
    n: int
    p_hat: float
    ci: tuple[float, float]
    rule_of_three: float | None  # successes==0일 때 상한, 아니면 None
    example: RunResult | None  # invariant 위반의 예시 trace(있으면)


@dataclass(frozen=True)
class DistributionResult:
    """distribution 체크의 추정 결과(평균±CI·백분위·범위)."""

    check_id: str
    desc: str | None
    n: int
    mean: float
    stddev: float
    ci: tuple[float, float]
    vmin: float
    vmax: float
    percentiles: dict[int, float] | None
    histogram: dict[float, int] | None = None  # 값→빈도(히스토그램 시각화용). 초과 시 None
    ghost_expr: bool = False  # 식이 ghost 서술 변수(D31)를 참조 — "논리 검증 제외" 라벨용


CheckResult = ProportionResult | DistributionResult


@dataclass(frozen=True)
class ConfigResult:
    """한 sweep 설정(자유변수 배정)의 결과."""

    config: dict[str, Any]
    n_samples: int
    truncated: int  # 지평 H에 걸려 잘린 run 수(절단 편향 보고)
    terminated: int  # 자연 종료(흡수) run 수
    checks: tuple[CheckResult, ...]


@dataclass(frozen=True)
class SimReport:
    samples: int
    horizon: int
    seed: int
    configs: tuple[ConfigResult, ...]
    skipped: tuple[str, ...]  # sim이 다루지 않는 체크(prob/no_deadlock)
    uses_policy: bool = False  # pref(무작위 정책, D20)로 선택을 해소했는가 → 정책 라벨
    policy_players: tuple[str, ...] = ()  # pref 전이의 소유 플레이어(D27) — 라벨에 명시


_PERCENTILES = (5, 50, 95)


# ---------- 배치(부분) 집계 — 결합 가능, RNG 무관 ----------


@dataclass
class BatchAggregate:
    """한 표집 배치(청크)의 부분 집계. merge로 합칠 수 있어 분산/병렬에서 모은다(Phase 3).

    RNG에 무관하다 — `run_batch`가 받은 rng(stdlib random 또는 numpy Generator)로 채운다.
    """

    props: dict[str, ProportionAggregate]
    dists: dict[str, DistributionAggregate]
    examples: dict[str, RunResult]
    truncated: int = 0
    terminated: int = 0
    n: int = 0

    def merge(self, other: BatchAggregate) -> None:
        for k, agg in other.props.items():
            self.props[k].merge(agg)
        for k, dagg in other.dists.items():
            self.dists[k].merge(dagg)
        for k, ex in other.examples.items():
            self.examples.setdefault(k, ex)  # 청크 순서상 먼저 온 예시를 유지(결정적)
        self.truncated += other.truncated
        self.terminated += other.terminated
        self.n += other.n


def select_sim_checks(ruleset: RuleSet) -> list[Check]:
    """sim이 다루는 체크(reachable/invariant/distribution)만 추린다."""
    return [c for c in ruleset.checks if c.kind in ("reachable", "invariant", "distribution")]


def parse_check_exprs(sim_checks: list[Check]) -> dict[str, ast.expr]:
    """체크 식을 한 번만 파싱한다(스텝·run마다 재파싱 회피)."""
    return {c.id: _parse_check_expr(c) for c in sim_checks}


def new_batch(sim_checks: list[Check]) -> BatchAggregate:
    return BatchAggregate(
        props={
            c.id: ProportionAggregate() for c in sim_checks if c.kind in ("reachable", "invariant")
        },
        dists={c.id: DistributionAggregate() for c in sim_checks if c.kind == "distribution"},
        examples={},
    )


def run_batch(
    ruleset: RuleSet,
    constants: dict[str, Any],
    sim_checks: list[Check],
    parsed: dict[str, ast.expr],
    initial: dict[str, Any],
    rng: Any,  # SupportsRandom: stdlib random.Random 또는 numpy Generator(.random())
    count: int,
    horizon: int,
) -> BatchAggregate:
    """count회 표집해 부분 집계(BatchAggregate)를 만든다. rng는 .random()만 요구한다(D19)."""
    batch = new_batch(sim_checks)
    for _ in range(count):
        run = run_once(ruleset, rng, horizon, initial=dict(initial))
        batch.n += 1
        batch.truncated += int(run.truncated)
        batch.terminated += int(run.terminated)
        for c in sim_checks:
            node = parsed[c.id]
            if c.kind == "reachable":
                batch.props[c.id].update(_any_state(node, run, constants))
            elif c.kind == "invariant":
                violated = not _all_states(node, run, constants)
                batch.props[c.id].update(violated)
                if violated and c.id not in batch.examples:
                    batch.examples[c.id] = run
            else:  # distribution
                batch.dists[c.id].update(float(evaluate(node, {**constants, **run.states[-1]})))
    return batch


def merge_batches(batches: list[BatchAggregate], sim_checks: list[Check]) -> BatchAggregate:
    """배치들을 **주어진 순서대로** 합친다(부동소수 결정성 — 워커 수 무관 동일 결과, D19)."""
    merged = new_batch(sim_checks)
    for b in batches:
        merged.merge(b)
    return merged


def finalize_config(
    config: dict[str, Any],
    batch: BatchAggregate,
    sim_checks: list[Check],
    ghosts: frozenset[str] = frozenset(),
) -> ConfigResult:
    """배치 집계를 사람이 읽는 ConfigResult(체크별 추정값)로 마무리한다.

    `ghosts`(D31)가 주어지면 ghost를 참조하는 distribution 결과에 서술 변수 라벨을 단다."""
    checks = tuple(
        _check_result(c, batch.props, batch.dists, batch.examples, ghosts) for c in sim_checks
    )
    return ConfigResult(
        config=config,
        n_samples=batch.n,
        truncated=batch.truncated,
        terminated=batch.terminated,
        checks=checks,
    )


# ---------- 시뮬레이션 드라이버(직렬 참조 구현, stdlib RNG) ----------


def simulate(ruleset: RuleSet, *, samples: int, horizon: int, seed: int) -> SimReport:
    """sweep 설정마다 N회 표집해 체크별로 집계한다(직렬 참조 구현, D19).

    병렬·재현성(numpy SeedSequence) 경로는 `sim.runner.run_sim`이다 — 본 함수는 단순한
    직렬 기준 구현으로 stdlib random을 쓴다. DtmcViolation/SimError는 그대로 전파한다.
    """
    constants = enum_constants(ruleset)
    configs = sweep_configs(ruleset, constants)
    sim_checks = select_sim_checks(ruleset)
    parsed = parse_check_exprs(sim_checks)
    skipped = tuple(c.id for c in ruleset.checks if c.kind == "no_deadlock")

    results: list[ConfigResult] = []
    for ci, config in enumerate(configs):
        initial = initial_state(ruleset, constants, overrides=config)
        rng = random.Random(seed * 1_000_003 + ci)
        batch = run_batch(ruleset, constants, sim_checks, parsed, initial, rng, samples, horizon)
        results.append(finalize_config(config, batch, sim_checks, ghost_var_names(ruleset)))

    return SimReport(
        samples=samples,
        horizon=horizon,
        seed=seed,
        configs=tuple(results),
        skipped=skipped,
        uses_policy=uses_policy(ruleset),
        policy_players=policy_players(ruleset),
    )


# ---------- 내부 헬퍼 ----------


def _refs_any(expr: str | None, names: frozenset[str]) -> bool:
    """식이 주어진 이름들 중 하나라도 참조하는가(ghost 라벨 판정용, D31)."""
    if not expr:
        return False
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    return any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(tree))


def ghost_var_names(ruleset: RuleSet) -> frozenset[str]:
    """ghost 서술 변수(D31) 이름 집합 — distribution 라벨 판정용."""
    return frozenset(v.name for v in ruleset.variables if v.ghost)


def _parse_check_expr(c: Check) -> ast.expr:
    """sim 체크의 식을 파싱한다. reachable/invariant는 that, distribution은 expr."""
    text = c.that if c.kind in ("reachable", "invariant") else c.expr
    if text is None:  # loader가 보장하므로 도달하지 않음(방어적)
        raise ValueError(f"검사 '{c.id}'(kind={c.kind})에 식이 없습니다.")
    return ast.parse(text, mode="eval").body


def _any_state(node: ast.expr, run: RunResult, constants: dict[str, Any]) -> bool:
    return any(bool(evaluate(node, {**constants, **s})) for s in run.states)


def _all_states(node: ast.expr, run: RunResult, constants: dict[str, Any]) -> bool:
    return all(bool(evaluate(node, {**constants, **s})) for s in run.states)


def _check_result(
    c: Check,
    props: dict[str, ProportionAggregate],
    dists: dict[str, DistributionAggregate],
    examples: dict[str, RunResult],
    ghosts: frozenset[str] = frozenset(),
) -> CheckResult:
    if c.kind == "distribution":
        agg = dists[c.id]
        return DistributionResult(
            check_id=c.id,
            desc=c.desc,
            n=agg.n,
            mean=agg.mean,
            stddev=agg.stddev,
            ci=agg.ci,
            vmin=agg.vmin,
            vmax=agg.vmax,
            percentiles=agg.percentiles(_PERCENTILES),
            histogram=(dict(agg.counts) if not agg.histogram_overflow and agg.counts else None),
            ghost_expr=bool(ghosts) and _refs_any(c.expr, ghosts),
        )
    agg_p = props[c.id]
    return ProportionResult(
        check_id=c.id,
        kind=c.kind,
        desc=c.desc,
        event_label="도달" if c.kind == "reachable" else "위반",
        successes=agg_p.successes,
        n=agg_p.n,
        p_hat=agg_p.p_hat,
        ci=agg_p.ci,
        rule_of_three=rule_of_three(agg_p.n) if agg_p.successes == 0 else None,
        example=examples.get(c.id),
    )
