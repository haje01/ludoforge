"""Ludoforge — 게임 기획 검증 툴킷.

하나의 DSL(SSOT)로 게임 룰·전이 시스템을 기술하고, 여러 백엔드로 검증한다:
- RuleForge (Z3/BMC) — 논리 증명: 모순·도달성·불변식·데드락
- ProbForge (PRISM) — 확률 증명: 승리 확률 등 PCTL 속성

공유 DSL 프론트엔드(IR·로더·스키마)는 forge_core. 이 패키지는 통합 CLI 진입점
(check/bmc/prob)을 제공한다.
"""

__version__ = "0.0.1"
