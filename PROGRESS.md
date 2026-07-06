# PROGRESS.md — Ludoforge 진행 상태

> 새 에이전트는 [PLAN.md](PLAN.md)와 이 파일을 먼저 읽고 작업을 이어간다.
> 각 단계 완료 시 상태와 날짜를 갱신한다.
> **상세 이력은 git 커밋과 [docs/decisions.md](docs/decisions.md)에 있다** — 이 파일은
> 현재 활성 마일스톤에 집중하고, 완료분은 요약 표로만 남긴다(2026-06-25 리셋).

## 완료된 마일스톤 (기반 — 상세는 git·decisions.md)

| 마일스톤 | 핵심 | 누적 테스트 | decisions |
|----------|------|-----------|-----------|
| 1차 (수직 슬라이스) | LIA 수치·조건부 룰·enum, 정적 모순 검사 `ludoforge check` | 61 | D1~D5 |
| 2차 (표현력) | bool/상호배제·real LRA·EnumSort·실수 끝점·`expect:` | 99 | D6~D10 |
| 다중 백엔드 | 공유 IR(`core`) + Z3/BMC(`ludoforge bmc`) + PRISM(`ludoforge prob`)·우산 CLI·리네임 | 147 | D11~D17 |
| 템플릿 | `for:`/`${expr}`/`tables:` desugar | — | D18 |
| 4차 (정량 추정) | Monte Carlo 시뮬레이터(`ludoforge sim`), PRISM=교차검증 오라클 | 197 | D19 |
| 5차 (sim 정책) | `pref` 무작위 정책(2단 표집), 정책 라벨 | 211 | D20 |

기반 전체 211건 통과(2026-06-24). ruff/format/mypy(strict) clean. 네 경로
(`check`/`bmc`/`prob`/`sim`)가 하나의 DSL(SSOT) 위에서 동작.

## 6차 마일스톤 — 외부 DSL(자체 문법) — ✅ 완료 (2026-06-25)

YAML→자체 문법(Lark) **표면 언어 승격** + `=`(대입)/`==`(비교) 분리. IR은 불변(AST→기존
IR lowering) → 백엔드·결정론 경계 **무회귀**. 계획·문법 초안은 [PLAN.md 6차](PLAN.md),
근거는 [decisions.md D21](docs/decisions.md).

> **구현 방식:** PLAN의 Phase 1(파서)·Phase 2(lowering)를 **얇은 수직 슬라이스**로 합쳐
> 진행한다(D1 선례) — domain → 정적식 → 전이 → checks → 템플릿. 각 슬라이스는 기존 IR과
> **골든 등가 테스트**로 고정한다. YAML 로더는 골든 등가(S6)가 통과할 때까지 병행 유지.

| 슬라이스 | 내용 | 상태 | 비고 |
|----------|------|------|------|
| S1 domain | `domain {}` int/real/bool/enum → `Variable` IR | ✅ | Lark 인프라·골든 등가, 테스트 11건 |
| S2 정적식 | `init`·`constraints`·`expects` (`==` 술어, 표현식 문자열 lowering) | ✅ | 표현식 문법·ast 골든 비교, 테스트 12건 |
| S3 전이 | `transitions`·`outcomes`·`=`/`==`·`;` 다중대입·프레임(D15) | ✅ | **핵심(D21 의미론)**, 골든 등가, 테스트 8건 |
| S4 checks | `reachable`/`invariant`/`no_deadlock`/`prob`/`distribution` | ✅ | dialect 분리 보존, 골든 등가, 테스트 6건 |
| S5 템플릿 | `for`/`${}`/`table` desugar → 구체 항목 | ✅ | D18 등가(트리 확장 패스), 골든 등가, 테스트 6건 |
| S6 골든·이관 | 코퍼스 양포맷 IR 등가, 에러 리포트 정련, 예제 이관, YAML 디프리케이트 | ✅ | desc/author·`.lf` 디스패치·CLI e2e·**전 예제(14) 이관**·source 추적·YAML 경고·문서. 남은 도구화(LSP/하이라이트)는 후속 |

상태 범례: ⬜ 대기 / 🔵 진행중 / ✅ 완료 / ⚠️ 막힘

## 7차 마일스톤 — 구조 단순화(PRISM 격하 + 던전 통합) — ✅ 완료 (2026-06-26)

PRISM을 사용자 표면에서 내려 테스트 전용 오라클로 격하(D23) + 던전 예제 통합. 계획은
[PLAN.md 7차](PLAN.md), 근거는 [decisions.md D23](docs/decisions.md). `market_sim`은 최소 보존.

| Phase | 내용 | 상태 | 비고 |
|-------|------|------|------|
| P1 표면 제거 | DSL `kind: prob`/`spec`·`ludoforge prob` 제거, prism_gen prob 분기 제거 | ✅ | 오라클(reachable→Pmax)·prob/ 보존 |
| P2 오라클 픽스처화 | `dungeon_sim` → `tests/fixtures/oracle_dungeon.lf` | ✅ | 골든 `.rule` 삭제, 오라클 회귀 통과(PRISM 실측) |
| P3 던전 통합 | 단일 `dungeon.lf`(클래스밸런스+pref), 4→2(+market_sim) | ✅ | bmc 9검사✅·sim 4직업 sweep·골든 등가 유지 |
| P4 문서 정합 | CLAUDE·concepts·README·D13/16/19 주석 | ✅ | 라이브 문서·코드 메시지 prob 표면 제거 |

