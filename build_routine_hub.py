#!/usr/bin/env python3
"""
routines/team.json  ->  live/routines/index.html

루틴 7종을 "7명의 비서와 나누는 대화"로 보여주는 아이메시지 스타일 허브.
왼쪽은 대화 목록(예정됨 필터 포함), 오른쪽은 스레드. 데이터가 없으면
아무것도 만들지 않는다.

사용:
    python build_routine_hub.py [team.json] [out_dir]
"""
import html
import json
import sys
from pathlib import Path

from routine_avatars import avatar_svg

INLINE_OK = ["<strong>", "</strong>", "<em>", "</em>", "<br>"]


def rich(text):
    """**강조** 와 최소 인라인 태그만 살리고 나머지는 이스케이프한다."""
    out = html.escape(text or "")
    for tag in INLINE_OK:
        out = out.replace(html.escape(tag), tag)
    parts = out.split("**")
    if len(parts) > 2:
        out = "".join(
            p if i % 2 == 0 else f"<strong>{p}</strong>" for i, p in enumerate(parts)
        )
    return out


def plain(text):
    return html.escape(str(text or ""))


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --sys:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Helvetica Neue",
        "Apple SD Gothic Neo","Pretendard Variable",Pretendard,"Malgun Gothic",
        "Noto Sans KR",sans-serif;
  --bg:#FFFFFF; --bg-side:#FFFFFF; --chrome:rgba(249,249,249,.82);
  --hair:rgba(0,0,0,.13); --hair-soft:rgba(0,0,0,.07);
  --ink:#000000; --ink-2:#8A8A8E; --ink-3:#AEAEB2;
  --in-bg:#E9E9EB; --in-ink:#000000;
  --out-1:#2E9BFB; --out-2:#1180F5; --out-ink:#FFFFFF;
  --blue:#007AFF; --field:#EFEFF0; --sel:#3B82F6;
  --card:rgba(255,255,255,.55); --card-line:rgba(0,0,0,.10);
  --hot:#FF3B30; --warm:#FF9500; --good:#28A745; --cool:#8E8E93;
  --shadow:0 1px 2px rgba(0,0,0,.06);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#000000; --bg-side:#1C1C1E; --chrome:rgba(28,28,30,.82);
  --hair:rgba(255,255,255,.16); --hair-soft:rgba(255,255,255,.08);
  --ink:#FFFFFF; --ink-2:#98989F; --ink-3:#636366;
  --in-bg:#26252A; --in-ink:#FFFFFF;
  --out-1:#2E9BFB; --out-2:#0A72E0; --out-ink:#FFFFFF;
  --blue:#0A84FF; --field:#1C1C1E; --sel:#2563EB;
  --card:rgba(255,255,255,.07); --card-line:rgba(255,255,255,.12);
  --hot:#FF453A; --warm:#FF9F0A; --good:#30D158; --cool:#98989F;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --bg:#000000; --bg-side:#1C1C1E; --chrome:rgba(28,28,30,.82);
  --hair:rgba(255,255,255,.16); --hair-soft:rgba(255,255,255,.08);
  --ink:#FFFFFF; --ink-2:#98989F; --ink-3:#636366;
  --in-bg:#26252A; --in-ink:#FFFFFF;
  --out-1:#2E9BFB; --out-2:#0A72E0; --out-ink:#FFFFFF;
  --blue:#0A84FF; --field:#1C1C1E; --sel:#2563EB;
  --card:rgba(255,255,255,.07); --card-line:rgba(255,255,255,.12);
  --hot:#FF453A; --warm:#FF9F0A; --good:#30D158; --cool:#98989F;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sys);
  font-size:17px;line-height:1.4;-webkit-font-smoothing:antialiased;
  overscroll-behavior:none}
button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}
:focus-visible{outline:2px solid var(--blue);outline-offset:2px;border-radius:6px}

/* ---------- 셸 ---------- */
.app{display:grid;grid-template-columns:340px 1fr;height:100dvh;
  background:var(--bg);overflow:hidden}
@media (max-width:820px){
  .app{grid-template-columns:1fr}
  .side{grid-area:1/1}
  .main{grid-area:1/1;transform:translateX(100%);transition:transform .28s cubic-bezier(.32,.72,0,1);
    z-index:3;background:var(--bg)}
  .app[data-open="1"] .main{transform:translateX(0)}
  .app[data-open="1"] .side{transform:translateX(-22%);filter:brightness(.9)}
  .side{transition:transform .28s cubic-bezier(.32,.72,0,1),filter .28s}
}

