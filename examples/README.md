# 예제 룰셋 모음

실제 게임 기획에서 나올 법한 모순을 담은 예제다. Ludoforge가 잡아내는 모순 유형
(범위 봉쇄 / enum 도달 불가 / 전역 over-constraint / 상태 봉쇄 / 실수 끝점 봉쇄 /
도달성 단언 미충족)과 정합 케이스를 보여준다.

각 파일은 **자기완결적**(domain + constraints)이라 개별로 검사한다.
서로 도메인이 달라 함께 병합하면 안 되므로 `ludoforge check examples/`처럼
디렉토리째 검사하지 말 것 — 파일을 하나씩 지정한다.

| 예제 | 모순 유형 | 기획 시나리오 |
|------|----------|--------------|
| [`item_enchant.lf`](item_enchant.lf) | 범위 봉쇄 | 전설 아이템 강화 한도(0~10)가 파워 상한(500)에 막혀 5까지만 가능 |
| [`loot_table.lf`](loot_table.lf) | 전역 over-constraint | 드롭 확률 합 100% 제약과 "common≥90%·epic≥15%"가 동시 성립 불가(105%) |
| [`drop_rates_real.lf`](drop_rates_real.lf) | 전역 over-constraint (실수) | 위 모순을 정수 스케일링 없이 실수 확률(합=1.0)로 직접 표현 (LRA, D7) |
| [`crit_chance.lf`](crit_chance.lf) | 실수 끝점 봉쇄 | 크리율을 [0,1]로 선언했지만 수확체감 룰(≤0.5)이 선언 최대값 1.0을 막음 (D9) |
| [`stat_budget.lf`](stat_budget.lf) | 도달성 단언 미충족 | `expect:`로 "공격·방어 동시 최대"를 단언했지만 예산 룰이 막음 — 변수별 경계로는 안 보이는 동시 도달성 (D10) |
| [`starter_zone_drops.lf`](starter_zone_drops.lf) | enum 도달 불가 | 레벨 상한 40인 초보 존에서 레벨 50+ 를 요구하는 unique 등급은 등장 불가 |
| [`stealth_combat.lf`](stealth_combat.lf) | 상태 봉쇄 | "항상 공격" 룰과 "은신·공격 상호 배제"가 함께 두면 은신 상태에 영영 도달 불가 (D6) |
| [`day_night_cycle.lf`](day_night_cycle.lf) | enum 도달 불가 (중복 값) | sky·lighting이 같은 값 이름(day/night)을 쓰며, 두 시스템이 밤 조명을 상충 강제해 sky=night 봉쇄 (D8) |
| [`balanced_stats.lf`](balanced_stats.lf) | (정합) | 공격력=레벨×10, 상한 500, 레벨 상한 50이 정확히 맞아떨어져 모순 없음 |
| [`balanced_build.lf`](balanced_build.lf) | (정합, expect 충족) | stat_budget과 같은 예산이지만 "공40·방40 균형 빌드"(합 80)는 도달 가능 → `expect:` 충족 (D10) |
| [`dungeon.lf`](dungeon.lf) | (전이 시스템, MDP+정책+덱) | 던전!(WotC 2012판) 통합 모델 — 클래스 4종·클래스별 전투(2d6 환산)에 **적응적 욕심 정책**(`pref max(win_gold - gold, 0)`, D26)과 **2층 몬스터 덱 비복원 추출**(남은 카드 수 비례 weight, D26)을 얹었다. **한 모델, 두 질문:** `bmc`로 건전성(클래스별 winnable·불변식·데드락 — k-귀납 증명 포함), `sim`으로 직업별 승률·보물 분포 추정 (D12·D15·D20·D23·D25·D26) |
| [`market_sim.lf`](market_sim.lf) | (전이 시스템, real) | 두 자산을 복리로 굴리는 **연속(real)·다변수** 모델 — `sim`이 분포로 추정(PRISM이 못 다루는 영역, D19) |
| [`team_example/`](team_example/) | (협업 패턴) | 공유 `_domain.lf` + 기획자별 constraints 파일을 디렉토리로 병합 검사 |