## 8차 마일스톤 — BMC k-귀납(무한 지평 증명 승격) — ✅ 완료 (2026-07-02)

표현력 확장 아크(8차 k-귀납 → 9차 상태 의존 pref/weight → 10차 플레이어 태그 → 11차
배열/컬렉션, 북극성 = Dungeon! 2~4인 레이스판)의 첫 마일스톤. 계획은 [PLAN.md 8차](PLAN.md),
근거는 [decisions.md D25](docs/decisions.md).

| Phase | 내용 | 상태 | 비고 |
|-------|------|------|------|
| P0 D25 기록·비준 | 설계 + `unreachable`→종료코드 1 승격 비준 | ✅ | 2026-07-02 사용자 비준 |
| P1 솔버 매개화 | `_solver_to_depth`→`_solver_span(anchored)` | ✅ | 순수 리팩터, 행위 불변 |
| P2 invariant 귀납 | base 통과 후 스텝 검사 → `holds`(최소 j 보고) | ✅ | 던전 불변식 3종 증명 승격, 픽스처 `bmc_induction.lf` |
| P3 no_deadlock·reachable | `no_deadlock` 증명·`unreachable` 확정(종료코드 1) | ✅ | 던전 no_stuck 증명(j=0), 건전성 회귀(도달 가능이면 귀납 실패) |
| P4 리포트·문서 | 텍스트/HTML 라벨, CLAUDE §4.1·concepts·README | ✅ | 증명/유계 구분 명시, README 낡은 prob 서술 정정 |

P5(distinct-state 강화)는 보류 — 트리거: 실전에서 "참인데 비귀납" 반복 관측 시.

## 9차 마일스톤 — 상태 의존 pref/weight(런타임 식) — ✅ 완료 (2026-07-02)

`pref`(D20)·outcome `weight`(D12)에 현재 상태의 식을 허용(D26) — 적응적 정책과 비복원
추출이 표현된다. 계획은 [PLAN.md 9차](PLAN.md), 근거는 [decisions.md D26](docs/decisions.md).

| Phase | 내용 | 상태 | 비고 |
|-------|------|------|------|
| P0 D26 기록·비준 | enabledness=가드 단독·BMC 과근사 수용·`.lf` 전용 | ✅ | 2026-07-02 사용자 비준 |
| P1+P2 프론트엔드+sim | 문법/IR `float\|str`/schema + 엔진 런타임 평가 | ✅ | 수직 슬라이스(6차 선례). 골든: `urn.lf`(닫힌형 2/3)·`policy_adaptive.lf`(0.3) |
| P3 PRISM 오라클 | 비율형 `(w_i)/(Σw)` 렌더 + urn 교차검증 | ✅ | PRISM 정확값 ∈ sim CI(D19 DNA). BMC erasure 무회귀 |
| P4 북극성 1단계 | 던전 2층 몬스터 덱(비복원)+적응 욕심 pref + 문서 | ✅ | bmc 9검사 지위 불변(k-귀납 증명 유지)·min/max 요율 허용. 이관 골든은 old_examples 스냅샷으로 동결 |

## 10차 마일스톤 — 플레이어 태그(전이 소유·다인 게임 입구) — ✅ 완료 (2026-07-02)

전이에 `player` 소유 태그(D27) — sim이 선택 집합의 소유 일관성을 검증하고 BMC/PRISM은
무시(주석). 계획은 [PLAN.md 10차](PLAN.md), 근거는 [decisions.md D27](docs/decisions.md).

| Phase | 내용 | 상태 | 비고 |
|-------|------|------|------|
| P0 D27 기록·비준 | 소유 선언(스케줄러 아님)·혼성 거부·enum 값 게이트 | ✅ | 2026-07-02 사용자 비준 |
| P1+P2 태그+소유 게이트 | `.lf` `player` 절·IR·schema + sim 혼성 co-enabled 거부·정책 라벨 플레이어 명시 | ✅ | 수직 슬라이스. YAML은 명시 거부(.lf 전용). 기존 모델 무회귀 |
| P3 북극성 2단계 | `dungeon_race.lf`(2인 레이스: 턴 교대·공유 덱·비대칭 정책) + 문서 | ✅ | bmc: p1 깊이11/p2 깊이12·불변식/데드락 k-귀납 증명. sim: 욕심 67% vs 안전 33%. 수동 복제 부피가 11차(배열) 동기 시연 |

## 11차 마일스톤 — 배열/인덱스 변수(유한 색인 스칼라 가족) — ✅ 완료 (2026-07-02)

배열 선언·색인 식을 순수 desugar(스칼라 가족)로 도입(D28) — IR·백엔드 무변경. 계획은
[PLAN.md 11차](PLAN.md), 근거는 [decisions.md D28](docs/decisions.md).

