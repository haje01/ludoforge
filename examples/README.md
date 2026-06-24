# 예제 룰셋 모음

실제 게임 기획에서 나올 법한 모순을 담은 예제다. Ludoforge가 잡아내는 모순 유형
(범위 봉쇄 / enum 도달 불가 / 전역 over-constraint / 상태 봉쇄 / 실수 끝점 봉쇄 /
도달성 단언 미충족)과 정합 케이스를 보여준다.

각 파일은 **자기완결적**(domain + constraints)이라 개별로 검사한다.
서로 도메인이 달라 함께 병합하면 안 되므로 `ludoforge check examples/`처럼
디렉토리째 검사하지 말 것 — 파일을 하나씩 지정한다.

| 예제 | 모순 유형 | 기획 시나리오 |
|------|----------|--------------|
| [`item_enchant.rule`](item_enchant.rule) | 범위 봉쇄 | 전설 아이템 강화 한도(0~10)가 파워 상한(500)에 막혀 5까지만 가능 |
| [`loot_table.rule`](loot_table.rule) | 전역 over-constraint | 드롭 확률 합 100% 제약과 "common≥90%·epic≥15%"가 동시 성립 불가(105%) |
| [`drop_rates_real.rule`](drop_rates_real.rule) | 전역 over-constraint (실수) | 위 모순을 정수 스케일링 없이 실수 확률(합=1.0)로 직접 표현 (LRA, D7) |
| [`crit_chance.rule`](crit_chance.rule) | 실수 끝점 봉쇄 | 크리율을 [0,1]로 선언했지만 수확체감 룰(≤0.5)이 선언 최대값 1.0을 막음 (D9) |
| [`stat_budget.rule`](stat_budget.rule) | 도달성 단언 미충족 | `expect:`로 "공격·방어 동시 최대"를 단언했지만 예산 룰이 막음 — 변수별 경계로는 안 보이는 동시 도달성 (D10) |
| [`starter_zone_drops.rule`](starter_zone_drops.rule) | enum 도달 불가 | 레벨 상한 40인 초보 존에서 레벨 50+ 를 요구하는 unique 등급은 등장 불가 |
| [`stealth_combat.rule`](stealth_combat.rule) | 상태 봉쇄 | "항상 공격" 룰과 "은신·공격 상호 배제"가 함께 두면 은신 상태에 영영 도달 불가 (D6) |
| [`day_night_cycle.rule`](day_night_cycle.rule) | enum 도달 불가 (중복 값) | sky·lighting이 같은 값 이름(day/night)을 쓰며, 두 시스템이 밤 조명을 상충 강제해 sky=night 봉쇄 (D8) |
| [`balanced_stats.rule`](balanced_stats.rule) | (정합) | 공격력=레벨×10, 상한 500, 레벨 상한 50이 정확히 맞아떨어져 모순 없음 |
| [`balanced_build.rule`](balanced_build.rule) | (정합, expect 충족) | stat_budget과 같은 예산이지만 "공40·방40 균형 빌드"(합 80)는 도달 가능 → `expect:` 충족 (D10) |
| [`dungeon.rule`](dungeon.rule) | (전이 시스템, MDP) | 던전!(WotC 2012판) 모델 — 클래스 4종·클래스별 전투 난이도(2d6 환산)·몬스터 2종(고블린/드래곤)·조우→전투·승패. 보물 모아 중앙 귀환 승리, 전투 실패 시 드물게 사망. `bmc`/`prob`로 검사 (D12·D15·D16) |
| [`dungeon_sim.rule`](dungeon_sim.rule) | (전이 시스템, DTMC) | 던전판을 **전략 해소(DTMC)**해 `sim`(Monte Carlo)으로 직업별 승률을 추정. win_gold는 클래스별 constraints 파생. PRISM 정확값과 교차검증 (D19) |
| [`dungeon_policy.rule`](dungeon_policy.rule) | (전이 시스템, MDP+정책) | "욕심 vs 안전"을 가드가 아니라 **`pref`(무작위 정책)**로 가른 던전판. 규칙과 전략을 분리 — `sim`이 정책 하에서 보물 분포·전멸 위험을 추정("Pmax 아님" 라벨) (D20) |
| [`team_example/`](team_example/) | (협업 패턴) | 공유 `_domain.rule` + 기획자별 constraints 파일을 디렉토리로 병합 검사 |

`team_example/`만은 여러 파일을 병합해야 하므로 **디렉토리째** 검사한다:
`ludoforge check examples/team_example/`. 나머지는 자기완결 파일이라 개별로 검사한다.

