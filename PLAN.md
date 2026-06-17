# PLAN.md — RuleForge 작업 계획

> 진행 상태는 [PROGRESS.md](PROGRESS.md), 설계 결정의 "왜"는
> [docs/decisions.md](docs/decisions.md), 아키텍처 SSOT는 [CLAUDE.md](CLAUDE.md).
> 완료된 작업의 상세 이력은 git 커밋과 decisions.md에 있다.

**기반(완료):** 1차·2차 마일스톤으로 정적 논리 검사기가 end-to-end 동작한다
(`ruleforge check <path>`, LIA/real/enum/bool, 6가지 모순 유형, 테스트 99건).
상세는 [PROGRESS.md](PROGRESS.md)와 decisions.md D1~D10 참조.

---

## 다중 백엔드 마일스톤 — ✅ 완료 (2026-06-17)

> **상태: 완료.** Phase 0~4 모두 끝났다(D11~D16). 공유 IR(`forge_core`) 위에 RuleForge
> (Z3/BMC, `ruleforge bmc`)와 ProbForge(PRISM, `ruleforge prob`) 두 백엔드가 동작하며,
> 던전!(WotC)을 논리·확률 양쪽으로 검증해 e2e 확인했다(승리 확률 Pmax [F win]=1.0).
> **Phase 5(저엄밀 Machinations/몬테카를로 export)는 생략**하고 마일스톤을 마감한다.
> 배경·용어는 [docs/concepts.md §8](docs/concepts.md). 상세 이력은 git·PROGRESS·decisions.
>
> 아래는 마감 시점의 계획 내용 보존(동기·결정·DSL·단계). 완료 단계는 PROGRESS 참조.

### 1. 동기와 한 줄 목표

**하나의 DSL을 게임 월드의 SSOT로 쓰되, 그 위에서 논리 증명(RuleForge/Z3)과 확률
증명(ProbForge/PRISM)을 *각각의 수학*으로 수행한다.**

현재 RuleForge는 변수의 **단일 정적 스냅샷**에서 논리적 모순만 본다. 게임처럼 턴·이동·
누적이 있는 동역학, 그리고 주사위·확률은 표현조차 못 한다. 이를 한 엔진으로 다 하려는
건 수학적으로 불가능하다 — 증명(SMT)과 확률(모델검사)은 다른 수학이다. 따라서 **모델은
하나, 백엔드는 둘**로 간다.

### 2. 3대 구조 결정 (이 마일스톤의 전제)

1. **파서/IR은 공유 라이브러리(`forge-core`).** RuleForge와 ProbForge는 *같은 IR을
   소비하는 두 백엔드*다. 각자 loader를 재구현하면 "하나의 SSOT"가 "어긋나는 두 파서"가
   된다 — 이것이 구조의 생사를 가른다.
2. **모델은 공유, 속성(질의) dialect는 각자.** 전이 모델은 둘이 공유하지만, 질의 언어는
   Z3쪽(도달성/불변식/unsat-core)과 PRISM쪽(PCTL/CSL)이 본질적으로 다르다. **질의 언어를
   통일하지 않는다.**
3. **ProbForge = PRISM 기반 *증명기*.** RuleForge(논리 증명)와 대칭. 유한 상태를 강제
   요구하며 상태 폭발이 천장이다. 몬테카를로/Machinations export는 *별도의 저엄밀 경로*로
   명확히 라벨링한다(증명 아님).

### 3. 왜 공유 코어가 억지가 아닌가 (핵심 근거)

공유 코어는 **guarded-command 전이 시스템**이다: `변수 + 가드된 전이 + (선택적) 확률 가중치`.
이 골격을 두 백엔드가 다르게 해석할 뿐이다.

- **RuleForge:** 가중치를 **지우고**(weight-erasure) 비결정 전이 관계로 본 뒤 k 스텝
  언롤링해 Z3로 증명. 주사위 = 적대적 비결정.
- **ProbForge:** 가중치를 **읽어** DTMC/MDP로 PRISM에 넘겨 PCTL 검사.

정성(논리) 모델은 정량(확률) 모델에서 확률을 잊은 **건전한 추상**이다. 둘은 이질적
접합이 아니라 한쪽이 다른 쪽의 정련(refinement)이라, 단일 DSL이 자의적이지 않다.

```
                 forge-core/   ← 진짜 SSOT: loader + schema + IR (단 하나)
                  (전이 시스템: 변수 · init · transitions · properties)
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
      ruleforge/                probforge/
   IR → Z3/BMC (논리 증명)     IR → PRISM (확률 증명)
   도달성 · 불변식 · 데드락     P/E 속성 · a.s. 도달성
   unsat-core · 반례 시퀀스     정확 확률·기댓값 (유한 상태)
          │
          └─(선택, 저엄밀)→ Machinations/몬테카를로 export (증명 아님, 플레이테스트용)
```

