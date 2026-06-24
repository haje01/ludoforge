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

## 4차 마일스톤 — 정량 추정 백엔드 (Monte Carlo `sim/`) — ✅ 완료 (2026-06-24)

정량 백엔드 무게중심을 PRISM(증명)→Monte Carlo(추정)로 이동. PRISM은 소형 모델 교차검증
오라클로 유지. Phase 0~5 완료 — `ludoforge sim` 동작, PRISM 교차검증(추정↔증명 일치),
real·고차원 스케일 우위 실증. 계획·근거는 [PLAN.md](PLAN.md)·[decisions.md D19](docs/decisions.md).

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| Phase 0 | 범위 합의 & D19 기록, D13·D14 갱신/개정, CLAUDE.md 정련 | ✅ | 코드 변경 없음 |
| Phase 1 | sim 엔진 코어 (engine.py·평가기·DTMC 게이트·1 run 표집) | ✅ | D15 프레임 재사용, 테스트 13건 |
| Phase 2 | 집계 & 리포트 (Welford·히스토그램·rule-of-three·CI·sweep) | ✅ | distribution kind·흡수감지, 테스트 12건 |
| Phase 3 | runner & CLI (multiprocessing·SeedSequence·`ludoforge sim`) | ✅ | 워커 무관 재현성, 테스트 6건 |
| Phase 4 | PRISM 오라클 교차검증 (sim↔PRISM CI 내 일치 회귀) | ✅ | DTMC 던전판·constraints 파생, 테스트 3건 |
| Phase 5 | real·고차원 시연 (PRISM 거부 모델을 sim으로) | ✅ | market_sim(real 복리), 테스트 3건 |

4차 마일스톤 전체 197건 통과(sim 37 + PRISM 교차검증 실측 포함). ruff/mypy(strict) clean.

상태 범례: ⬜ 대기 / 🔵 진행중 / ✅ 완료 / ⚠️ 막힘

## 작업 로그
- 2026-06-24: 4차 마일스톤 Phase 5 완료 + 마일스톤 마감(real·고차원 시연). `examples/market_sim.rule`
  — 두 자산(gold·silver, real)을 30라운드 복리로 굴리는 다변수 연속 모델. PRISM은 real을
  유한상태 게이트(D13)에서 즉시 거부, sim은 표집으로 연속 분포 추정(평균 2.66·금 2배 84.9%·
  연속이라 백분위 생략 평균/CI만·불변식 0위반 rule of three). 테스트 3건(PRISM 거부·sim 추정·
  rule-of-three). test_corpus 기대표에 market_sim 추가. 전체 197건 통과. **4차 마일스톤(정량
  추정 백엔드) 완료** — Phase 0~5 끝. `ludoforge sim`으로 Monte Carlo 추정, PRISM 교차검증으로
  추정↔증명 일치 확립, real·고차원 스케일 우위 실증.
- 2026-06-24: 4차 마일스톤 Phase 4 완료(PRISM 오라클 교차검증). DTMC 던전판
  `examples/dungeon_sim.rule`(전략을 가드에 인코딩 → 결정적, win_gold는 클래스별 constraints
  파생). sim engine에 constraints 전파(initial_state — role→win_gold, PRISM init 인코딩 대응),
  sweep_configs가 constraint 파생 변수 제외. `distribution` kind를 BMC(skipped)·PRISM(continue)이
  건너뛰도록 수정(이전엔 BMC가 no_deadlock로 오인·PRISM은 에러). 교차검증 회귀(PRISM 4.10.1
  실측): role 고정 시 Pmax=정확값이 sim 95% CI에 포함(fighter 0.922·rogue 0.834·wizard 0.945,
  |Δ|<0.0022). 테스트 3건(constraints 파생·DTMC sweep·sim↔PRISM, prism 미설치 시 skip).
  test_corpus 기대표에 dungeon_sim 추가. 전체 193건 통과, ruff/mypy(strict) clean.
- 2026-06-24: 4차 마일스톤 Phase 3 완료(러너·병렬·CLI). aggregate를 RNG-무관 배치 단위로
  리팩터(BatchAggregate·run_batch·merge_batches·finalize_config; simulate는 직렬 참조 구현
  으로 유지). `sim/runner.py` — numpy SeedSequence([seed,ci]).spawn(청크수)로 청크별 독립
  스트림, multiprocessing.Pool 병렬, 청크 수 워커 무관(min(samples,64))·병합 청크 순서 고정
  → **워커 1↔N 비트 동일**. engine에 SupportsRandom Protocol(stdlib/numpy rng 공용), random
  import 제거. CLI `ludoforge sim`(-n/-H/-s/-w). numpy 의존성 추가(<2.2 핀 — 2.2+ 스텁 PEP695
  type이 mypy target 3.11 파싱 실패). 테스트 6건(청크 분할·재현성·워커무관·승률·CLI 동작/거부).
  전체 189건 통과, ruff/mypy(strict) clean. 향후 분산은 BatchAggregate.merge·pickle 가능한
  청크 task라 transport만 교체(Ray/dask/k8s).
