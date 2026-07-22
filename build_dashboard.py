#!/usr/bin/env python3
"""
scored.json -> dashboard.html (나라장터 공고 스코어링 다이제스트)

두 가지 입력을 모두 지원한다:
  - dict (fetch_g2b_listings.py build_digest()가 만든 {"입찰공고":[...], "사전규격":[...], "낙찰정보":[...]})
    -> render_digest(): 검색창 + 3개 탭(입찰공고/사전규격/낙찰정보) 구조로 렌더링
  - list (score_listings.py 출력, 기존 sample_listings.json 계열)
    -> render(): 기존 TOP5 + 전체목록 단일 리스트 구조로 렌더링 (하위 호환)
"""
import sys, json
from datetime import date, datetime, timedelta

import analytics as an


def days_left(deadline_str, today=None):
    today = today or date.today()
    try:
        d = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        return (d - today).days
    except Exception:
        return None


def deadline_txt(deadline_str, closed_label="마감"):
    dl = days_left(deadline_str)
    if dl is None:
        return "-"
    return f"D-{dl}" if dl >= 0 else closed_label


def tier(score):
    if score >= 70: return ("최우선", "#0B3D2E", "#E6F4EC")
    if score >= 45: return ("검토", "#7A5C00", "#FBF3D9")
    return ("보류", "#6B6B6B", "#EFEFEF")


def budget_txt(budget):
    return f"{budget/100000000:.1f}억" if budget else "미상"


def search_blob(*parts):
    return " ".join(str(p) for p in parts if p).lower().replace('"', "")


BASE_STYLE = '''
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700&family=JetBrains+Mono:wght@400;600&family=Noto+Sans+KR:wght@400;500;600&display=swap');
  :root {
    --paper:#F5F2EC; --ink:#1B1B18; --navy:#14213D; --line:#D8D2C4;
    --accent:#B23A28;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--paper); color:var(--ink); font-family:'Noto Sans KR',sans-serif; padding:0 0 60px; }
  header { background:var(--navy); color:#EFE9DA; padding:28px 24px 22px; }
  .eyebrow { font-family:'JetBrains Mono',monospace; font-size:12px; letter-spacing:.12em; opacity:.7; text-transform:uppercase; }
  h1 { font-family:'Noto Serif KR',serif; font-weight:700; font-size:26px; margin-top:6px; }
  .sub { font-size:13px; opacity:.75; margin-top:8px; font-family:'JetBrains Mono',monospace; }
  .stats { display:flex; gap:18px; margin-top:18px; flex-wrap:wrap; }
  .stat { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); border-radius:4px; padding:10px 16px; }
  .stat b { font-family:'JetBrains Mono',monospace; font-size:20px; display:block; }
  .stat span { font-size:11px; opacity:.7; }
  .notice { max-width:900px; margin:18px auto 0; padding:12px 16px; background:#FBF3D9; border:1px solid #E6D48A; border-radius:4px; font-size:12.5px; color:#6B5300; }
  main { max-width:900px; margin:24px auto 0; padding:0 20px; }
  .toolbar { position:sticky; top:0; background:var(--paper); z-index:5; padding:16px 0 10px; margin-bottom:4px; border-bottom:1px solid var(--line); }
  .search-input { width:100%; padding:11px 14px; border:1px solid var(--line); border-radius:4px; font-size:14px; font-family:'Noto Sans KR',sans-serif; background:#fff; color:var(--ink); }
  .search-input:focus { outline:2px solid var(--navy); outline-offset:1px; }
  .tabs { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
  .tab-btn { font-family:'JetBrains Mono',monospace; font-size:12.5px; padding:8px 14px; border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:20px; cursor:pointer; }
  .tab-btn.active { background:var(--navy); color:#EFE9DA; border-color:var(--navy); }
  .tab-panel { display:none; }
  .tab-panel.active { display:block; }
  .section-title { font-family:'Noto Serif KR',serif; font-size:15px; font-weight:600; border-bottom:2px solid var(--ink); padding-bottom:6px; margin:22px 0 14px; display:flex; justify-content:space-between; align-items:baseline; }
  .section-title small { font-family:'JetBrains Mono',monospace; font-weight:400; font-size:11px; color:#7a7a72; }
  .card { background:#fff; border:1px solid var(--line); border-radius:3px; padding:16px 18px; margin-bottom:12px; }
  .card-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }
  .tier { font-size:11px; font-weight:600; padding:3px 9px; border-radius:20px; }
  .score { font-family:'JetBrains Mono',monospace; font-weight:600; font-size:18px; color:var(--accent); }
  .score em { font-style:normal; font-size:11px; color:#9a9a90; }
  h3 { font-family:'Noto Serif KR',serif; font-size:16px; font-weight:600; line-height:1.4; margin-bottom:6px; }
  h3 a { color:var(--ink); text-decoration:none; }
  h3 a:hover { text-decoration:underline; }
  .meta { font-size:12px; color:#6b6b62; margin-bottom:12px; font-family:'JetBrains Mono',monospace; }
  .dot { margin:0 6px; opacity:.5; }
  .deadline { color:var(--accent); font-weight:600; }
  .bars { display:grid; gap:5px; }
  .bar { display:grid; grid-template-columns:64px 1fr 44px; align-items:center; gap:8px; font-size:11px; color:#7a7a72; }
  .bar i { display:block; height:6px; background:var(--navy); border-radius:3px; opacity:.8; }
  .bar span { font-family:'Noto Sans KR'; }
  .bar b { font-family:'JetBrains Mono',monospace; font-weight:400; text-align:right; }
  .win-card { background:#fff; border:1px solid var(--line); border-left:4px solid var(--navy); border-radius:3px; padding:14px 18px; margin-bottom:10px; }
  .win-top { display:flex; justify-content:space-between; align-items:baseline; gap:10px; flex-wrap:wrap; }
  .winner { font-family:'Noto Serif KR',serif; font-size:15px; font-weight:700; color:var(--navy); }
  .win-amt { font-family:'JetBrains Mono',monospace; font-weight:600; color:var(--accent); }
  .win-title { font-size:13px; color:var(--ink); margin:6px 0 8px; line-height:1.4; }
  .win-title a { color:inherit; text-decoration:none; }
  .win-title a:hover { text-decoration:underline; }
  .empty-msg { font-size:13px; color:#9a9a90; padding:20px 0; text-align:center; display:none; }
  footer { max-width:900px; margin:30px auto 0; padding:0 20px; font-size:11px; color:#9a9a90; font-family:'JetBrains Mono',monospace; }
'''