> **숨은 의존:** 공유 코어인 전이 시스템(BMC)은 현재 RuleForge엔 아직 없는 신규 차원이다
> (지금은 정적 스냅샷만). Phase 2~3이 사실상 RuleForge 자체의 큰 표현력 확장이고,
> ProbForge(Phase 4)는 그 공유 모델을 두 번째로 소비한다.

### 4. DSL 확장 스케치 (forge-core v2)

기존 `domain`/`rules`/`expects`는 유지(하위 호환). 전이 시스템을 위해 `init` /
`transitions` / `properties`를 추가한다. **확률 가중치와 PRISM 전용 속성은 RuleForge가
무시하는 주석**이다(레이어드 — 두 백엔드가 *똑같이* 소비하지 않음을 전제).

```yaml
domain:
  variables:
    gold: { type: int, min: 0, max: 30000 }   # ProbForge 위해 유한 max 필수
    room: { type: enum, values: [center, l1, l2, l3] }
    role: { type: enum, values: [fighter, wizard] }
    win_gold: { type: int, min: 0, max: 30000 }

rules:                                  # 정적 불변/관계 (기존, 유지)
  - id: wizard_win_target
    when: "role == wizard"
    then: "win_gold == 20000"

init: "gold == 0 and room == center"    # 초기 상태 술어 (신규)

transitions:                            # 상태 → 다음 상태 (신규). next.<var>로 다음값 참조
  - id: descend
    when: "room == l1"
    then: "next.room == l2"
  - id: fight_l2
    when: "room == l2"
    outcomes:                           # 가중치 = ProbForge용, RuleForge는 분기로만 해석
      - { weight: 0.7, then: "next.gold == gold + 500" }
      - { weight: 0.3, then: "next.gold == gold" }     # 패배

properties:                             # 백엔드별 dialect, 공통 의미는 kind로
  - id: winnable
    kind: reachable                     # RuleForge: BMC 도달성 / ProbForge: P>0
    that: "gold >= win_gold and room == center"
  - id: gold_nonneg
    kind: invariant                     # RuleForge: 모든 경로에서 불변
    that: "gold >= 0"
  - id: likely_win
    kind: prob                          # ProbForge 전용 (RuleForge 무시)
    spec: "P>=0.95 [ F (gold >= win_gold and room == center) ]"
```

**같은 전이 한 장면, 두 해석:** `fight_l2`를 RuleForge는 "0.7/0.3 가중치를 버리고 두
분기 모두 가능"으로 보고 *모든 주사위열에서 불변식이 성립하는지* 증명한다. ProbForge는
가중치를 살려 *승리 확률 ≥ 0.95* 를 PRISM으로 검사한다.

### 5. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).
> 구조적 변경과 행위적 변경을 분리한다(벡 Tidy First).

**Phase 0 — 범위 합의 & 결정 기록** *(행위 변경 없음)*
- decisions.md에 D11~ 기록: ① 다중 백엔드 계약, ② 전이 시스템 의미, ③ ProbForge 유한
  상태 요구, ④ 비목표 선(밸런스 *튜닝* 제외, *건전성* 속성만 — §7).
- **성공 기준:** CLAUDE.md §1/§3 갱신안 합의, 본 마일스톤 범위 비준.

**Phase 1 — `forge-core` 추출** *(구조적 변경, 행위 불변 — 순수 리팩터)*
- 현재 `ruleforge/dsl/`(loader·schema·ir)를 공유 패키지 `forge-core`로 분리. `ruleforge`는
  그 위 백엔드로 재배치(`solver/` 유지). 기존 99건 테스트 **전부 그대로 통과**.
- **성공 기준:** `ruleforge check` 기존 동작·리포트·테스트가 동일. 행위 변경 0.

**Phase 2 — 전이 시스템 확장 (DSL/IR)** *(행위적 변경)*
- IR에 `init` / `Transition`(when·outcomes·next.* 참조) / `Property`(kind·that·spec) 추가.
  스키마 검증(미정의 심볼, `next.` 참조 무결성, 유한 범위 요구) 확장. 던전! 미니 예제
  (`examples/`)와 파싱 테스트 우선.
- **성공 기준:** §4 예제가 IR로 로드되고 스키마 검증을 통과/거부(경계 누락 시 친절한
  에러). 기존 정적 DSL은 하위 호환.

**Phase 3 — RuleForge BMC 백엔드** *(행위적 변경)*
- IR 전이를 k 스텝 언롤링 → Z3. `assert_and_track` 규율 유지(unsat-core가 존재 이유).
  속성: `reachable`(sat + 도달 경로), `invariant`(unsat이면 안전 증명, 아니면 깨짐 시퀀스),
  `no_deadlock`. 주사위는 비결정으로.
