# PROGRESS.md — RuleForge 진행 상태

> 새 에이전트는 [PLAN.md](PLAN.md)와 이 파일을 먼저 읽고 작업을 이어간다.
> 각 단계 완료 시 상태와 날짜를 갱신한다.

## 완료된 마일스톤 (기반)

| 마일스톤 | 내용 | 테스트 | 비고 |
|----------|------|--------|------|
| 1차 (수직 슬라이스) | LIA 수치 공식 + 조건부 룰 + enum, 3가지 모순 유형 | 61건 | git S0~S8, decisions D1~D5 |
| 2차 (표현력 확장) | bool/상호배제(D6)·실수 LRA(D7)·EnumSort(D8)·실수 끝점(D9)·`expect:`(D10) | 99건 | decisions D6~D10 |

정적 논리 검사기가 end-to-end 동작: `ruleforge check` → 로드 → 스키마·참조 검증 → Z3
번역 → 도달성 검사 → 한국어 리포트. ruff/format/mypy(strict) 통과. 상세 이력은 git
커밋과 [docs/decisions.md](docs/decisions.md) 참조.

## 현재 마일스톤: 다중 백엔드 (forge-core + RuleForge + ProbForge)

하나의 DSL을 SSOT로 두고 논리 증명(Z3/BMC)에 더해 확률 증명(PRISM)을 별도 백엔드로.
계획·근거·DSL 스케치는 [PLAN.md](PLAN.md) "현재 마일스톤" 참조. **Phase 0(범위 비준)부터
착수.** 각 Phase 착수 시 아래 표 상태를 갱신한다.

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| Phase 0 | 범위 합의 & decisions.md D11~ 기록, CLAUDE.md §1/§3 갱신안 | ✅ | D11~D14 기록, §1/§3 갱신. 사용자 비준 대기 |
| Phase 1 | `forge-core` 추출 (loader·schema·ir 공유 패키지화) | ✅ | 순수 리팩터, 105건 통과·mypy clean |
| Phase 2 | 전이 시스템 확장 (init·transitions·properties) | ⬜ | 던전! 미니 예제 |
| Phase 3 | RuleForge BMC 백엔드 (k 언롤링·도달성·불변식·데드락) | ⬜ | unsat-core·반례 시퀀스 |
| Phase 4 | `probforge` 스켈레톤 (IR → PRISM, PCTL 속성) | ⬜ | 유한 상태 강제 |
| Phase 5 | (선택) 저엄밀 export (Machinations/몬테카를로) | ⬜ | 증명 아님 라벨 |

상태 범례: ⬜ 대기 / 🔵 진행중 / ✅ 완료 / ⚠️ 막힘

## 작업 로그
- 2026-06-16: 1차 마일스톤 완료(S0~S8). 협업 패턴 문서화, 기획 모순 예제 모음(examples/).
- 2026-06-16: 2차 마일스톤 완료(D6~D10). bool/상호배제, 실수 LRA, enum EnumSort, 실수
  끝점 도달성, `expect:` 명시 단언. 테스트 99건.
- 2026-06-17: 다중 백엔드 아키텍처 계획 수립. PLAN/PROGRESS를 새 마일스톤으로 재작성
  (CI 통합 등 기존 후보는 PLAN "보류 중"으로 이동). 착수 전 — Phase 0부터.
- 2026-06-17: Phase 0 완료. decisions.md D11(다중 백엔드 계약)·D12(전이 시스템 의미)·
  D13(ProbForge=PRISM 증명기, 유한 상태)·D14(비목표 선 정련) 기록. CLAUDE.md §1 비목표
  정련 + §3 다중 백엔드 방향 주석 추가. 코드 변경 없음. 사용자 비준 후 Phase 1 착수.
- 2026-06-17: Phase 1 완료(순수 리팩터, 행위 불변). `ruleforge/dsl/`(ir·loader·schema)를
  공유 패키지 `forge_core/`로 git mv, import 경로 `ruleforge.dsl.*`→`forge_core.*` 일괄 갱신.
  pyproject(wheel packages·mypy files)·README 디렉토리 구성·`forge_core/__init__` docstring
  갱신. 검증: pytest 105건 통과, mypy clean, 만진 파일 ruff check/format clean, CLI
  엔드투엔드(정합 sat / 모순 unsat) 동일. (기존 ruff 위반 docs/build_slides.py·checks.py·
  report.py format은 Phase 1 범위 밖이라 미수정.)