TAB_SCRIPT = '''
<script>
  var searchInput = document.getElementById('searchBox');
  var panels = Array.prototype.slice.call(document.querySelectorAll('.tab-panel'));
  function applySearch() {
    var q = (searchInput.value || '').toLowerCase().trim();
    panels.forEach(function(panel) {
      var cards = panel.querySelectorAll('[data-q]');
      var visible = 0;
      cards.forEach(function(c) {
        var show = !q || (c.getAttribute('data-q') || '').indexOf(q) !== -1;
        c.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      var empty = panel.querySelector('.empty-msg');
      if (empty) empty.style.display = (cards.length > 0 && visible === 0) ? 'block' : 'none';
    });
  }
  if (searchInput) searchInput.addEventListener('input', applySearch);

  document.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
      document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
      btn.classList.add('active');
      document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
      applySearch();
    });
  });
</script>
'''


def render_bid_card(item, closed_label="마감"):
    dl_txt = deadline_txt(item.get("마감일", ""), closed_label)
    label, fg, bg = tier(item["점수"])
    detail = item["점수상세"]
    title = item["공고명"]
    q = search_blob(title, item.get("발주기관"), item.get("지역"))
    return f'''
        <article class="card" data-q="{q}">
          <div class="card-top">
            <span class="tier" style="color:{fg};background:{bg}">{label}</span>
            <span class="score">{item["점수"]}<em>/100</em></span>
          </div>
          <h3><a href="{item.get("url","#")}" target="_blank" rel="noopener">{title}</a></h3>
          <div class="meta">
            <span>{item.get("발주기관","-")}</span>
            <span class="dot">·</span>
            <span>{item.get("지역","-")}</span>
            <span class="dot">·</span>
            <span>{budget_txt(item.get("예산", 0))}</span>
            <span class="dot">·</span>
            <span class="deadline">{dl_txt}</span>
          </div>
          <div class="bars">
            <div class="bar"><span>키워드</span><i style="width:{detail['키워드']/40*100:.0f}%"></i><b>{detail['키워드']}/40</b></div>
            <div class="bar"><span>예산</span><i style="width:{detail['예산']/25*100:.0f}%"></i><b>{detail['예산']}/25</b></div>
            <div class="bar"><span>지역</span><i style="width:{detail['지역']/20*100:.0f}%"></i><b>{detail['지역']}/20</b></div>
            <div class="bar"><span>마감임박도</span><i style="width:{detail['마감임박도']/15*100:.0f}%"></i><b>{detail['마감임박도']}/15</b></div>
          </div>
        </article>'''


def render_spec_card(item):
    title = item["공고명"].replace("[사전규격] ", "")
    dl_txt = deadline_txt(item.get("마감일", ""), "등록마감")
    label, fg, bg = tier(item["점수"])
    detail = item["점수상세"]
    q = search_blob(title, item.get("발주기관"), item.get("지역"))
    return f'''
        <article class="card" data-q="{q}">
          <div class="card-top">
            <span class="tier" style="color:{fg};background:{bg}">{label}</span>
            <span class="score">{item["점수"]}<em>/100</em></span>
          </div>
          <h3><a href="{item.get("url","#")}" target="_blank" rel="noopener">{title}</a></h3>
          <div class="meta">
            <span>{item.get("발주기관","-")}</span>
            <span class="dot">·</span>
            <span>{item.get("지역","-")}</span>
            <span class="dot">·</span>
            <span>{budget_txt(item.get("예산", 0))}</span>
            <span class="dot">·</span>
            <span class="deadline">의견 {dl_txt}</span>
          </div>
          <div class="bars">
            <div class="bar"><span>키워드</span><i style="width:{detail['키워드']/40*100:.0f}%"></i><b>{detail['키워드']}/40</b></div>
            <div class="bar"><span>예산</span><i style="width:{detail['예산']/25*100:.0f}%"></i><b>{detail['예산']}/25</b></div>
            <div class="bar"><span>지역</span><i style="width:{detail['지역']/20*100:.0f}%"></i><b>{detail['지역']}/20</b></div>
            <div class="bar"><span>마감임박도</span><i style="width:{detail['마감임박도']/15*100:.0f}%"></i><b>{detail['마감임박도']}/15</b></div>
          </div>
        </article>'''


