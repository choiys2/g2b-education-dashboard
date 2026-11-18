#!/usr/bin/env python3
"""관리 탭 '앱 홈'(타일 화면)과 '개인 앱스토어'.

- 타일은 기존 관리 칸(pane)을 앱처럼 묶어 보여 주고, 누르면 admPane(k)로 그 칸을 연다.
- 개인 앱 목록은 비공개 저장소 config/personal_apps.json 에서만 읽는다(공개 저장소에 주소 없음).
  https + 허용 도메인만 통과, 모든 글자는 이스케이프, 새 창은 rel="noopener noreferrer".
- 결과 HTML 은 관리 탭 암호문(ADMIN_PASSWORD) 안에만 들어간다.
"""
import html
import json
import re
from urllib.parse import urlsplit

E = html.escape
ALLOW_HOSTS = {"claude.ai", "choiys2.github.io"}
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# (그룹, [(pane 키, 아이콘, 색, 크기)])  크기: s=1칸, w=가로 2칸, l=2x2
GROUPS = [
    ("경영", [("exec", "📊", "#0f6cbd", "l"), ("decide", "⚖️", "#b91c1c", "w"), ("plan", "🗓️", "#0369a1", "s"), ("weekly", "📝", "#475569", "s")]),
    ("나의 업무", [("actions", "✅", "#c2410c", "l"), ("schedule", "📅", "#0e7a6e", "w"), ("aiops", "🤖", "#7c3aed", "w")]),
    ("영업 · 시장", [("edu", "🏛️", "#0369a1", "w"), ("comp", "🔍", "#b91c1c", "s"), ("sales", "🧾", "#a16207", "s"),
                   ("branch", "🗺️", "#475569", "s"), ("tb3", "📚", "#15803d", "s"), ("strat", "🎯", "#0f6cbd", "w")]),
    ("상품 · 매출", [("cpl", "💰", "#15803d", "l"), ("mkt", "📣", "#be185d", "w"), ("samall", "🛒", "#c2410c", "s"), ("b2c", "👤", "#7c3aed", "s")]),
    ("시스템", [("sys", "🧩", "#475569", "x")]),
]

CSS = """<style>
.ah{background:var(--surface-2, #f6f7f9);color:var(--ink, inherit);border:1px solid var(--border, #e5e7eb);border-radius:14px;padding:18px 16px 20px;margin:0 0 16px;}
.ah-top{display:flex;justify-content:space-between;align-items:flex-end;gap:10px;flex-wrap:wrap;margin-bottom:14px;}
.ah-top h3{margin:0;font-size:21px;font-weight:800;color:var(--ink, inherit);}.ah-top p{margin:3px 0 0;font-size:12.5px;color:var(--muted, #6b7280);}
.ah-q{background:var(--surface, #fff);border:1px solid var(--border, #d1d5db);border-radius:999px;padding:7px 14px;color:inherit;font:inherit;font-size:13px;min-width:200px;}
.ah-q::placeholder{color:var(--muted, #9ca3af);}
.ah-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:20px;}
.ah-g h4{margin:0 0 8px;font-size:12.5px;font-weight:700;letter-spacing:.3px;color:var(--ink-2, #374151);}
.ah-tiles{display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:82px;gap:8px;}
.ah-t{all:unset;box-sizing:border-box;position:relative;border-radius:6px;padding:10px 12px;color:#fff;cursor:pointer;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;transition:transform .12s,box-shadow .12s;}
.ah-t:hover,.ah-t:focus-visible{transform:scale(1.03);box-shadow:0 6px 16px rgba(0,0,0,.18);outline:2px solid var(--accent, #2563eb);outline-offset:1px;}
.ah-t .ic{font-size:22px;line-height:1;}.ah-t .nm{font-size:12.5px;font-weight:700;line-height:1.3;}.ah-t .lv{font-size:11.5px;opacity:.9;line-height:1.3;}
.ah-t .big{font-size:23px;font-weight:800;line-height:1.1;}
.ah-w{grid-column:span 2;}.ah-l{grid-column:span 2;grid-row:span 2;}.ah-x{grid-column:span 4;}
.ah-me{margin-top:18px;padding:14px;border-radius:10px;background:var(--surface, #fff);border:1px dashed var(--border, #cbd5e1);}
.ah-me h4{color:var(--ink, inherit);font-size:14px;margin:0 0 10px;cursor:pointer;}.ah-me h4 span{font-size:11.5px;color:var(--muted, #6b7280);font-weight:500;}
.ah-me .ah-tiles{grid-template-columns:repeat(6,1fr);}
.ah-add{background:var(--surface-2, #f6f7f9);color:var(--ink, #111)!important;border:1px dashed var(--border, #cbd5e1);align-items:center;justify-content:center;text-align:center;cursor:default;}
.ah-add:hover{transform:none;box-shadow:none;outline:none;}
.ah-hide{display:none!important;}
.adm-tabs button[data-pane=home]{font-weight:800;}
@media (max-width:640px){.ah-tiles,.ah-me .ah-tiles{grid-template-columns:repeat(2,1fr);}.ah-x{grid-column:span 2;}.ah-top h3{font-size:18px;}.ah-q{min-width:0;width:100%;}}
</style>"""