`dungeon.rule`은 정적 모순이 아니라 **전이 시스템**(init/transitions/checks) 예제다.
던전!(WotC 2012판)을 모델링해 클래스 4종(rogue·cleric·fighter·wizard, 목표 보물액 10·10·20·30)과
**클래스의존 전투**(같은 몬스터라도 클래스별 승률이 다름 — 2d6 격파 목표값을 확률로 환산),
몬스터 2종(고블린/드래곤)·조우→전투·승리/패배를 담았다. 정적 `check`로는 모순이 없고, 동역학은
두 백엔드로 검사한다:
- 논리(승리/사망 도달성·불변식·규칙 건전성·데드락): `ludoforge bmc examples/dungeon.rule --k 12` (D15, k 유계)
- 확률(최적 전략 승리 확률 등 PCTL): `ludoforge prob examples/dungeon.rule` (D16, PRISM 설치 시)

`dungeon_sim.rule`은 같은 던전을 **DTMC(전략 해소)**로 다시 쓴 sim 백엔드 예제다. 던전!(MDP)은
중앙 귀환 시 "더 탐험 vs 승리 선언"처럼 *선택*이 있어 sim(표집)으로 못 본다 — 이를 가드에
인코딩("목표 미달이면 싸우고, 달성이면 귀환·승리")해 결정적으로 만든다. `win_gold`는 클래스별
constraints로 파생한다. Monte Carlo로 직업별 승률을 *추정*하고(증명 아님, 신뢰구간 동반),
소형이라 PRISM 정확값과 교차검증한다(D19):
- 추정(직업별 승률·기대 보물 분포): `ludoforge sim examples/dungeon_sim.rule -n 20000 -w 4`
- 교차검증(role 고정 시 PRISM Pmax=정확값 ↔ sim CI): `tests/test_sim_oracle.py`

8개 전투 전이(클래스×몬스터)는 `tables:`(전투 격파표) + 곱 `for:` 템플릿 한 벌로 펼쳐 쓴다
— 클래스·몬스터가 늘면 도메인 enum과 표의 행/열만 추가하면 된다(템플릿 확장 Tier 1+2,
CLAUDE.md §4.2 / D18).

`dungeon_policy.rule`은 던전을 **MDP로 두고 플레이어 전략을 `pref`로 분리한** sim 예제다.
`dungeon_sim.rule`이 전략을 가드에 박아 선택을 없앤 것과 달리, 던전에서 "한 번 더 싸운다
(fight)" vs "귀환한다(leave)"를 동시에 enabled로 두고 `pref`(욕심 0.6 : 안전 0.4)로 표집한다
(무작위 정책, D20). 환경 우연(승/사망)은 outcome `weight`로 그대로 둔다 — 매 스텝 **2단
표집**(정책→우연). 같은 규칙을 `pref`만 바꿔 다른 전략으로 돌릴 수 있다:
- 추정(보물 분포·전멸 위험; "주어진 정책 하의 추정 · Pmax 아님" 라벨): `ludoforge sim examples/dungeon_policy.rule -n 5000`
- BMC·PRISM은 `pref`를 무시하고 fight/leave를 비결정으로 본다(dialect 분리): `ludoforge bmc examples/dungeon_policy.rule --k 8`

## 실행 예

```bash
$ ludoforge check examples/item_enchant.rule
❌ 모순 1건이 발견되었습니다.

[1] rarity=legendary일 때 'enchant_level'은(는) 최대 5까지만 도달 가능합니다 (선언 max=10).
    → 범인 룰: global_power_cap, legendary_power_formula
```

```bash
$ ludoforge check examples/balanced_stats.rule
✅ 모순이 발견되지 않았습니다.
```

각 모순이 다른 경로로 탐지된다는 점에 주목하자. `item_enchant`는 독립 변수(강화 레벨)의
선언 범위가 봉쇄된 경우, `starter_zone_drops`는 특정 enum 값(unique) 조합이 통째로
불가능한 경우, `loot_table`은 enum 없이 전역적으로 어떤 값 조합도 제약을 만족 못 하는
경우, `stealth_combat`은 자유 불리언 상태(은신=true)가 상호 배제로 봉쇄된 경우(D6),
`crit_chance`는 실수 변수의 선언 끝점(최대 1.0)이 룰로 봉쇄된 경우(D9), `stat_budget`은
`expect:`로 단언한 동시 도달성(공격·방어 동시 최대)을 룰이 막은 경우다(D10).