| Phase | 내용 | 상태 | 비고 |
|-------|------|------|------|
| P0 D28 기록·비준 | 유한 색인 경계 게이트·순수 desugar·동적 색인 읽기 전용 | ✅ | 2026-07-02 사용자 비준 |
| P1 선언·정적 색인 | `gold[p1,p2]:` 선언 펼침·식/효과 LHS 색인 해소·충돌 거부 | ✅ | 배열판·수동판 IR 등가 골든 |
| P2 레이스 접기 | dungeon_race를 배열+템플릿 한 벌로(북극성 3단계) | ✅ | 수동판 골든(race_manual.lf)과 IR 등가 영구 증명. bmc/sim 무변경 |
| P3 동적 색인(읽기) | `arr[enum변수]` → 유한 IfExp — sim/Z3/PRISM 지원 | ✅ | dyn_index 오라클 일치(PRISM 정확값 ∈ sim CI). LHS는 명시 거부 |
| P4 문서·아크 마감 | CLAUDE §4.3·concepts·README·보류 항목 정리 | ✅ | 표현력 확장 아크(8~11차) 종결 |

### 표현력 확장 아크(8~11차) 마감 요약 (2026-07-02)

진단("복잡한 보드게임·온라인 게임으로 가는 세 개의 벽") 이후 한 아크로 진행:
**8차** k-귀납(무한 지평 증명, D25) → **9차** 상태 의존 pref/weight(적응 정책·비복원 추출,
D26) → **10차** 플레이어 태그(다인 소유·혼성 거부, D27) → **11차** 배열(개체별 상태 접기,
D28). 북극성(Dungeon! 2인 레이스판)은 `dungeon_race.lf`로 완성 — 배열×템플릿×정책 표×
공유 덱×소유 태그가 한 모델에서 합주하고, bmc(증명)와 sim(추정)이 같은 모델에 다른
질문을 던진다. 다음 후보는 PLAN "보류 중"(모노폴리-미니 스트레스 테스트·LHS 동적 색인·
한정자 init 등 — 각자 트리거 명시).

## 규칙서 SSOT 아크 (12~14차) — 🔵 진행중 (12차 착수 2026-07-06)

`.lf`를 기획자·개발자가 읽는 게임 규칙 SSOT 문서로 승격하되 검증·추정 부하는 유지하는
아크 — **12차** 문서 메타데이터(`note`/`ref`/`tag`/`section`)+`ludoforge doc` 규칙서
생성기(D29) → **13차** 주사위 확률식 `chance`/`rest` desugar(D30 후보) → **14차**
`ghost` 서술 변수+`erase_ghosts`(D31 후보). 계획 상세는 [PLAN.md](PLAN.md) 해당 절.

### 12차 마일스톤 — 문서 메타데이터 + 규칙서 생성기 (D29) — ✅ 완료 (2026-07-06)

| Phase | 내용 | 상태 | 비고 |
|-------|------|------|------|
| P0 D29 기록·비준 | `.lf` 전용·Doc passthrough·desugar 전 트리 docgen·`[[이름]]` 게이트 | ✅ | 2026-07-06 사용자 비준 |
| P1 문법·IR·참조 게이트 | note/ref/tag/section·변수/table desc 문법 + IR `Doc` + `[[..]]` 무결성 | ✅ | 골든 무회귀(전체 358 통과)·bmc/sim 무변경·테스트 7건 |
| P2 docgen+CLI | `core/docgen.py` + `ludoforge doc`(HTML/MD, 접힌 템플릿 렌더) | ✅ | desugar 전 트리·원문 슬라이스·[[..]] 앵커 링크·check 모음. 테스트 9건, 전체 367 통과 |
| P3 예제 저술·문서 정합 | dungeon.lf·dungeon_race.lf 저술 + CLAUDE §4·README | ✅ | section·note·ref 저술(형식부 불변 — bmc/sim 무회귀), CLAUDE §4.4 신설, race 골든 compare_meta 정련 |

### 13차 마일스톤 — 주사위 확률식 `chance`/`rest` (D30) — ✅ 완료 (2026-07-06)

| Phase | 내용 | 상태 | 비고 |
|-------|------|------|------|
| P0 D30 기록·비준 | 문법·상수 목표값 한정·예제 수치 변동 수용·pref 불허 | ✅ | 2026-07-06 사용자 비준 |
| P1 문법+desugar | DICE 토큰·chance/rest·Fraction 콘볼루션 → float lowering | ✅ | 손 계산 골든·거부 게이트 5종, 테스트 10건 |
| P2 예제·오라클 | dungeon 전투 beat/fumble 표 재저술 + dice_fight 오라클 | ✅ | bmc 지위 불변·PRISM 실측 교차검증 통과·규칙서에 주사위 원형 노출 |

**다음 = 14차(ghost 서술 변수) P0 비준.**

| 마일스톤 | 내용 | 상태 |
|----------|------|------|
| 14차 ghost 서술 변수 | 단방향 의존 게이트·bmc/PRISM은 erase·sim만 실행 | ⬜ P0 비준 대기 |

