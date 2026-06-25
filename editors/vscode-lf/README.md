# Ludoforge `.lf` 구문 강조 (VS Code)

Ludoforge 자체 문법(`.lf`, D21 외부 DSL)용 TextMate 문법 + 언어 설정이다. 키워드(`domain`·
`constraint`·`transition`·`for`·`table`·`check` 등), 타입(`int`/`real`/`bool`/`enum`), 논리
연산자(`and`/`or`/`not`), 비교/대입(`==`/`=`/`->`), 다음 상태 변수(`gold'`), `//` 주석,
문자열·`${...}` 보간, 수치를 강조한다.

## 설치 (VS Code · Cursor)

개발용 로컬 설치 — 둘 중 하나:

1. **심볼릭 링크**(권장): 이 폴더를 확장 디렉토리에 연결한다.
   ```bash
   # macOS/Linux
   ln -s "$(pwd)/editors/vscode-lf" ~/.vscode/extensions/ludoforge-lf
   # 이후 VS Code 재시작
   ```
   Windows(PowerShell, 관리자):
   ```powershell
   New-Item -ItemType Junction -Path "$HOME\.vscode\extensions\ludoforge-lf" -Target "editors\vscode-lf"
   ```
2. **VSIX 패키징**: `npm i -g @vscode/vsce && vsce package` 후 생성된 `.vsix`를
   VS Code "Extensions: Install from VSIX…"로 설치.

설치 후 `.lf` 파일이 자동으로 강조된다.

## 다른 에디터

`syntaxes/lf.tmLanguage.json`은 표준 TextMate 문법이라 Sublime Text·Notepad++(NppTextMate
플러그인) 등 TextMate 문법을 받는 에디터에 그대로 쓸 수 있다.
