# dungeon 규칙서

## 목차

- 게임 개요
- 직업과 목표 보물액
- 전투 데이터
- 게임의 흐름 — 탐험과 선택
- 전투
- 검증·추정 성질

## 게임 개요

### 용어집

| 변수 | 타입 | 설명 |
|---|---|---|
| `gold` | `int 0..30` | 지금 들고 있는 보물액 |
| `win_gold` | `int 0..30` | 목표 보물액 — `role`이 정하며 게임 내내 불변 |
| `room` | `enum { hall, l1, l2, l3 }` | 현재 위치 — 중앙 홀(hall)과 던전 1~3층 |
| `role` | `enum { rogue, cleric, fighter, wizard }` | 직업 — 게임 시작 시 하나를 고른다 |
| `monster` | `enum { none, goblin, dragon }` | 지금 마주친 몬스터(none이면 조우 없음) |
| `status` | `enum { exploring, won, dead }` | 게임 진행 상태 — 탐험 중·승리·사망 |
| `l2_goblins` | `int 0..2` | 2층 몬스터 덱에 남은 고블린 카드(비복원) |
| `l2_dragons` | `int 0..2` | 2층 몬스터 덱에 남은 드래곤 카드(비복원) |
| `fights` | `ghost int 0.. — 서술 변수(논리 검증 제외)` | 치른 전투 횟수 — 게임 노출량의 서술 지표 |

## 직업과 목표 보물액

### rogue_win_target — 제약

도적의 목표 보물액은 10

*출처 던전! 2012판 — 직업 카드(승리 조건) · 태그 balance*

- **언제**: `role == rogue`
- **항상**: `win_gold == 10`

> 직업이 강할수록 목표 보물액이 높다(클래스 밸런스 축) — 전투가 약한 `rogue`·`cleric`은 10, `fighter`는 20, 가장 강한 `wizard`는 30을 모아 귀환해야 승리한다.

### cleric_win_target — 제약

성직자의 목표 보물액은 10

- **언제**: `role == cleric`
- **항상**: `win_gold == 10`

### fighter_win_target — 제약

전사의 목표 보물액은 20

- **언제**: `role == fighter`
- **항상**: `win_gold == 20`

### wizard_win_target — 제약

마법사의 목표 보물액은 30

- **언제**: `role == wizard`
- **항상**: `win_gold == 30`

## 전투 데이터

### 표 reward

몬스터 처치 보상(보물액)

|  | 값 |
|---|---|
| **goblin** | 2 |
| **dragon** | 10 |

### 표 beat

격파 목표값 — 2d6이 이 값 이상이면 승리

|  | fighter | cleric | rogue | wizard |
|---|---|---|---|---|
| **goblin** | 4 | 5 | 6 | 5 |
| **dragon** | 7 | 9 | 11 | 6 |

### 표 fumble

치명 문턱 — 2d6이 이 값 이하면 사망

|  | fighter | cleric | rogue | wizard |
|---|---|---|---|---|
| **goblin** | 2 | 2 | 2 | 2 |
| **dragon** | 2 | 3 | 3 | 2 |

## 게임의 흐름 — 탐험과 선택

### 초기 상태

- **초기 상태**: `gold == 0 and room == hall and monster == none and status == exploring and l2_goblins == 2 and l2_dragons == 2 and fights == 0`

### claim_victory — 행동/사건

목표 보물액 달성 + 중앙 → 즉시 승리

*출처 던전! 2012판 — 승리 조건 · 태그 victory*

- **언제**: `room == hall and status == exploring and monster == none and gold >= win_gold`
- **효과**: `status = won`

> 목표 보물액(`win_gold`) 이상을 들고 중앙 홀로 돌아오면 즉시 승리한다.

### enter_l1 — 행동/사건

Great Hall에서 1층으로 진입(목표 미달) — 고블린 조우

*태그 explore*

- **언제**: `room == hall and status == exploring and monster == none and gold < win_gold`
- **효과**: `{ room = l1; monster = goblin }`

> 홀에서 목표가 아직 미달이면 1층으로 (재)진입한다 — 1층 조우는 항상 고블린이다.

### descend_l2 — 행동/사건

욕심: 2층으로 — 몬스터 덱에서 비복원 추출(남은 카드 수에 비례, D26)

*출처 던전! 2012판 — 레벨별 몬스터 카드 덱 · 태그 choice*

- **언제**: `room == l1 and status == exploring and monster == none and l2_goblins + l2_dragons > 0`
- **선호도(pref)**: `max(win_gold - gold, 0)`
- **결과** (확률 → 효과):
  - `l2_goblins / (l2_goblins + l2_dragons)` → `{ room = l2; monster = goblin; l2_goblins = l2_goblins - 1 }`
  - `l2_dragons / (l2_goblins + l2_dragons)` → `{ room = l2; monster = dragon; l2_dragons = l2_dragons - 1 }`

> 한 층을 클리어하면(조우 해소, `monster`가 none) 더 깊이 내려갈지 귀환할지 고른다 — 이 게임의 유일한 플레이어 선택이다.

> 2층 조우는 몬스터 덱에서 비복원으로 뽑는다: 남은 카드 수(`l2_goblins`·`l2_dragons`)에 비례하는 확률로 몬스터가 나오고, 뽑힌 카드는 줄어든다. 덱이 비면 더 내려갈 수 없다.

> 이 모델의 잠수 성향(욕심)은 남은 목표액에 비례한다 — 목표를 채우면 욕심이 0이 되어 반드시 귀환(`go_home`)한다.

### descend_l3 — 행동/사건

욕심: 3층으로 — 드래곤만

*태그 choice*