- **성공 기준:** 알려진 코퍼스에서 (a) 도달성 sat 경로, (b) 불변식 위반 시퀀스, (c)
  k-bound 한계를 리포트에 명시(무한 지평 미증명 구간 숨기지 않음).

**Phase 4 — `probforge` 스켈레톤 (PRISM)** *(신규)*
- IR(가중치 보존) → PRISM 모델(guarded commands) 생성, `prism` CLI 호출, 결과 파싱.
  유한 상태 강제: 경계 없는 변수는 ProbForge에서 **명시적 거부**. 속성: `kind: prob`의
  PCTL spec 통과, `reachable`/`invariant`는 P>0 / P=1로 매핑.
- **성공 기준:** §4 예제에서 승리 확률·기대 턴 수가 PRISM으로 계산되고, 상태공간 크기와
  `unknown`/타임아웃을 별도 보고(sat/unsat·수치로 뭉개지 않음).

**Phase 5 — (선택) 저엄밀 export** *(신규, 명확히 비증명)*
- IR → Machinations(단방향 *뷰*, 편집 금지) 또는 내장 몬테카를로 시뮬레이터.
- **성공 기준:** 생성물이 "증명 아님 · 표집 추정 · lossy 투영"임을 출력에 라벨. 역방향
  편집 차단으로 SSOT 드리프트 방지.

### 6. 위험 & 미해결 질문 (착수 전 검증)

- **상태 폭발(ProbForge 1순위 리스크):** `gold×room×hp×class`가 수백만 상태로 폭발 가능.
  추상화/구간화 전략, PRISM 심볼릭 엔진 한계 측정 필요.
- **BMC k-bound:** 긴 지평의 전역 보장은 k-induction/불변식이 필요. 어디까지를 "증명"으로
  주장할지 경계 명시.
- **공유 IR이 두 백엔드 요구를 다 수용하는가:** Z3는 무한/정확 산술, PRISM은 유한·비선형
  OK — sweet spot이 상보적이라 IR이 양쪽 제약을 어떻게 공존시킬지(변수별 "ProbForge 대상"
  표식이 필요할 수 있음).
- **`next.` 참조·outcomes 문법:** 종속/독립 변수 판정(D5 휴리스틱)을 전이 문맥으로 확장
  시 오분류 위험. 코퍼스로 검증.
- **별도 패키지 vs 단일 CLI:** `forge prove` / `forge measure` 서브커맨드 한 프로젝트에
  둘지, 리포지토리를 가를지 — 파서 공유만 깨지지 않으면 패키징 선택.

### 7. 비목표 (scope 경계)

- **밸런스 *튜닝*·재미 평가는 비목표**(CLAUDE.md §1 유지). ProbForge는 *건전성* 속성만:
  "승리 가능한가", "확률적 데드락 없는가", "기대 게임 길이 유한한가". "A직업 승률이 B와
  5% 이내인가" 같은 튜닝은 Machinations 몫.
- **공간 보드의 픽셀 단위 충실 재현은 비목표.** 방=enum, 통로=전이 가드로 *위상*만 표현.
- **질의 언어 통일은 비목표.** 모델만 공유, 속성 dialect는 백엔드별.
- **생성된 Machinations 파일의 양방향 편집은 비목표(금지).** 단방향 파생 뷰만.

---

## 보류 중 (기존 후보 — 다중 백엔드와 별개로 잔존)

- **CI 통합**: PR마다 `ruleforge check` 자동 실행 + 모순을 PR 코멘트로, 모순 시 fail.
- **Real 범위 도달성 — 완전 Optimize(A-ii)**: 정확 달성값·gap·접근(`<`) 구분. D9 후속.
- **경계 검사 확장**: 종속 변수 정보성 리포트 / 기획 의도 상한.

## 남은 열린 질문 (검증 필요)

- **unsat core 정밀도**: Optimize gap → 경계값 재-assert로 범인 룰을 뽑는 방식이 코어를
  적정 크기로 잡는지 — 더 복잡한 룰셋 코퍼스로 확인.
- **종속 변수 휴리스틱**(D5): `then`의 단일 등식 판정이 `2*hp == ...` 변형에서
  오분류하지 않는지 — 코퍼스로 검증, 필요 시 정교화.

## 작업 규약 (유지)

- 각 단계는 작은 PR. TDD(Red→Green→Refactor), 단계마다 테스트 우선/동시.
- 게이트: `pytest` + `ruff check` + `ruff format` + `mypy`(strict) 통과.
- DSL 문법을 바꾸면 CLAUDE.md §4와 forge-core 로더/스키마/백엔드 번역기/문서를 함께 갱신.
- Z3/PRISM의 `unknown`·타임아웃은 sat/unsat·수치로 뭉개지 않고 별도 경로로 보고.
- 비선형(NIA)은 RuleForge에서 우회(상수화·구간분할) 제안+한계 명시. ProbForge에선 유한
  열거라 허용되나 상태 폭발 비용을 보고.
