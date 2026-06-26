# Ludoforge `.lf` 구문 강조 (Vim / Neovim)

Ludoforge 자체 문법(`.lf`, D21 외부 DSL)용 Vim 구문 강조 플러그인이다. 키워드(`domain`·
`constraint`·`transition`·`for`·`table`·`check` 등), 타입(`int`/`real`/`bool`/`enum`), 논리
연산자(`and`/`or`/`not`), 비교/대입(`==`/`=`/`->`), `//` 주석, 문자열·`${...}` 보간, 수치를
강조한다. (VS Code용 TextMate 문법 [`../vscode-lf`](../vscode-lf)와 키워드 집합을 맞춘다.)

```
vim-lf/
  ftdetect/lf.vim    # *.lf → filetype=lf 인식
  syntax/lf.vim      # 구문 강조 규칙
  ftplugin/lf.vim    # 주석 문자열(//)·들여쓰기(4칸) 설정
```

## 설치

### Vim 8+ / Neovim — packages (플러그인 매니저 없이)

이 `vim-lf` 폴더를 패키지 경로에 심볼릭 링크하거나 복사한다.

```bash
# Vim
mkdir -p ~/.vim/pack/ludoforge/start
ln -s "$PWD/editors/vim-lf" ~/.vim/pack/ludoforge/start/vim-lf

# Neovim
mkdir -p ~/.local/share/nvim/site/pack/ludoforge/start
ln -s "$PWD/editors/vim-lf" ~/.local/share/nvim/site/pack/ludoforge/start/vim-lf
```

창을 다시 열면 `.lf` 파일이 자동으로 강조된다.

### 플러그인 매니저

- **vim-plug:** `Plug '<repo>', { 'rtp': 'editors/vim-lf' }`
- **lazy.nvim:** `{ '<repo>', config = function() end }` 후 `editors/vim-lf`를 `rtp`에 추가.
- **packer.nvim:** `use { '<repo>', rtp = 'editors/vim-lf' }`

`<repo>`는 이 저장소의 git URL 또는 로컬 경로다.

### 빠른 임시 적용 (설치 없이)

플러그인을 깔지 않고 한 세션만 보려면 `~/.vimrc`(또는 `init.vim`)에:

```vim
autocmd BufRead,BufNewFile *.lf set filetype=lf
set runtimepath+=/path/to/ludoforge/editors/vim-lf
```

## 확인

`.lf` 파일을 연 뒤 `:set filetype?` 가 `filetype=lf` 면 인식 성공이다. 강조가 안 보이면
`:syntax on` 이 켜져 있는지 확인한다.
