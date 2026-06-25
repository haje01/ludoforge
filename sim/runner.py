"""sim 러너(Phase 3, D19): 표집을 청크로 나눠 multiprocessing으로 병렬 실행한다.

**재현성이 워커 수와 무관**해야 한다(D19) — 워커 1개든 N개든 같은 seed면 같은 결과.
이를 위해:
- 설정마다 표본을 **워커 수와 무관한 고정 개수의 청크**로 나눈다.
- 청크 시드는 numpy `SeedSequence([seed, config_index]).spawn(청크 수)`로 만든다 — 청크마다
  독립·재현 스트림(상관 없음). 청크 k는 항상 같은 시드를 받는다(워커 배치와 무관).
- 부분 집계(BatchAggregate)를 **청크 순서대로** 합친다(부동소수 결정성).

따라서 (seed, samples, horizon)만 같으면 workers 값과 상관없이 SimReport가 동일하다.
분산(Ray/dask/k8s)으로 확장하려면 청크 task를 다른 transport로 보내고 같은 순서로 합치면
된다 — 집계가 결합 가능하게 설계된 이유다(현재 구현은 로컬 multiprocessing).
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.ir import RuleSet
from sim.aggregate import (
    BatchAggregate,
    ConfigResult,
    SimReport,
    finalize_config,
    merge_batches,
    parse_check_exprs,
    run_batch,
    select_sim_checks,
)
from sim.engine import enum_constants, initial_state, sweep_configs, uses_policy

# 설정당 청크 수 상한 — 워커 수와 무관(재현성). 병렬도는 이 값까지(코어가 더 많아도).
_MAX_CHUNKS = 64


@dataclass(frozen=True)
class _ChunkTask:
    """한 청크의 작업 명세(워커로 pickle돼 넘어간다)."""

    ruleset: RuleSet
    config: dict[str, Any]
    initial: dict[str, Any]
    horizon: int
    seed_seq: np.random.SeedSequence
    count: int


def run_sim(
    ruleset: RuleSet, *, samples: int, horizon: int, seed: int, workers: int = 1
) -> SimReport:
    """sweep 설정마다 N회 표집을 청크 병렬로 집계한다(워커 수 무관 재현성, D19).

    DtmcViolation/SimError는 그대로 전파한다(모델이 sim 대상이 아니면 호출자가 보고).
    """
    constants = enum_constants(ruleset)
    configs = sweep_configs(ruleset, constants)
    sim_checks = select_sim_checks(ruleset)
    skipped = tuple(c.id for c in ruleset.checks if c.kind == "no_deadlock")

    results: list[ConfigResult] = []
    for ci, config in enumerate(configs):
        initial = initial_state(ruleset, constants, overrides=config)
        counts = _chunk_counts(samples, min(samples, _MAX_CHUNKS))
        seqs = np.random.SeedSequence([seed, ci]).spawn(len(counts))
        tasks = [
            _ChunkTask(ruleset, config, initial, horizon, seqs[k], counts[k])
            for k in range(len(counts))
        ]
        batches = _run_tasks(tasks, workers)
        merged = merge_batches(batches, sim_checks)  # 청크 순서대로 합침(결정성)
        results.append(finalize_config(config, merged, sim_checks))

    return SimReport(
        samples=samples,
        horizon=horizon,
        seed=seed,
        configs=tuple(results),
        skipped=skipped,
        uses_policy=uses_policy(ruleset),
    )


def _run_tasks(tasks: list[_ChunkTask], workers: int) -> list[BatchAggregate]:
    """청크 task들을 실행해 입력 순서대로 BatchAggregate 목록을 돌려준다."""
    if workers <= 1 or len(tasks) <= 1:
        return [_run_chunk(t) for t in tasks]
    with mp.Pool(processes=workers) as pool:
        return pool.map(_run_chunk, tasks)  # map은 입력 순서 보존 → 청크 순서 유지


def _run_chunk(task: _ChunkTask) -> BatchAggregate:
    """한 청크를 표집한다(워커 프로세스에서 실행). 시드로 numpy Generator를 만들어 쓴다."""
    constants = enum_constants(task.ruleset)
    sim_checks = select_sim_checks(task.ruleset)
    parsed = parse_check_exprs(sim_checks)
    rng = np.random.Generator(np.random.PCG64(task.seed_seq))
    return run_batch(
        task.ruleset, constants, sim_checks, parsed, task.initial, rng, task.count, task.horizon
    )


def _chunk_counts(samples: int, n_chunks: int) -> list[int]:
    """samples를 n_chunks개로 최대한 고르게 나눈 개수 목록(워커 수와 무관)."""
    if n_chunks <= 0:
        return []
    base, extra = divmod(samples, n_chunks)
    return [base + 1 if i < extra else base for i in range(n_chunks)]
