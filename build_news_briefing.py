#!/usr/bin/env python3
"""
briefings/YYYY-MM-DD.json  ->  live/news/YYYY-MM-DD.html + live/news/index.html (최신호)

매일 아침 브리핑을 신문(조간) 레이아웃 한 장으로 렌더링한다.
발행 호수는 briefings/ 안의 날짜 순서로 자동 부여하고, 각 호 하단에
지난 호로 넘어가는 셀렉트를 넣는다. 데이터가 없으면 아무것도 만들지 않는다.

사용:
    python build_news_briefing.py [briefings_dir] [out_dir]
"""
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

# JSON 본문에서 허용하는 인라인 태그. 나머지는 전부 이스케이프한다
# (브리핑 JSON은 뉴스 기사 문구를 옮겨 담으므로 마크업을 그대로 신뢰하지 않는다).
INLINE_OK = ["<strong>", "</strong>", "<em>", "</em>", "<br>"]


def rich(text):
    out = html.escape(text or "")
    for tag in INLINE_OK:
        out = out.replace(html.escape(tag), tag)
    return out


def plain(text):
    return html.escape(text or "")


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --paper:#F2F1EC; --sheet:#FBFAF7;
  --ink:#15171A; --ink-mid:#55595E; --ink-soft:#83878C;
  --rule:#C4C2BB; --rule-bold:#15171A;
  --carmine:#93221F; --slate:#2C4B63; --forest:#1F4A34; --ochre:#7E5116;
  --up:#B03A2E; --down:#1F5FA8;
  --serif:AppleMyungjo,"Apple Myungjo","Nanum Myeongjo","Noto Serif KR","Source Han Serif K",Batang,"바탕","Times New Roman",serif;
  --sans:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","맑은 고딕","Noto Sans KR","Nanum Gothic",sans-serif;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#131418; --sheet:#1A1C21;
    --ink:#E9E7E1; --ink-mid:#A4A7AD; --ink-soft:#787C82;
    --rule:#32353C; --rule-bold:#E9E7E1;
    --carmine:#E07B73; --slate:#84ADCD; --forest:#72C295; --ochre:#D9A75E;
    --up:#E8776C; --down:#6BA6E8;
  }
}
:root[data-theme="dark"]{
  --paper:#131418; --sheet:#1A1C21;
  --ink:#E9E7E1; --ink-mid:#A4A7AD; --ink-soft:#787C82;
  --rule:#32353C; --rule-bold:#E9E7E1;
  --carmine:#E07B73; --slate:#84ADCD; --forest:#72C295; --ochre:#D9A75E;
  --up:#E8776C; --down:#6BA6E8;
}

body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.7;
  -webkit-font-smoothing:antialiased;
}
.sheet{max-width:1180px; margin:0 auto; padding:0 24px 72px}
a{color:inherit}
em{font-style:normal; box-shadow:inset 0 -0.45em 0 color-mix(in srgb,var(--carmine) 16%,transparent)}

/* ---------- 제호 ---------- */
.plate{padding:40px 0 0}
.plate-meta{
  display:flex; flex-wrap:wrap; gap:10px 20px; justify-content:space-between;
  font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--ink-soft); padding-bottom:12px;
}
.plate-main{
  display:flex; flex-wrap:wrap; align-items:flex-end; justify-content:space-between;
  gap:16px 32px; border-top:3px solid var(--rule-bold); padding-top:20px;
}
.nameplate{
  font-family:var(--serif); font-weight:700;
  font-size:clamp(2.6rem,7vw,4.4rem); line-height:.95;
  letter-spacing:.06em; margin:0; color:var(--ink); text-wrap:balance;
}
.nameplate .dot{color:var(--carmine)}
.plate-side{
  text-align:right; font-size:.72rem; letter-spacing:.14em;
  text-transform:uppercase; color:var(--ink-soft); line-height:1.5;
}
.plate-side b{
  display:block; font-family:var(--serif); font-size:1.6rem; color:var(--ink);
  letter-spacing:.02em; text-transform:none; font-variant-numeric:tabular-nums;
}
.plate-rules{border-top:2px solid var(--rule-bold); margin-top:18px}
.plate-rules::after{content:""; display:block; border-top:1px solid var(--rule-bold); margin-top:3px}

/* ---------- 섹션 네비 ---------- */
.nav{
  position:sticky; top:0; z-index:20; background:var(--paper);
  border-bottom:1px solid var(--rule); margin-bottom:28px;
}
.nav-inner{
  max-width:1180px; margin:0 auto; padding:0 24px;
  display:flex; gap:4px; overflow-x:auto; scrollbar-width:none;
}
.nav-inner::-webkit-scrollbar{display:none}
.nav a{
  flex:none; padding:11px 14px; font-size:.82rem; font-weight:600;
  letter-spacing:.06em; color:var(--ink-mid); text-decoration:none;
  border-bottom:2px solid transparent; white-space:nowrap;
}
.nav a:hover{color:var(--ink)}
.nav a.on{color:var(--ink); border-bottom-color:var(--carmine)}
.nav a:focus-visible{outline:2px solid var(--carmine); outline-offset:-2px}

