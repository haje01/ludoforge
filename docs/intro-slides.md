---
marp: true
theme: gaia
paginate: true
size: 16:9
---

<!--
이 파일은 Marp 슬라이드다(Markdown 기반). 렌더링/내보내기:
  - VS Code: "Marp for VS Code" 확장 설치 후 미리보기
  - CLI:   npx @marp-team/marp-cli docs/intro-slides.md --pptx   # 또는 --pdf, --html
-->

# RuleForge

### MMORPG 룰 정합성 검증기

기획 룰의 **논리적 모순을 결정론적으로 증명**하는 도구

<br>

대상: 게임 기획자 · 프로그래머

---

## 왜 이런 툴이 필요한가

기획자가 여럿이면, 각자 **합리적으로** 쓴 룰이 함께 두면 모순된다:

- 기획자 A: "전사 최대 HP = 레벨 × 100"
- 기획자 B: "모든 캐릭터 HP는 5000을 넘지 않는다"
- 기획자 C: "레벨 상한은 100"

→ **레벨 51 전사**는 HP가 5100이어야 하는데 상한 5000과 충돌.
   즉 *존재할 수 없는 상태*가 조용히 만들어진다.

룰이 수백 개면 사람 눈으로 모든 조합을 검토하는 건 불가능하다.

---

## 기존 방식 vs RuleForge

| 방식 | 모순 발견 |
|------|-----------|
| 사람 리뷰 | 놓치기 쉬움 (조합 폭발) |
| 시뮬레이션 | **우연히** 그 상태를 만나야 발견 |
| **RuleForge** | 모순의 **존재 자체를 증명** (반례 없이도) |

핵심 원칙: **판정은 사람·LLM이 아니라 Z3(SMT solver)가 한다.**
결정론적이라 "거짓 일관성"을 환각하지 않는다.

---

## 알아둘 개념 (1) — DSL과 Z3

- **DSL**: 게임 룰을 산문 대신 **기계가 검증할 수 있는 구조**(YAML)로 작성.
  형식화하는 행위 자체가 숨은 가정을 드러낸다.
- **SMT solver / Z3**: `x + y <= 10 ∧ x > 3` 같은 산술 논리식을 푸는 도구.
  답은 셋 중 하나:
  - **sat** — 모든 제약을 만족하는 값이 존재 (예시 값을 줌)
  - **unsat** — 어떤 값으로도 전부 만족 불가 = **모순**
  - **unknown** — 시간초과/이론적 한계로 판단 못 함 (숨기지 않고 따로 보고)

---

## 알아둘 개념 (2) — 범인 룰과 도달성

- **unsat core (범인 룰)**: unsat일 때 Z3가 **모순을 일으킨 최소 룰 집합**을
  돌려준다. "이 룰들이 서로 싸운다"를 정확히 짚는다.
- **핵심 통찰**: 룰을 그냥 다 모아 unsat을 물으면 **모순을 놓친다.**
  Z3가 `role=mage`처럼 모순을 피해 가는 값을 골라버리기 때문.
- 그래서 **도달성 검사**: "기획자가 합법이라 여기는 상태(레벨 100 전사)를
  룰들이 봉쇄하는가?"를 묻는다. 봉쇄되면 모순.

---

## 설치 — 준비물은 uv 하나

```bash
# 1) uv 설치 (Python은 uv가 자동으로 받아온다)
#    https://docs.astral.sh/uv/getting-started/installation/

# 2) RuleForge 설치
uv tool install git+https://github.com/haje01/ruleforge.git

# 3) 어디서나 사용
ruleforge check <룰 폴더>
```

Windows 비개발자도 위 3단계면 끝. 별도 Python 설치 불필요.

---

## DSL 구조 — domain + rules

```yaml
domain:                       # ① 변수와 그 범위 선언
  variables:
    level: { type: int,  min: 1, max: 100 }
    hp:    { type: int,  min: 0 }
    role:  { type: enum, values: [warrior, mage, archer] }

rules:                        # ② 지켜야 할 룰
  - id: warrior_hp_formula
    when: "role == warrior"   # 조건 → Implies(when, then)
    then: "hp == level * 100"
  - id: global_hp_cap
    then: "hp <= 5000"
```

각 룰은 `id`로 추적되어, 모순 시 어떤 룰이 범인인지 짚을 수 있다.

---

## 검증 사례 — 모순을 짚어낸다

```bash
$ ruleforge check warrior.rule
```

```text
❌ 모순 1건이 발견되었습니다.

[1] role=warrior일 때 'level'은(는) 최대 50까지만
    도달 가능합니다 (선언 max=100).
    → 범인 룰: global_hp_cap, warrior_hp_formula
```

사람이 읽는 한국어로 **어떤 조건에서 / 무엇이 봉쇄됐고 / 누가 범인인지** 보고.
모순이면 종료코드 1 → **CI에서 PR마다 자동 차단** 가능.

---

## 팀 협업 — domain과 rules 분리

공유 도메인 1개 + 기획자별 rules 파일. 디렉토리째 검사하면 병합된다.

```
rules/
  _domain.rule     # 공유: 변수 정의만
  planner_a.rule   # 기획자 A: 전사 HP 공식 (rules만)
  planner_b.rule   # 기획자 B: HP 상한 (rules만)
```

```bash
ruleforge check rules/
```

→ 각 파일은 정상이어도, **합쳤을 때 생기는 파일 간 모순**까지 잡아낸다.
   (별도 import 구문 불필요 · 변수 충돌은 오류로 보고)

---

## 한계 (현재)

- **정수 선형 산술(LIA) 중심**: `level * 100`은 OK, 변수 × 변수(비선형)는
  느리거나 판단 불가 → 우회(상수화·구간분할)를 안내한다.
- **비목표**: 밸런스의 "재미" 평가(시뮬레이션 영역), 런타임 서버 검증 아님.
  **기획 단계 정적 검증** 도구다.
- **아직(2차 예정)**: 상호 배제 상태, 확률/실수(LRA), `Datatype` enum,
  CI PR 코멘트 연동.

---

<!-- _class: lead -->

# 감사합니다

## Q & A

<br>

GitHub: `github.com/haje01/ruleforge`
문서: `docs/concepts.md` · `examples/`
