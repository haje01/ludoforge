# PROGRESS.md — Ludoforge 진행 상태

> 새 에이전트는 [PLAN.md](PLAN.md)와 이 파일을 먼저 읽고 작업을 이어간다.
> 각 단계 완료 시 상태와 날짜를 갱신한다.
>
> **명명 규약 갱신 (2026-06-17):** 디렉토리 `ruleforge/→logic/`, `probforge/→prob/`,
> `forge_core/→core/`; 브랜드명 **RuleForge/ProbForge**는 **'논리 백엔드'/'확률 백엔드'**로
> 통일(우산 CLI `ludoforge` 서브명령으로만 노출). 이하 과거 로그의 옛 이름·경로는
> 그 시점의 사실을 보존한 역사적 표기다.

## 완료된 마일스톤 (기반)

| 마일스톤 | 내용 | 테스트 | 비고 |
|----------|------|--------|------|
| 1차 (수직 슬라이스) | LIA 수치 공식 + 조건부 룰 + enum, 3가지 모순 유형 | 61건 | git S0~S8, decisions D1~D5 |
| 2차 (표현력 확장) | bool/상호배제(D6)·실수 LRA(D7)·EnumSort(D8)·실수 끝점(D9)·`expect:`(D10) | 99건 | decisions D6~D10 |

정적 논리 검사기가 end-to-end 동작: `ludoforge check` → 로드 → 스키마·참조 검증 → Z3
번역 → 도달성 검사 → 한국어 리포트. ruff/format/mypy(strict) 통과. 상세 이력은 git
커밋과 [docs/decisions.md](docs/decisions.md) 참조.

## 다중 백엔드 마일스톤 — ✅ 완료·마감 (2026-06-17)

하나의 DSL(SSOT) 위에 논리 증명(Z3/BMC)과 확률 증명(PRISM)을 두 백엔드로. Phase 0~4
완료, e2e 검증(던전! 승리 확률 1.0). **Phase 5(저엄밀 export)는 생략하고 마감.** 계획·
근거는 [PLAN.md](PLAN.md), 배경·용어는 [docs/concepts.md §8](docs/concepts.md).

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| Phase 0 | 범위 합의 & decisions.md D11~ 기록, CLAUDE.md §1/§3 갱신 | ✅ | D11~D14 기록 |
| Phase 1 | `forge_core` 추출 (loader·schema·ir 공유 패키지화) | ✅ | 순수 리팩터 |
| Phase 2 | 전이 시스템 확장 (init·transitions·checks) | ✅ | 프론트엔드(로더·스키마)·던전! 픽스처 |
| Phase 3 | RuleForge BMC 백엔드 (k 언롤링·도달성·불변식·데드락) | ✅ | 반례 경로·k-bound, `ludoforge bmc` |
| Phase 4 | ProbForge (IR → PRISM, PCTL 속성) | ✅ | PRISM 4.8.1 e2e 검증, `ludoforge prob` |
| Phase 5 | (선택) 저엄밀 export (Machinations/몬테카를로) | ⬜ | **생략(마일스톤 마감)** |

전체 테스트 146 + PRISM 통합 1 = 147. ruff/mypy(strict) clean.

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
- 2026-06-17: Phase 2 완료(전이 시스템 프론트엔드). IR에 Outcome·Transition·Check +
  RuleSet.init/transitions/checks 추가. 로더가 init/transitions(outcomes·bare then 정규화)/
  checks 파싱, 스키마가 next.* 참조 무결성(전이 then 한정)·전이/속성 dup id·init/property
  참조 검사. ProbForge용 유한 상태 게이트 check_finite_state()(validate와 분리). 던전!
  픽스처(tests/fixtures/dungeon.rule)·테스트 21건 추가(총 126건). CLAUDE.md §4.1에 전이
  시스템 DSL 문서화. 하위 호환 유지(번역기/검사기 미변경, 기존 정적 DSL·CLI 동일).
  BMC 검사는 Phase 3. 커밋 5f3733e.