def render_win_card(item):
    q = search_blob(item.get("공고명"), item.get("발주기관"), item.get("낙찰업체"))
    rate = item.get("낙찰율(%)", "")
    rate_txt = f"{rate}%" if rate not in ("", None) else "-"
    prtcpt = item.get("참여업체수", "")
    prtcpt_txt = f"{prtcpt}개사 경쟁" if prtcpt not in ("", None) else "-"
    return f'''
        <article class="win-card" data-q="{q}">
          <div class="win-top">
            <span class="winner">{item.get("낙찰업체","-")}</span>
            <span class="win-amt">{budget_txt(item.get("낙찰금액", 0))} <em style="color:#9a9a90;font-size:11px;">(낙찰율 {rate_txt})</em></span>
          </div>
          <div class="win-title"><a href="{item.get("url","#")}" target="_blank" rel="noopener">{item.get("공고명","-")}</a></div>
          <div class="meta">
            <span>{item.get("발주기관","-")}</span>
            <span class="dot">·</span>
            <span>{prtcpt_txt}</span>
            <span class="dot">·</span>
            <span>개찰 {item.get("개찰일","-")}</span>
          </div>
        </article>'''


def render_digest(digest, out_path, notice=None):
    """fetch_g2b_listings.build_digest() 결과(dict)를 검색+탭 대시보드로 렌더링."""
    bid = digest.get("입찰공고", [])
    spec = digest.get("사전규격", [])
    win = digest.get("낙찰정보", [])

    bid_top = len([x for x in bid if x["점수"] >= 70])
    spec_top = len([x for x in spec if x["점수"] >= 70])

    bid_html = "".join(render_bid_card(x) for x in bid) or '<p class="empty-msg" style="display:block">해당 기간에 조건에 맞는 입찰공고가 없습니다.</p>'
    spec_html = "".join(render_spec_card(x) for x in spec) or '<p class="empty-msg" style="display:block">해당 기간에 조건에 맞는 사전규격이 없습니다.</p>'
    win_html = "".join(render_win_card(x) for x in win) or '<p class="empty-msg" style="display:block">해당 기간에 조건에 맞는 낙찰정보가 없습니다.</p>'

    notice_html = f'<div class="notice">{notice}</div>' if notice else ''

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>나라장터 교원연수 공고 다이제스트</title>
<style>{BASE_STYLE}</style>
</head>
<body>
<header>
  <div class="eyebrow">비바샘원격교육연수원 · B2G 인텔리전스</div>
  <h1>나라장터 교원연수 공고 다이제스트</h1>
  <div class="sub">기준일시 {digest.get("생성일시","-")} · 최근 {digest.get("조회기간_일","-")}일 · {digest.get("기준_범위","")}</div>
  <div class="stats">
    <div class="stat"><b>{len(bid)}</b><span>입찰공고 (최우선 {bid_top})</span></div>
    <div class="stat"><b>{len(spec)}</b><span>사전규격 (최우선 {spec_top})</span></div>
    <div class="stat"><b>{len(win)}</b><span>낙찰정보(경쟁사 동향)</span></div>
  </div>
</header>
{notice_html}
<main>
  <div class="toolbar">
    <input id="searchBox" class="search-input" type="text" placeholder="공고명 · 발주기관 · 지역으로 검색 (예: 경북, AI, ○○교육청)">
    <div class="tabs">
      <button class="tab-btn active" data-tab="bid">입찰공고 ({len(bid)})</button>
      <button class="tab-btn" data-tab="spec">사전규격 ({len(spec)})</button>
      <button class="tab-btn" data-tab="win">낙찰정보 ({len(win)})</button>
    </div>
  </div>

  <div id="panel-bid" class="tab-panel active">
    <div class="section-title">입찰공고<small>점수 내림차순 · 교육청·연수원 발주</small></div>
    {bid_html}
    <p class="empty-msg">검색 결과가 없습니다.</p>
  </div>

  <div id="panel-spec" class="tab-panel">
    <div class="section-title">사전규격<small>조기 정보 · 의견등록마감 기준</small></div>
    {spec_html}
    <p class="empty-msg">검색 결과가 없습니다.</p>
  </div>

  <div id="panel-win" class="tab-panel">
    <div class="section-title">낙찰정보<small>최근 낙찰 동향 · 경쟁사 벤치마크</small></div>
    {win_html}
    <p class="empty-msg">검색 결과가 없습니다.</p>
  </div>
