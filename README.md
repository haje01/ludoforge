# Ludoforge

> 게임 기획 검증 툴킷 — 게임 룰을 하나의 DSL로 작성하면, 논리는 SMT solver(Z3/BMC)로
> **결정론적으로 증명**하고(논리 백엔드), 확률은 PRISM으로 **계산**한다(확률 백엔드).

여러 기획자가 각자 합리적으로 쓴 룰이 함께 두면 모순되는 일(예: "전사 HP =
레벨×100" + "HP 상한 5000" + "레벨 상한 100" → 레벨 51부터 모순)을,
시뮬레이션처럼 우연히 마주치는 게 아니라 **모순의 존재 자체를 증명**한다.

정적 모순뿐 아니라 턴·이동·누적이 있는 **동역학**도 다룬다 — 하나의 DSL을 공유하며
**논리는 Z3/BMC로 증명**(`ludoforge bmc`), **확률은 PRISM으로 계산**(`ludoforge prob`)
하는 다중 백엔드 구조다. 배경은 [개념 문서 §8](docs/concepts.md)을 참고.

## 주요 기능

- **DSL 기반 룰 작성**: 룰을 산문이 아닌 기계 검증 가능한 DSL(YAML)로 기술.
- **스키마·참조 무결성 검증**: 미정의 심볼 참조, 중복 rule id, 표현식 구문 오류,
  변수 범위(min>max) 등 형식 오류를 Z3 검사 이전에 탐지.
- **논리 모순 검증**: Z3로 번역해 도달 가능성 검사 — 기획자가 합법이라 여기는
  상태를 룰들이 봉쇄하면 모순으로 보고하고, **범인 룰(unsat core)** 을 짚는다.
- **사람이 읽는 리포트**: 어떤 룰이 충돌하는지, 어떤 입력에서 깨지는지 한국어로 출력.
- **전이 시스템 검사(BMC)**: 턴·이동·누적이 있는 동역학을 `transitions`로 기술하고,
  도달성·불변식·데드락을 k 스텝 BMC로 검증 — 반례 경로를 함께 제시(`ludoforge bmc`).
- **확률 검사(PRISM)**: 같은 전이 시스템을 PRISM 확률 모델로 번역해 승리
  확률·기대값 등 PCTL 속성을 검사(`ludoforge prob`). 확률 백엔드는 PRISM이 설치돼
  있어야 동작한다([설치 안내](#prism-설치-확률-검사에-필요)).

## 실행 환경

- Python 3.11+ / 패키지 관리자 `uv`
- 핵심 의존성(자동 설치): `z3-solver`, `pyyaml`, `typer`, `pytest`, `ruff`, `mypy`
- **외부 도구 — PRISM**: 확률 백엔드(`ludoforge prob`)가 호출하는 확률 모델검사기.
  Java(JRE/JDK)가 필요하며 별도로 설치한다([설치 안내](#prism-설치-확률-검사에-필요)).
  논리 검사(`check`·`bmc`)만 쓸 때는 없어도 된다.

## 디렉토리 구성

```
core/         # 공유 DSL 프론트엔드(SSOT): schema.py(검증) loader.py(.rule→IR) ir.py(중간표현)
ludoforge/    # 우산: 통합 CLI 진입점 — cli.py (check / bmc / prob)
logic/        # 논리 증명 백엔드(Z3)
  solver/     # translator.py(IR→Z3) checks.py(정적 검사) bmc.py(전이 BMC) report.py(리포트)
prob/         # 확률 증명 백엔드(PRISM): prism_gen.py(IR→PRISM) runner.py(실행·파싱)
rules/        # 실제 기획 룰 (.rule), git SSOT
examples/     # 게임 기획 모순/정합 예제 (.rule)
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

#### PRISM 설치 (확률 검사에 필요)

확률 백엔드(`ludoforge prob`)는 [PRISM](https://www.prismmodelchecker.org/)
확률 모델검사기를 내부적으로 호출한다. 논리 검사(`check`·`bmc`)만 쓸 거라면 건너뛰어도
되지만, 확률 속성을 계산하려면 PRISM이 **반드시** 설치돼 있어야 한다.

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

검사할 `.rule` 파일들이 들어 있는 폴더(또는 파일 하나)를 지정한다:

```bash
ludoforge check 내룰폴더          # 폴더 안 모든 .rule을 병합해 함께 검사
ludoforge check 내룰폴더\some.rule  # 파일 하나만 검사
```

모순이 있으면 어떤 룰들이 충돌하는지 한국어로 알려준다. 저장소에 포함된 예제로
바로 확인해 볼 수 있다(아이템 강화 한도가 파워 상한에 막히는 경우):

```bash
ludoforge check examples/item_enchant.rule
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
상태 도달성, 불변식 유지, 데드락을 k 스텝까지 본다(반례 경로 동봉). 던전!(WotC)을
단순화한 예제(클래스·레벨·몬스터·전투·보물·승패)로 확인:

```bash
ludoforge bmc examples/dungeon.rule --k 12
```

```text
[1] 속성 'winnable' (reachable) — ...: ✅ 도달 가능 (깊이 6)
    경로:
      s0: gold=0, win_gold=10, room=hall, role=fighter, status=exploring
        --[enter_l1]-->
      ... (중략) ...
      s6: gold=10, win_gold=10, room=hall, role=fighter, status=won
```

`k`까지의 **유계 검사**다(무한 지평 증명 아님 — 리포트에 명시). 확률(`prob`) 속성은
확률(PRISM) 백엔드 몫이라 건너뛴다. **종료코드:** `0` 정상 · `1` 증명된 위반
(불변식/데드락) · `2` 오류 · `3` k 한계 미확인.

### 확률 검사 (PRISM)

같은 전이 시스템을 **PRISM 확률 모델**로 번역해, BMC로는 못 보는 *정량* 질문(승리
확률, 기대 게임 길이)을 검사한다 — 공유 DSL 하나에서 논리 증명(Z3/BMC)과 확률
증명(PRISM)을 각각의 백엔드로(다중 백엔드 아키텍처).

이 명령은 [PRISM](https://www.prismmodelchecker.org/)이 설치돼 있다고 전제한다
([설치 안내](#prism-설치-확률-검사에-필요)).

```bash
ludoforge prob examples/dungeon.rule          # PRISM으로 PCTL 속성 계산
```

> **`Pmax=? [ F ... ]`가 처음이라면:** 출력에 함께 표시되는 이 표기는 **PCTL**(확률 시제
> 논리) 질의다. 짧게 — `P`는 "얼마의 확률로?"(`Pmax`=최적 전략의 최댓값, `Pmin`=최악의
> 최솟값, `=?`=그 값을 계산), `F`는 "언젠가(결국)", `G`는 "항상". 즉
> `Pmax=? [ F (status=won) ]` = "최적 전략으로 **결국 승리할** 확률의 최댓값은?". 연산자와
> 구문을 더 알고 싶으면 [concepts.md §8.8 PCTL 구문 기초](docs/concepts.md#88-pctl-구문-기초)
> 를 참고.

PATH(또는 `PRISM` 환경변수)에서 PRISM을 찾아 각 PCTL 속성을 계산해 한국어로 보고한다.
유한 상태가 전제라 경계 없는 int·real 변수는 거부한다. 생성된 PRISM 모델 자체를 보려면
`--show-model`을 붙인다.

예제에서 `best_win_prob`(`Pmax=? [ F status=won ]`)는 `[0.56, 0.75]` 같은 **구간**으로
나오는데, 이는 초기 상태가 여럿(클래스별 fighter·wizard)일 때의 최소~최대다 — 목표 보물이
적은 fighter의 최적 승률이 높고, 더 많이 필요한 wizard가 낮다. 즉 같은 던전이라도 **클래스
균형이 정량적으로 드러난다**.

PRISM을 찾지 못하면 계산 없이 생성된 모델만 출력하고 종료코드 `3`으로 끝난다 — 이때는
위 [PRISM 설치](#prism-설치-확률-검사에-필요)를 마쳤는지 확인한다. **종료코드:**
`0` 정상 · `2` 로드/검증/번역 오류 · `3` PRISM 미설치(미계산).

### 여러 기획자가 함께 쓸 때

`.rule` 파일은 `domain`(변수 선언)과 `constraints`(제약) 섹션으로 나뉘는데, **둘 중
하나만 담은 파일도 된다.** 디렉토리를 검사하면 그 안의 모든 `.rule`을 하나로
병합해 함께 검사하기 때문이다. 그래서 협업은 다음처럼 나눠 쓰면 깔끔하다:

```
rules/
  _domain.rule        # 공유: domain(변수)만 — 모두가 합의하는 도메인 정의
  planner_a.rule      # 기획자 A: constraints만
  planner_b.rule      # 기획자 B: constraints만
```

`ludoforge check rules/` 한 번이면 공유 도메인 위에서 A·B의 룰을 합쳐 검사하므로,
**서로 다른 파일에 흩어진 룰 사이의 모순**까지 잡아낸다(별도 import 구문 불필요).
이 저장소의 [`examples/team_example/`](examples/team_example/)에 위 구조 그대로의
예시가 있다 — `ludoforge check examples/team_example/`로 동작을 확인해 볼 수 있다.

> 참고: `constraints`만 담은 파일을 단독으로 검사하면 변수 선언이 없어 오류가 난다.
> 이때는 공유 도메인 파일이 함께 있는 **디렉토리**를 검사하면 된다(도구가 안내해 준다).
> 같은 변수를 두 파일에서 서로 다르게 선언하면 충돌로 보고된다.

### 개발자용 — 소스에서 실행

저장소를 클론해 기여하거나 직접 고쳐 쓸 때:

```bash
uv sync                                       # 의존성 설치 (.venv 생성)
uv run ludoforge check examples/item_enchant.rule  # 설치 없이 소스에서 바로 실행
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
- [CLAUDE.md](CLAUDE.md) — 아키텍처/도메인 의사결정 SSOT.
- [PLAN.md](PLAN.md) / [PROGRESS.md](PROGRESS.md) — 구현 계획과 진행 상태.

> **1차**(수직 슬라이스): 정수 선형 수치 공식 + 조건부(`when`) 룰 + enum + 도달성 검사.
> **2차**(표현력 확장): 불리언 상태·상호 배제(D6), 실수 LRA(D7), EnumSort·중복 값 이름
> (D8), 실수 끝점 도달성(D9), 명시적 도달성 단언 `expect:`(D10).
> **3차**(다중 백엔드, 완료): 공유 IR(`core`) 위에 전이 시스템(init/transitions/
> checks, D12)을 두고, **논리 백엔드**(Z3/BMC — 도달성·불변식·데드락, D15)와
> **확률 백엔드**(PRISM — 확률·PCTL, D16) 두 백엔드로 동역학을 검사한다. 보드게임
> *던전!*(WotC)을 논리·확률 양쪽으로 검증하는 것이 동기였다.
> CI PR 코멘트 연동은 후속 단계다.
