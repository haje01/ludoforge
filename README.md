# Ludoforge

> 게임 기획 검증 툴킷 — 게임 룰을 하나의 [DSL](docs/concepts.md#dsl-domain-specific-language-도메인-특화-언어)로 작성하면, 논리는 [SMT solver](docs/concepts.md#smt-solver--z3)(Z3/[BMC](docs/concepts.md#bmc-bounded-model-checking-유계-모델-검사))로
> **결정론적으로 증명**하고(논리 백엔드), 정량 속성(승률·기대값·분포)은 Monte Carlo로
> **추정**한다(sim 백엔드; 소형 모델은 PRISM으로 교차검증).

여러 기획자가 각자 합리적으로 쓴 룰이 함께 두면 모순되는 일(예: "전사 HP =
레벨×100" + "HP 상한 5000" + "레벨 상한 100" → 레벨 51부터 모순)을,
시뮬레이션처럼 우연히 마주치는 게 아니라 **수학적으로 증명**한다.

정적 모순뿐 아니라 턴·이동·누적이 있는 **동역학**도 다룬다 — 하나의 DSL을 공유하며
**논리는 Z3/BMC로 증명**(`ludoforge bmc`), **정량은 Monte Carlo로 추정**(`ludoforge sim`,
소형 모델은 PRISM 테스트 오라클로 교차검증)하는 [다중 백엔드](docs/concepts.md#86-다중-백엔드-아키텍처--모델은-하나-질문은-여럿) 구조다. *존재·건전성은
결정론적 증명, 정량 크기는 정직한 추정*(신뢰구간·"증명 아님" 라벨)으로 나눈다(D19). 배경은
[개념 문서 §8](docs/concepts.md)을 참고.

## 주요 기능

- **DSL 기반 룰 작성**: 룰을 산문이 아닌 기계 검증 가능한 DSL(자체 문법 `.lf`)로 기술
  (`=` 대입 / `==` 비교 구분, D21).
- **스키마·참조 무결성 검증**: 미정의 심볼 참조, 중복 rule id, 표현식 구문 오류,
  변수 범위(min>max) 등 형식 오류를 Z3 검사 이전에 탐지.
- **논리 모순 검증**: Z3로 번역해 도달 가능성 검사 — 기획자가 합법이라 여기는
  상태를 룰들이 봉쇄하면 모순으로 보고하고, **범인 룰([unsat core](docs/concepts.md#assert_and_track--unsat-core-이-프로젝트의-존재-이유))** 을 짚는다.
- **사람이 읽는 리포트**: 어떤 룰이 충돌하는지, 어떤 입력에서 깨지는지 한국어로 출력.
- **[전이 시스템](docs/concepts.md#82-전이-시스템--상태가-변하는-모델) 검사(BMC)**: 턴·이동·누적이 있는 동역학을 `transitions`로 기술하고,
  [도달성](docs/concepts.md#그래서--도달-가능성reachability-검사)·[불변식](docs/concepts.md#84-논리-백엔드의-bmc--논리로-동역학-검증-d15)·[데드락](docs/concepts.md#84-논리-백엔드의-bmc--논리로-동역학-검증-d15)을 k 스텝 BMC로 검증 — 반례 경로를 함께 제시(`ludoforge bmc`).
- **정량 추정([Monte Carlo](docs/concepts.md#93-새-용어-사전), sim)**: 같은 전이 시스템을 표집 시뮬레이션해 승리 확률·기대
  게임 길이·직업별 분포를 *[추정](docs/concepts.md#9-4차-확장--정량-추정-증명에서-추정으로-sim-d19)*(`ludoforge sim`). 신뢰구간·미관측 사건의 rule-of-three
  상한·절단 비율을 정직하게 보고(증명 아님). [DTMC만](docs/concepts.md#94-왜-dtmc만-받나) 지원하고, real·고차원·큰 범위 모델도
  상태폭발 없이 다룬다. 병렬(`--workers`)이며 결과는 워커 수와 무관하게 재현된다(D19).
- **확률 증명 오라클(PRISM, 테스트 전용)**: 소형 유한 모델을 PRISM 확률 모델로 번역해 승리
  확률을 *정확히* 계산하고 **sim 추정을 검정**한다 — 추정기에 신뢰를 부여하는 교차검증
  오라클이다(D19). D23으로 사용자 CLI 표면에서는 내려 테스트(`tests/test_sim_oracle.py`)로만
  쓴다. PRISM 설치 시 동작([설치 안내](#prism-설치-테스트-오라클-선택)).

## 한눈에 보기

각각은 멀쩡한 룰 몇 개가 함께 두면 깨지는 상황을, 시뮬레이션처럼 *우연히* 마주치길
기다리는 대신 **수학적으로 증명**한다. 아래를 `warrior.lf`로 저장하고 검사해 보자
(자체 문법 `.lf` — `==`는 비교, 같은상태 술어):

```text
domain {
    level: int 1..100               // ① 레벨 상한 100
    hp:    int 0..
    role:  enum { warrior, mage }
}

constraint warrior_hp_formula:      // ② 전사 HP = 레벨 × 100  (기획자 A)
    when role == warrior
    then hp == level * 100
constraint global_hp_cap:           // ③ 모든 HP는 5000 이하    (기획자 B)
    then hp <= 5000
```

```bash
ludoforge check warrior.lf
```

```text
❌ 모순 1건이 발견되었습니다.

[1] role=warrior일 때 'level'은(는) 최대 50까지만 도달 가능합니다 (선언 max=100).
    → 범인 룰: global_hp_cap (warrior.lf), warrior_hp_formula (warrior.lf)
```

①②③ 각각은 합리적이지만, 전사는 HP 상한(5000) 때문에 **레벨 50을 넘을 수 없다** —
"레벨 100까지 성장"이라는 설계 의도와 충돌한다. 도구는 이 모순을 증명하고 범인 룰을
함께 짚는다. 더 많은 예제는 [`examples/`](examples/README.md)에 있다.

## 실행 환경

- Python 3.11+ / 패키지 관리자 `uv`
- 핵심 의존성(자동 설치): `z3-solver`, `lark`, `pyyaml`, `typer`, `pytest`, `ruff`, `mypy`
- **외부 도구 — PRISM(선택)**: sim↔정확값 교차검증 테스트가 호출하는 확률 [모델검사기](docs/concepts.md#모델-검사-model-checking).
  미설치 시 해당 오라클 테스트만 skip되고 본 도구 사용엔 지장 없다([설치 안내](#prism-설치-테스트-오라클-선택)).
  논리 검사(`check`·`bmc`)만 쓸 때는 없어도 된다.

## 디렉토리 구성

```
core/         # 공유 DSL 프론트엔드(SSOT): schema.py(검증) loader.py(확장자 디스패치) text_loader.py(.lf→IR) ir.py(중간표현)
ludoforge/    # 우산: 통합 CLI 진입점 — cli.py (check / bmc / sim / prob)
logic/        # 논리 증명 백엔드(Z3)
  solver/     # translator.py(IR→Z3) checks.py(정적 검사) bmc.py(전이 BMC) report.py(리포트)
sim/          # 확률 추정 백엔드(Monte Carlo): engine.py(인터프리터) aggregate.py(집계) runner.py(병렬) report.py
prob/         # 확률 증명 오라클(PRISM): prism_gen.py(IR→PRISM) runner.py(실행·파싱)
rules/        # 실제 기획 룰 (.lf), git SSOT
examples/     # 게임 기획 모순/정합 예제 (.lf)
tests/        # 모순/정합 코퍼스 포함
docs/         # 문서
```

## 빠른 시작

개발 지식이 없어도 아래 순서를 그대로 따라 하면 Windows에서 바로 쓸 수 있다.

### 1단계 — 사전 준비 (한 번만)

준비물은 **uv**(필수)와 **PRISM**(확률 검사용)이다. Python은 따로 설치할 필요가
없다 — uv가 필요한 Python(3.11 이상)을 자동으로 내려받아 이 도구 전용으로 쓴다.

**uv 설치** → <https://docs.astral.sh/uv/getting-started/installation/>
Windows는 PowerShell을 열고 그 페이지의 한 줄 명령을 붙여넣으면 된다.
설치 후에는 PowerShell 창을 **새로 열어야** 명령이 인식된다.

> 참고(선택): 이미 Python이 있거나 직접 설치·관리하고 싶다면
> <https://www.python.org/> (Windows 설치 시 "Add python.exe to PATH" 체크).
> 없어도 무방하다.

#### PRISM 설치 (테스트 오라클, 선택)

sim↔정확값 교차검증 테스트(`tests/test_sim_oracle.py`)는 [PRISM](https://www.prismmodelchecker.org/)
확률 모델검사기를 호출해 sim 추정을 검정한다. **본 도구 사용(`check`·`bmc`·`sim`)에는 PRISM이
필요 없다** — 미설치 시 해당 오라클 테스트만 skip된다. 추정기 신뢰를 직접 재검증하려면 설치한다.

1. **Java 준비** — PRISM은 Java(JRE/JDK)가 있어야 실행된다. 없으면 먼저
   <https://adoptium.net/> 등에서 설치한다(`java -version`으로 확인).
2. **PRISM 내려받기** — <https://www.prismmodelchecker.org/download.php>에서
   운영체제에 맞는 패키지를 받는다.
   - **Windows**: 설치 프로그램(installer)을 실행한다. 설치 폴더 안 `bin\prism.bat`이
     실행 파일이다.
   - **macOS/Linux**: 압축을 풀고 `bin/prism`을 쓴다(배포본에 따라 `./install.sh` 실행).
3. **Ludoforge가 PRISM을 찾게 하기** — 둘 중 하나면 된다.
   - PRISM의 `bin` 폴더를 **PATH**에 추가한다(권장), 또는
   - 환경변수 **`PRISM`** 을 실행 파일 경로로 지정한다
     (Windows 예: `setx PRISM "C:\prism\bin\prism.bat"`).
4. **확인** — 새 터미널에서 `prism -version`이 버전을 출력하면 준비 완료다.

> 설치 후에는 터미널을 **새로 열어야** PATH·환경변수 변경이 반영된다.

### 2단계 — Ludoforge 설치

PowerShell(또는 터미널)에서 아래 한 줄을 실행하면 `ludoforge` 명령이 설치된다:

```bash
uv tool install git+https://github.com/haje01/ludoforge.git
```

설치 후에는 어느 폴더에서나 `ludoforge` 명령을 쓸 수 있다. 나중에 최신 버전으로
갱신하려면 `uv tool upgrade ludoforge`, 제거하려면 `uv tool uninstall ludoforge`.


### 3단계 — 룰 검사하기

검사할 `.lf` 파일들이 들어 있는 폴더(또는 파일 하나)를 지정한다:

```bash
ludoforge check 내룰폴더           # 폴더 안 모든 .lf을 병합해 함께 검사
ludoforge check 내룰폴더\some.lf   # 파일 하나만 검사
```

모순이 있으면 어떤 룰들이 충돌하는지 한국어로 알려준다. 저장소에 포함된 예제로
바로 확인해 볼 수 있다(아이템 강화 한도가 파워 상한에 막히는 경우):

```bash
ludoforge check examples/item_enchant.lf
```

```text
❌ 모순 1건이 발견되었습니다.

[1] rarity=legendary일 때 'enchant_level'은(는) 최대 5까지만 도달 가능합니다 (선언 max=10).
    → 범인 룰: global_power_cap, legendary_power_formula
```

다양한 기획 모순/정합 예제는 [`examples/`](examples/README.md)에 있다.

**종료코드:** `0` 정합 · `1` 모순 발견 · `2` 로드/검증 오류 · `3` 판단 불가(unknown).
CI에서 PR마다 실행해 모순 시 빌드를 실패시키는 용도로 쓴다.

### 전이 시스템 검사 (BMC)

`transitions`로 상태 전이를 기술한 룰셋은 `bmc` 명령으로 동역학을 검사한다 — 승리
상태 도달성, 불변식 유지, 데드락을 k 스텝까지 본다(반례 경로 동봉). 던전!(WotC 2012판)을
모델링한 예제(클래스 4종·클래스별 전투 난이도·몬스터 2종·조우→전투·승패)로 확인:

```bash
ludoforge bmc examples/dungeon.lf --k 12
ludoforge bmc examples/dungeon.lf --k 14 --html bmc.html   # 경로·반례를 시각화한 HTML로 저장
```

```text
[1] 검사 'winnable' (reachable) — ...: ✅ 도달 가능 (깊이 6)
    경로:
      s0: gold=0, win_gold=10, room=hall, role=rogue, monster=none, status=exploring
        --[enter_l1]-->
      s1: gold=0, win_gold=10, room=l1, role=rogue, monster=goblin, status=exploring
        --[fight_goblin_rogue]-->
      s2: gold=0, win_gold=10, room=l1, role=rogue, monster=none, status=exploring
        --[descend_l2]-->
      s3: gold=0, win_gold=10, room=l2, role=rogue, monster=dragon, status=exploring
        --[fight_dragon_rogue]-->
      s4: gold=10, win_gold=10, room=l2, role=rogue, monster=none, status=exploring
        --[go_home]-->
      s5: gold=10, win_gold=10, room=hall, role=rogue, monster=none, status=exploring
        --[claim_victory]-->
      s6: gold=10, win_gold=10, room=hall, role=rogue, monster=none, status=won
```

`rogue_winnable`·`wizard_winnable` 검사는 전투에 가장 약한 rogue와 목표액이 가장 높은
wizard도 각각 이길 길이 있음을 확인한다(클래스 건전성).

`k`까지의 **유계 검사**다(무한 지평 증명 아님 — 리포트에 명시). 확률(`prob`) 속성은
확률(PRISM) 백엔드 몫이라 건너뛴다. **`--html <경로>`** 를 주면 같은 결과를 시각화한 자체
완결형 HTML(상태 카드 + 전이 화살표로 그린 경로, 바뀐 변수 강조, 상태 배지)로도 저장한다 —
상태 카드가 모든 변수값을 인라인으로 펼쳐 보여줘 호버 없이 한눈에 읽힌다(외부 라이브러리·CDN·JS
없음). **종료코드:** `0` 정상 · `1` 증명된 위반(불변식/데드락) · `2` 오류 · `3` k 한계 미확인.

### 정량 추정 (Monte Carlo · sim)

BMC로는 못 보는 *정량* 질문(승리 확률, 기대 게임 길이, 직업별 분포)을 **표집
시뮬레이션**으로 추정한다. 망라적 증명(PRISM)은 [상태폭발](docs/concepts.md#상태-폭발-state-explosion)에 막히지만, sim은 상태공간을
빌드하지 않고 표집만 하므로 **real·고차원·큰 범위** 모델도 다룬다. 증명이 아니라 추정이라
**신뢰구간**과 함께 보고하고, 한 번도 관측되지 않은 사건은 "불가능"이라 하지 않고
**rule-of-three 상한**으로 보고한다(존재 증명은 `bmc` 몫). 배경·용어는
[개념 문서 §9](docs/concepts.md#9-4차-확장--정량-추정-증명에서-추정으로-sim-d19) 참고.

```bash
ludoforge sim examples/dungeon.lf -H 300 -n 20000 -w 4   # 직업별 승률·보물 분포 추정(+신뢰구간)
ludoforge sim examples/market_sim.lf  -n 20000           # real 복리 자산 분포(PRISM이 못 푸는 모델)
ludoforge sim examples/dungeon.lf --html report.html     # 결과를 시각화한 HTML로 저장(브라우저로 열기)
```

```text
[설정] role=fighter
  절단(지평 H 미종료): 0/20000 (0.0%) · 자연종료 20000/20000
  [1] 'winnable' (reachable) — ...: 도달 P̂ = 0.9221  95% CI [0.9184, 0.9258]  (18442/20000)
```

`init`이 고정하지 않은 enum/bool 자유변수(예 `role`)는 **설정별로 분리해(sweep)** 각각
추정한다 — 직업별 승률 비교가 곧 이것이다. **DTMC만 지원**한다(도달 상태마다 가드가 참인
전이가 최대 1개거나, co-enabled가 모두 `pref`를 단 선택 집합): 미선언 비결정은 친절히 거부하고
`bmc`로 안내한다(D20). `--workers`로
병렬 실행하며 결과는 워커 수와 무관하게 재현된다(`--seed`). `kind: distribution` 검사는
종료 상태에서 식 값을 모아 평균·신뢰구간·백분위로 추정한다(sim 전용). **`--html <경로>`**
를 주면 같은 결과를 시각화한 자체 완결형 HTML(인라인 SVG — 비율은 CI 막대, 분포는
히스토그램)로도 저장한다 — 막대·히스토그램 칸에 커서를 올리면 그 값이 툴팁으로 뜬다(경량
자체 JS, 외부 라이브러리·CDN 없음). 브라우저로 바로 열린다. **종료코드:**
`0` 정상 · `2` 로드/검증/sim 오류(비결정 모델 등).

> **증명이 아니라 추정이다.** sim은 표집이라 희귀한 모순·도달성을 놓칠 수 있다 — 그건
> `bmc`(Z3)가 증명으로 잡는다. sim은 *얼마나 자주/얼마나 큰가*(정량)를 신뢰구간과 함께
> 답하고, 존재·건전성(*가능한가/항상 그런가*)은 논리 백엔드가 증명한다(D19).

### 확률 증명 오라클 (PRISM, 테스트 전용)

sim은 *추정*이라 "정말 맞나?"라는 의심이 따른다. 이를 **증명기로 검정**한다: 소형 **DTMC**를
PRISM 확률 모델로 번역하면 선택이 없어 `Pmax=Pmin=정확값`이 나오고, 같은 모델의 sim 추정이
그 정확값을 신뢰구간 안에 담는지 회귀로 확인한다 — *증명기가 추정기를 검정*해 추정기에 신뢰를
세운다(D19). 이것이 "표집은 증명이 아니니 못 믿는다"는 반론을 건설적으로 무력화한다.

PRISM은 **D23으로 사용자 CLI 표면에서 내렸다** — `ludoforge prob` 같은 명령은 없고, 교차검증
회귀(`tests/test_sim_oracle.py`)와 오라클 픽스처(`tests/fixtures/oracle_dungeon.lf`)로만 쓴다.
PRISM 미설치 시 그 테스트만 skip되고 본 도구 사용(`check`·`bmc`·`sim`)엔 지장 없다
([설치 안내](#prism-설치-테스트-오라클-선택)).

```text
# 던전 오라클 교차검증(PRISM 4.10.1 실측) — role 고정 시 정확값 ∈ sim 95% CI
fighter  PRISM 0.922  ↔  sim P̂ 0.922   rogue 0.834 ↔ 0.834   wizard 0.945 ↔ 0.945
```

### 여러 기획자가 함께 쓸 때

> **DSL 포맷 (D21):** 룰은 자체 문법 **`.lf`**(외부 DSL)로 작성한다 — 참조 예제
> [`examples/dungeon.lf`](examples/dungeon.lf).

`.lf` 파일은 `domain`(변수 선언)과 `constraints`(제약) 섹션으로 나뉘는데, **둘 중
하나만 담은 파일도 된다.** 디렉토리를 검사하면 그 안의 모든 `.lf`을 하나로
병합해 함께 검사하기 때문이다. 그래서 협업은 다음처럼 나눠 쓰면 깔끔하다:

```
rules/
  _domain.lf          # 공유: domain(변수)만 — 모두가 합의하는 도메인 정의
  planner_a.lf        # 기획자 A: constraints만
  planner_b.lf        # 기획자 B: constraints만
```

`ludoforge check rules/` 한 번이면 공유 도메인 위에서 A·B의 룰을 합쳐 검사하므로,
**서로 다른 파일에 흩어진 룰 사이의 모순**까지 잡아낸다(별도 import 구문 불필요).
이 저장소의 [`examples/team_example/`](examples/team_example/)에 위 구조 그대로의
예시가 있다 — `ludoforge check examples/team_example/`로 동작을 확인해 볼 수 있다.

> 참고: `constraints`만 담은 파일을 단독으로 검사하면 변수 선언이 없어 오류가 난다.
> 이때는 공유 도메인 파일이 함께 있는 **디렉토리**를 검사하면 된다(도구가 안내해 준다).
> 같은 변수를 두 파일에서 서로 다르게 선언하면 충돌로 보고된다.

### 에디터 구문 강조

**자체 문법 `.lf`** — 두 에디터용 구문 강조가 저장소에 포함돼 있다(키워드 집합은 서로 맞춤):

- **VS Code · Cursor** — TextMate 문법 확장 [`editors/vscode-lf/`](editors/vscode-lf/).
  설치는 `Ctrl+Shift+P` → **`Developer: Install Extension from Location...`** 로 그 폴더를
  고른 뒤 창을 reload 하면 된다(WSL/Remote 포함 어디서나 동작 — 수동 복사는 Remote-WSL에서
  무시되니 이 방법을 쓴다). 표준 TextMate 문법이라 Sublime·Notepad++ 등에도 이식 가능하다.
- **Vim · Neovim** — 구문 강조 플러그인 [`editors/vim-lf/`](editors/vim-lf/). 이 폴더를
  패키지 경로(`~/.vim/pack/.../start/` 또는 nvim `site/pack/.../start/`)에 링크하면 `.lf`
  파일이 자동 인식·강조된다.

둘 다 키워드·타입·연산자(`=`/`==`/`->`)·`//` 주석·`${...}` 보간을 강조한다(자세한 설치·대안은
각 폴더의 README 참고).

### 개발자용 — 소스에서 실행

저장소를 클론해 기여하거나 직접 고쳐 쓸 때:

```bash
uv sync                                       # 의존성 설치 (.venv 생성)
uv run ludoforge check examples/item_enchant.lf  # 설치 없이 소스에서 바로 실행
```

## DSL 작성 팁

DSL은 게임을 *재현*하는 게 아니라 *검증·추정*하기 위한 모델이다. 그래서 작성의 첫
원칙은 **실제 게임의 형식이 아니라 검증 목적에 맞춰 모델링하라**는 것이다.

### 검증에 충분한 가장 단순한 단위로 묶어라 (원자적 번들링)

실제 게임에서 서로 다른 액션이라도, 검증·추정 결과에 영향이 없다면 **하나의 전이로
원자적으로 묶는** 편이 더 단순하고 충분하다. 실제 턴 구조를 그대로 옮길 필요는 없다.

예) [`examples/dungeon.lf`](examples/dungeon.lf)에서 "층 이동"과 "이동 후 몬스터 조우"는
보드게임상 별개의 행동이지만, 한 전이에 함께 담는다:

```text
transition enter_l1:
    when room == hall and status == exploring and monster == none and gold < win_gold
    then { room = l1; monster = goblin }   // 이동 + 조우를 원자적으로
```

이동과 조우를 **별도 전이로 쪼개면** 오히려 비용이 든다:

- **상태 의미가 흐려진다.** 여기서 `monster == none`은 곧 "이 층을 클리어해 다음 행동을
  선택할 수 있다"는 뜻이다. 쪼개면 `monster == none`이 "막 도착(미조우)"과 "격파(클리어)"
  둘을 동시에 가리켜, 이를 가르는 도메인 변수를 **새로 추가**해야 한다 — 단순화가 아니라
  복잡화다.
- **스텝/상태가 늘어난다.** 한 행동이 두 스텝이 되면 BMC의 `--k`와 sim의 지평 `H`를 더
  키워야 한다.
- **줄일 중복도 없다.** 각 층의 진입 경로가 하나뿐이면 층별 몬스터 데이터는 이미 한 번씩만
  쓰인다 — 쪼개도 제거할 반복이 없다.

판단 기준은 **"쪼개면 검증·추정 결과가 달라지는가?"** 다. 달라지지 않으면 묶어라.

### 분리가 필요하면 런타임이 아니라 desugar 단계에서

한 층에 **진입 경로가 여럿**이거나 데이터를 이동과 독립적으로 변주하고 싶어 실제로 중복이
생긴다면, 전이를 런타임으로 쪼개지 말고 **`table` + `for` 템플릿**으로 펼치기(desugar)
단계에서 분리한다([4.2절](CLAUDE.md)). 소스의 중복은 사라지지만 상태기계·지평 비용은
그대로다 — "펼치기는 소스를 줄일 뿐 검증 모델은 줄이지 않는다".

```text
table floor_monster { l1: goblin, l2: dragon, l3: dragon }
for f in [l1, l2, l3]:
    transition "enter_${f}": ... then { room = f; monster = floor_monster[f] }
```

## 테스트 하기

```bash
uv run pytest          # 단위 테스트 + 모순/정합 코퍼스 (tests/)
uv run ruff check .    # 린트
uv run mypy            # 타입 검사 (strict)
```

## 문서

- [소개 슬라이드 (docs/build_slides.py)](docs/build_slides.py) — 기획자·프로그래머
  대상 발표 자료. `uv run docs/build_slides.py`로 `docs/intro-slides.pptx`를
  생성한다(python-pptx, 네이티브 편집 가능 슬라이드). 콘텐츠는 스크립트에 내장.
- [예제 모음 (examples/)](examples/README.md) — 아이템 강화·드롭 확률·등급 등
  실제 게임 기획에서 나올 법한 모순 예제와 정합 예제.
- [기본 개념 설명 (일반 프로그래머용)](docs/concepts.md) — SMT/Z3, unsat core,
  도달성 검사 등 핵심 용어와 배경 지식.
- [설계 결정 기록 (ADR)](docs/decisions.md) — 주요 결정과 기각한 대안·그 이유.
- [CLAUDE.md](CLAUDE.md) — 아키텍처/도메인 의사결정 [SSOT](docs/concepts.md#ssot-single-source-of-truth-단일-진실-원천).
- [PLAN.md](PLAN.md) / [PROGRESS.md](PROGRESS.md) — 구현 계획과 진행 상태.

> **1차**(수직 슬라이스): 정수 선형 수치 공식 + 조건부(`when`) 룰 + enum + 도달성 검사.
> **2차**(표현력 확장): 불리언 상태·상호 배제(D6), 실수 [LRA](docs/concepts.md#lia--lra--nia--산술의-종류와-난이도)(D7), [EnumSort](docs/concepts.md#enum-인코딩-enumsort)·중복 값 이름
> (D8), 실수 끝점 도달성(D9), 명시적 도달성 단언 `expect:`(D10).
> **3차**(다중 백엔드, 완료): 공유 [IR](docs/concepts.md#ir-intermediate-representation-중간-표현)(`core`) 위에 전이 시스템(init/transitions/
> checks, D12)을 두고, **논리 백엔드**(Z3/BMC — 도달성·불변식·데드락, D15)와
> **확률 백엔드**(PRISM — 확률·PCTL, D16) 두 백엔드로 동역학을 검사한다. 보드게임
> *던전!*(WotC)을 논리·확률 양쪽으로 검증하는 것이 동기였다.
> **4차**(정량 추정, 완료): 정량 백엔드 무게중심을 PRISM(증명)에서 **Monte Carlo
> 추정**(`sim`, D19)으로 옮겨 상태폭발 천장을 넘는다 — DTMC 표집으로 승률·분포를
> 신뢰구간과 함께 추정(`ludoforge sim`)하고, PRISM은 소형 모델 **교차검증 오라클**로
> 남겨 추정↔증명 일치를 확인한다. real·고차원도 상태공간 빌드 없이 다룬다.
> CI PR 코멘트 연동은 후속 단계다.
