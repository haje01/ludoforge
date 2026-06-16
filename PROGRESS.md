# PROGRESS.md — RuleForge 진행 상태

> 새 에이전트는 [PLAN.md](PLAN.md)와 이 파일을 먼저 읽고 작업을 이어간다.
> 각 단계 완료 시 상태와 날짜를 갱신한다.

## 현재 마일스톤: 1차 수직 슬라이스

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| S0 | 프로젝트 셋업 (pyproject, uv, ruff, mypy) | ✅ 완료 | 게이트 통과, CLI 골격 동작 |
| S1 | IR 데이터클래스 (`dsl/ir.py`) | ⬜ 대기 | |
| S2 | 로더 (`dsl/loader.py`) | ⬜ 대기 | |
| S3 | 스키마·참조 검증 (`dsl/schema.py`) | ⬜ 대기 | |
| S4 | 표현식 번역기 (`solver/translator.py`) | ⬜ 대기 | ast 화이트리스트 |
| S5 | 검사 로직 (`solver/checks.py`) | ⬜ 대기 | Optimize 도달성 |
| S6 | 리포터 (`solver/report.py`) | ⬜ 대기 | 한국어 |
| S7 | CLI (`cli.py`) | ⬜ 대기 | |
| S8 | 테스트 코퍼스 (`tests/fixtures/`) | ⬜ 대기 | |

상태 범례: ⬜ 대기 / 🔵 진행중 / ✅ 완료 / ⚠️ 막힘

## 작업 로그
- 2026-06-16: deep-interview로 1차 설계 결정 확정(D1~D4), PLAN.md/PROGRESS.md 작성.
- 2026-06-16: S0 완료 — pyproject.toml(uv, z3/pyyaml/typer, ruff/mypy strict), 패키지 골격(dsl/solver/cli), 스모크 테스트 3건, `ruleforge check` CLI 골격. pytest/ruff/mypy 모두 통과.