- 2026-06-24: 4차 마일스톤 Phase 2 완료(집계·sweep·리포트). IR/loader/schema에 `kind:
  distribution`(+`expr` 수치식 필드, next.* 불가) 추가. `sim/aggregate.py` — 결합가능 집계
  ProportionAggregate(Wilson CI·rule-of-three)·DistributionAggregate(Welford+값빈도 백분위,
  _HIST_CAP 초과 시 평균만), `simulate`(sweep 설정별 N회 표집·체크별 집계). `sim/report.py`
  ("증명 아님" 라벨·CI·rule-of-three·절단 비율 한국어). engine에 sweep_configs(자유 enum/bool
  데카르트 곱)·initial_state overrides·**흡수(fixpoint) 상태 자연종료 감지**(절단 지표 정상화)·
  eval_expr 추가. DTMC 클래스밸런스 픽스처 arena.rule. 테스트 12건(통계·merge·sweep·승률
  추정 win³ 일치·rule-of-three·분포·재현성·리포트). Phase 1 동전 테스트 2건은 흡수감지 의미
  변경 반영해 갱신. 전체 183건 통과, sim/core/tests ruff/mypy(strict) clean. CLI(`ludoforge
  sim`)·multiprocessing은 Phase 3. 던전!은 MDP+win_gold(constraints 파생)라 sim 비대상 — DTMC
  던전판은 Phase 4 오라클로.
- 2026-06-23: 4차 마일스톤 Phase 1 완료(sim 엔진 코어). `sim/engine.py` 신설 — IR 전이
  시스템 인터프리터(가드 평가→DTMC 게이트(enabled>1 거부)→weight 표집→next.* 배정+프레임
  유지 D15), ast 화이트리스트 평가기(`eval` 미사용, enum=불투명 문자열), `run_once`(지평
  H까지/자연 종료까지, terminated/truncated 보고). DTMC 픽스처 coin.rule·비결정 픽스처
  nondet.rule 추가. 테스트 13건(평가기·초기상태·프레임·재현성·DTMC 거부). 던전!은 MDP+자유
  init이라 Phase 1 거부 대상(경계 문서화). pyproject에 `sim` 등록. 전체 171건 통과, sim/
  테스트 ruff/mypy(strict) clean(기존 범위 밖 docs/build_slides.py 드리프트는 미수정).
  재현성은 stdlib random.Random(seed) — Phase 3에서 numpy SeedSequence.spawn로 교체 예정.
- 2026-06-23: 4차 마일스톤(정량 추정) Phase 0 완료. 사용자가 PRISM 상태폭발 천장을 이유로
  정량 검증을 Monte Carlo 추정으로 전환 결정(4가지: PRISM=오라클 유지·DTMC만 허용·튜닝=
  목표 승격·로컬 mp+분산 구조). decisions.md D19 기록, D13(증명기)·D14(비목표 선) 갱신/개정.
  CLAUDE.md §1 개요·비목표·§4.1 checks kind(distribution)·§6 디렉토리(`sim/`) 정련.
  PLAN/PROGRESS에 4차 마일스톤 추가. 코드 변경 없음 — 사용자 비준 후 Phase 1 착수.
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
- 2026-06-24: **5차 마일스톤(sim 선택 확률) Phase 1 완료** — decisions.md D20 비준·확정.
  IR `Transition.pref: float | None = None`(플레이어 선택 상대 가중치, sim 전용·BMC/PRISM
  무시. None=미선언 — opt-in 안전망 위해 "1.0 선언"과 구분), loader `_parse_pref`(생략 None·
  음수/비수 거부·`for:`/`${expr}` 템플릿 타입 보존 호환), schema `_check_transition_prefs`
  (IR 직접 구성 시 음수 방어). pref 테스트 6건. 전체 203 통과(기존 197 무변경 = 하위 호환),
  ruff/format/mypy(strict) clean. 착수 중 D20 초안의 결정(1)"기본 1.0→균등"과 결정(3)"미선언
  시 거부" 모순을 발견 — None=미선언으로 정정(균등은 같은 pref 명시로 얻음).
- 2026-06-24: **Phase 2 완료(sim 엔진 선택 표집)** — `run_once`의 `len(enabled)>1` 분기를
  `_select_transition`으로 교체: enabled 1개면 rng 미소비(기존 DTMC 재현성·비트 동일 보존),
  2개+면 모든 전이 `pref` 보유 시 enabled끼리 정규화해 표집(2단 표집: 정책→outcome), 미선언
  혼재 시 `DtmcViolation`, 합 0이면 SimError. 골든 픽스처 policy_choice.rule(pref 0.3/0.7) →
  도달 분포 0.3 수렴(n=4000, |Δ|<0.03) + 재현성 + 혼재/합0/기존 nondet 거부, 테스트 5건.
  엔진 docstring D19→D20 갱신. 전체 207 통과, ruff/format/mypy clean. **리포트 라벨·예제는
  Phase 3.**
- 2026-06-24: **Phase 3 완료(리포트 정책 라벨 & 예제)** — `sim/engine.py uses_policy(ruleset)`
  (pref 선언 여부) + `SimReport.uses_policy`(runner·aggregate 두 생성 지점에서 채움), report에
  조건부 정책 라벨("주어진 정책(pref) 하의 추정 — 최적(Pmax) 아님 …하한"). 선택 없는 순수
  DTMC엔 미노출(오해 방지). 예제 `examples/dungeon_policy.rule`(던전 MDP+정책: 욕심 fight vs
  안전 leave를 pref 0.6/0.4로 가른 2단 표집 시연; sim은 보물 분포·전멸 위험 추정, bmc/prism은
  pref 무시). CLAUDE.md §4.1(pref 문법·예시·dialect)·concepts.md §9.4.1(무작위 정책)·
  examples/README·test_corpus 기대표 갱신. 테스트 3건(정책 라벨 노출/미노출/예제 동작).
  전체 211 통과, ruff/format/mypy clean. **5차 마일스톤 Phase 1~3 완료(핵심 기능 완성),
  Phase 4(민감도 sweep·PRISM 유도-DTMC 교차검증)는 선택.**
