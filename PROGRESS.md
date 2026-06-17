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
| Phase 2 | 전이 시스템 확장 (init·transitions·properties) | ✅ | 프론트엔드만(로더·스키마). 던전! 픽스처, 126건 |
| Phase 3 | RuleForge BMC 백엔드 (k 언롤링·도달성·불변식·데드락) | ✅ | 반례 경로·k-bound 명시. `ruleforge bmc`, 136건 |
| Phase 4 | `probforge` 스켈레톤 (IR → PRISM, PCTL 속성) | 🔵 | 모델 생성·게이트·CLI 완료. 실제 PRISM 실행 미검증(바이너리 부재) |
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
  report.py format은 Phase 1 범위 밖이라 미수정.) 커밋 b43e1dd(Phase 0)·acba78f(Phase 1).
- 2026-06-17: Phase 2 완료(전이 시스템 프론트엔드). IR에 Outcome·Transition·Property +
  RuleSet.init/transitions/properties 추가. 로더가 init/transitions(outcomes·bare then 정규화)/
  properties 파싱, 스키마가 next.* 참조 무결성(전이 then 한정)·전이/속성 dup id·init/property
  참조 검사. ProbForge용 유한 상태 게이트 check_finite_state()(validate와 분리). 던전!
  픽스처(tests/fixtures/dungeon.rule)·테스트 21건 추가(총 126건). CLAUDE.md §4.1에 전이
  시스템 DSL 문서화. 하위 호환 유지(번역기/검사기 미변경, 기존 정적 DSL·CLI 동일).
  BMC 검사는 Phase 3. 커밋 5f3733e.
- 2026-06-17: Phase 3 완료(RuleForge BMC 백엔드). decisions.md D15(프레임=미변경 유지,
  rules=상태 불변식, weight-erasure, 반복 심화). `ruleforge/solver/bmc.py` 신설 — 전이를
  k 스텝 언롤링, reachable(도달 경로)·invariant(위반 시퀀스)·no_deadlock 검사, action@i로
  전이 추적, k-bound 정직 보고. 번역기에 translate_expression 재사용 진입점, `next.X`는
  호출자가 Name 치환. CLI `ruleforge bmc <path> --k N`(종료코드 0/1/2/3). 던전!을
  examples/로 승격(+전투 보상 조정으로 작은 k 시연), README·examples/README 갱신. BMC
  테스트 9건(총 136). prob 속성은 ProbForge(Phase 4) 몫이라 건너뜀. (기존 ruff format
  드리프트 checks.py·report.py는 Phase 3 범위 밖이라 유지.) 커밋 965679e.
- 2026-06-17: Phase 4 부분 완료(ProbForge 스켈레톤). decisions.md D16(IR→PRISM 매핑).
  probforge/ 신설 — prism_gen.py(enum const·init+rules 인코딩·확률 명령·속성 매핑,
  유한 상태 게이트), runner.py(prism 발견·실행·파싱, 미설치 시 graceful). CLI
  `ruleforge prob`. 던전! prob spec을 PRISM 문법(Pmax/&/=)으로 정정. 테스트 10건+통합
  1건(skip, 총 146). **검증 범위: 모델 생성·게이트·오류·CLI graceful은 통과. 실제 PRISM
  실행(승리 확률 계산)은 바이너리 부재로 미검증** — 통합 테스트는 prism 있을 때만 실행.
  설치 스크립트 실행이 보안 가드로 차단됨 → 사용자 승인/설치 후 e2e 확인 필요.
