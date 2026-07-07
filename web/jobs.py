"""인메모리 비동기 잡 저장소 — bmc/sim은 수 초~분이 걸려 폴링으로 결과를 받는다.

MVP 범위: 프로세스 내 스레드 + dict(락 보호). 서버 재시작 시 잡은 사라진다 —
영속화·큐는 다중 사용자 요구가 생길 때 도입한다.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending | running | done | error
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class JobStore:
    _jobs: dict[str, Job] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def submit(self, fn: Callable[[], dict[str, Any]]) -> str:
        """fn을 백그라운드 스레드로 실행하고 잡 id를 즉시 돌려준다."""
        job = Job(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job

        def work() -> None:
            with self._lock:
                job.status = "running"
            try:
                result = fn()
            except Exception as e:  # 잡 경계 — 실패를 상태로 보고(조용히 삼키지 않는다)
                with self._lock:
                    job.status = "error"
                    job.error = f"{type(e).__name__}: {e}"
                return
            with self._lock:
                job.status = "done"
                job.result = result

        threading.Thread(target=work, daemon=True).start()
        return job.id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)
