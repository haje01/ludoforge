"""웹 서버 설정 — configs/web.yaml (없으면 기본값).

자원 상한(caps)은 안전장치다: `.lf`는 비-튜링완전이라 샌드박스는 불필요하지만,
BMC 깊이·표집 수·지평은 실행 시간을 좌우하므로 서버가 상한을 강제한다(요청은 클램프).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "web.yaml"


@dataclass(frozen=True)
class WebConfig:
    model: str = "claude-opus-4-8"  # 번역용 Claude 모델(기본 Opus — 번역 품질 우선)
    max_translate_attempts: int = 3  # LLM 수리 루프 상한
    bmc_k_max: int = 30  # BMC 언롤링 깊이 상한
    sim_samples_max: int = 200_000  # sim 설정당 표집 상한
    sim_horizon_max: int = 10_000  # sim run당 스텝 상한
    sim_workers: int = 1  # sim 병렬 워커(결과는 워커 수 무관)


class ConfigError(Exception):
    """설정 파일 로드/검증 실패."""


def load_config(path: str | Path | None = None) -> WebConfig:
    """설정을 로드한다. path가 None이면 configs/web.yaml, 그것도 없으면 기본값."""
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        if path is not None:
            raise ConfigError(f"설정 파일을 찾을 수 없습니다: {cfg_path}")
        return WebConfig()

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{cfg_path}: 최상위는 매핑이어야 합니다.")
    known = {f.name for f in fields(WebConfig)}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"{cfg_path}: 알 수 없는 설정 키: {sorted(unknown)}")
    return WebConfig(**raw)