</main>
<footer>
  스코어링 기준(입찰공고·사전규격) — 키워드적합도 40 · 예산규모적합도 25 · 지역적합도 20 · 마감임박도 15 (총 100점)<br>
  대상 범위 — 발주기관/수요기관명에 "교육청" 또는 "연수원"이 포함된 건만 수집 (g2b_config.json org_filter_keywords) · 강점권역: 대구·강원·경북·광주·전북·전남·경기·충남·세종·충북
</footer>
{TAB_SCRIPT}
</body>
</html>'''
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"saved: {out_path}")


def render(scored, out_path, sample_notice=True):
    """구버전 호환: score_listings.py가 만든 단일 리스트를 TOP5+전체목록으로 렌더링."""
    today = date.today().isoformat()
    rows = [render_bid_card(item) for item in scored]

    top_n = len([x for x in scored if x["점수"] >= 70])

    notice = '''
    <div class="notice">
      ※ 본 화면은 샘플 데이터로 파이프라인을 검증한 결과입니다. 실데이터 연동은
      data.go.kr "나라장터 입찰공고정보서비스" OpenAPI(인증키 신청) 또는
      fetch_g2b_listings.py 실데이터 수집 경로를 사용하세요.
    </div>''' if sample_notice else ''

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>나라장터 공고 스코어링 다이제스트</title>
<style>{BASE_STYLE}</style>
</head>
<body>
<header>
  <div class="eyebrow">비바샘원격교육연수원 · B2G 인텔리전스</div>
  <h1>나라장터 공고 스코어링 다이제스트</h1>
  <div class="sub">기준일 {today} · 총 {len(scored)}건 분석 · 최우선 {top_n}건</div>
  <div class="stats">
    <div class="stat"><b>{top_n}</b><span>최우선(70점↑)</span></div>
    <div class="stat"><b>{len(scored)}</b><span>전체 분석 건수</span></div>
    <div class="stat"><b>{sum(1 for x in scored if x.get('예산',0)>=100_000_000)}</b><span>1억↑ 예산 규모</span></div>
  </div>
</header>
{notice}
<main>
  <div class="section-title">TOP 5 우선 검토<small>점수순</small></div>
  {''.join(rows[:5])}
  <div class="section-title">전체 목록<small>점수 내림차순</small></div>
  {''.join(rows[5:]) if len(rows) > 5 else '<p style="font-size:13px;color:#9a9a90;">TOP 5 외 추가 건 없음</p>'}
</main>
<footer>
  스코어링 기준 — 키워드적합도 40 · 예산규모적합도 25 · 지역적합도 20 · 마감임박도 15 (총 100점)<br>
  score_listings.py 로 재생성 가능 · 강점권역: 대구·강원·경북·광주·전북·전남·경기·충남·세종·충북
</footer>
</body>
</html>'''
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"saved: {out_path}")


V2_STYLE = '''
  :root[data-theme="dark"] {
    --paper:#14161A; --ink:#E8E6E0; --navy:#7C93C9; --line:#2E3238; --accent:#E08670;
    --card-bg:#1C1F24;
  }
  :root { --card-bg:#ffffff; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper:#14161A; --ink:#E8E6E0; --navy:#7C93C9; --line:#2E3238; --accent:#E08670;
      --card-bg:#1C1F24;
    }
  }
  .theme-toggle { position:absolute; top:20px; right:24px; background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.25); color:#EFE9DA; border-radius:20px; padding:6px 14px; font-size:12px; font-family:'JetBrains Mono',monospace; cursor:pointer; }
  .nav { display:flex; gap:4px; flex-wrap:wrap; padding:10px 0; margin-bottom:6px; }
  .nav a { font-family:'JetBrains Mono',monospace; font-size:11.5px; color:#6b6b62; text-decoration:none; padding:5px 10px; border:1px solid var(--line); border-radius:14px; }
  .nav a:hover { background:var(--navy); color:#fff; border-color:var(--navy); }
  .kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-top:16px; }
  .kpi { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); border-radius:6px; padding:12px 14px; }
  .kpi b { font-family:'JetBrains Mono',monospace; font-size:19px; display:block; }
  .kpi span { font-size:10.5px; opacity:.75; }
  section.blk { margin:34px 0; }
  .blk h2 { font-family:'Noto Serif KR',serif; font-size:17px; border-bottom:2px solid var(--ink); padding-bottom:7px; margin-bottom:14px; }
  .blk h2 small { font-family:'JetBrains Mono',monospace; font-weight:400; font-size:11px; color:#7a7a72; margin-left:8px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  @media (max-width:760px) { .grid2 { grid-template-columns:1fr; } }
  .panel { background:var(--card-bg); border:1px solid var(--line); border-radius:6px; padding:16px; }
  .insight-list { list-style:none; display:grid; gap:10px; }
  .insight-list li { font-size:13px; line-height:1.55; padding:10px 12px; background:var(--card-bg); border:1px solid var(--line); border-left:3px solid var(--accent); border-radius:4px; }
  .cloud { display:flex; flex-wrap:wrap; gap:8px 12px; align-items:baseline; padding:8px 4px; }
  .cloud span { font-family:'Noto Serif KR',serif; color:var(--navy); font-weight:600; }
  table.dt { width:100%; border-collapse:collapse; font-size:12.5px; }
  table.dt th, table.dt td { padding:7px 9px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }
  table.dt th { font-family:'JetBrains Mono',monospace; font-size:11px; color:#7a7a72; cursor:pointer; user-select:none; position:sticky; top:0; background:var(--paper); }
  table.dt th:hover { color:var(--accent); }
  table.dt td.title { white-space:normal; max-width:340px; }
  table.dt td.title a { color:var(--ink); text-decoration:none; }
  table.dt td.title a:hover { text-decoration:underline; }
  .table-wrap { overflow-x:auto; }
  .filters { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; margin-bottom:14px; }
  .filters select, .filters input { padding:8px 10px; border:1px solid var(--line); border-radius:4px; font-size:12.5px; background:var(--card-bg); color:var(--ink); font-family:'Noto Sans KR',sans-serif; }
  .btn { display:inline-block; padding:7px 14px; border:1px solid var(--line); border-radius:4px; background:var(--card-bg); color:var(--ink); font-size:12px; font-family:'JetBrains Mono',monospace; cursor:pointer; }
  .btn:hover { border-color:var(--navy); color:var(--navy); }
  .tag { display:inline-block; font-size:10.5px; padding:2px 7px; border-radius:10px; font-family:'JetBrains Mono',monospace; }
  .tag-bid { background:#E6F4EC; color:#0B3D2E; }
  .tag-spec { background:#E8ECF7; color:#243B7A; }
  .tag-win { background:#FBF3D9; color:#7A5C00; }
  :root[data-theme="dark"] .tag-bid, :root:not([data-theme="light"]) .tag-bid { background:#0B3D2E; color:#B7E8C8; }
  :root[data-theme="dark"] .tag-spec, :root:not([data-theme="light"]) .tag-spec { background:#243B7A; color:#C7D3F2; }
  :root[data-theme="dark"] .tag-win, :root:not([data-theme="light"]) .tag-win { background:#5C4900; color:#F2DE9E; }
  .caveat { font-size:11px; color:#9a9a90; margin-top:8px; }
'''


