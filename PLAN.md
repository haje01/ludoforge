# PLAN.md — RuleForge 1차 마일스톤 구현 계획

> 이 문서는 1차 마일스톤(수직 슬라이스)의 작업 계획이다.
> 진행 상태는 [PROGRESS.md](PROGRESS.md)에서 추적한다.
> 아키텍처/도메인 SSOT는 [CLAUDE.md](CLAUDE.md).

---

## 1. 1차 마일스톤 목표 (완료 기준)

`ruleforge check rules/` 한 줄로 아래 파이프라인이 **end-to-end**로 도는 것:

```
.rule(YAML) → loader → IR → schema 검증 → Z3 번역 → 도달성 검사 → 한국어 리포트
```

대표 검증: `warrior_hp` 룰셋이 **모순으로 잡히고**, 리포트에
"전사는 레벨 50까지만 가능(선언 max=100)" + 범인 룰 ID가 출력된다.

**완료 판정:**
- `tests/fixtures/`의 모순 코퍼스(warrior_hp 레벨상한 추가본)가 정확히 범인 룰을 짚는다.
- 정합 코퍼스(상한 없는 버전)는 모순 없음으로 통과한다.
- `ruleforge check` CLI가 모순 시 비정상 종료코드, 정합 시 0을 반환한다.
- `ruff`, `mypy strict`, `pytest` 모두 통과.

---

## 2. 확정된 설계 결정 (이번 인터뷰 산출물)

> 각 결정의 맥락·기각한 대안·근거 전문은 [docs/decisions.md](docs/decisions.md)에 박제.
> 아래 표는 요약이며, 충돌 시 decisions.md가 우선.

| # | 결정 | 근거(요약) |
|---|------|------|
| [D1](docs/decisions.md#d1-1차-마일스톤을-수직-슬라이스로-한정) | **수직 슬라이스 우선**: LIA 수치공식 + `when→Implies` + 리포트만 1차 | 점진적 형식화 (CLAUDE.md §2.5) |
| [D2](docs/decisions.md#d2-표현식-파싱은-ast--노드-화이트리스트) | 표현식 파싱 = **`ast.parse(mode="eval")` + 노드 화이트리스트 → Z3 매핑** | `eval` 금지(임의코드 실행 차단), Lark는 비용과다 |
| [D3](docs/decisions.md#d3-모순-검사-의미론--선언-도메인의-도달-가능성) | 모순 검사 의미론 = **선언 도메인의 도달 가능성 검사** | naive "assert 전부→unsat"은 조건부 모순(warrior 예시)을 못 잡음 |
| [D4](docs/decisions.md#d4-도달성-구현--z3-optimize로-달성범위-vs-선언범위-비교) | 도달성 구현 = **Z3 `Optimize`로 달성범위 vs 선언범위 비교** (enum값×변수 선형) | 데카르트 조합 폭발/거짓양성 회피, CLAUDE.md "경계 검사"와 일치 |

### 2차 이후로 미룬 것 (비목표)
- 상호 배제 상태(`Not(And(...))`), 비율/확률(LRA), Datatype enum
- Lark 자체 문법, 명시적 도달성 단언(`expect:`) 문법

---

## 3. 단계별 작업 (각 단계 = 작은 PR, 테스트 우선/동시)

CLAUDE.md §9 로드맵을 1차 결정에 맞춰 구체화.

### S0. 프로젝트 셋업
- `pyproject.toml` + 의존성: `z3-solver`, `pyyaml`, `typer`, `pytest`, `ruff`, `mypy`
- `uv` 기반 가상환경, `ruff`/`mypy strict` 설정
- 패키지 골격: `ruleforge/{dsl,solver}/`, `tests/`, `rules/`

### S1. IR (`dsl/ir.py`)
- frozen 데이터클래스: `Variable`(name, type, min, max / enum values),
  `Rule`(id, author, desc, when?, then), `Domain`, `RuleSet`
- 순수 데이터, IO 없음

### S2. 로더 (`dsl/loader.py`)
- `.rule` YAML → IR. CLAUDE.md §4 예시 1개 파싱
- 파싱 실패 시 어떤 파일/필드가 문제인지 명시 예외

### S3. 스키마·참조 검증 (`dsl/schema.py`)
- 미정의 심볼 참조, enum 값 오타, 중복 rule id, 타입 불일치 검출
- **실패 시 여기서 중단(Z3까지 안 감)** — CLAUDE.md §3.3

### S4. 표현식 번역기 (`solver/translator.py`)
- `ast` 화이트리스트 노드 → Z3 식 (BinOp +−×, Compare ==/<=/</>=/>, Name, Num, BoolOp and/or, UnaryOp not)
- 허용 외 노드 → 명시적 에러
- enum = 정수 인코딩(값↔int 매핑)
- 각 rule = `when` 있으면 `Implies(when, then)`, `assert_and_track(constr, rule_id)` 로 등록 (익명 assert 금지)

### S5. 검사 로직 (`solver/checks.py`)
- **도달성 검사**: 각 enum 값 고정 × 각 수치 변수마다 `Optimize`로 달성 max/min 계산
  - 달성범위 ⊊ 선언범위 → 모순 후보
  - 봉쇄 룰 추출: 경계값(`var == 선언max`)을 tracked로 추가 assert 후 `unsat_core()` → 범인 룰 집합
- Z3 결과는 `sat`/`unsat`만 단정. `unknown`(타임아웃/비선형)은 **별도 경로로 보고**, 절대 뭉개지 않음

### S6. 리포터 (`solver/report.py`)
- (봉쇄된 변수·범위, 범인 룰 ID·desc) → 한국어 리포트
- 예: "❌ 모순: role=warrior일 때 level은 50까지만 도달 가능 (선언 max=100). 범인 룰: warrior_hp_formula, global_hp_cap, level_cap"

### S7. CLI (`cli.py`)
- `ruleforge check <dir>`: 로드→스키마→번역→검사→리포트
- 모순/스키마오류 시 비정상 종료코드, 정합 시 0

### S8. 테스트 코퍼스 (`tests/fixtures/`)
- 모순본: warrior_hp + `hp<=5000` + `level<=100` → 정확히 3룰 unsat core
- 정합본: 상한 없는 버전 → 모순 없음
- 거짓양성/음성 회귀 테스트 고정

---

## 4. 남은 열린 질문 (구현 중 확인 필요, 1차 차단요소 아님)

1. **unsat core 정밀도**: Optimize로 gap을 찾되 범인 룰은 "경계값 assert 후 unsat_core"로
   재추출하는 방식이 코어를 너무 크게/작게 잡지 않는지 — 구현 후 코퍼스로 검증.
2. **enum 정수 인코딩**: 1차는 단순 int 매핑. Datatype 전환은 2차.
3. **리포트 출력 형식**: 1차는 콘솔 텍스트. CI PR 코멘트 연동은 2차.

---

## 5. 단계 의존성

```
S0 → S1 → S2 → S3 ─┐
                   ├→ S5 → S6 → S7 → S8
          S4 ──────┘
```
S4(번역기)는 S1(IR) 이후 S3와 병렬 가능. S5는 S3·S4 모두 필요.