## 작업 로그
- 2026-07-06: **13차 완료 — 주사위 확률식 chance/rest(D30, P0~P2).** ① 문법: outcome
  weight 자리에 `chance(NdM CMP 상수)` | `rest`(DICE 전용 토큰 — chance 괄호 안에서만
  기대돼 렉서 충돌 없음). pref 위치는 문법 차원 거부. ② desugar: NdM 분포를 Fraction
  콘볼루션으로 정확 계산 → 술어 확률 → 기존 float weight lowering(IR·백엔드 불변, D18
  계보). `rest` = 1 − 같은 블록 상수 가중치 합(십진도 Fraction 정확 — D18의 ${1-win-death}
  보류 해소). 게이트: 합>1·rest 중복·상태 의존 목표·상태 식 weight 혼합·주사위 범위
  (n×m≤10000) 거부. ③ dungeon.lf 전투 재저술 — 승률 매직 넘버 표 3개(win/miss/death 24칸)
  → 룰북 원형 표 2개(beat 격파 목표값·fumble 치명 문턱) + chance/rest. bmc 9검사 지위
  불변(도달 깊이·k-귀납 증명 유지), 전투 가중치는 2d6 격자로 이동(33/36 등 — 비준된 수치
  변동). note의 [[win]]/[[death]] 참조가 표 삭제로 깨진 것을 **참조 게이트가 잡아** 수정
  (D29 드리프트 억제의 실증). ④ 오라클: `tests/fixtures/dice_fight.lf` — PRISM 정확값
  10/36 = 닫힌형 = sim 95% CI 포함, **PRISM 4.10.1 실측 통과**(D19 DNA). ⑤ 문서: CLAUDE
  §4.1 D30 절·§4.2 잔여 해소 주석, examples README, docgen 테스트에 주사위 원형 렌더 단언.
  전체 378 통과, ruff/format/mypy(strict) clean. **다음 = 14차(ghost) P0 비준.**
- 2026-07-06: **12차 P3 완료 — 12차 마일스톤 마감(예제 저술·문서 정합, D29).**
  ① `examples/dungeon.lf` 저술 — section 5개(게임 개요/직업과 목표/전투 데이터/게임의
  흐름/전투), 전 변수 desc(용어집), 표 4개 desc, 규칙 note(승리 조건·비복원 덱·적응 욕심·
  전투 2d6 환산 — **실물 규칙의 단순화도 명시**: 무소득=조우 종료·재도전 없음), 룰북 ref·
  tag. 헤더 `//` 주석은 모델링 노트(도구 문맥)만 남김. ② `examples/dungeon_race.lf` 동일
  저술(레이스 개요/정책 표/턴과 행동 + 공유 덱 자원 경쟁 note). **형식부(가드·효과·수치)
  불변** — bmc k-귀납 증명 지위·sim 결과(욕심 ~68%) 무변경. ③ race 접힘 골든을
  `_assert_ir_equiv(compare_meta=False)`로 정련 — 문서 절은 desugar 등가의 증명 대상이
  아니므로 형식부만 비교(PLAN 12차 위험 "명시적 제외 목록"의 이행). frozen 스냅샷
  (old_examples) 쌍 하니스는 desc까지 비교 유지(이관 충실성). ④ 문서: CLAUDE §4.4 신설
  (D29 — 문서 절·[[이름]] 게이트·doc 생성)·§6(docgen.py·cli doc), README(기능 bullet·
  "규칙서 생성 (doc)" 섹션·디렉토리), examples README. 전체 367 통과, ruff/format/mypy
  clean. **12차 완료 — 다음 = 13차(주사위 확률식) P0 비준.**
- 2026-07-06: **12차 P2 완료(규칙서 생성기, D29 핵심).** ① `core/text_loader.py`에
  `parse_doc_tree(src)` 공개 — desugar *전* 파스 트리(위치 보존, `propagate_positions=True`)
  를 돌려주고 parse_rule_text가 파싱 단계를 이것으로 공유(중복 제거). ② `core/docgen.py`
  신설 — 트리→문서 모델(VarEntry/TableEntry/RuleEntry/Section)→Markdown·자체 완결 HTML
  렌더. 접힌 for 템플릿(펼치지 않고 바인딩 표기 "mon ∈ {…} × cls ∈ {…}"), 2단 표→행렬,
  가드/효과/pref/outcomes는 **원문 위치 슬라이스**(재포매팅 없음 — 래퍼 노드가 키워드를
  포함해 자식 식 노드를 자름, 개행은 한 칸으로 접음), `[[이름]]`은 앵커 있는 이름만 링크
  (enum 값 등은 용어 스타일 — 죽은 링크 방지), check는 본문에서 빼내 맨 끝 "검증·추정
  성질" 절(기계 확인 라벨 — 규칙서 차별점). 비결정 요소 없음(같은 입력=같은 출력).
  ③ `ludoforge doc <path> [-o] [--md]` — `.lf` 전용(YAML 거부), 생성 전 load+validate
  +참조 게이트 통과 요구(깨진 모델 거부, exit 2), 기본 출력 `<입력>.doc.html`.
  테스트 9건(tests/test_docgen.py — 구조 단언: 절 분리·접힘·행렬·링크·자체완결·결정론·
  CLI e2e). 전체 367 통과, ruff/format/mypy(strict) clean. 다음=P3(예제 저술·문서 정합).
