# PROGRESS.md — RuleForge 진행 상태

> 새 에이전트는 [PLAN.md](PLAN.md)와 이 파일을 먼저 읽고 작업을 이어간다.
> 각 단계 완료 시 상태와 날짜를 갱신한다.

## 현재 마일스톤: 1차 수직 슬라이스

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| S0 | 프로젝트 셋업 (pyproject, uv, ruff, mypy) | ✅ 완료 | 게이트 통과, CLI 골격 동작 |
| S1 | IR 데이터클래스 (`dsl/ir.py`) | ✅ 완료 | frozen Variable/Rule/RuleSet, 테스트 6건 |
| S2 | 로더 (`dsl/loader.py`) | ✅ 완료 | .rule→IR, 구조 파싱만, LoaderError 명시 |
| S3 | 스키마·참조 검증 (`dsl/schema.py`) | ✅ 완료 | 중복id·구문·미정의심볼·min>max, 오류 모아 보고 |
| S4 | 표현식 번역기 (`solver/translator.py`) | ⬜ 대기 | ast 화이트리스트 |
| S5 | 검사 로직 (`solver/checks.py`) | ⬜ 대기 | Optimize 도달성 |
| S6 | 리포터 (`solver/report.py`) | ⬜ 대기 | 한국어 |
| S7 | CLI (`cli.py`) | ⬜ 대기 | |
| S8 | 테스트 코퍼스 (`tests/fixtures/`) | ⬜ 대기 | |

상태 범례: ⬜ 대기 / 🔵 진행중 / ✅ 완료 / ⚠️ 막힘

## 작업 로그
- 2026-06-16: deep-interview로 1차 설계 결정 확정(D1~D4), PLAN.md/PROGRESS.md 작성.
- 2026-06-16: S0 완료 — pyproject.toml(uv, z3/pyyaml/typer, ruff/mypy strict), 패키지 골격(dsl/solver/cli), 스모크 테스트 3건, `ruleforge check` CLI 골격. pytest/ruff/mypy 모두 통과.
- 2026-06-16: S1 완료 — IR(frozen Variable/Rule/RuleSet, `RuleSet.variable()` 조회). TDD(Red→Green), 테스트 6건. 전체 게이트 통과.
- 2026-06-16: S2 완료 — 로더(.rule YAML→IR). 구조 파싱만 담당(참조 무결성은 S3), 실패 시 파일/필드 명시 LoaderError. 픽스처 warrior_hp.rule, 테스트 6건. 전체 게이트 통과.
- 2026-06-16: S3 완료 — 스키마·참조 검증. 중복 rule id, 표현식 구문오류, 미정의 심볼 참조(ast Name 추출), int min>max 검사. 모든 오류를 모아 SchemaError로 보고. 순환의존은 현 DSL상 비해당. 테스트 7건. 전체 게이트 통과.