def _fmt_amount(n):
    return f"{n/100_000_000:.1f}억" if n else "0"


def _kpi_grid(items):
    cells = "".join(f'<div class="kpi"><b>{v}</b><span>{label}</span></div>' for label, v in items)
    return f'<div class="kpi-grid">{cells}</div>'


def _keyword_cloud(freq):
    if not freq:
        return '<p class="caveat">최근 데이터에서 매칭된 정책 키워드가 없습니다.</p>'
    max_v = max(f["빈도"] for f in freq) or 1
    spans = []
    for f in freq:
        size = 12 + round((f["빈도"] / max_v) * 16)
        spans.append(f'<span style="font-size:{size}px">{f["키워드"]}<sub style="font-size:10px;color:#9a9a90;">{f["빈도"]}</sub></span>')
    return f'<div class="cloud">{"".join(spans)}</div>'


def _org_table(orgs):
    rows = "".join(
        f'<tr><td>{o["기관"]}</td><td>{o["건수"]}</td><td>{_fmt_amount(o["총예산"])}</td><td>{_fmt_amount(o["평균사업비"])}</td></tr>'
        for o in orgs
    )
    return f'''<div class="table-wrap"><table class="dt">
      <thead><tr><th>발주기관</th><th>건수</th><th>총예산</th><th>평균사업비</th></tr></thead>
      <tbody>{rows or '<tr><td colspan="4">데이터 없음</td></tr>'}</tbody></table></div>'''


def _competitor_table(comps):
    rows = "".join(
        f'<tr><td>{i+1}</td><td>{c["낙찰업체"]}</td><td>{c["낙찰건수"]}</td><td>{_fmt_amount(c["총낙찰금액"])}</td>'
        f'<td>{c["평균낙찰률"] if c["평균낙찰률"] is not None else "-"}%</td><td>{c["최근수주일"]}</td>'
        f'<td>{c["주요수주기관"]}</td><td>{c["주요지역"]}</td></tr>'
        for i, c in enumerate(comps)
    )
    return f'''<div class="table-wrap"><table class="dt">
      <thead><tr><th>#</th><th>낙찰업체</th><th>낙찰건수</th><th>총낙찰금액</th><th>평균낙찰률</th><th>최근수주일</th><th>주요수주기관</th><th>주요지역</th></tr></thead>
      <tbody>{rows or '<tr><td colspan="8">데이터 없음</td></tr>'}</tbody></table></div>'''


