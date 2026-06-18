# rules/ — 실제 기획 룰 (SSOT)

여기에 **당신의 실제 게임 룰**(`.rule` 파일)을 둔다. 이 디렉토리가 룰의
단일 진실 원천(SSOT)이며 git으로 버전 관리한다.

```bash
ludoforge check rules/
```

여러 기획자가 함께 쓴다면 공유 도메인 파일(`_domain.rule`) 하나와 기획자별
constraints 파일로 나눠 두면 된다. 동작하는 예시는 [`../examples/`](../examples/README.md) 참고.

> 사용법을 익히는 용도의 예제(아이템 강화·드롭 확률 등)는 모두 `examples/`에 있다.
> 이 디렉토리는 비워 두고 실제 룰만 채운다.