/* ---------- 사이드바 ---------- */
.side{display:flex;flex-direction:column;min-height:0;background:var(--bg-side);
  border-right:.5px solid var(--hair)}
.side-top{position:sticky;top:0;z-index:2;padding:12px 16px 8px;
  background:var(--chrome);backdrop-filter:saturate(180%) blur(20px);
  -webkit-backdrop-filter:saturate(180%) blur(20px);border-bottom:.5px solid var(--hair-soft)}
.side-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
.side-title{font-size:26px;font-weight:700;letter-spacing:-.5px}
.icon-btn{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;
  color:var(--blue)}
.icon-btn:hover{background:var(--hair-soft)}
.search{margin-top:10px;display:flex;align-items:center;gap:7px;background:var(--field);
  border-radius:10px;padding:7px 10px;color:var(--ink-2)}
.search input{flex:1;border:0;background:none;color:var(--ink);font:inherit;font-size:15px;
  outline:none;min-width:0}
.search input::placeholder{color:var(--ink-2)}
.tabs{margin-top:10px;display:flex;gap:4px;background:var(--field);border-radius:9px;padding:2px}
.tab{flex:1;padding:5px 0;border-radius:7px;font-size:13px;font-weight:600;color:var(--ink-2);
  text-align:center}
.tab[aria-selected="true"]{background:var(--bg-side);color:var(--ink);box-shadow:var(--shadow)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .tab[aria-selected="true"]{background:#3A3A3C}}
:root[data-theme="dark"] .tab[aria-selected="true"]{background:#3A3A3C}

.list{flex:1;overflow-y:auto;padding:4px 0 24px;-webkit-overflow-scrolling:touch}
.group{padding:14px 16px 5px;font-size:12px;font-weight:700;letter-spacing:.4px;
  color:var(--ink-2);text-transform:uppercase}
.row{display:grid;grid-template-columns:14px 50px 1fr;gap:0 10px;align-items:start;
  width:100%;text-align:left;padding:9px 14px;position:relative}
.row+.row::after{content:"";position:absolute;left:78px;right:0;top:0;
  border-top:.5px solid var(--hair-soft)}
.row:hover{background:var(--hair-soft)}
.row[aria-current="true"]{background:var(--sel)}
.row[aria-current="true"] *{color:#fff !important}
.row[aria-current="true"] .dot{background:#fff}
.dot{width:9px;height:9px;border-radius:50%;background:var(--blue);align-self:center;
  justify-self:center;visibility:hidden}
.row[data-unread="1"] .dot{visibility:visible}
.av{width:50px;height:50px;border-radius:50%;overflow:hidden;flex:none;
  box-shadow:inset 0 0 0 .5px rgba(0,0,0,.08)}
.av svg{display:block}
.row-body{min-width:0}
.row-head{display:flex;align-items:baseline;gap:6px}
.row-name{font-size:16px;font-weight:600;letter-spacing:-.2px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.row-time{margin-left:auto;font-size:13px;color:var(--ink-2);white-space:nowrap;flex:none}
.row-sub{font-size:14px;color:var(--ink-2);line-height:1.32;margin-top:1px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.row-tag{display:inline-block;font-size:11px;font-weight:700;padding:1px 6px;border-radius:5px;
  margin-top:4px;background:var(--hair-soft);color:var(--ink-2)}
.empty{padding:40px 20px;text-align:center;color:var(--ink-2);font-size:15px}

/* ---------- 스레드 ---------- */
.main{display:flex;flex-direction:column;min-height:0;min-width:0}
.bar{position:sticky;top:0;z-index:4;display:grid;
  grid-template-columns:minmax(72px,1fr) auto minmax(72px,1fr);
  align-items:center;padding:8px 12px;background:var(--chrome);
  backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px);
  border-bottom:.5px solid var(--hair)}
.back{display:flex;align-items:center;gap:1px;color:var(--blue);font-size:17px}
@media (min-width:821px){.back{visibility:hidden}}
.bar-mid{display:flex;flex-direction:column;align-items:center;gap:2px;min-width:0}
.bar-av{width:34px;height:34px;border-radius:50%;overflow:hidden}
.bar-name{font-size:12px;font-weight:600;display:flex;align-items:center;gap:3px;
  white-space:nowrap}
.bar-right{display:flex;justify-content:flex-end;gap:6px}
.run-btn{display:flex;align-items:center;gap:5px;color:var(--blue);font-size:15px;
  font-weight:500;padding:4px 9px;border-radius:8px;white-space:nowrap}
.run-btn:hover{background:var(--hair-soft)}
.run-btn[disabled]{color:var(--ink-3);cursor:default;background:none}

.scroll{flex:1;overflow-y:auto;padding:12px 0 8px;-webkit-overflow-scrolling:touch}
.thread{max-width:760px;margin:0 auto;padding:0 16px}

.profile{display:flex;flex-direction:column;align-items:center;gap:8px;
  padding:14px 0 26px;text-align:center}
.profile .av-lg{width:78px;height:78px;border-radius:50%;overflow:hidden}
.profile h1{margin:2px 0 0;font-size:19px;font-weight:600;letter-spacing:-.3px}
.profile p{margin:0;font-size:13px;color:var(--ink-2);max-width:34ch}
.chips{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:6px}
.chip{font-size:12px;padding:3px 9px;border-radius:100px;background:var(--in-bg);
  color:var(--ink-2)}
.chip.accent{color:#fff}

.day{text-align:center;font-size:11px;font-weight:600;color:var(--ink-2);
  margin:16px 0 10px;letter-spacing:.2px}
.day span{color:var(--ink-2)}
.day b{color:var(--ink-2);font-weight:700}

.msg{display:flex;margin:2px 0;position:relative}
.msg.them{justify-content:flex-start}
.msg.me{justify-content:flex-end}
.msg.tail{margin-bottom:10px}
.bubble{position:relative;max-width:min(74%,520px);padding:8px 14px;border-radius:19px;
  font-size:16px;line-height:1.36;word-break:break-word;letter-spacing:-.2px}
.msg.them .bubble{background:var(--in-bg);color:var(--in-ink);border-bottom-left-radius:19px}
.msg.me .bubble{background:linear-gradient(var(--out-1),var(--out-2));color:var(--out-ink)}
.msg.tail.them .bubble{border-bottom-left-radius:6px}
.msg.tail.me .bubble{border-bottom-right-radius:6px}
/* 말풍선 꼬리 */
.msg.tail .bubble::after{content:"";position:absolute;bottom:0;width:14px;height:16px}
.msg.tail.them .bubble::after{left:-6px;
  background:radial-gradient(circle at 100% 0,transparent 14px,var(--in-bg) 14px) bottom left/14px 16px no-repeat;
  -webkit-mask:radial-gradient(circle at 0 0,transparent 8px,#000 8px) bottom left/14px 16px no-repeat;
  mask:radial-gradient(circle at 0 0,transparent 8px,#000 8px) bottom left/14px 16px no-repeat}
.msg.tail.me .bubble::after{right:-6px;
  background:var(--out-2);
  -webkit-mask:radial-gradient(circle at 100% 0,transparent 8px,#000 8px) bottom right/14px 16px no-repeat;
  mask:radial-gradient(circle at 100% 0,transparent 8px,#000 8px) bottom right/14px 16px no-repeat}
.bubble strong{font-weight:700}
.msg .stamp{position:absolute;bottom:-1px;font-size:10px;color:var(--ink-3);
  white-space:nowrap;opacity:0;transition:opacity .16s}
.msg.them .stamp{left:calc(100% + 8px)}
.msg.me .stamp{right:calc(100% + 8px)}
.scroll.show-time .msg .stamp{opacity:1}
.msg:hover .stamp{opacity:1}

/* 탭백 */
.tapback{position:absolute;top:-13px;font-size:13px;line-height:1;padding:4px 5px;
  border-radius:50%;background:var(--in-bg);box-shadow:0 0 0 2px var(--bg);
  animation:pop .28s cubic-bezier(.34,1.56,.64,1)}
.msg.them .tapback{left:-8px}
.msg.me .tapback{right:-8px}
@keyframes pop{from{transform:scale(0);opacity:0}to{transform:scale(1);opacity:1}}

.read{text-align:right;font-size:11px;color:var(--ink-2);margin:-4px 2px 10px}

/* 리치 말풍선 — overflow 를 열어둬야 꼬리(::after)가 잘리지 않는다 */
.rich{padding:0;background:var(--in-bg)}
.rich-head{padding:11px 14px 9px;border-bottom:.5px solid var(--card-line)}
.rich-head .t{font-size:15px;font-weight:650;letter-spacing:-.2px}
.rich-head .s{font-size:12.5px;color:var(--ink-2);margin-top:2px}
.rows{display:grid}
.kv{display:flex;gap:10px;justify-content:space-between;align-items:baseline;
  padding:7px 14px;font-size:14px}
.kv+.kv{border-top:.5px solid var(--card-line)}
.kv .k{color:var(--ink-2);flex:none}
.kv .v{text-align:right;font-weight:560;font-variant-numeric:tabular-nums}
.kv .v.hot{color:var(--hot)} .kv .v.warm{color:var(--warm)}
.kv .v.good{color:var(--good)} .kv .v.cool{color:var(--cool)}
.rich-foot{padding:8px 14px;font-size:12.5px;color:var(--ink-2);
  border-top:.5px solid var(--card-line)}
.ul{list-style:none;margin:0;padding:4px 0}
.ul li{display:flex;gap:9px;padding:6px 14px;font-size:14.5px;line-height:1.35}
.ul li::before{content:"";flex:none;width:6px;height:6px;border-radius:50%;margin-top:7px;
  background:currentColor;opacity:.35}

/* 파일 첨부 */
.file{display:flex;align-items:center;gap:11px;padding:10px 14px}
.file .ico{width:36px;height:44px;border-radius:4px;background:var(--bg);
  display:grid;place-items:center;font-size:9px;font-weight:800;color:var(--hot);
  box-shadow:0 0 0 .5px var(--card-line);letter-spacing:.4px}
.file .n{font-size:14.5px;font-weight:560;line-height:1.25}
.file .m{font-size:12px;color:var(--ink-2);margin-top:1px}

/* 투표 */
.poll{padding:11px 14px 12px}
.poll .q{font-size:15px;font-weight:600;margin-bottom:9px;letter-spacing:-.2px}
.opt{display:flex;align-items:center;gap:9px;width:100%;text-align:left;
  padding:8px 11px;border-radius:100px;background:var(--bg);margin-top:6px;
  box-shadow:inset 0 0 0 .5px var(--card-line);font-size:14.5px;transition:background .15s}
.opt:hover{background:var(--hair-soft)}
.opt .lbl{flex:1;min-width:0}
.opt .cnt{font-size:12.5px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.opt .mark{width:19px;height:19px;border-radius:50%;flex:none;
  box-shadow:inset 0 0 0 1.5px var(--ink-3);display:grid;place-items:center}
.opt[aria-pressed="true"] .mark{box-shadow:none;background:var(--blue);color:#fff}
.opt[aria-pressed="true"]{background:color-mix(in srgb,var(--blue) 12%,transparent)}
.opt .mark svg{opacity:0}
.opt[aria-pressed="true"] .mark svg{opacity:1}

/* 타이핑 */
.dots{display:inline-flex;gap:5px;padding:12px 15px}
.dots i{width:8px;height:8px;border-radius:50%;background:var(--ink-3);
  animation:bob 1.3s infinite ease-in-out}
.dots i:nth-child(2){animation-delay:.18s} .dots i:nth-child(3){animation-delay:.36s}
@keyframes bob{0%,60%,100%{transform:translateY(0);opacity:.45}
  30%{transform:translateY(-4px);opacity:1}}

/* 컴포저 */
.composer{padding:8px 12px calc(10px + env(safe-area-inset-bottom));
  border-top:.5px solid var(--hair);background:var(--chrome);
  backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px)}
.composer form{max-width:760px;margin:0 auto;display:flex;align-items:flex-end;gap:9px}
.plus{width:32px;height:32px;border-radius:50%;background:var(--field);color:var(--ink-2);
  display:grid;place-items:center;flex:none;font-size:20px;line-height:1}
.field{flex:1;display:flex;align-items:center;gap:8px;border-radius:18px;padding:6px 6px 6px 13px;
  box-shadow:inset 0 0 0 1px var(--hair);min-width:0}
.field input{flex:1;border:0;background:none;color:var(--ink);font:inherit;font-size:16px;
  outline:none;min-width:0;padding:2px 0}
.field input::placeholder{color:var(--ink-3)}
.send{width:28px;height:28px;border-radius:50%;background:var(--blue);color:#fff;
  display:grid;place-items:center;flex:none;transform:scale(.6);opacity:0;
  transition:transform .16s cubic-bezier(.34,1.56,.64,1),opacity .16s;pointer-events:none}
.field[data-ready="1"] .send{transform:scale(1);opacity:1;pointer-events:auto}
.hint{max-width:760px;margin:6px auto 0;font-size:11px;color:var(--ink-3);text-align:center}
@media (max-width:520px){.hint{display:none}}

.sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;
  clip:rect(0 0 0 0);white-space:nowrap;border:0}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01ms !important;
  transition-duration:.01ms !important}}
"""

CHEV_L = ('<svg width="12" height="20" viewBox="0 0 12 20" fill="none" aria-hidden="true">'
          '<path d="M10 2L2.5 10 10 18" stroke="currentColor" stroke-width="2.6" '
          'stroke-linecap="round" stroke-linejoin="round"/></svg>')
MAGNIFY = ('<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
           '<circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.8"/>'
           '<path d="M11 11l4 4" stroke="currentColor" stroke-width="1.8" '
           'stroke-linecap="round"/></svg>')
BOLT = ('<svg width="14" height="16" viewBox="0 0 12 16" fill="currentColor" '
        'aria-hidden="true"><path d="M7 0L0 9h4l-1 7 8-9.5H6.5L7 0z"/></svg>')
ARROW_UP = ('<svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
            '<path d="M8 13.5V3M8 3L3.5 7.5M8 3l4.5 4.5" stroke="currentColor" '
            'stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/></svg>')
CHECK = ('<svg width="11" height="9" viewBox="0 0 12 10" fill="none" aria-hidden="true">'
         '<path d="M1 5l3.4 3.4L11 1.6" stroke="currentColor" stroke-width="2.2" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')
CLOCK = ('<svg width="19" height="19" viewBox="0 0 20 20" fill="none" aria-hidden="true">'
         '<circle cx="10" cy="10" r="7.6" stroke="currentColor" stroke-width="1.6"/>'
         '<path d="M10 5.6V10l3 1.8" stroke="currentColor" stroke-width="1.6" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def render_msg(m, accent, tail):
    """메시지 하나를 말풍선 하나로. tail=True 면 꼬리를 단다."""
    who = "me" if m.get("from") == "me" else "them"
    kind = m.get("t", "text")
    stamp = plain(m.get("time", ""))
    tap = m.get("reaction")

    if kind == "typing":
        return ('<div class="msg them tail"><div class="bubble dots" '
                'aria-label="입력 중"><i></i><i></i><i></i></div></div>')

    if kind == "text":
        inner = f'<div class="bubble">{rich(m.get("text"))}</div>'
    elif kind == "card":
        rows = "".join(
            '<div class="kv"><span class="k">%s</span>'
            '<span class="v %s">%s</span></div>'
            % (plain(r.get("k")), plain(r.get("tone", "")), plain(r.get("v")))
            for r in m.get("rows", [])
        )
        foot = (f'<div class="rich-foot">{plain(m["footer"])}</div>'
                if m.get("footer") else "")
        inner = (
            '<div class="bubble rich"><div class="rich-head">'
            f'<div class="t">{plain(m.get("title"))}</div>'
            f'<div class="s">{plain(m.get("subtitle"))}</div></div>'
            f'<div class="rows">{rows}</div>{foot}</div>'
        )
    elif kind == "list":
        items = "".join(f"<li>{rich(i)}</li>" for i in m.get("items", []))
        inner = (
            '<div class="bubble rich"><div class="rich-head">'
            f'<div class="t">{plain(m.get("title"))}</div></div>'
            f'<ul class="ul">{items}</ul></div>'
        )
    elif kind == "file":
        inner = (
            '<div class="bubble rich"><div class="file">'
            '<div class="ico">PDF</div><div>'
            f'<div class="n">{plain(m.get("name"))}</div>'
            f'<div class="m">{plain(m.get("meta"))}</div></div></div></div>'
        )
    elif kind == "poll":
        opts = "".join(
            '<button type="button" class="opt" aria-pressed="%s" data-votes="%d">'
            '<span class="mark">%s</span><span class="lbl">%s</span>'
            '<span class="cnt">%d</span></button>'
            % ("true" if o.get("picked") else "false", int(o.get("votes", 0)),
               CHECK, plain(o.get("label")), int(o.get("votes", 0)))
            for o in m.get("options", [])
        )
        inner = (
            '<div class="bubble rich"><div class="poll">'
            f'<div class="q">{plain(m.get("question"))}</div>{opts}</div></div>'
        )
    else:
        return ""

    tb = f'<span class="tapback">{plain(tap)}</span>' if tap else ""
    cls = f'msg {who}{" tail" if tail else ""}'
    return (f'<div class="{cls}">{inner}<span class="stamp">{stamp}</span>{tb}</div>')


def render_thread(a):
    av = avatar_svg(a["avatar"])
    sch = a.get("schedule", {})
    chips = "".join(f'<span class="chip">{plain(s)}</span>' for s in a.get("scope", []))
    out = [
        '<div class="profile">',
        f'<div class="av-lg">{av}</div>',
        f'<h1>{plain(a["name"])}</h1>',
        f'<p>{plain(a["title"])} · {plain(a["tagline"])}</p>',
        '<div class="chips">'
        f'<span class="chip accent" style="background:{plain(a["accent"])}">'
        f'루틴 {plain(a["no"])} · {plain(a["routine"])}</span>'
        f'<span class="chip">{plain(sch.get("label"))}</span>'
        f'<span class="chip">다음 실행 {plain(sch.get("next"))}</span>'
        f"</div>",
        f'<div class="chips">{chips}</div>',
        "</div>",
    ]

    msgs = a.get("thread", [])
    for i, m in enumerate(msgs):
        if m.get("t") == "day":
            out.append(f'<div class="day"><b>{plain(m["text"])}</b></div>')
            continue
        nxt = msgs[i + 1] if i + 1 < len(msgs) else None
        tail = not (nxt and nxt.get("t") not in ("day",)
                    and nxt.get("from") == m.get("from"))
        out.append(render_msg(m, a["accent"], tail))

    last = next((m for m in reversed(msgs) if m.get("t") not in ("day", "typing")), None)
    if last and last.get("from") == "me":
        out.append('<div class="read">읽음</div>')
    return "".join(out)


def preview_of(a):
    for m in reversed(a.get("thread", [])):
        t = m.get("t")
        if t == "text":
            return m["text"].replace("**", "")
        if t == "card":
            return f'[{m.get("title","")}] {m.get("subtitle","")}'
        if t == "list":
            return f'[{m.get("title","")}]'
        if t == "poll":
            return f'[투표] {m.get("question","")}'
        if t == "file":
            return f'[첨부] {m.get("name","")}'
    return ""


def last_time_of(a):
    """목록에 찍을 시각. 대화가 오늘 것이 아니면 날짜 라벨을 대신 보여준다."""
    day = next((m["text"] for m in a.get("thread", []) if m.get("t") == "day"), "")
    if day and day != "오늘":
        return day
    for m in reversed(a.get("thread", [])):
        if m.get("time"):
            return m["time"]
    return ""


def render_row(a, idx):
    av = avatar_svg(a["avatar"])
    unread = int(a.get("unread", 0))
    return (
        f'<button type="button" class="row" role="option" data-idx="{idx}" '
        f'data-id="{plain(a["id"])}" data-unread="{1 if unread else 0}" '
        f'data-cadence="{plain(a.get("schedule",{}).get("cadence",""))}" '
        f'data-q="{plain((a["name"]+" "+a["title"]+" "+a["routine"]+" "+preview_of(a)).lower())}" '
        f'aria-current="false">'
        '<span class="dot"></span>'
        f'<span class="av">{av}</span>'
        '<span class="row-body">'
        f'<span class="row-head"><span class="row-name">{plain(a["name"])}</span>'
        f'<span class="row-time">{plain(last_time_of(a))}</span></span>'
        f'<span class="row-sub">{plain(preview_of(a))}</span>'
        f'<span class="row-tag">루틴 {plain(a["no"])} · {plain(a["routine"])}</span>'
        "</span></button>"
    )


JS = """
(function(){
  var app=document.getElementById('app'), list=document.getElementById('list'),
      panes=document.getElementById('panes'), q=document.getElementById('q'),
      scroll=document.getElementById('scroll');
  var rows=[].slice.call(list.querySelectorAll('.row'));
  var STORE='routine-hub';

  function load(){ try{return JSON.parse(localStorage.getItem(STORE))||{};}catch(e){return{};} }
  function save(s){ try{localStorage.setItem(STORE,JSON.stringify(s));}catch(e){} }
  var state=load();

  function open(idx,push){
    rows.forEach(function(r){r.setAttribute('aria-current', r.dataset.idx==idx?'true':'false');
      if(r.dataset.idx==idx) r.dataset.unread='0';});
    [].forEach.call(panes.children,function(p){p.hidden = p.dataset.idx!=idx;});
    app.dataset.open='1';
    requestAnimationFrame(function(){scroll.scrollTop=scroll.scrollHeight;});
    state.last=String(idx); save(state);
    var r=rows.filter(function(x){return x.dataset.idx==idx;})[0];
    if(r) document.getElementById('barmount').innerHTML=
      document.querySelector('[data-bar="'+idx+'"]').innerHTML;
  }
  list.addEventListener('click',function(e){
    var r=e.target.closest('.row'); if(r) open(r.dataset.idx);
  });
  document.getElementById('back').addEventListener('click',function(){app.dataset.open='0';});

  q.addEventListener('input',function(){
    var v=q.value.trim().toLowerCase(); var n=0;
    rows.forEach(function(r){
      var hit=!v||r.dataset.q.indexOf(v)>-1;
      r.hidden=!hit || (r.dataset.filtered==='1'); if(hit&&r.dataset.filtered!=='1')n++;
    });
    document.getElementById('empty').hidden=n>0;
  });

  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  tabs.forEach(function(t){
    t.addEventListener('click',function(){
      tabs.forEach(function(x){x.setAttribute('aria-selected',x===t?'true':'false');});
      var f=t.dataset.filter, n=0;
      rows.forEach(function(r){
        var ok = f==='all' || r.dataset.cadence===f;
        r.dataset.filtered = ok?'0':'1';
        var v=q.value.trim().toLowerCase();
        var hit=!v||r.dataset.q.indexOf(v)>-1;
        r.hidden=!(ok&&hit); if(ok&&hit)n++;
      });
      document.getElementById('empty').hidden=n>0;
      state.tab=f; save(state);
    });
  });

  // 탭백 — 우클릭/길게 누르기
  var PICK=['❤️','👍','👎','‼️','😂','❓'];
  function tapback(msg){
    var old=msg.querySelector('.tapback');
    var cur=old?old.textContent:null;
    var i=PICK.indexOf(cur);
    var next=PICK[(i+1)%PICK.length];
    if(old) old.remove();
    if(cur!==next||!old){
      var s=document.createElement('span'); s.className='tapback'; s.textContent=next;
      msg.appendChild(s);
    }
  }
  panes.addEventListener('contextmenu',function(e){
    var m=e.target.closest('.msg'); if(!m||m.querySelector('.dots'))return;
    e.preventDefault(); tapback(m);
  });
  var timer=null;
  panes.addEventListener('pointerdown',function(e){
    var m=e.target.closest('.msg'); if(!m||m.querySelector('.dots')||e.target.closest('.opt'))return;
    timer=setTimeout(function(){tapback(m);},480);
  });
  ['pointerup','pointerleave','pointercancel','scroll'].forEach(function(ev){
    panes.addEventListener(ev,function(){clearTimeout(timer);},true);
  });

  // 투표
  panes.addEventListener('click',function(e){
    var o=e.target.closest('.opt'); if(!o)return;
    var box=o.parentNode, on=o.getAttribute('aria-pressed')==='true';
    [].forEach.call(box.querySelectorAll('.opt'),function(x){
      var was=x.getAttribute('aria-pressed')==='true';
      var base=+x.dataset.votes;
      x.setAttribute('aria-pressed','false');
      x.querySelector('.cnt').textContent=base;
      if(was&&x!==o){}
    });
    if(!on){ o.setAttribute('aria-pressed','true');
      o.querySelector('.cnt').textContent=(+o.dataset.votes)+1; }
  });

  // 시간 표시 토글
  document.getElementById('clock').addEventListener('click',function(){
    scroll.classList.toggle('show-time');
  });

  // 컴포저
  var form=document.getElementById('composer'), input=document.getElementById('draft'),
      field=document.getElementById('field');
  input.addEventListener('input',function(){
    field.dataset.ready=input.value.trim()?'1':'0';
  });
  form.addEventListener('submit',function(e){
    e.preventDefault();
    var v=input.value.trim(); if(!v)return;
    var pane=[].filter.call(panes.children,function(p){return !p.hidden;})[0];
    if(!pane)return;
    var prev=pane.querySelector('.read'); if(prev) prev.remove();
    var d=document.createElement('div'); d.className='msg me tail';
    var now=new Date();
    var h=now.getHours(), ap=h<12?'오전':'오후'; var hh=h%12||12;
    d.innerHTML='<div class="bubble"></div><span class="stamp">'+ap+' '+hh+':'
      +String(now.getMinutes()).padStart(2,'0')+'</span>';
    d.querySelector('.bubble').textContent=v;
    pane.appendChild(d);
    var r=document.createElement('div'); r.className='read'; r.textContent='전달됨';
    pane.appendChild(r);
    input.value=''; field.dataset.ready='0';
    scroll.scrollTop=scroll.scrollHeight;
  });

  // 루틴 실행 시뮬레이션
  var running=false;
  document.getElementById('panes').addEventListener('click',function(e){});
  document.getElementById('run').addEventListener('click',function(){
    if(running)return;
    var pane=[].filter.call(panes.children,function(p){return !p.hidden;})[0];
    if(!pane)return;
    var src=pane.querySelector('[data-run]'); if(!src)return;
    var steps=[].slice.call(src.children);
    if(!steps.length)return;
    running=true;
    var btn=document.getElementById('run'); btn.disabled=true;
    var prev=pane.querySelector('.read'); if(prev) prev.remove();
    var day=document.createElement('div'); day.className='day';
    day.innerHTML='<b>지금 실행됨</b>';
    pane.appendChild(day); scroll.scrollTop=scroll.scrollHeight;
    var i=0;
    (function step(){
      if(i>=steps.length){ running=false; btn.disabled=false; return; }
      var t=document.createElement('div'); t.className='msg them tail';
      t.innerHTML='<div class="bubble dots"><i></i><i></i><i></i></div>';
      pane.appendChild(t); scroll.scrollTop=scroll.scrollHeight;
      setTimeout(function(){
        t.remove();
        var node=steps[i].cloneNode(true);
        pane.appendChild(node); scroll.scrollTop=scroll.scrollHeight;
        i++; setTimeout(step,420);
      }, 700+Math.random()*500);
    })();
  });

  var start=state.last && document.querySelector('.row[data-idx="'+state.last+'"]')
    ? state.last : '0';
  open(start);
  if(window.matchMedia('(max-width:820px)').matches) app.dataset.open='0';
})();
"""


def render_page(data):
    ppl = data["assistants"]
    owner = data.get("owner", {})

    rows = "".join(render_row(a, i) for i, a in enumerate(ppl))

    panes, bars, runs = [], [], []
    for i, a in enumerate(ppl):
        run_html = "".join(
            render_msg(dict(m, time=""), a["accent"], True) for m in a.get("run", [])
        )
        panes.append(
            f'<section class="thread" data-idx="{i}" hidden>'
            f'{render_thread(a)}'
            f'<div data-run hidden>{run_html}</div>'
            "</section>"
        )
        bars.append(
            f'<template data-bar="{i}">'
            f'<div class="bar-av">{avatar_svg(a["avatar"])}</div>'
            f'<div class="bar-name">{plain(a["name"])} '
            f'<span style="color:var(--ink-2);font-weight:400">'
            f'· {plain(a["title"])}</span></div>'
            "</template>"
        )

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>루틴 허브 — 나의 비서 7인</title>
<style>{CSS}</style>
</head><body>
<div class="app" id="app" data-open="0">

  <aside class="side">
    <div class="side-top">
      <div class="side-row">
        <div class="side-title">루틴</div>
        <button class="icon-btn" type="button" id="clock" title="모든 메시지 시간 표시"
          aria-label="메시지 시간 표시 전환">{CLOCK}</button>
      </div>
      <label class="search">{MAGNIFY}
        <input id="q" type="search" placeholder="검색" aria-label="비서·루틴 검색">
      </label>
      <div class="tabs" role="tablist">
        <button class="tab" role="tab" data-filter="all" aria-selected="true">전체</button>
        <button class="tab" role="tab" data-filter="평일" aria-selected="false">평일</button>
        <button class="tab" role="tab" data-filter="주간" aria-selected="false">주간</button>
        <button class="tab" role="tab" data-filter="월간" aria-selected="false">월간</button>
      </div>
    </div>
    <div class="list" id="list" role="listbox" aria-label="비서 대화 목록">
      <div class="group">예정됨 · {plain(owner.get("name"))} 전용</div>
      {rows}
      <div class="empty" id="empty" hidden>검색 결과가 없습니다</div>
    </div>
  </aside>

  <main class="main">
    <header class="bar">
      <button class="back" type="button" id="back">{CHEV_L}<span>루틴</span></button>
      <div class="bar-mid" id="barmount"></div>
      <div class="bar-right">
        <button class="run-btn" type="button" id="run">{BOLT}<span>실행</span></button>
      </div>
    </header>

    <div class="scroll" id="scroll">
      <div id="panes">{"".join(panes)}</div>
    </div>

    <div class="composer">
      <form id="composer" autocomplete="off">
        <button class="plus" type="button" aria-label="첨부">+</button>
        <label class="field" id="field" data-ready="0">
          <span class="sr">메시지</span>
          <input id="draft" type="text" placeholder="지시 사항 입력">
          <button class="send" type="submit" aria-label="보내기">{ARROW_UP}</button>
        </label>
      </form>
      <div class="hint">
        말풍선을 길게 누르면 탭백 · 상단 <b>실행</b>은 해당 루틴을 지금 돌린 결과를 보여줍니다
      </div>
    </div>
  </main>
</div>
{"".join(bars)}
<script>{JS}</script>
</body></html>
"""


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "routines/team.json")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "live/routines")

    if not src.exists():
        print(f"[routine-hub] {src} 없음 - 건너뜀")
        return

    data = json.loads(src.read_text(encoding="utf-8"))
    if not data.get("assistants"):
        print("[routine-hub] 비서 데이터 없음 - 건너뜀")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "index.html"
    target.write_text(render_page(data), encoding="utf-8")
    print(f"[routine-hub] {target} ({len(data['assistants'])}명, "
          f"{target.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