- 2026-06-17: Phase 3 완료(RuleForge BMC 백엔드). decisions.md D15(프레임=미변경 유지,
  constraints=상태 불변식, weight-erasure, 반복 심화). `ruleforge/solver/bmc.py` 신설 — 전이를
  k 스텝 언롤링, reachable(도달 경로)·invariant(위반 시퀀스)·no_deadlock 검사, action@i로
  전이 추적, k-bound 정직 보고. 번역기에 translate_expression 재사용 진입점, `next.X`는
  호출자가 Name 치환. CLI `ludoforge bmc <path> --k N`(종료코드 0/1/2/3). 던전!을
  examples/로 승격(+전투 보상 조정으로 작은 k 시연), README·examples/README 갱신. BMC
  테스트 9건(총 136). prob 속성은 ProbForge(Phase 4) 몫이라 건너뜀. (기존 ruff format
  드리프트 checks.py·report.py는 Phase 3 범위 밖이라 유지.) 커밋 965679e.
- 2026-06-17: Phase 4 부분 완료(ProbForge 스켈레톤). decisions.md D16(IR→PRISM 매핑).
  probforge/ 신설 — prism_gen.py(enum const·init+constraints 인코딩·확률 명령·속성 매핑,
  유한 상태 게이트), runner.py(prism 발견·실행·파싱, 미설치 시 graceful). CLI
  `ludoforge prob`. 던전! prob spec을 PRISM 문법(Pmax/&/=)으로 정정. 테스트 10건+통합
  1건(skip, 총 146). 모델 생성·게이트·오류·CLI graceful 통과. 커밋 6afca9c.
- 2026-06-17: Phase 4 e2e 검증 완료(사용자가 PRISM 4.8.1 설치). 던전!에서 Pmax/Pmin이
  실제 계산됨(승리 확률 Pmax [F win] = 1.0). 실행 중 발견·수정: ① 상태 폭발 — gold
  [0..30000]→[0..20] 축약 + 전투 상한 가드(BMC 무영향, k 스텝만 펼침), ② prob spec
  `Pmax>=0.95`→쿼리형 `Pmax=?`(PRISM이 바운드형 거부). 통합 테스트
  (test_prism_computes_results_when_available)가 PRISM 지정 시 통과. 전체 146 + 통합 1 =
  147. **다중 백엔드(Z3 BMC + PRISM)가 하나의 DSL에서 동작 확인 — 마일스톤 핵심 검증.**
- 2026-06-17: 다중 백엔드 마일스톤 **마감**(Phase 5 생략). 신규 도입 전수 지식을
  docs/concepts.md §8(전이 시스템·BMC·ProbForge·다중 백엔드·새 용어)에 기록. README(소개·
  마일스톤 노트), CLAUDE.md §3(구현됨 반영), PLAN/PROGRESS 갱신. 코드 변경 없음(문서만).
- 2026-06-17: 프로젝트 **Ludoforge로 리네이밍**. 우산 패키지 `ludoforge/`(통합 CLI
  check/bmc/prob·버전) 신설, `ruleforge/cli.py`→`ludoforge/cli.py` 이동. 백엔드명
  RuleForge(Z3/BMC)·ProbForge(PRISM)·코어 forge_core는 유지. pyproject(name·script·
  packages·mypy), 콘솔 명령 `ruleforge`→`ludoforge`, 문서 전반(제목·소개·명령어·CLAUDE §6
  디렉토리 구조)·슬라이드 갱신. GitHub URL(haje01/ruleforge)은 리포명이라 유지(개명 시 갱신).
  검증: 146 통과, mypy/ruff clean, `ludoforge` CLI 동작.
- 2026-06-17: **백엔드/코어 디렉토리 리네임 + 브랜드명 통일**. 우산 통합 후 사용자에게
  혼란을 주던 `RuleForge`/`ProbForge` 브랜드를 폐기 — `ruleforge/→logic/`,
  `probforge/→prob/`, `forge_core/→core/`로 git mv, import·`ProbForgeError`→`ProbError`·
  주석·리포트 문자열을 "논리 백엔드/확률 백엔드"로 통일. 정리 중 발견: 직전 커밋이
  리네임을 절반만 해 옛/새 디렉토리가 HEAD에 중복 존재(코드는 옛것 import)했고 venv가
  옛 경로에서 생성돼 깨져 있었음 — 둘 다 해소. 역사 문서(decisions/PLAN/PROGRESS)는 본문
  보존+상단 노트. GitHub 저장소 개명에 맞춰 URL을 `haje01/ludoforge`로 갱신(README·
  build_slides). 검증: 147 통과, mypy/ruff clean, check/bmc/prob CLI 동작.
