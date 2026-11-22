#!/usr/bin/env python3
"""관리 탭 '앱 홈'(타일 화면)과 '개인 앱스토어'.

- 타일은 기존 관리 칸(pane)을 앱처럼 묶어 보여 주고, 누르면 admPane(k)로 그 칸을 연다.
- 개인 앱 목록은 비공개 저장소 config/personal_apps.json 에서만 읽는다(공개 저장소에 주소 없음).
  https + 허용 도메인만 통과, 모든 글자는 이스케이프, 새 창은 rel="noopener noreferrer".
- 결과 HTML 은 관리 탭 암호문(ADMIN_PASSWORD) 안에만 들어간다.
"""
import html
import json
import os
from pathlib import Path
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
                   ("branch", "🗺️", "#475569", "s"), ("tb3", "📚", "#15803d", "s"), ("strat", "🎯", "#0f6cbd", "w"), ("intel", "🧠", "#4f46e5", "w"), ("vizm", "📊", "#0891b2", "s"), ("salesx", "📈", "#047857", "w"), ("vizx", "🎨", "#9333ea", "s"),
                   ("authors", "🎓", "#be185d", "w")]),
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


HOST_RX = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")  # 정확한 호스트명만(와일드카드·IP·포트 불가)


def _safe_url(u, extra=()):
    allow = ALLOW_HOSTS | set(extra)
    if not isinstance(u, str):
        return None
    u = u.strip()
    try:
        p = urlsplit(u)
    except ValueError:
        return None
    if p.scheme != "https" or (p.hostname or "") not in allow or p.username or p.password or p.port:
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
    # 추가 허용 도메인은 비공개 목록에만 둔다(공개 저장소에 내부 주소를 남기지 않기 위해). 정확한 호스트명만 인정.
    extra = {h.strip().lower() for h in raw.get("allow_hosts") or [] if isinstance(h, str) and HOST_RX.match(h.strip().lower())}
    out = []
    for a in raw.get("apps") or []:
        if not isinstance(a, dict):
            continue
        url = _safe_url(a.get("url"), extra)
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


def system_status():
    """관리센터 화면용 시스템 상태(수집원 신선도·마지막 전체 수집 점검·서울 날씨). 실패하면 None."""
    try:
        import freshness
        F = freshness.build({})
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 관리센터 신선도 실패: {type(e).__name__}")
        return None
    watch, full = {}, []
    try:
        W = [json.loads(l) for l in Path("history/pipeline_watch.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        full = [r for r in W if not r.get("quick")]
        if full:
            r = full[-1]
            watch = {"at": r.get("at"), "status": r.get("status"), "fail": r.get("fail") or [],
                     "checks": [{"n": c.get("n"), "ok": bool(c.get("ok")), "m": c.get("m", "")} for c in r.get("checks") or []]}
    except Exception:  # noqa: BLE001
        pass
    wx = {}
    try:
        d = json.loads(Path("live/weather.json").read_text(encoding="utf-8"))
        c = next((x for x in d.get("cities") or [] if x.get("city") == "서울"), None)
        if c and c.get("today"):
            wx = {"city": "서울", **{k: c["today"].get(k) for k in ("cond", "icon", "tmax", "tmin", "pop")}}
    except Exception:  # noqa: BLE001
        pass
    BLD = [("news", r"레이더|브리핑|조간"), ("g2b", r"나라장터|수의계약|낙찰|KERIS|AIEP|학교단위"), ("mkt", r"재정|학교알리미|NEIS|경기데이터|학원"),
           ("comp", r"카탈로그|선정 여론"), ("tch", r"교사|크리에이터|협력 후보"), ("biz", r"영업|운영 시트|일일 지표")]
    hist = []
    try:  # 최근 7회 전체 수집 결과(정상/실패)
        byd = {}
        for r in full:
            d = str(r.get("at", ""))[:10]
            byd[d] = byd.get(d, True) and r.get("status") == "ok"
        hist = [{"d": d[5:].replace("-", "/"), "ok": ok} for d, ok in sorted(byd.items())[-7:]]
    except Exception:  # noqa: BLE001
        pass
    meter = {}
    try:  # 외부 수집 월 사용량(무료 한도 보호용 상한 대비)
        u = json.loads(Path("history/firecrawl_usage.json").read_text(encoding="utf-8"))
        from datetime import datetime, timedelta, timezone
        ym = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m")
        meter = {"used": int(u.get(ym, 0)), "cap": int(os.environ.get("FIRECRAWL_MONTH_CAP", "500") or 500)}
    except Exception:  # noqa: BLE001
        pass
    mix = {}
    try:  # B2G 비중: 2026 실적 기준(prev) → 2027 계획, 목표 40%
        import plan2027
        P = plan2027.load_plan()
        if P:
            c = plan2027.chan(P)
            sh = lambda k: round(sum(c[x][k] for x in plan2027.B2G_KEYS) / max(1, sum(v[k] for v in c.values())) * 100)
            mix = {"prev": sh("prev"), "plan": sh("plan"), "target": 40}
    except Exception:  # noqa: BLE001
        pass
    rows = [{**{k: r.get(k) for k in ("name", "tab", "at", "age", "cad", "state")},
             "b": next((b for b, rx in BLD if re.search(rx, r.get("name") or "")), "mkt")} for r in F.get("rows") or []]
    return {"fresh": {"rows": rows, "checked": F.get("checked")}, "watch": watch, "wx": wx, "hist": hist, "meter": meter, "mix": mix}


def build(labels, live=None, apps=None, status=None):
    """labels: {pane: 이름}, live: {pane: (큰 숫자, 보조 문구)}, status: 관리센터 데이터(없으면 타일만)"""
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
    head = ""
    if status:
        head = ('<div class="ah-sw view-toggle" role="group" aria-label="앱 홈 보기" style="display:flex;justify-content:flex-end;gap:4px;margin:0 0 8px;">'
                '<button type="button" data-ahv="bm" aria-pressed="true">🐄 농장 작업장</button><button type="button" data-ahv="tile" aria-pressed="false">🟦 타일</button></div>'
                f'<div id="admBm" style="margin-bottom:16px;" data-p="{E(json.dumps(status, ensure_ascii=False, separators=(",", ":")))}"></div>')
    return (CSS + head + f'<div class="ah"{" id=admTiles hidden" if status else ""}><div class="ah-top"><div><h3>🔒 관리 앱 홈</h3>'
            f'<p>경영 앱 {n}개 · 개인 앱 {len(apps)}개 — 타일을 누르면 열리고, 위 탭 줄의 「🏠 앱 홈」으로 돌아옵니다</p></div>'
            '<input class="ah-q" type="search" placeholder="앱 검색 (예: 손익, 할 일)" aria-label="앱 검색" '
            'oninput="(function(q){q=q.trim();document.querySelectorAll(\'#adminBody .ah-t[data-q]\').forEach(function(t){t.classList.toggle(\'ah-hide\',!!q&&t.dataset.q.indexOf(q)<0);});})(this.value)"></div>'
            f'<div class="ah-groups">{"".join(groups)}</div>{store_section(apps)}</div>')


def build_store(apps=None):
    apps = personal_apps() if apps is None else apps
    return (CSS + '<div class="ah"><div class="ah-top"><div><h3>⭐ 개인 앱스토어</h3>'
            '<p>업무 밖 개인 웹 앱을 모아 두는 공간입니다. 새 아이디어가 생기면 채팅으로 주소를 알려 주세요.</p></div></div>'
            + store_section(apps, link=False) + '</div>')
