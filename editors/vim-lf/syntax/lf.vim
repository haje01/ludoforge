" Vim syntax file
" Language:   Ludoforge DSL (.lf)
" Maintainer: Ludoforge
" 자체 문법(.lf, D21 외부 DSL)용 구문 강조. VS Code TextMate 문법
" (editors/vscode-lf)과 키워드·연산자 집합을 맞춘다.

if exists("b:current_syntax")
  finish
endif

" 주석 — // 부터 줄 끝까지
syn match   lfComment        "//.*$" contains=@Spell

" 문자열 — id 이름 보간 ${...} 포함
syn region  lfString         start=+"+ skip=+\\"+ end=+"+ contains=lfInterp
syn match   lfInterp         "\${[^}]*}" contained

" 수치 (정수·실수)
syn match   lfNumber         "\<-\?\d\+\(\.\d\+\)\?\>"

" 제어 키워드 (선언·블록·전이 구문)
syn keyword lfKeyword        domain table for in constraint transition check
syn keyword lfKeyword        expect init when then outcomes pref desc author

" check 종류 (질의 dialect)
syn keyword lfQueryKind      reachable invariant no_deadlock distribution prob

" 논리 연산자
syn keyword lfLogical        and or not

" 타입
syn keyword lfType           int real bool enum

" 연산자 — 비교/대입/화살표/범위/산술
syn match   lfComparison     "==\|!=\|<=\|>=\|<\|>"
syn match   lfArrow          "->"
syn match   lfRange          "\.\."
syn match   lfAssign         "="
syn match   lfArith          "[+\-*/]"

" 하이라이트 그룹 연결
hi def link lfComment        Comment
hi def link lfString         String
hi def link lfInterp         Special
hi def link lfNumber         Number
hi def link lfKeyword        Keyword
hi def link lfQueryKind      Type
hi def link lfLogical        Operator
hi def link lfType           Type
hi def link lfComparison     Operator
hi def link lfArrow          Operator
hi def link lfRange          Operator
hi def link lfAssign         Operator
hi def link lfArith          Operator

let b:current_syntax = "lf"
