" Ludoforge DSL — 편집 동작 설정
if exists("b:did_ftplugin")
  finish
endif
let b:did_ftplugin = 1

" // 주석 (gc·주석 토글·자동 줄바꿈용)
setlocal commentstring=//\ %s
setlocal comments=://

" 들여쓰기 — 블록은 4칸(자체 문법 관례)
setlocal expandtab
setlocal shiftwidth=4
setlocal softtabstop=4