def _detail_rows(bid, spec, win):
    rows = []
    for x in bid:
        rows.append({
            "구분": "입찰공고", "공고명": x["공고명"], "기관": x.get("발주기관", "-"), "지역": x.get("지역", "-"),
            "예산": x.get("예산", 0), "날짜": x.get("마감일") or x.get("공고일", ""), "점수": x.get("점수", ""), "url": x.get("url", "#"),
        })
    for x in spec:
        rows.append({
            "구분": "사전규격", "공고명": x["공고명"].replace("[사전규격] ", ""), "기관": x.get("발주기관", "-"), "지역": x.get("지역", "-"),
            "예산": x.get("예산", 0), "날짜": x.get("마감일") or x.get("공고일", ""), "점수": x.get("점수", ""), "url": x.get("url", "#"),
        })
    for x in win:
        rows.append({
            "구분": "낙찰정보", "공고명": f'{x.get("공고명","-")} → {x.get("낙찰업체","-")}', "기관": x.get("발주기관", "-"), "지역": x.get("지역", "-"),
            "예산": x.get("낙찰금액", 0), "날짜": x.get("개찰일", ""), "점수": "", "url": x.get("url", "#"),
        })
    rows.sort(key=lambda r: r["날짜"], reverse=True)
    return rows


def _detail_table(rows):
    tag_cls = {"입찰공고": "tag-bid", "사전규격": "tag-spec", "낙찰정보": "tag-win"}
    trs = []
    for r in rows:
        q = search_blob(r["공고명"], r["기관"], r["지역"], r["구분"])
        trs.append(
            f'<tr data-q="{q}" data-cat="{r["구분"]}" data-region="{r["지역"]}" data-budget="{r["예산"]}">'
            f'<td><span class="tag {tag_cls.get(r["구분"],"")}">{r["구분"]}</span></td>'
            f'<td class="title"><a href="{r["url"]}" target="_blank" rel="noopener">{r["공고명"]}</a></td>'
            f'<td>{r["기관"]}</td><td>{r["지역"]}</td><td data-v="{r["예산"]}">{_fmt_amount(r["예산"])}</td>'
            f'<td>{r["날짜"]}</td><td>{r["점수"]}</td></tr>'
        )
    return "".join(trs)


V2_SCRIPT_TEMPLATE = '''
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
(function() {
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem('g2b-theme'); } catch (e) {}
  if (saved) root.setAttribute('data-theme', saved);
  var btn = document.getElementById('themeToggle');
  if (btn) btn.addEventListener('click', function() {
    var cur = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', cur);
    try { localStorage.setItem('g2b-theme', cur); } catch (e) {}
  });
})();

var TREND = __TREND__;
new Chart(document.getElementById('trendChart'), {
  type: 'line',
  data: { labels: TREND.months, datasets: [
    { label: '사전규격', data: TREND['사전규격'], borderColor: '#7C93C9', tension: .25 },
    { label: '입찰공고', data: TREND['입찰공고'], borderColor: '#B23A28', tension: .25 },
    { label: '낙찰', data: TREND['낙찰'], borderColor: '#0B3D2E', tension: .25 },
  ]},
  options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
});

var REGION = __REGION__;
new Chart(document.getElementById('regionChart'), {
  type: 'bar',
  data: { labels: REGION.map(r => r['지역']), datasets: [
    { label: '건수', data: REGION.map(r => r['건수']), backgroundColor: '#14213D' }
  ]},
  options: { responsive: true, plugins: { legend: { display: false } } }
});

var BIZ = __BIZ__;
new Chart(document.getElementById('bizChart'), {
  type: 'pie',
  data: { labels: BIZ.map(b => b['유형']), datasets: [
    { data: BIZ.map(b => b['건수']), backgroundColor: ['#14213D','#B23A28','#7C93C9','#0B3D2E','#E0A458','#6B6B6B','#9A6FB0'] }
  ]},
  options: { responsive: true, plugins: { legend: { position: 'right' } } }
});

(function() {
  var searchBox = document.getElementById('dtSearch');
  var regionSel = document.getElementById('dtRegion');
  var catSel = document.getElementById('dtCat');
  var budgetSel = document.getElementById('dtBudget');
  var rows = Array.prototype.slice.call(document.querySelectorAll('#dtBody tr'));

  function apply() {
    var q = (searchBox.value || '').toLowerCase().trim();
    var region = regionSel.value;
    var cat = catSel.value;
    var minBudget = parseInt(budgetSel.value || '0', 10);
    var visible = 0;
    rows.forEach(function(tr) {
      var okQ = !q || (tr.getAttribute('data-q') || '').indexOf(q) !== -1;
      var okR = !region || tr.getAttribute('data-region') === region;
      var okC = !cat || tr.getAttribute('data-cat') === cat;
      var okB = (parseInt(tr.getAttribute('data-budget') || '0', 10)) >= minBudget;
      var show = okQ && okR && okC && okB;
      tr.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    document.getElementById('dtCount').textContent = visible + '건';
  }
  [searchBox, regionSel, catSel, budgetSel].forEach(function(el) {
    el.addEventListener('input', apply);
    el.addEventListener('change', apply);
  });

  document.querySelectorAll('table.dt th[data-col]').forEach(function(th) {
    var asc = true;
    th.addEventListener('click', function() {
      var col = parseInt(th.getAttribute('data-col'), 10);
      var tbody = document.getElementById('dtBody');
      var trs = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
      trs.sort(function(a, b) {
        var av = a.children[col].getAttribute('data-v') || a.children[col].textContent.trim();
        var bv = b.children[col].getAttribute('data-v') || b.children[col].textContent.trim();
        var an = parseFloat(av), bn = parseFloat(bv);
        var cmp = (!isNaN(an) && !isNaN(bn)) ? (an - bn) : av.localeCompare(bv, 'ko');
        return asc ? cmp : -cmp;
      });
      trs.forEach(function(tr) { tbody.appendChild(tr); });
      asc = !asc;
    });
  });

  document.getElementById('csvBtn').addEventListener('click', function() {
    var visRows = rows.filter(function(tr) { return tr.style.display !== 'none'; });
    var lines = ['구분,공고명,기관,지역,예산,날짜,점수'];
    visRows.forEach(function(tr) {
      var cells = Array.prototype.map.call(tr.children, function(td) { return '"' + td.textContent.trim().replace(/"/g, '""') + '"'; });
      lines.push(cells.join(','));
    });
    var blob = new Blob(['\\ufeff' + lines.join('\\n')], { type: 'text/csv;charset=utf-8;' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'g2b_dashboard_export.csv';
    a.click();
  });
})();
</script>
'''