- **언제**: `room == l2 and status == exploring and monster == none`
- **선호도(pref)**: `max(win_gold - gold, 0)`
- **효과**: `{ room = l3; monster = dragon }`

> 3층에는 드래곤만 나온다 — 격파 목표값(`beat`)이 높아 가장 위험하고, 보상(`reward`)이 가장 크다.

### go_home — 행동/사건

안전: 지금 보물을 들고 중앙으로 귀환(목표 미달이면 hall에서 재진입)

*태그 choice*

- **언제**: `(room == l1 or room == l2 or room == l3) and status == exploring and monster == none`
- **선호도(pref)**: `5`
- **효과**: `room = hall`

> 지금 들고 있는 보물과 함께 중앙 홀로 귀환한다. 목표 미달이면 홀에서 다시 1층으로 들어가게 된다(`enter_l1`).

## 전투

### fight_${mon}_${cls} — 행동/사건

*템플릿 — mon ∈ {goblin, dragon} × cls ∈ {fighter, cleric, rogue, wizard} 조합마다 하나씩.*

직업×몬스터 전투 — 2d6 판정

*출처 던전! 2012판 — 전투 판정(2d6) · 태그 combat*

- **언제**: `role == cls and monster == mon and status == exploring`
- **결과** (확률 → 효과):
  - `chance(2d6 >= beat[mon][cls])` → `{ gold = min(gold + reward[mon], 30); monster = none; fights = fights + 1 }`
  - `chance(2d6 <= fumble[mon][cls])` → `{ gold = 0; room = hall; status = dead; monster = none; fights = fights + 1 }`
  - `rest` → `{ monster = none; fights = fights + 1 }`

> 전투는 2d6 판정이다 — 굴림이 격파 목표값(`beat`) 이상이면 승리해 보상(`reward`)을 얻고 몬스터는 사라진다. 치명 문턱(`fumble`) 이하면 사망해 보물을 모두 잃고 게임이 끝난다.

> 그 사이 굴림은 무소득 — 보상 없이 조우가 끝난다(실물 규칙의 재도전·후퇴는 이 모델에선 단순화). 확률 환산은 도구가 한다(chance/rest, D30) — 모델에는 룰북 수치만 남는다.

> 보상은 보물액 상한(30)에서 포화된다 — 상한을 넘는 초과분은 버린다.

### won_absorb — 행동/사건

모델링 — 승리 상태 유지(데드락 방지용 흡수)

*태그 modeling*

- **언제**: `status == won`
- **효과**: `status = won`

### dead_absorb — 행동/사건

모델링 — 사망 상태 유지(데드락 방지용 흡수)

*태그 modeling*

- **언제**: `status == dead`
- **효과**: `status = dead`

## 검증·추정 성질

이 규칙서의 아래 성질은 기계가 검증/추정한다 (`ludoforge bmc` 증명 · `ludoforge sim` 추정).

### winnable — 검증 성질

승리에 도달 가능(어떤 클래스로든 이길 길이 존재) — sim에선 직업별 승률

- **종류**: 도달 가능해야 함 (존재 — bmc 증명/sim 추정)
- **조건**: `status == won`

### rogue_winnable — 검증 성질

전투에 가장 약한 rogue도 승리 가능해야 한다(낮은 목표액으로 보상)

- **종류**: 도달 가능해야 함 (존재 — bmc 증명/sim 추정)
- **조건**: `role == rogue and status == won`

### wizard_winnable — 검증 성질

목표액이 가장 높은 wizard도 승리 가능해야 한다(주문으로 강한 몬스터 처치)

- **종류**: 도달 가능해야 함 (존재 — bmc 증명/sim 추정)
- **조건**: `role == wizard and status == won`

### dragon_reachable — 검증 성질

드래곤을 실제로 조우할 수 있어야 한다(욕심 정책으로 깊이 내려가면)

- **종류**: 도달 가능해야 함 (존재 — bmc 증명/sim 추정)
- **조건**: `monster == dragon`

### death_possible — 검증 성질

사망(패배)도 발생 가능 — 전투에 실제 위험이 있는지

- **종류**: 도달 가능해야 함 (존재 — bmc 증명/sim 추정)
- **조건**: `status == dead`

### gold_nonneg — 검증 성질

보물은 음수가 되지 않는다

- **종류**: 불변식 (항상 성립 — bmc 증명)
- **조건**: `gold >= 0`

### no_monster_in_hall — 검증 성질

규칙 건전성 — 중앙(hall)에는 몬스터가 따라오지 않는다

- **종류**: 불변식 (항상 성립 — bmc 증명)
- **조건**: `room != hall or monster == none`

### sound_victory — 검증 성질

규칙 건전성 — 목표액 미달 상태로는 결코 승리할 수 없어야 한다

- **종류**: 불변식 (항상 성립 — bmc 증명)
- **조건**: `status != won or gold >= win_gold`

### no_stuck — 검증 성질

막다른(후속 없는) 상태가 없어야 한다

- **종류**: 막다른 상태 없음 (bmc 증명)

### final_gold — 검증 성질

종료 시 확보한 보물 분포(sim 전용) — 정책의 욕심도에 따라 달라진다

- **종류**: 분포 추정 (sim 전용 — 증명 아님)
- **값**: `gold`

### fight_count — 검증 성질

게임당 전투 횟수 분포(`fights` — 서술 변수, D31) — 직업별 노출량·게임 길이의 대리

- **종류**: 분포 추정 (sim 전용 — 증명 아님)
- **값**: `fights`

> ghost 변수라 bmc/PRISM 상태공간엔 없다 — 검증 부하 0으로 얻는 서술 지표(sim 전용).