- 2026-07-06: **규칙서 SSOT 아크(12~14차) 계획 수립 + 12차 P0·P1 완료(D29).** 진단(형식화
  손실/서술 손실) 후 3개 마일스톤 계획을 PLAN에 기록, D29 비준. **P1 구현:** ① `.lf` 문서
  절 문법 — 선언 몸통 `note`(반복 허용)·`ref`·`tag`, domain 변수·table `desc`, 최상위
  `section`(신규 키워드 7종 코퍼스 충돌 없음 실측). ② IR passthrough — frozen `Doc(notes,
  ref, tags)` + 선언 4종에 `doc: Doc | None`, `Variable.desc`(기본 None → 골든 무회귀,
  백엔드 무시 = "지워지는 주석" 계보). section·table desc는 IR 미탑재(문서 전용 — P2
  docgen이 desugar 전 트리 소비). ③ `[[이름]]` 참조 게이트 — note/desc(변수·table desc·
  section 제목 포함)의 미정의 참조를 선언·필드 짚어 로드 거부(`ref`는 외부 출처라 제외).
  var_decl 헬퍼들을 위치 기반→노드 종류 기반으로 리팩터(v_desc가 자식 수를 바꿈), 배열
  desc는 펼친 원소에 승계, for 템플릿 안 note의 `${}` 보간 동작(id와 동일 경로). 테스트
  7건(round-trip·기본값 None·IR 무흔적·게이트 거부 3종·템플릿 보간). 전체 358 통과,
  ruff/format/mypy(strict) clean, bmc/sim e2e 무변경(doc 스모크 포함). 다음=P2(docgen+CLI).
- 2026-06-25: **6차 마일스톤 착수.** PLAN.md 6차·decisions.md D21·CLAUDE.md §4/§5 동기화
  완료(외부 DSL·`=`/`==` 분리). PROGRESS를 리셋(이전 상세 로그는 git 이력으로, 기반
  마일스톤은 요약 표로 압축).
- 2026-06-25: **S1(domain) 완료.** `lark>=1.1` 의존성 추가(py.typed → mypy strict 호환).
  `core/text_loader.py` 신설 — Lark 문법 + Transformer로 `domain { ... }` 블록을 기존
  `Variable` IR로 lowering. int/real/bool/enum 및 단일 경계(`int 0..`)·무경계·줄 주석(`//`)
  지원. `RANGENUM`(소수점 뒤 숫자 강제)으로 `0..30`의 float 잠식 차단. int 경계 소수점 거부·
  구문 오류는 줄·열과 함께 `TextLoaderError`. 골든 등가 테스트(YAML↔자체 동일 `Variable`
  튜플). 테스트 11건. 전체 222건 통과(기존 211 무변경 = 회귀 없음), ruff/format/mypy(strict)
  clean. 다음=S2(정적 표현식 — 표현식 문자열을 ast 재파싱해 골든 비교).
- 2026-06-25: **S2(정적식) 완료.** `text_loader`에 표현식 문법 추가 — `and`/`or`/`not`·비교
  (`CMP: ==|!=|<=|>=|<|>`)·산술(`+ - * /`·단항 `-`)·괄호·이름·수, LALR 우선순위 계층. 표현식을
  **파이썬-식 문자열로 lowering**해 기존 IR(`Constraint.then`·`when`, `Expect.that`, `init`)에
  넣는다(다운스트림 ast 평가기·Z3 번역기 재사용, §7). `init`·`constraint <id>: [when] then`·
  `expect <id>:` 구조 + 따옴표 id. 골든 등가는 표현식을 ast 재파싱해 구조 비교(공백·괄호 무관).
  단독 `=`는 CMP에 없어 술어 위치에서 구문 오류(D21 `=`/`==` 판별 기반 — S3 전이 대입의 토대).
  테스트 12건(우선순위·괄호·상수나눗셈·`=` 거부·init 중복 거부·정적 골든 등가). 전체 234건
  통과(기존 222 무변경), ruff/format/mypy(strict) clean. desc/author surface는 S6로 연기.
  다음=S3(전이 — `gold' = expr` 대입·`;` 다중대입·프레임 D15, D21 의미론 핵심).
- 2026-06-25: **S3(전이) 완료 — D21 의미론 핵심.** `text_loader`에 전이 문법 추가:
  `transition <id>: [when <pred>] [pref <n>] (then <update> | outcomes: <n -> update>+)`.
  **효과는 대입** — `var' = sum`을 IR의 `next.var == sum` 문자열로 lowering(S2 표현식 RHS
  재사용), `;` 다중 대입은 `and` 결합(병렬 대입 집합, YAML 다중 효과와 동형). bare then→
  weight=1.0 단일 Outcome 정규화. **D21 `=`/`==` 판별을 문법이 강제** — 효과의 `==`(비교),
  프라임 없는 LHS, 우변 프라임이 모두 구문 오류(테스트 3건으로 고정). 골든 등가에 전이
  비교(가드 ast·pref·outcomes weight·then) 추가, YAML↔자체 전이 시스템 IR 등가 확인.
  테스트 8건. 전체 242건 통과(기존 234 무변경), ruff/format/mypy(strict) clean. 골든 등가가
  통과하므로 BMC/sim 백엔드 동작도 동일(IR 동일) — 백엔드 e2e는 S6 코퍼스 이관에서.
  다음=S4(checks — reachable/invariant/no_deadlock/prob/distribution, dialect 분리 보존).