def render_v2(full, out_path, company_name="비상교육"):
    """전략 대시보드: KPI + 추이/지역/사업유형 차트 + 기관/경쟁사 랭킹 + 키워드 클라우드
    + 규칙기반 인사이트 + 검색/필터/정렬/CSV 가능한 상세 테이블. Chart.js는 CDN에서 로드한다
    (인터넷 연결 필요). 실시간 LLM 분석은 포함하지 않으며, 인사이트는 전부 결정적 규칙으로
    계산한 값이다(analytics.py 참고)."""
    action, ana = full["action"], full["analytics"]
    bid_a, spec_a, win_a = ana["입찰공고"], ana["사전규격"], ana["낙찰정보"]
    bid_act, spec_act = action["입찰공고"], action["사전규격"]

    win_a = an.enrich_win_region(win_a, bid_a)

    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    year = str(today.year)

    kpi_today_spec = len([x for x in spec_a if x.get("공고일") == today.isoformat()])
    kpi_today_bid = len([x for x in bid_a if x.get("공고일") == today.isoformat()])
    kpi_week_win = len([x for x in win_a if x.get("개찰일", "") >= week_start])
    ytd_win = [x for x in win_a if x.get("개찰일", "").startswith(year)]
    ytd_bid = [x for x in bid_a if x.get("공고일", "").startswith(year)]
    kpi_ytd_amount = sum(x.get("낙찰금액", 0) for x in ytd_win)
    kpi_ytd_market = sum(x.get("예산", 0) for x in ytd_bid)
    rates = []
    for x in ytd_win:
        v = x.get("낙찰율(%)", "")
        if v in (None, "", "nan"):
            continue
        try:
            rates.append(float(v))
        except ValueError:
            continue
    kpi_avg_rate = f"{sum(rates)/len(rates):.1f}%" if rates else "-"

    trend = an.monthly_trend(spec_a, bid_a, win_a)
    regions = an.region_stats(bid_a)
    orgs = an.org_ranking(bid_a, top_n=20)
    kwfreq = an.keyword_frequency(bid_a + spec_a)
    biztypes = an.biz_type_breakdown(bid_a + spec_a)
    competitors = an.competitor_ranking(win_a, top_n=30)
    recommend = sorted(bid_act + spec_act, key=lambda x: x["점수"], reverse=True)[:5]
    insights = an.generate_insights(bid_a, spec_act, win_a, recommend, today)

    region_options = "".join(f'<option value="{r["지역"]}">{r["지역"]}</option>' for r in regions)
    cat_options = '<option value="입찰공고">입찰공고</option><option value="사전규격">사전규격</option><option value="낙찰정보">낙찰정보</option>'
    detail_rows = _detail_rows(bid_a, spec_a, win_a)

    insight_html = "".join(f"<li>{s}</li>" for s in insights) or "<li>표시할 인사이트가 없습니다.</li>"

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{company_name} 교육청 B2G 전략 대시보드</title>
<style>{BASE_STYLE}{V2_STYLE}</style>
</head>
<body>
<header style="position:relative">
  <button id="themeToggle" class="theme-toggle">🌙 다크모드</button>
  <div class="eyebrow">{company_name} · 비바샘원격교육연수원 · B2G 전략 대시보드</div>
  <h1>교육청·연수원 나라장터 시장 현황</h1>
  <div class="sub">기준일시 {full.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))} · 대상: 발주기관/수요기관명에 "교육청" 또는 "연수원" 포함 건</div>
  {_kpi_grid([
      ("오늘 등록 사전규격", kpi_today_spec),
      ("오늘 등록 입찰공고", kpi_today_bid),
      ("이번주 낙찰건수", kpi_week_win),
      (f"{year}년 누적 계약금액", _fmt_amount(kpi_ytd_amount)),
      (f"{year}년 누적 공고예산", _fmt_amount(kpi_ytd_market)),
      ("평균 낙찰률", kpi_avg_rate),
  ])}
