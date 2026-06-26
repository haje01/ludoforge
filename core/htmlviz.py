"""HTML 리포트 인터랙션 조각(D19): 의존성 없는 경량 호버 툴팁.

sim 백엔드의 자체 완결형 HTML이 쓴다 — 커서 위치의 값을 호버로 보여주는 작은 바닐라 JS와
그 스타일이다. 막대·히스토그램 칸처럼 값이 도형에만 인코딩돼 직접 보이지 않는 요소에서
유용하다(BMC HTML은 상태 카드가 값을 인라인으로 다 펼쳐 호버가 불필요하므로 쓰지 않는다).
Plotly 같은 외부 라이브러리·CDN을 쓰지 않아 오프라인에서 그대로 동작하고 리포트가 비대해지지
않는다(자체 완결성 유지). `data-tip` 속성을 가진 요소에 마우스를 올리면 그 텍스트를 띄운다.
"""

from __future__ import annotations

# <style>에 덧붙이는 툴팁 스타일.
TOOLTIP_CSS = """
.tip { position: fixed; pointer-events: none; z-index: 30; display: none;
  background: #1c2128; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px;
  padding: .3rem .55rem; font-size: .8rem; max-width: 320px; white-space: pre-wrap;
  box-shadow: 0 2px 10px rgba(0,0,0,.5); font-variant-numeric: tabular-nums; }
[data-tip] { cursor: crosshair; }
[data-tip]:hover { filter: brightness(1.18); }
"""

# </body> 직전에 넣는 인라인 스크립트. 단일 툴팁 div를 만들고 mousemove로 따라다닌다.
TOOLTIP_JS = """
<script>
(function () {
  var tip = document.createElement('div');
  tip.className = 'tip';
  document.body.appendChild(tip);
  document.addEventListener('mousemove', function (e) {
    var el = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (!el) { tip.style.display = 'none'; return; }
    tip.textContent = el.getAttribute('data-tip');
    tip.style.display = 'block';
    var pad = 14, x = e.clientX + pad, y = e.clientY + pad;
    var r = tip.getBoundingClientRect();
    if (x + r.width > window.innerWidth) x = e.clientX - r.width - pad;
    if (y + r.height > window.innerHeight) y = e.clientY - r.height - pad;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  });
})();
</script>
"""