- 2026-06-25: **S4(checks) 완료.** `text_loader`에 `check <id> <kind>` 문법 추가 — 5가지
  kind. **dialect 분리 보존(D11):** reachable/invariant→`that`(술어 lowering),
  distribution→`expr`(sim 수치식 lowering), prob→`spec`(**PCTL 불투명 문자열**, 따옴표만
  벗기고 core 미파싱), no_deadlock→필드 없음. 골든 등가에 checks 비교 추가(that/expr은 ast,
  prob.spec은 정확 문자열). 테스트 6건(5 kind + 5종 골든 등가). 전체 248건 통과(기존 242
  무변경), ruff/format/mypy(strict) clean. 다음=S5(템플릿 — `for`/`${}`/`table` desugar,
  D18 등가). 로더 기존 desugar(`_expand_items`)와 동형 결과를 내야 함.
- 2026-06-25: **S5(템플릿) 완료 — D18 desugar 동형.** 문법에 `table`/`for`/`index`(name[key])
  추가. **트리 확장 패스**(`_expand_tree`)를 `_ToIR` 변환 앞에 둠: table 수집→for 데카르트 곱
  (키 순서=로더와 동형)→loop var(name) 치환·표 색인(index) 리터럴 평가·id `${}` 보간. 외부
  DSL은 loop var·색인이 1급 식이라 `${}`는 id 문자열에만 남음(D21). 색인 평가는 로더
  `_eval_template_node`와 같은 화이트리스트(Name/Subscript/Constant). `outcome` weight를 `sum`
  으로 넓혀 표 색인 가중치(`win[mon][cls]`) 허용(desugar 후 수치 평가). 단일-item `for`(YAML의
  per-item for와 동형)라 들여쓰기 불필요. 골든 등가에 for/tables/${} 블록(2×2 전투 전이)
  추가 — YAML `for:`/`tables:`/`${}`와 펼친 IR 바이트/ast 등가. 테스트 6건(곱 순서·id 보간·
  색인 in 가드/weight/RHS·for-constraints·미정의 표/파라미터 거부·골든). 전체 254건 통과(기존
  248 무변경), ruff/format/mypy(strict) clean. **연기:** 레코드-리스트 for·중첩 for·numeric
  binding·desc/author surface는 S6/후속. 다음=S6(전체 코퍼스 양포맷 골든 등가 + 백엔드 e2e +
  예제 이관 + 에러 리포트 정련).
- 2026-06-25: **S6 핵심 검증 완료(밀스톤 인수).** ① **loop-var/도메인-var 충돌 감지**(fail
  loud) — 동명이면 거부(dungeon의 loop var `monster` ↔ 도메인 `monster` 같은 조용한 shadowing
  방지). ② **실제 `examples/dungeon.rule` 전체를 자체 문법판으로 → 골든 IR 등가**: 도메인·정적
  constraints·5개 table·init·이동/조우/전투(8-way for-template)/흡수 전이·5종 check kind·괄호-or
  가드·다중 대입·표 색인 가중치를 한 번에 검증. loop var는 `mon`으로 써 도메인 `monster`와의
  충돌 회피(IR id·값 동일). ③ `validate(native_rs)`로 자체 IR이 백엔드 스키마 게이트(참조
  무결성·next.* 규칙·중복 id) 통과 확인 — IR 동일 ⇒ BMC/sim/PRISM 동작 동일. 테스트 2건.
  전체 256건 통과, ruff/format/mypy(strict) clean. **외부 DSL이 전이 시스템 전체를 YAML과
  등가로 표현함이 입증됨(D21 Phase 3 골든 등가 충족).**
  **남은 S6(결정 대기, 파괴적):** ⓐ CLI 통합/포맷 디스패치(.rule 확장자 정책), ⓑ desc/author
  surface 문법, ⓒ 예제·rules 실제 이관 + YAML 디프리케이트. 사용자 결정 후 진행.