/* ---------- 지수 스트립 ---------- */
.ticker{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  border:1px solid var(--rule); border-left:none; margin:22px 0 34px; background:var(--sheet);
}
.tick{padding:12px 16px; border-left:1px solid var(--rule)}
.tick-l{font-size:.7rem; letter-spacing:.1em; color:var(--ink-soft); margin-bottom:3px}
.tick-v{font-family:var(--serif); font-size:1.35rem; font-variant-numeric:tabular-nums; line-height:1.2}
.tick-d{font-size:.76rem; font-weight:600; font-variant-numeric:tabular-nums}
.tick-d.up{color:var(--up)} .tick-d.down{color:var(--down)} .tick-d.flat{color:var(--ink-soft)}

/* ---------- 1면 톱 ---------- */
.lead{border-top:1px solid var(--rule); padding-top:26px; margin-bottom:44px}
.kicker{
  display:inline-block; font-size:.74rem; font-weight:700; letter-spacing:.16em;
  color:var(--carmine); border-bottom:2px solid var(--carmine); padding-bottom:3px; margin-bottom:14px;
}
.lead h2{
  font-family:var(--serif); font-weight:700; margin:0 0 12px;
  font-size:clamp(1.85rem,4.3vw,2.9rem); line-height:1.22; letter-spacing:-.01em; text-wrap:balance;
}
.lead-sub{
  font-size:1.02rem; color:var(--ink-mid); margin:0 0 22px; max-width:62ch;
  padding-left:14px; border-left:3px solid var(--rule);
}
.lede{
  font-family:var(--serif); font-size:1.1rem; line-height:1.85; margin:0 0 24px; max-width:66ch;
}
.facts{
  list-style:none; margin:0; padding:20px 22px; background:var(--sheet);
  border:1px solid var(--rule); display:grid; gap:14px;
  grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
}
.facts li{font-size:.93rem; line-height:1.65}
.facts b{
  display:block; font-size:.7rem; letter-spacing:.12em; color:var(--carmine);
  margin-bottom:3px; font-weight:700;
}

/* ---------- 섹션 ---------- */
.sec{margin-bottom:48px; scroll-margin-top:60px}
.sec-bar{
  display:flex; align-items:baseline; gap:12px;
  background:var(--tone); color:var(--paper); padding:7px 14px; margin-bottom:22px;
}
.sec-bar h3{font-family:var(--serif); font-size:1.15rem; margin:0; letter-spacing:.22em; font-weight:700}
.sec-bar span{font-size:.7rem; letter-spacing:.14em; opacity:.72}
.arts{display:grid; gap:26px; grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}
.art{border-top:1px solid var(--rule); padding-top:14px}
.art.wide{grid-column:1/-1; border-top:2px solid var(--tone)}
.art h4{
  font-family:var(--serif); font-size:1.22rem; line-height:1.4; margin:0 0 9px;
  font-weight:700; text-wrap:balance;
}
.art p{margin:0; font-size:.94rem; line-height:1.78; color:var(--ink-mid)}
.art.wide p{font-size:1rem; color:var(--ink)}
.tags{display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px}
.tag{
  font-size:.66rem; letter-spacing:.1em; font-weight:600; padding:2px 7px;
  border:1px solid var(--tone); color:var(--tone);
}
.tag.hot{background:var(--tone); color:var(--paper)}

/* ---------- 시사점 박스 ---------- */
.box{border:3px double var(--rule-bold); background:var(--sheet); padding:26px 24px; scroll-margin-top:60px}
.box-head{border-bottom:1px solid var(--rule); padding-bottom:12px; margin-bottom:6px}
.box-head h3{font-family:var(--serif); font-size:1.4rem; margin:0 0 4px; letter-spacing:.04em}
.box-head p{margin:0; font-size:.82rem; color:var(--ink-soft)}
.box-scroll{overflow-x:auto}
table{border-collapse:collapse; width:100%; min-width:520px; font-size:.92rem}
th,td{text-align:left; vertical-align:top; padding:13px 14px 13px 0; border-bottom:1px solid var(--rule)}
th{
  font-size:.7rem; letter-spacing:.12em; color:var(--ink-soft);
  font-weight:600; padding-top:16px; border-bottom:1px solid var(--rule-bold);
}
td:first-child{width:32%; font-weight:600; padding-right:24px; color:var(--ink)}
td:last-child{color:var(--ink-mid); line-height:1.7}
tr:last-child td{border-bottom:none}