`team_example/`만은 여러 파일을 병합해야 하므로 **디렉토리째** 검사한다:
`ludoforge check examples/team_example/`. 나머지는 자기완결 파일이라 개별로 검사한다.

`dungeon.lf`은 정적 모순이 아니라 **전이 시스템**(init/transitions/checks) 예제다. 던전!(WotC
2012판)을 모델링해 클래스 4종(rogue·cleric·fighter·wizard, 목표 보물액 10·10·20·30)과
**클래스의존 전투**(같은 몬스터라도 클래스별 승률이 다름 — 2d6 격파 목표값을 확률로 환산),
몬스터 2종(고블린/드래곤)을 담는다. 한 층을 클리어하면 **"더 깊이(욕심) vs 귀환(안전)"** 을
고르는데 욕심이 **남은 목표액에 비례**하고(`pref max(win_gold - gold, 0)` — 상태 의존
정책, D26), 2층 조우는 **몬스터 덱에서 비복원 추출**한다(남은 카드 수에 비례하는 상태 의존
weight, 뽑힌 카드는 감소 — 실물 게임의 레벨별 몬스터 카드, D26). 한 모델을 **두 질문**으로
검사한다(dialect 분리, D11):

- 논리·건전성(`bmc`): "클래스별로 이길 길이 *존재*하는가·불변식·데드락" — `pref`를 무시하고
  비결정으로 탐색한다. `ludoforge bmc examples/dungeon.lf --k 14`
- 정량·추정(`sim`): "*이 정책*에서 직업별 승률·보물 분포는?" — role을 sweep하고 `pref`로
  선택을 표집한다("주어진 정책 하의 추정 · Pmax 아님" 라벨). `ludoforge sim examples/dungeon.lf -H 300 -n 20000`

8개 전투 전이(클래스×몬스터)는 `tables:`(전투 격파표) + 곱 `for:` 템플릿 한 벌로 펼쳐 쓴다
— 클래스·몬스터가 늘면 도메인 enum과 표의 행/열만 추가하면 된다(템플릿 확장 Tier 1+2,
CLAUDE.md §4.2 / D18).

> **참고(D23):** sim↔PRISM 교차검증용 DTMC 던전판은 사용자 예제가 아니라 테스트 오라클
> 픽스처(`tests/fixtures/oracle_dungeon.lf`)다 — `tests/test_sim_oracle.py`가 PRISM 정확값을
> sim 추정의 신뢰구간과 대조한다(PRISM은 D23으로 사용자 표면에서 내려 테스트 오라클로만 남음).

## 실행 예

```bash
$ ludoforge check examples/item_enchant.lf
❌ 모순 1건이 발견되었습니다.

[1] rarity=legendary일 때 'enchant_level'은(는) 최대 5까지만 도달 가능합니다 (선언 max=10).
    → 범인 룰: global_power_cap, legendary_power_formula
```

```bash
$ ludoforge check examples/balanced_stats.lf
✅ 모순이 발견되지 않았습니다.
```

각 모순이 다른 경로로 탐지된다는 점에 주목하자. `item_enchant`는 독립 변수(강화 레벨)의
선언 범위가 봉쇄된 경우, `starter_zone_drops`는 특정 enum 값(unique) 조합이 통째로
불가능한 경우, `loot_table`은 enum 없이 전역적으로 어떤 값 조합도 제약을 만족 못 하는
경우, `stealth_combat`은 자유 불리언 상태(은신=true)가 상호 배제로 봉쇄된 경우(D6),
`crit_chance`는 실수 변수의 선언 끝점(최대 1.0)이 룰로 봉쇄된 경우(D9), `stat_budget`은
`expect:`로 단언한 동시 도달성(공격·방어 동시 최대)을 룰이 막은 경우다(D10).
