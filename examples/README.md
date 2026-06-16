# 예제 룰셋 모음

실제 게임 기획에서 나올 법한 모순을 담은 예제다. RuleForge가 잡아내는 네 가지
모순 유형(범위 봉쇄 / enum 도달 불가 / 전역 over-constraint / 상태 봉쇄)과 정합 케이스를 보여준다.

각 파일은 **자기완결적**(domain + rules)이라 개별로 검사한다.
서로 도메인이 달라 함께 병합하면 안 되므로 `ruleforge check examples/`처럼
디렉토리째 검사하지 말 것 — 파일을 하나씩 지정한다.

| 예제 | 모순 유형 | 기획 시나리오 |
|------|----------|--------------|
| [`item_enchant.rule`](item_enchant.rule) | 범위 봉쇄 | 전설 아이템 강화 한도(0~10)가 파워 상한(500)에 막혀 5까지만 가능 |
| [`loot_table.rule`](loot_table.rule) | 전역 over-constraint | 드롭 확률 합 100% 제약과 "common≥90%·epic≥15%"가 동시 성립 불가(105%) |
| [`drop_rates_real.rule`](drop_rates_real.rule) | 전역 over-constraint (실수) | 위 모순을 정수 스케일링 없이 실수 확률(합=1.0)로 직접 표현 (LRA, D7) |
| [`starter_zone_drops.rule`](starter_zone_drops.rule) | enum 도달 불가 | 레벨 상한 40인 초보 존에서 레벨 50+ 를 요구하는 unique 등급은 등장 불가 |
| [`stealth_combat.rule`](stealth_combat.rule) | 상태 봉쇄 | "항상 공격" 룰과 "은신·공격 상호 배제"가 함께 두면 은신 상태에 영영 도달 불가 (D6) |
| [`balanced_stats.rule`](balanced_stats.rule) | (정합) | 공격력=레벨×10, 상한 500, 레벨 상한 50이 정확히 맞아떨어져 모순 없음 |
| [`team_example/`](team_example/) | (협업 패턴) | 공유 `_domain.rule` + 기획자별 rules 파일을 디렉토리로 병합 검사 |

`team_example/`만은 여러 파일을 병합해야 하므로 **디렉토리째** 검사한다:
`ruleforge check examples/team_example/`. 나머지는 자기완결 파일이라 개별로 검사한다.

## 실행 예

```bash
$ ruleforge check examples/item_enchant.rule
❌ 모순 1건이 발견되었습니다.

[1] rarity=legendary일 때 'enchant_level'은(는) 최대 5까지만 도달 가능합니다 (선언 max=10).
    → 범인 룰: global_power_cap, legendary_power_formula
```

```bash
$ ruleforge check examples/balanced_stats.rule
✅ 모순이 발견되지 않았습니다.
```

네 가지 모순이 각각 다른 경로로 탐지된다는 점에 주목하자. `item_enchant`는
독립 변수(강화 레벨)의 선언 범위가 봉쇄된 경우, `starter_zone_drops`는 특정 enum
값(unique) 조합이 통째로 불가능한 경우, `loot_table`은 enum 없이 전역적으로 어떤
값 조합도 제약을 만족 못 하는 경우, `stealth_combat`은 자유 불리언 상태(은신=true)가
상호 배제로 봉쇄된 경우다(D6).