</header>
<main>
  <nav class="nav">
    <a href="#insight">AI 인사이트</a><a href="#trend">월별 추이</a><a href="#region">지역별</a>
    <a href="#org">기관 랭킹</a><a href="#keyword">키워드</a><a href="#biz">사업유형</a>
    <a href="#competitor">경쟁사 분석</a><a href="#detail">상세 검색</a>
  </nav>

  <section class="blk" id="insight">
    <h2>AI 인사이트<small>규칙 기반 자동 요약 · LLM 미사용</small></h2>
    <ul class="insight-list">{insight_html}</ul>
    <p class="caveat">※ 여기서 "AI"는 통계 규칙(전주/전월 대비 증감 등)으로 자동 생성한 요약입니다. 자연어 생성형 AI 분석을 붙이려면 별도 LLM API 연동이 필요합니다.</p>
  </section>

  <section class="blk" id="trend">
    <h2>월별 발주 추이<small>사전규격 · 입찰공고 · 낙찰 동시비교</small></h2>
    <div class="panel"><canvas id="trendChart" height="90"></canvas></div>
  </section>

  <section class="blk" id="region">
    <h2>지역별 발주현황<small>시도별 건수(입찰공고 기준)</small></h2>
    <div class="panel"><canvas id="regionChart" height="110"></canvas></div>
  </section>

  <div class="grid2">
    <section class="blk" id="org" style="margin-top:0">
      <h2>기관 Ranking<small>Top 20 · 총예산순</small></h2>
      <div class="panel">{_org_table(orgs)}</div>
    </section>
    <section class="blk" id="biz" style="margin-top:0">
      <h2>사업유형 분석<small>제목 기반 규칙 분류</small></h2>
      <div class="panel"><canvas id="bizChart" height="200"></canvas></div>
    </section>
  </div>

  <section class="blk" id="keyword">
    <h2>정책 키워드 분석<small>AIDT·AI·교원연수·기초학력·SEL·논술 등 · 빈도순</small></h2>
    <div class="panel">{_keyword_cloud(kwfreq)}</div>
  </section>

  <section class="blk" id="competitor">
    <h2>경쟁사(낙찰기업) 분석<small>Top 30 · 총낙찰금액순</small></h2>
    <div class="panel">{_competitor_table(competitors)}</div>
    <p class="caveat">※ 지역은 동일 공고번호의 입찰공고에서 역추적해 채운 값이라 일부 "전국"(매칭 실패)으로 표시될 수 있습니다.</p>
  </section>

  <section class="blk" id="detail">
    <h2>상세 검색 · 전체 목록<small><span id="dtCount">{len(detail_rows)}건</span></small></h2>
    <div class="filters">
      <input id="dtSearch" type="text" placeholder="공고명 · 기관 · 지역 검색">
      <select id="dtRegion"><option value="">전체 지역</option>{region_options}</select>
      <select id="dtCat"><option value="">전체 구분</option>{cat_options}</select>
      <select id="dtBudget">
        <option value="0">전체 예산</option>
        <option value="100000000">1억 이상</option>
        <option value="500000000">5억 이상</option>
        <option value="1000000000">10억 이상</option>
      </select>
      <button id="csvBtn" class="btn">CSV 다운로드</button>
    </div>
    <div class="table-wrap"><table class="dt">
      <thead><tr>
        <th data-col="0">구분</th><th data-col="1">공고명</th><th data-col="2">기관</th>
        <th data-col="3">지역</th><th data-col="4">예산/금액</th><th data-col="5">날짜</th><th data-col="6">점수</th>
      </tr></thead>
      <tbody id="dtBody">{_detail_table(detail_rows)}</tbody>
    </table></div>
    <p class="caveat">제목을 클릭하면 나라장터(g2b.go.kr) 원문 공고로 이동합니다. Excel에서 바로 열리는 CSV로 내려받을 수 있습니다.</p>
  </section>
</main>
<footer>
  대상 범위 — 발주기관/수요기관명에 "교육청" 또는 "연수원" 포함 건만 수집(g2b_config.json org_filter_keywords) · data.go.kr 조달청 나라장터 OpenAPI 3종(입찰공고/사전규격/낙찰정보) 실시간 조회<br>
  스코어링 — 키워드적합도 40 · 예산규모적합도 25 · 지역적합도 20 · 마감임박도 15 (총 100점) · 강점권역: 대구·강원·경북·광주·전북·전남·경기·충남·세종·충북<br>
  구성상 생략된 기능 — 발주계획현황서비스(오퍼레이션 미확인), 5개년 예측 모델·Slack/Teams/메일 알림·PDF 리포트(외부 연동·과거 스냅샷 DB 필요, 별도 요청 시 추가 가능)
</footer>
{V2_SCRIPT_TEMPLATE.replace("__TREND__", json.dumps(trend, ensure_ascii=False)).replace("__REGION__", json.dumps(regions, ensure_ascii=False)).replace("__BIZ__", json.dumps(biztypes, ensure_ascii=False))}
</body>
</html>'''
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"saved: {out_path}")


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "action" in data and "analytics" in data:
        render_v2(data, sys.argv[2])
    elif isinstance(data, dict):
        render_digest(data, sys.argv[2])
    else:
        render(data, sys.argv[2])
