# Ludoforge `.lf` 구문 강조 (VS Code)

Ludoforge 자체 문법(`.lf`, D21 외부 DSL)용 TextMate 문법 + 언어 설정이다. 키워드(`domain`·
`constraint`·`transition`·`for`·`table`·`check` 등), 타입(`int`/`real`/`bool`/`enum`), 논리
연산자(`and`/`or`/`not`), 비교/대입(`==`/`=`/`->`), 다음 상태 변수(`gold'`), `//` 주석,
문자열·`${...}` 보간, 수치를 강조한다.

## 설치 (VS Code · Cursor)

**권장 — Install from Location** (WSL/Remote 포함 어디서나 동작):

1. `Ctrl+Shift+P` → **`Developer: Install Extension from Location...`**
2. 이 **`editors/vscode-lf`** 폴더를 선택한다(폴더 바로 아래에 `package.json`이 있어야 함).
3. `Ctrl+Shift+P` → **`Developer: Reload Window`**.

이후 `.lf` 파일을 열면 자동으로 강조된다(우하단 언어 표시가 "Ludoforge DSL"). 안 되면
우하단 언어 칸을 클릭해 "Ludoforge DSL"을 고른다.

> **WSL/Remote 주의:** 확장 폴더를 `~/.vscode/extensions/`에 **수동 복사하면 Remote-WSL은
> 무시한다**(서버는 `~/.vscode-server/extensions/`를 읽음). 그래서 위 *Install from Location*을
> 쓰면 위치·리모트 문제를 우회한다. `Developer: Show Running Extensions`에 "Ludoforge DSL"이
> 보이면 로드 성공이다.

**대안 — VSIX 패키징:**
```bash
cd editors/vscode-lf && npx @vscode/vsce package   # ludoforge-lf-0.1.0.vsix 생성
# VS Code 확장 뷰 ⋯ 메뉴 → "Install from VSIX..."로 설치
```

## 다른 에디터

`syntaxes/lf.tmLanguage.json`은 표준 TextMate 문법이라 Sublime Text·Notepad++(NppTextMate
플러그인) 등 TextMate 문법을 받는 에디터에 그대로 쓸 수 있다.
