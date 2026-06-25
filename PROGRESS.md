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

## 6차 마일스톤 — 외부 DSL(자체 문법) — 🔵 진행중 (착수 2026-06-25)

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

## 작업 로그
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