def _safe_url(u):
    if not isinstance(u, str):
        return None
    u = u.strip()
    try:
        p = urlsplit(u)
    except ValueError:
        return None
    if p.scheme != "https" or (p.hostname or "") not in ALLOW_HOSTS or p.username or p.password or p.port:
        return None
    if re.search(r"[\s\"'<>`]", u):
        return None
    return u


def personal_apps():
    """비공개 저장소 config/personal_apps.json → 검증된 앱 목록(주소는 출력하지 않음)."""
    try:
        from strategy_room import _private
        d = _private()
        f = d / "config" / "personal_apps.json" if d else None
        raw = json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else {}
    except Exception as e:  # noqa: BLE001
        print("개인 앱 목록 오류:", type(e).__name__)
        raw = {}
    out = []
    for a in raw.get("apps") or []:
        if not isinstance(a, dict):
            continue
        url = _safe_url(a.get("url"))
        if not url or not str(a.get("name") or "").strip():
            continue
        col = a.get("color") if isinstance(a.get("color"), str) and COLOR.match(a.get("color")) else "#0f6cbd"
        out.append({"name": str(a["name"])[:30], "desc": str(a.get("desc") or "")[:40], "icon": str(a.get("icon") or "🔗")[:4], "color": col, "url": url})
    print(f"개인 앱: {len(out)}개")
    return out


def _store_tiles(apps):
    t = "".join(
        f'<a class="ah-t ah-w" href="{E(a["url"])}" target="_blank" rel="noopener noreferrer" style="background:{a["color"]};" data-q="{E(a["name"] + " " + a["desc"])}">'
        f'<span class="ic">{E(a["icon"])}</span><div><div class="nm">{E(a["name"])}</div><div class="lv">{E(a["desc"])} ↗</div></div></a>' for a in apps)
    t += ('<div class="ah-t ah-w ah-add"><div><div style="font-size:22px;">＋</div><div class="nm">앱 추가</div>'
          '<div class="lv">채팅으로 주소를 알려 주시면 연결합니다</div></div></div>')
    return f'<div class="ah-tiles">{t}</div>'


def store_section(apps, link=True):
    head = ('<h4 onclick="admPane(\'apps\')" title="개인 앱스토어 열기">⭐ 개인 앱스토어 <span>— 나만의 웹 앱 연결 공간 · 새 창으로 열림</span></h4>' if link
            else '<h4>⭐ 개인 앱스토어 <span>— 나만의 웹 앱 연결 공간 · 새 창으로 열림</span></h4>')
    return f'<section class="ah-me">{head}{_store_tiles(apps)}</section>'


def build(labels, live=None, apps=None):
    """labels: {pane: 이름}, live: {pane: (큰 숫자, 보조 문구)}"""
    live = live or {}
    apps = personal_apps() if apps is None else apps
    groups = []
    for g, items in GROUPS:
        tiles = []
        for k, ic, col, size in items:
            if k not in labels:
                continue
            big, sub = live.get(k, ("", ""))
            name = labels[k]
            cls = {"w": " ah-w", "l": " ah-l", "x": " ah-x"}.get(size, "")
            body = (f'<div>{f"<div class=big>{E(big)}</div>" if big and size == "l" else ""}<div class="nm">{E(name)}</div>'
                    f'{f"<div class=lv>{E(sub)}</div>" if sub and size != "s" else ""}</div>')
            tiles.append(f'<button type="button" class="ah-t{cls}" style="background:{col};" onclick="admPane(\'{k}\')" data-q="{E(name + " " + sub)}">'
                         f'<span class="ic">{ic}</span>{body}</button>')
        groups.append(f'<section class="ah-g"><h4>{E(g)}</h4><div class="ah-tiles">{"".join(tiles)}</div></section>')
    n = sum(len(i) for _, i in GROUPS)
    return (CSS + '<div class="ah"><div class="ah-top"><div><h3>🔒 관리 앱 홈</h3>'
            f'<p>경영 앱 {n}개 · 개인 앱 {len(apps)}개 — 타일을 누르면 열리고, 위 탭 줄의 「🏠 앱 홈」으로 돌아옵니다</p></div>'
            '<input class="ah-q" type="search" placeholder="앱 검색 (예: 손익, 할 일)" aria-label="앱 검색" '
            'oninput="(function(q){q=q.trim();document.querySelectorAll(\'#adminBody .ah-t[data-q]\').forEach(function(t){t.classList.toggle(\'ah-hide\',!!q&&t.dataset.q.indexOf(q)<0);});})(this.value)"></div>'
            f'<div class="ah-groups">{"".join(groups)}</div>{store_section(apps)}</div>')


def build_store(apps=None):
    apps = personal_apps() if apps is None else apps
    return (CSS + '<div class="ah"><div class="ah-top"><div><h3>⭐ 개인 앱스토어</h3>'
            '<p>업무 밖 개인 웹 앱을 모아 두는 공간입니다. 새 아이디어가 생기면 채팅으로 주소를 알려 주세요.</p></div></div>'
            + store_section(apps, link=False) + '</div>')