/* ---------- 판권 ---------- */
.colophon{
  margin-top:48px; border-top:2px solid var(--rule-bold); padding-top:18px;
  display:flex; flex-wrap:wrap; gap:16px 32px; justify-content:space-between;
  font-size:.78rem; color:var(--ink-soft); line-height:1.7;
}
.archive{display:flex; align-items:center; gap:9px}
.archive select{
  font-family:var(--sans); font-size:.78rem; color:var(--ink);
  background:var(--sheet); border:1px solid var(--rule); padding:5px 9px;
}
.archive select:focus-visible{outline:2px solid var(--carmine); outline-offset:1px}

@media (max-width:640px){
  .sheet{padding:0 16px 56px} .nav-inner{padding:0 16px}
  .plate{padding-top:26px} .facts{padding:16px}
  .box{padding:20px 16px}
}
@media print{
  .nav{display:none} body{background:#fff; font-size:10.5pt}
  .sheet{max-width:none; padding:0}
  .arts{display:block; columns:2; column-gap:26px}
  .art{break-inside:avoid; margin-bottom:16px} .art.wide{columns:1}
  .lead,.sec,.box{break-inside:avoid}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
"""

JS = """
(function(){
  var links=[].slice.call(document.querySelectorAll('.nav a[href^="#"]'));
  var map={}; links.forEach(function(a){map[a.getAttribute('href').slice(1)]=a;});
  var seen={};
  var io=new IntersectionObserver(function(es){
    es.forEach(function(e){seen[e.target.id]=e.isIntersecting?e.intersectionRatio:0;});
    var best=null,bv=0;
    Object.keys(seen).forEach(function(k){if(seen[k]>bv){bv=seen[k];best=k;}});
    links.forEach(function(a){a.classList.remove('on');});
    if(best&&map[best])map[best].classList.add('on');
  },{rootMargin:'-56px 0px -55% 0px',threshold:[0,.25,.5,1]});
  Object.keys(map).forEach(function(id){
    var el=document.getElementById(id); if(el)io.observe(el);
  });
  var sel=document.getElementById('archive');
  if(sel)sel.addEventListener('change',function(){if(sel.value)location.href=sel.value;});
})();
"""

TONES = {
    "carmine": "var(--carmine)",
    "slate": "var(--slate)",
    "forest": "var(--forest)",
    "ochre": "var(--ochre)",
}
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
ARROWS = {"up": "▲", "down": "▼", "flat": "－"}


def fmt_date(iso, weekday):
    y, m, d = iso.split("-")
    if not weekday:
        weekday = WEEKDAYS[date.fromisoformat(iso).weekday()]
    return "%s년 %s월 %s일 %s요일" % (y, int(m), int(d), weekday)


def render_ticker(indices):
    if not indices:
        return ""
    cells = []
    for it in indices:
        d = it.get("dir", "flat")
        arrow = ARROWS.get(d, "")
        cells.append(
            '<div class="tick"><div class="tick-l">%s</div>'
            '<div class="tick-v">%s</div>'
            '<div class="tick-d %s">%s %s</div></div>'
            % (plain(it["label"]), plain(it["value"]), d, arrow, plain(it.get("delta", "")))
        )
    return '<div class="ticker">%s</div>' % "".join(cells)


def render_lead(lead):
    if not lead:
        return ""
    facts = "".join(
        "<li><b>%s</b>%s</li>" % (plain(f.get("label", "")), rich(f.get("text", "")))
        for f in lead.get("facts", [])
    )
    return (
        '<article class="lead" id="lead">'
        '<div class="kicker">%s</div>'
        "<h2>%s</h2>"
        '<p class="lead-sub">%s</p>'
        '<p class="lede">%s</p>'
        '<ul class="facts">%s</ul>'
        "</article>"
    ) % (
        plain(lead.get("kicker", "")),
        rich(lead.get("headline", "")),
        rich(lead.get("sub", "")),
        rich(lead.get("lede", "")),
        facts,
    )


def render_section(sec):
    tone = TONES.get(sec.get("tone", "slate"), TONES["slate"])
    arts = []
    for it in sec.get("items", []):
        tags = "".join(
            '<span class="tag%s">%s</span>' % (" hot" if it.get("priority") else "", plain(t))
            for t in it.get("tags", [])
        )
        arts.append(
            '<article class="art%s">%s<h4>%s</h4><p>%s</p></article>'
            % (
                " wide" if it.get("priority") else "",
                '<div class="tags">%s</div>' % tags if tags else "",
                rich(it.get("title", "")),
                rich(it.get("body", "")),
            )
        )
    return (
        '<section class="sec" id="%s" style="--tone:%s">'
        '<div class="sec-bar"><h3>%s</h3><span>%d건</span></div>'
        '<div class="arts">%s</div>'
        "</section>"
    ) % (sec["id"], tone, plain(sec["name"]), len(sec.get("items", [])), "".join(arts))


def render_box(rows):
    if not rows:
        return ""
    body = "".join(
        "<tr><td>%s</td><td>%s</td></tr>" % (rich(r.get("news", "")), rich(r.get("impact", "")))
        for r in rows
    )
    return (
        '<section class="box" id="implications">'
        '<div class="box-head"><h3>비바샘 교원연수원 시사점</h3>'
        "<p>오늘 뉴스가 B2G 정책연수 · 샘크리에이티브 · 콘텐츠 파이프라인에 주는 함의</p></div>"
        '<div class="box-scroll"><table><thead><tr><th>뉴스</th><th>사업 함의</th></tr></thead>'
        "<tbody>%s</tbody></table></div></section>"
    ) % body


def render_page(data, issue_no, archive, self_href):
    sections = data.get("sections", [])
    nav = ['<a href="#lead">1면</a>']
    nav += ['<a href="#%s">%s</a>' % (s["id"], plain(s["name"])) for s in sections]
    nav.append('<a href="#implications">시사점</a>')

    opts = ['<option value="">지난 호 보기</option>']
    for iso, href, no in archive:
        opts.append(
            '<option value="%s"%s>제%d호 · %s</option>'
            % (href, " selected" if href == self_href else "", no, iso)
        )

    datestr = fmt_date(data["date"], data.get("weekday"))
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>조간 브리핑 — %s</title>"
        '<meta name="description" content="%s 경제·사회·교육 뉴스 브리핑">'
        "<style>%s</style></head><body>"
        '<div class="sheet"><header class="plate">'
        '<div class="plate-meta"><span>%s</span><span>제%d호</span>'
        "<span>경제 · 사회 · 교육</span></div>"
        '<div class="plate-main">'
        '<h1 class="nameplate">조간<span class="dot">·</span>브리핑</h1>'
        '<div class="plate-side">오늘 지면<b>%d건</b></div>'
        '</div><div class="plate-rules"></div></header></div>'
        '<nav class="nav"><div class="nav-inner">%s</div></nav>'
        '<div class="sheet"><main>%s%s%s%s</main>'
        '<footer class="colophon">'
        "<div>%s<br>자동 생성된 내부 브리핑입니다. 원문 확인 후 인용하세요.<br>"
        '<a href="../full/">← 통합 대시보드로 돌아가기</a></div>'
        '<div class="archive"><label for="archive">지난 호</label>'
        '<select id="archive">%s</select></div>'
        "</footer></div><script>%s</script></body></html>"
    ) % (
        datestr,
        datestr,
        CSS,
        datestr,
        issue_no,
        sum(len(s.get("items", [])) for s in sections) + (1 if data.get("lead") else 0),
        "".join(nav),
        render_ticker(data.get("indices", [])),
        render_lead(data.get("lead")),
        "".join(render_section(s) for s in sections),
        render_box(data.get("implications", [])),
        plain(data.get("sources", "")),
        "".join(opts),
        JS,
    )


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "briefings")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "live/news")
    files = sorted(src.glob("*.json"))
    if not files:
        print("브리핑 데이터 없음: %s" % src)
        return 0

    issues = []
    for i, f in enumerate(files, start=1):
        issues.append((json.loads(f.read_text(encoding="utf-8")), i, "%s.html" % f.stem))
    archive = [(d["date"], href, no) for d, no, href in reversed(issues)]

    out.mkdir(parents=True, exist_ok=True)
    for data, no, href in issues:
        (out / href).write_text(render_page(data, no, archive, href), encoding="utf-8")

    latest, no, href = issues[-1]
    page = render_page(latest, no, archive, href)
    (out / "index.html").write_text(page, encoding="utf-8")

    # Artifact로 재발행할 때 쓰는 본문 전용 사본. Artifact는 <!doctype>/<head>/<body>를
    # 자기가 씌우므로 그 껍데기를 벗겨서 title+style+본문만 남긴다.
    # out 바깥에 두어 _site/news/ 로 복사되지 않게 한다.
    body_only = "<title>%s</title>\n<style>%s</style>\n%s\n" % (
        re.search(r"<title>(.*?)</title>", page, re.S).group(1),
        re.search(r"<style>(.*?)</style>", page, re.S).group(1),
        re.search(r"<body>(.*?)</body>", page, re.S).group(1),
    )
    art = out.parent / "news_artifact.html"
    art.write_text(body_only, encoding="utf-8")

    print("%d개 호 생성 -> %s (최신: 제%d호 %s)" % (len(issues), out, no, latest["date"]))
    print("Artifact 본문 -> %s" % art)
    return 0


if __name__ == "__main__":
    sys.exit(main())
