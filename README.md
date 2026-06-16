# RuleForge

> MMORPG 룰 정합성 검증기 — 게임 룰을 DSL로 작성하면 SMT solver(Z3)로
> 룰 사이의 논리적 모순을 **결정론적으로 증명**해 찾아낸다.

여러 기획자가 각자 합리적으로 쓴 룰이 함께 두면 모순되는 일(예: "전사 HP =
레벨×100" + "HP 상한 5000" + "레벨 상한 100" → 레벨 51부터 모순)을,
시뮬레이션처럼 우연히 마주치는 게 아니라 **모순의 존재 자체를 증명**한다.

## 주요 기능

- **DSL 기반 룰 작성**: 룰을 산문이 아닌 기계 검증 가능한 DSL(YAML)로 기술.
- **스키마·참조 무결성 검증**: 미정의 심볼 참조, 중복 rule id, 표현식 구문 오류,
  변수 범위(min>max) 등 형식 오류를 Z3 검사 이전에 탐지.
- **논리 모순 검증**: Z3로 번역해 도달 가능성 검사 — 기획자가 합법이라 여기는
  상태를 룰들이 봉쇄하면 모순으로 보고하고, **범인 룰(unsat core)** 을 짚는다.
- **사람이 읽는 리포트**: 어떤 룰이 충돌하는지, 어떤 입력에서 깨지는지 한국어로 출력.

## 실행 환경

- Python 3.11+ / 패키지 관리자 `uv`
- 핵심 의존성: `z3-solver`, `pyyaml`, `typer`, `pytest`, `ruff`, `mypy`

## 디렉토리 구성

```
ruleforge/
  dsl/        # schema.py(검증) loader.py(.rule→IR) ir.py(중간표현)
  solver/     # translator.py(IR→Z3) checks.py(검사) report.py(리포트)
  cli.py      # 진입점
rules/        # 실제 기획 룰 (.rule), git SSOT
examples/     # 게임 기획 모순/정합 예제 (.rule)
tests/        # 모순/정합 코퍼스 포함
docs/         # 문서
```

## 빠른 시작

개발 지식이 없어도 아래 순서를 그대로 따라 하면 Windows에서 바로 쓸 수 있다.

### 1단계 — 사전 준비 (한 번만)

준비물은 **uv 하나뿐이다.** Python은 따로 설치할 필요가 없다 — uv가 필요한
Python(3.11 이상)을 자동으로 내려받아 이 도구 전용으로 쓴다.

**uv 설치** → <https://docs.astral.sh/uv/getting-started/installation/>
Windows는 PowerShell을 열고 그 페이지의 한 줄 명령을 붙여넣으면 된다.
설치 후에는 PowerShell 창을 **새로 열어야** 명령이 인식된다.

> 참고(선택): 이미 Python이 있거나 직접 설치·관리하고 싶다면
> <https://www.python.org/> (Windows 설치 시 "Add python.exe to PATH" 체크).
> 없어도 무방하다.

### 2단계 — RuleForge 설치

PowerShell(또는 터미널)에서 아래 한 줄을 실행하면 `ruleforge` 명령이 설치된다:

```bash
uv tool install git+https://github.com/haje01/ruleforge.git
```

설치 후에는 어느 폴더에서나 `ruleforge` 명령을 쓸 수 있다. 나중에 최신 버전으로
갱신하려면 `uv tool upgrade ruleforge`, 제거하려면 `uv tool uninstall ruleforge`.

### 3단계 — 룰 검사하기

검사할 `.rule` 파일들이 들어 있는 폴더(또는 파일 하나)를 지정한다:

```bash
ruleforge check 내룰폴더          # 폴더 안 모든 .rule을 병합해 함께 검사
ruleforge check 내룰폴더\some.rule  # 파일 하나만 검사
```

모순이 있으면 어떤 룰들이 충돌하는지 한국어로 알려준다. 저장소에 포함된 예제로
바로 확인해 볼 수 있다(아이템 강화 한도가 파워 상한에 막히는 경우):

```bash
ruleforge check examples/item_enchant.rule
```

```text
❌ 모순 1건이 발견되었습니다.

[1] rarity=legendary일 때 'enchant_level'은(는) 최대 5까지만 도달 가능합니다 (선언 max=10).
    → 범인 룰: global_power_cap, legendary_power_formula
```

다양한 기획 모순/정합 예제는 [`examples/`](examples/README.md)에 있다.

**종료코드:** `0` 정합 · `1` 모순 발견 · `2` 로드/검증 오류 · `3` 판단 불가(unknown).
CI에서 PR마다 실행해 모순 시 빌드를 실패시키는 용도로 쓴다.

### 여러 기획자가 함께 쓸 때

`.rule` 파일은 `domain`(변수 선언)과 `rules`(룰) 섹션으로 나뉘는데, **둘 중
하나만 담은 파일도 된다.** 디렉토리를 검사하면 그 안의 모든 `.rule`을 하나로
병합해 함께 검사하기 때문이다. 그래서 협업은 다음처럼 나눠 쓰면 깔끔하다:

```
rules/
  _domain.rule        # 공유: domain(변수)만 — 모두가 합의하는 도메인 정의
  planner_a.rule      # 기획자 A: rules만
  planner_b.rule      # 기획자 B: rules만
```

`ruleforge check rules/` 한 번이면 공유 도메인 위에서 A·B의 룰을 합쳐 검사하므로,
**서로 다른 파일에 흩어진 룰 사이의 모순**까지 잡아낸다(별도 import 구문 불필요).
이 저장소의 [`examples/team_example/`](examples/team_example/)에 위 구조 그대로의
예시가 있다 — `ruleforge check examples/team_example/`로 동작을 확인해 볼 수 있다.

> 참고: `rules`만 담은 파일을 단독으로 검사하면 변수 선언이 없어 오류가 난다.
> 이때는 공유 도메인 파일이 함께 있는 **디렉토리**를 검사하면 된다(도구가 안내해 준다).
> 같은 변수를 두 파일에서 서로 다르게 선언하면 충돌로 보고된다.

### 개발자용 — 소스에서 실행

저장소를 클론해 기여하거나 직접 고쳐 쓸 때:

```bash
uv sync                                       # 의존성 설치 (.venv 생성)
uv run ruleforge check examples/item_enchant.rule  # 설치 없이 소스에서 바로 실행
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

> 1차 마일스톤(수직 슬라이스) 완료: 정수 선형 수치 공식 + 조건부(`when`) 룰 + enum을
> 지원한다. 2차에서 불리언 상태 변수(상호 배제, D6), 실수 변수(비율/확률 LRA, D7),
> enum 인코딩 고도화(EnumSort, 중복 값 이름 지원, D8), 실수 끝점 도달성(D9), 명시적
> 도달성 단언(`expect:`, D10)을 추가했다 — 상태 봉쇄·over-constraint·실수 끝점 봉쇄를
> 모순으로 짚고, 서로 다른 enum이 같은 값 이름을 써도 안전하며, 기획자가 `expect:`로
> 선언한 조합 도달성(예: 두 스탯 동시 최대)을 룰이 막으면 잡아낸다.
> CI PR 코멘트 연동은 후속 단계다.
