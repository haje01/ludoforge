# old_examples — 디프리케이트된 YAML `.rule` 예제

여기 있는 `.rule` 파일들은 **디프리케이트된 YAML DSL**(D21 이전 포맷)이다. 자체 문법 `.lf`로
이관되면서 사용자용 예제 자리([`../examples/`](../examples/))에서 내렸다.

남겨둔 이유는 **이관 회귀 골든 하니스** 때문이다 — `tests/test_text_loader.py`가
`examples/<name>.lf`와 여기 `old_examples/<name>.rule`이 **같은 IR**을 내는지 비교해, 자체
문법 로더가 기존 YAML과 의미상 등가임을 영구 검증한다(`test_example_lf_matches_yaml`,
`test_full_dungeon_golden_equivalence`).

- 새 예제는 [`../examples/`](../examples/)에 `.lf`로만 추가한다.
- `.rule`은 새로 만들지 않는다. 기존 `.lf`의 의미가 바뀌면 대응 `.rule`도 같이 고쳐
  골든 등가를 유지한다.
- 로더는 여전히 `.rule`(YAML)을 하위 호환으로 읽지만 로드 시 1회 디프리케이션 경고를 낸다.