- 2026-06-25: **S6 이관/통합 진행(사용자 결정: `.lf` 확장자 + 네 가지 모두).** ① **desc/author
  surface** — constraint/transition/check/expect에 `desc "..."`(전체)·`author "..."`(constraint)
  추가, 골든 등가에 desc/author 비교 포함. ② **로더 디스패치** — `load_rule_file`이 확장자로
  분기(`.lf`→text_loader, `.rule`/`.yaml`→YAML), `load_rules` 디렉토리 글롭에 `.lf` 추가.
  ③ **YAML 디프리케이트** — YAML 로드 시 1회 `DeprecationWarning`. ④ **dungeon 이관** —
  `examples/dungeon.lf` 생성(desc 포함), 실제 파일 양포맷 골든 등가 + 파라미터화 하니스
  (examples/*.lf 자동 회귀). **CLI e2e 검증:** `ludoforge bmc examples/dungeon.lf --k 2`가
  동작하고 desc가 리포트에 노출(이관 충실성 입증). 테스트 5건 추가(메타 round-trip·디스패치·
  경고·파라미터화 하니스). 전체 259건 통과, ruff/format/mypy(strict) clean. **남음:** 나머지
  14개 examples 일괄 이관(.lf, 하니스가 자동 검증) + 문서(CLAUDE §4 전면·README) — 사용자 확인 후.
- 2026-06-25: **S6 완료 — 6차 마일스톤 마감.** 나머지 14개 예제 전부 자체 문법(`.lf`) 이관:
  단일파일 13개(crit_chance·starter_zone_drops·stealth_combat·balanced_build·balanced_stats·
  stat_budget·item_enchant·day_night_cycle·drop_rates_real·loot_table·market_sim·dungeon_policy·
  dungeon_sim)는 `.lf` 추가(+`.rule` 골든 참조 유지), team_example/은 3개 `.lf`로 이관하고
  `.rule` 삭제(디렉토리 병합 데모라 단일 포맷 필요). **파라미터화 하니스**가 examples/*.lf를
  자동 회귀(.rule과 IR 등가). 이관 중 발견·수정: text_loader가 `source`(범인 파일 추적,
  원칙4)를 IR에 안 채워 병합 시 출처 누락 → `parse_rule_text`가 source 부여(YAML과 동일
  `path.name` 규약), 로더 디스패치도 `path.name` 전달. team_example 병합 테스트 추가. 문서
  갱신: README(빠른시작 예제 `.lf`화·포맷 디프리케이션 안내·명령/디렉토리/에디터 섹션)·
  examples/README(`.rule`→`.lf`). 전체 274건 통과, ruff/format/mypy(strict) clean.
  **6차 마일스톤(외부 DSL) 완료** — 자체 문법 `.lf`가 전이 시스템·템플릿·메타데이터를 표현하고
  YAML과 골든 IR 등가, 로더 디스패치·CLI·YAML 디프리케이트까지 동작. **후속(선택):** `.lf`
  전용 구문 강조/LSP, CLAUDE §4 YAML 예시의 `.lf` 전면 교체, 단일파일 `.rule` 최종 제거.
- 2026-06-25: **후속 ①②(도구화·문서) 완료.** ① **`.lf` 구문 강조** — VS Code TextMate 확장
  `editors/vscode-lf/`(package.json·language-configuration·lf.tmLanguage.json): 키워드·타입·
  논리/비교/대입 연산자·다음상태 변수(`gold'`)·`//` 주석·`${}` 보간·수치 강조. 타 에디터 이식
  가능(표준 TextMate). README 에디터 섹션 갱신. ② **CLAUDE §4 본문 `.lf` 전면 교체** — warrior·
  전이 시스템·템플릿 3개 YAML 블록을 자체 문법으로, §4.2 prose(loop var·표 색인 1급 식·`${}`는
  id에만·동명 거부)·§4.1(`var'`/`=` 표기·구현완료 반영)·§4 헤더 갱신. ③ **단일파일 `.rule`
  최종 제거는 안 함(사용자 결정: 유지)** — `.rule`을 디프리케이트 골든 참조로 보존해 두 프론트엔드
  일치를 계속 검증(`test_example_lf_matches_yaml`). 7개 백엔드 테스트+corpus 글롭이 `examples/*.rule`를
  로드하는 현 구조 유지(무변경). **6차 마일스톤 후속까지 종료.**
- 2026-06-25: **D22 — 전이 효과 프라임(`var'`) 제거(사용자 결정).** D21의 `gold' = expr` 표기를
  `gold = expr`로 개정 — `then`/`outcomes` 문맥이 곧 다음상태라 프라임이 잉여(`=`/`==`가 대입/비교를
  가름). 문법 1줄(`assign: NAME "=" sum`), 변환기·lowering 무변경(IR은 여전히 `next.var == …`).
  예제 14개 `.lf`·테스트 효과 표기 일괄 갱신(sed), 프라임 거부 테스트 2건 삭제·가드-대입 거부
  1건 추가. 문서: decisions D22(D21은 원본 보존), CLAUDE §4·§4.1, PLAN 6차 §2·§3, README·editors
  (구문 강조 프라임 규칙 제거). 검증: 14개 `.lf`↔`.rule` 골든 IR 등가 유지, CLI 스모크 OK,
  전체 273 통과, ruff/format/mypy(strict) clean.
- 2026-06-25: **7차 마일스톤 착수 · Phase 1 완료(PRISM 사용자 표면 제거, D23).** ① DSL에서
  `kind: prob`/`spec` 제거 — `Check.spec` 필드 삭제(ir), YAML 로더 `_CHECK_KINDS`에서 prob 빼고
  spec 파싱 제거(kind:prob→"kind 잘못됨" 거부), `.lf` 문법에서 `prob:` 규칙·`check_prob` 변환기
  제거(파싱 오류로 거부). ② `ludoforge prob` 서브명령·prob import 제거(CLI=check/bmc/sim).
  ③ prism_gen의 prob(spec) 분기 제거(reachable→Pmax·invariant→Pmin만 — 오라클은 reachable로
  충분). ④ bmc `skipped_prob`→`skipped_other`(distribution만), sim skipped에서 prob 제거.
  ⑤ 예제 dungeon.{lf,rule}의 best_win_prob(prob) 검사 제거. 테스트: prob 거부 테스트로 전환
  (YAML·`.lf`), 골든 등가·probforge에서 spec/prob 단언 제거. **prob/·test_sim_oracle·prism_gen
  reachable/invariant 매핑은 보존**(증명기 오라클 = DNA). 전체 273 통과, ruff/format/mypy(strict)
  clean. e2e: `ludoforge prob` 없음·`.lf`/`YAML`의 prob 거부·dungeon bmc 동작 확인. 다음=P2(오라클
  픽스처화).
- 2026-06-25: **Phase 2 완료(오라클 DTMC 픽스처화, D23).** `examples/dungeon_sim.lf` →
  `tests/fixtures/oracle_dungeon.lf`(git mv, 헤더를 "테스트 전용 오라클"로 갱신), 디프리케이트
  골든 `examples/dungeon_sim.rule` 삭제. `test_sim_oracle`이 픽스처(.lf)를 로드하도록 경로
  갱신(EXAMPLES→ORACLE), 함수명 `test_oracle_dtmc_sweeps_roles`로 정리. `test_corpus`
  EXAMPLE_EXPECTED에서 dungeon_sim 제거, `examples/README`의 댕글링 참조(행·문단·상호참조)
  정리. **오라클 회귀 3건 모두 통과(PRISM 4.10.1 실측 — 직업별 정확값 ∈ sim CI)** — 픽스처
  이동에도 sim↔PRISM 교차검증 유지. 전체 271 통과(이동으로 하니스·corpus에서 -2),
  ruff/format/mypy(strict) clean. 다음=P3(던전 통합 — 핵심).
- 2026-06-25: **Phase 3 완료(던전 예제 통합, D23 핵심).** 던전 4벌→2벌(통합 dungeon +
  market_sim 최소 보존). 단일 실전형 `examples/dungeon.lf` 작성 — 클래스 밸런스(role sweep·
  win_gold 파생·8-way 전투 tables)에 "욕심(descend) vs 안전(go_home)"의 `pref` 정책(D20)을
  얹어 **한 모델로 bmc(건전성)·sim(직업별 추정)을 모두 시연**(dialect 분리). 선택점을 "층
  클리어 후 descend vs go_home" 2지선다로만 두어(진입+조우 결합·hall 가드 상호배타) 그 외
  상태는 단일 enabled → sim DTMC 환원·bmc는 pref 무시. `dungeon_policy.{lf,rule}` 제거(dungeon에
  흡수), `dungeon.rule`은 새 모델의 YAML 골든 트윈으로 재작성(골든 등가로 동기 검증). 테스트:
  test_transitions 전이 목록·enter_l1(다중대입)·pref 단언 갱신, test_sim_aggregate 정책 테스트를
  dungeon.lf로 재지정(rogue death>0), test_corpus에서 dungeon_policy 제거, README 던전 섹션
  통합(prob/D16 문구 제거). **검증:** bmc 9검사 전부 ✅(클래스별 winnable·dragon·death·불변식·
  데드락), sim 4직업 sweep(rogue 0.72<cleric 0.84<fighter 0.86<wizard 0.88, 절단 0%, 정책 라벨),
  dungeon.lf↔dungeon.rule 골든 등가 통과. 전체 269 통과, ruff/format/mypy(strict) clean.
  다음=P4(문서 정합 — CLAUDE·concepts·README 잔여·D13/16/19 주석).
- 2026-06-26: **Phase 4 완료 — 7차 마일스톤 마감(문서·메시지 정합, D23).** 라이브 문서에서
  PRISM 사용자 표면 흔적 제거: CLAUDE §3(아키텍처: PRISM=테스트 오라클)·§4.1(DSL 예시 prob
  줄·kind 집합·`bmc/prob/sim`→`bmc/sim`·dungeon_policy→dungeon.lf)·§6(CLI 목록), README(소개·
  기능 bullet·환경·PRISM 설치 섹션을 "테스트 오라클·선택"으로·`ludoforge prob` 명령 블록을
  교차검증 회귀 설명으로·dungeon_sim/policy 명령 정정·깨진 앵커·prob 종료코드 잔재 제거),
  concepts §8.5(D23 admonition)·§8.7 walkthrough(prob→sim)·§9.2/§9.4/§9.4.1/§9.6/§9.8(dungeon_sim
  →오라클 픽스처·dungeon_policy→dungeon.lf·market_sim.lf), build_slides(확률증명 슬라이드→sim).
  **코드 사용자 메시지:** sim/report skipped 안내·sim/engine DtmcViolation 문구에서 죽은
  `ludoforge prob` 제거(DtmcViolation은 D20 pref opt-in 안내로 갱신). **역사 ADR 본문(D13~D21)은
  보존**하고 D13·D16·D19에 "D23으로 갱신" 상태 주석만 추가. 테스트: DtmcViolation 문구 단언 2건
  갱신(비결정·pref·prob없음). 전체 269 통과, ruff/format/mypy(strict) clean.
  **7차 마일스톤(구조 단순화) 완료** — PRISM은 테스트 전용 오라클, 던전 예제 4→2, 사용자
  백엔드는 check/bmc/sim 3개로 단순화.
