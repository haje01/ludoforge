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
tests/        # 모순/정합 코퍼스 포함
docs/         # 문서
```

## 빠른 시작

```bash
uv sync                              # 의존성 설치 (.venv 생성)
uv run ruleforge check rules/        # rules/의 모든 .rule을 병합해 정합성 검증
```

저장소에 포함된 예시 룰(`rules/example_warrior.rule`)은 의도적 모순을 담고 있어,
위 명령은 모순을 탐지하고 다음처럼 출력한다(종료코드 1):

```text
❌ 모순 1건이 발견되었습니다.

[1] role=warrior일 때 'level'은(는) 최대 50까지만 도달 가능합니다 (선언 max=100).
    → 범인 룰: global_hp_cap, warrior_hp_formula
```

전사 HP 공식(`hp == level*100`)과 HP 상한(`hp <= 5000`)이 함께 있으면 전사는
레벨 50까지만 가능한데, 도메인은 레벨 100을 허용하므로 모순이다. HP 상한을
10000으로 올리면(레벨 100 → hp 10000) 모순이 사라진다.

단일 파일도 검사할 수 있다:

```bash
uv run ruleforge check rules/example_warrior.rule
```

**종료코드:** `0` 정합 · `1` 모순 발견 · `2` 로드/검증 오류 · `3` 판단 불가(unknown).
CI에서 PR마다 실행해 모순 시 빌드를 실패시키는 용도로 쓴다.

## 테스트 하기

```bash
uv run pytest          # 단위 테스트 + 모순/정합 코퍼스 (tests/)
uv run ruff check .    # 린트
uv run mypy            # 타입 검사 (strict)
```

## 문서

- [기본 개념 설명 (일반 프로그래머용)](docs/concepts.md) — SMT/Z3, unsat core,
  도달성 검사 등 핵심 용어와 배경 지식.
- [설계 결정 기록 (ADR)](docs/decisions.md) — 주요 결정과 기각한 대안·그 이유.
- [CLAUDE.md](CLAUDE.md) — 아키텍처/도메인 의사결정 SSOT.
- [PLAN.md](PLAN.md) / [PROGRESS.md](PROGRESS.md) — 구현 계획과 진행 상태.

> 1차 마일스톤(수직 슬라이스) 완료: 정수 선형 수치 공식 + 조건부(`when`) 룰 + enum을
> 지원한다. 상호 배제·확률(LRA)·CI PR 코멘트 연동은 후속 단계다.
