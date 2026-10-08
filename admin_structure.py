#!/usr/bin/env python3
"""
'관리' 탭 - 대시보드가 실제로 돌아가는 로직 구조(소스 → 수집 → 분석 → 화면)와 실행 상태.

- deploy.yml 을 직접 읽어 실행 순서·스크립트·쓰는 시크릿 '이름'·시간 상한을 뽑는다(코드와 화면이 어긋나지 않게).
- history/*status*.json 으로 소스별 마지막 수집일·건수·오류를 붙인다.
- 결과 HTML 조각은 combine_dashboard.py 가 GitHub Secret ADMIN_PASSWORD 로 따로 암호화해 싣는다
  (대시보드 비밀번호만으로는 열리지 않음). 시크릿이 없으면 내용은 아예 싣지 않는다.
- 시크릿 값·개인정보는 다루지 않는다(시크릿은 이름만 표시).
"""
import base64
import html
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
ITER = 250_000

# ---------------------------------------------------------------- 계보(소스 → 수집 → 분석 → 탭)
SOURCES = [
    ("g2b", "나라장터 입찰·낙찰·사전규격", "조달청 OpenAPI", "G2B_SERVICE_KEY"),
    ("cntr", "조달청 계약정보(수의 포함)", "조달청 OpenAPI", "G2B_SERVICE_KEY"),
    ("neis", "NEIS 학교·AI 중점·선도학교", "NEIS·odcloud", "NEIS_KEY · ODCLOUD_KEY"),
    ("sinfo", "학교알리미 교원·학생 수", "학교알리미 OpenAPI", "SCHOOLINFO_KEY"),
    ("edufin", "지방교육재정알리미 세입·세출", "eduinfo OpenAPI", "EDUINFO_KEY"),
    ("kosis", "KOSIS 교육재정", "KOSIS OpenAPI", "KOSIS_KEY"),
    ("eduweb", "교육청 수의계약 공개(K-에듀파인)", "교육청 홈페이지(robots 허용분)", "-"),
    ("comp", "경쟁사 강좌·홈페이지·재무", "공개 웹·금융위 공시", "G2B_SERVICE_KEY"),
    ("sheet", "구글시트 운영·영업소통·타사DT", "Sheets API(서비스계정)", "GOOGLE_SHEETS_SA_JSON"),
    ("tour", "관광공사 연수·숙박 시설", "KorService2", "TOUR_API_KEY"),
    ("wx", "기상청 단기예보", "VilageFcst", "G2B_SERVICE_KEY"),
    ("news", "조간 브리핑(언론 취재)", "briefings/*.json", "-"),
    ("gemini", "Gemini(요약·분석·초안)", "Google AI", "GEMINI_API_KEY"),
]
# 수집 스크립트: (id, 이름, 파일, 읽는 소스, 저장 위치, 분석 모듈)
COLLECT = [
    ("c_g2b", "입찰·낙찰 수집", "run_pipeline.py · g2b_full_export.py", ["g2b"], "live/full_live.json", ["m_mkt", "m_comp"]),
    ("c_topic", "연수 입찰 누적", "training_topics.py", ["g2b"], "history/training_bids.jsonl", ["m_mkt", "m_viz"]),
    ("c_cntr", "계약정보 누적", "competitor_contract_export.py", ["cntr"], "history/competitor_contracts.jsonl", ["m_comp", "m_ops", "m_viz"]),
    ("c_compwin", "경쟁사 낙찰 매트릭스", "competitor_g2b_export.py", ["g2b"], "live/competitor_g2b_export.json", ["m_comp"]),
    ("c_neis", "학교·선도학교", "neis_full_export.py", ["neis"], "live/neis_full_export.json", ["m_school"]),
    ("c_sinfo", "교원·학생 수", "schoolinfo_export.py", ["sinfo"], "history/schoolinfo_market.json", ["m_school", "m_ops"]),
    ("c_edufin", "시도 세입·세출", "eduinfo_export.py", ["edufin"], "history/eduinfo_finance.json", ["m_ops"]),
    ("c_kosis", "교육재정 규모", "kosis_edu_finance.py", ["kosis"], "live/kosis_edu_finance.json", ["m_ops"]),
    ("c_eduweb", "학교·교육청 수의계약", "edu_contracts.py", ["eduweb"], "history/edu_contracts.jsonl", ["m_school", "m_viz"]),
    ("c_comp", "강좌·이벤트·재무", "competitor_*_scrape.py · finance", ["comp"], "history/competitor_*.json", ["m_comp", "m_b2s"]),
    ("c_pipe", "운영DT(사업 84건)", "own_pipeline_export.py", ["sheet"], "live/own_pipeline_export.json", ["m_ops", "m_viz"]),
    ("c_comms", "영업소통DT(숫자만)", "pipeline_comms.py", ["sheet"], "live/pipeline_comms.json", ["m_ops"]),
    ("c_banner", "타사DT 배너", "banner_market.py", ["sheet"], "live/banner_market.json", ["m_ops"]),
    ("c_tour", "연수 장소", "tour_export.py", ["tour"], "history/tour_venues.json", ["m_ops"]),
    ("c_wx", "날씨", "weather_export.py", ["wx"], "live/weather.json", ["m_ops"]),
    ("c_news", "브리핑 지면·API", "build_news_briefing.py · news_api_export.py", ["news"], "live/news · live/api/news", ["m_ai", "m_viz"]),
    ("c_ai", "AI 요약·분석·초안", "news_ai · rfp_analysis · ai_insights · exec_story · ai_drafts · recruit_copy", ["gemini", "g2b"], "history/*_last.json · rfp_analysis.jsonl", ["m_ai"]),
]
MODULES = [
    ("m_mkt", "시장·발주 분석", "training_topics · early_warning · analytics"),
    ("m_comp", "경쟁 분석", "content_gap · bundle_products · competitor_*"),
    ("m_school", "학교 수요 분석", "b2s_demand · b2s_board · edu_contracts.build"),
    ("m_ops", "영업·운영 분석", "ops_insights(A·C·E·F) · pipeline_comms · banner_market"),
    ("m_b2s", "상품·콘텐츠 기획", "b2s_board · content_gap"),
    ("m_ai", "AI 해석", "gemini_client(대체 모델·재시도)"),
    ("m_viz", "경영 요약·시각화 집계", "exec_summary · viz_data"),
]
TABS = [
    ("exec", "경영 종합", ["m_viz", "m_ai", "m_ops"]), ("g2bfull", "나라장터 종합", ["m_mkt", "m_comp", "m_ai"]),
    ("market", "시장 분석", ["m_mkt", "m_ops", "m_viz"]), ("g2b", "AI·에듀테크 발주", ["m_mkt"]),
    ("school", "학교단위 발주", ["m_school", "m_viz"]), ("leading", "AI 중점·선도학교", ["m_school"]),
    ("competitor", "경쟁사 연수 분석", ["m_comp", "m_viz"]), ("pipeline", "B2G영업", ["m_ops", "m_ai", "m_viz"]),
    ("b2s", "B2S·샘몰 기획", ["m_b2s", "m_school"]), ("network", "관계망", ["m_comp"]), ("beta", "베타 기능", ["m_viz"]),
]


def _j(path, default=None):
    try:
        return json.loads((HERE / path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _lines(path):
    p = HERE / path
    return sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip()) if p.exists() else 0


def source_status(exec_sources=None):
    """소스별 (건수, 마지막 날짜, 상태, 메모)"""
    s = exec_sources or {}
    st = {}
    pipe, comms, ban = _j("history/pipeline_status.json", {}), _j("history/pipeline_comms_status.json", {}), _j("history/banner_market_status.json", {})
    edu, sinfo, tour = _j("history/eduinfo_status.json", {}), _j("history/schoolinfo_status.json", {}), _j("history/tour_status.json", {})
    ec, cc, ai = _j("history/edu_contracts_status.json", {}), _j("history/competitor_contracts_status.json", {}), _j("history/ai_insights_status.json", {})
    daily = [json.loads(l) for l in (HERE / "history/daily_stats.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] if (HERE / "history/daily_stats.jsonl").exists() else []
    last = daily[-1] if daily else {}
    st["g2b"] = (s.get("g2b") or last.get("g2b_total_detail"), last.get("date"), "ok" if last else "wait", f"연수 입찰 누적 {_lines('history/training_bids.jsonl'):,}건")
    st["cntr"] = (_lines("history/competitor_contracts.jsonl"), cc.get("date"), "ok" if cc.get("status") == "ok" else "warn", f"최근 {cc.get('days', '-')}일 재조회")
    st["neis"] = (s.get("neis"), None, "ok" if s.get("neis") else "wait", "")
    st["sinfo"] = (sinfo.get("market_schools"), sinfo.get("date"), "warn" if sinfo.get("error_count") else "ok", f"오류 {sinfo.get('error_count', 0)}건" if sinfo.get("error_count") else "")
    fin = (edu.get("finance") or {})
    st["edufin"] = (fin.get("sido"), edu.get("date"), "ok" if fin.get("sido") else ("warn" if fin.get("error") else "wait"),
                    f"{(fin.get('years') or ['-'])[0]}~{(fin.get('years') or ['-'])[-1]}" if fin.get("years") else (fin.get("error") or ""))
    st["kosis"] = (None, None, "ok", "")
    st["eduweb"] = (ec.get("total"), ec.get("date"), "ok" if ec.get("total") else "wait",
                    " · ".join(f"{k} {'robots' if (v or {}).get('skipped') else (v or {}).get('rows', '-')}" for k, v in ec.items() if k in ("jbe", "sen", "pen", "gne")))
    st["comp"] = (s.get("catalog"), None, "ok" if s.get("catalog") else "wait", "")
    st["sheet"] = (pipe.get("rows"), pipe.get("date"), "ok" if pipe.get("rows") and not pipe.get("error") else "warn",
                   f"운영 {pipe.get('rows', '-')} · 소통 {comms.get('rows', '-')} · 타사 {ban.get('rows', '-')}")
    st["tour"] = (tour.get("places"), (tour.get("at") or "")[:10], "ok" if tour.get("places") else "wait", f"오류 {len(tour.get('errors') or [])}건" if tour.get("errors") else "")
    st["wx"] = (s.get("weather"), None, "ok" if s.get("weather") else "wait", "")
    files = sorted((HERE / "briefings").glob("20*.json"))
    st["news"] = (len(files), files[-1].stem if files else None, "ok" if files else "wait", "")
    st["gemini"] = (s.get("gemini"), ai.get("date"), "ok" if ai.get("ok") else "warn", "" if ai.get("ok") else "마지막 호출 실패 → 이전 해석본 사용")
    return st


def parse_workflow(path=".github/workflows/deploy.yml"):
    """deploy.yml 단계 목록: 이름·실행 스크립트·시크릿 이름·시간 상한·실패 허용"""
    txt = (HERE / path).read_text(encoding="utf-8")
    steps, cur = [], None
    for line in txt.splitlines():
        m = re.match(r"\s*-\s+name:\s*(.+)$", line)
        if m:
            cur = {"name": m.group(1).strip(), "scripts": [], "secrets": [], "timeout": None, "soft": False, "if": ""}
            steps.append(cur)
            continue
        if not cur:
            continue
        for sc in re.findall(r"python\s+([\w./-]+\.py)", line):
            if sc not in cur["scripts"]:
                cur["scripts"].append(sc)
        for sec in re.findall(r"secrets\.([A-Z0-9_]+)", line):
            if sec not in cur["secrets"]:
                cur["secrets"].append(sec)
        m = re.search(r"timeout-minutes:\s*(\d+)", line)
        if m:
            cur["timeout"] = int(m.group(1))
        if "continue-on-error: true" in line:
            cur["soft"] = True
        m = re.search(r"^\s+if:\s*(.+)$", line)
        if m:
            cur["if"] = m.group(1).strip()
    cron = re.findall(r'cron:\s*"([^"]+)"', txt)
    return [s for s in steps if s["scripts"] or s["secrets"] or "커밋" in s["name"] or "deploy" in s["name"].lower()], cron


# ---------------------------------------------------------------- 렌더링
E = html.escape
COL = {"ok": "#10b981", "warn": "#f59e0b", "wait": "#94a3b8", "err": "#ef4444"}


def diagram(st):
    cols = [("데이터 소스", [(sid, lab, f"{via} · 키 {key}") for sid, lab, via, key in SOURCES]),
            ("수집 스크립트 → 저장", [(cid, lab, f"{f} → {store}") for cid, lab, f, _, store, _ in COLLECT]),
            ("분석 모듈", [(mid, lab, sub) for mid, lab, sub in MODULES]),
            ("대시보드 탭", [("t_" + tid, lab, "") for tid, lab, _ in TABS])]  # 탭 id 는 소스 id 와 겹칠 수 있어 접두어
    W, rowh, top = 1240, 40, 34
    xs, ws = [10, 330, 690, 990], [270, 300, 250, 220]
    H = top + max(len(c[1]) for c in cols) * rowh + 10
    pos = {}
    for ci, (_, nodes) in enumerate(cols):
        gap = (H - top - 10) / len(nodes)
        for ni, (nid, _, _) in enumerate(nodes):
            y = top + ni * gap + (gap - 32) / 2
            pos[nid] = (xs[ci], y, ws[ci])
    edges = []
    for cid, _, _, srcs, _, mods in COLLECT:
        edges += [(s, cid) for s in srcs] + [(cid, m) for m in mods]
    for tid, _, mods in TABS:
        edges += [(m, "t_" + tid) for m in mods]
    out = [f'<svg viewBox="0 0 {W} {H}" style="width:100%;min-width:1000px;height:auto;display:block;font-family:inherit;">']
    for ci, (title, _) in enumerate(cols):
        out.append(f'<text x="{xs[ci]}" y="16" font-size="12" fill="var(--muted)" font-weight="700">{E(title)}</text>')
    for a, b in edges:
        if a not in pos or b not in pos:
            continue
        x1, y1, w1 = pos[a]
        x2, y2, _ = pos[b]
        x1, y1, y2 = x1 + w1, y1 + 16, y2 + 16
        mx = (x1 + x2) / 2
        out.append(f'<path d="M{x1:.0f},{y1:.0f} C{mx:.0f},{y1:.0f} {mx:.0f},{y2:.0f} {x2:.0f},{y2:.0f}" fill="none" stroke="var(--muted)" stroke-width="1.2" opacity=".45"/>')
    for ci, (_, nodes) in enumerate(cols):
        for nid, lab, sub in nodes:
            x, y, w = pos[nid]
            stt = st.get(nid, (None, None, None, ""))[2] if ci == 0 else None
            stroke = COL.get(stt) if stt else ("var(--accent)" if ci == 3 else "var(--border)")
            fill = "color-mix(in srgb, var(--accent) 10%, var(--surface))" if ci == 2 else "var(--surface-2)"
            cnt = st.get(nid, (None,))[0] if ci == 0 else None
            attr = f' data-goto="{nid[2:]}" style="cursor:pointer;"' if ci == 3 else ""
            tip = sub + (f" · 상태 {stt}" if stt else "")
            out.append(f'<g{attr}><title>{E(tip)}</title><rect x="{x}" y="{y:.0f}" width="{w}" height="32" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="{2 if stt or ci == 3 else 1}"/>'
                       f'<text x="{x + 10}" y="{y + 15:.0f}" font-size="12" font-weight="700" fill="var(--ink)">{E(lab[:24])}</text>'
                       f'<text x="{x + 10}" y="{y + 27:.0f}" font-size="9.5" fill="var(--muted)">{E((f"{cnt:,}건 · " if isinstance(cnt, int) and cnt else "") + sub)[:46]}</text></g>')
    out.append("</svg>")
    return "".join(out)


def live_board():
    """V1 업무 플로우 실시간 현황: 지금 각 단계에 있는 일의 수(시트·운영DT 기준)"""
    so = _j("live/sheets_ops.json", {}) or {}
    pipe = (_j("live/own_pipeline_export.json", {}) or {}).get("records", [])
    comms = _j("live/pipeline_comms.json", {}) or {}
    conv = comms.get("conversion") or {}
    c, b, st, bl = so.get("contents") or {}, so.get("bids") or {}, so.get("settle") or {}, so.get("blended") or {}
    stc = (c.get("stages") or {})
    status = {}
    for r in pipe:
        k = str(r.get("status") or "미정").strip()[:8]
        status[k] = status.get(k, 0) + 1
    run = sum(v for k, v in status.items() if re.search(r"진행|운영|모집|확정|계약", k))
    done = sum(v for k, v in status.items() if re.search(r"완료|종료", k))
    flags = st.get("flags") or {}
    low = sum(1 for r in bl.get("rows", []) if (r.get("ready") or 0) < 50)
    lanes = [
        ("연수(콘텐츠) 개발", [("제작·준비", stc.get("제작·준비")), ("심사 중", stc.get("심사 중")), ("인증 완료", stc.get("인증 완료")),
                           ("오픈 예정", stc.get("오픈 예정")), ("서비스 중", stc.get("서비스 중"))]),
        ("B2G 판매", [("소통 기관", conv.get("orgs")), ("입찰 검토", b.get("n")), ("입찰 참여", b.get("joined")), ("수주", b.get("won")),
                    ("운영 중", run), ("종료", done), ("정산 경보", sum(flags.values()) if flags else 0)]),
        ("오프라인 연수", [("준비 사업", bl.get("n")), ("준비율 50% 미만", low)]),
        ("B2C·학교 판매", [("매출 과정", len([r for r in c.get("rows", []) if (r.get("total") or 0) > 0]) or None)]),
    ]
    cell = lambda lab, v, warn=False: (f'<div style="flex:1;min-width:110px;padding:8px 10px;border-radius:8px;border:1px solid {"#ef4444" if warn and v else "var(--border)"};'
                                       f'background:var(--surface-2);"><div style="font-size:11.5px;color:var(--muted);">{E(lab)}</div>'
                                       f'<div class="num" style="font-size:20px;font-weight:800;">{"-" if v in (None, "") else f"{v:,}"}</div></div>')
    rows = "".join(f'<div style="display:flex;gap:8px;align-items:stretch;margin:8px 0;flex-wrap:wrap;"><div style="width:130px;font-weight:800;font-size:13px;padding-top:8px;">{E(n)}</div>'
                   + '<span style="color:var(--muted);align-self:center;">→</span>'.join(cell(l, v, "경보" in l or "미만" in l) for l, v in cells) + "</div>" for n, cells in lanes)
    note = f"기준: 시트 {E(so.get('fetched') or '-')} 조회 · 운영DT {len(pipe)}건"
    return rows + f'<p class="tt-note">{note}. 빨간 테두리는 조치가 필요한 칸입니다. 단계 정의는 아래 업무 플로우 표와 같습니다.</p>'


def build_html(exec_sources=None):
    st = source_status(exec_sources)
    steps, cron = parse_workflow()
    now = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
    badge = lambda s: f'<span style="display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:700;background:color-mix(in srgb, {COL.get(s, "#94a3b8")} 18%, transparent);color:{COL.get(s, "#94a3b8")};">{ {"ok": "정상", "warn": "주의", "wait": "대기", "err": "오류"}.get(s, s or "-") }</span>'
    src_rows = "".join(
        f"<tr><td><b>{E(lab)}</b><div style='font-size:11.5px;color:var(--muted);'>{E(via)}</div></td><td><code>{E(key)}</code></td>"
        f"<td class='num'>{'' if not isinstance(st[sid][0], int) else f'{st[sid][0]:,}'}</td><td>{E(str(st[sid][1] or '-'))}</td><td>{badge(st[sid][2])}</td><td style='font-size:12px;'>{E(st[sid][3] or '')}</td></tr>"
        for sid, lab, via, key in SOURCES)
    phase = lambda n: ("수집" if re.search(r"수집|export|누적|fetch|스크레이핑|날씨|장소|알리미|수의계약|소통|배너|파이프라인|KOSIS|재무", n) else
                       "AI" if re.search(r"AI|Gemini", n) else "조합·산출" if re.search(r"조합|보고|캘린더|PDF|지면|JSON|히스토리|건전성", n) else "배포")
    step_rows = "".join(
        f"<tr><td class='num'>{i + 1}</td><td>{E(phase(s['name']))}</td><td>{E(s['name'])}</td><td style='font-size:12px;'><code>{E(' · '.join(s['scripts']) or '-')}</code></td>"
        f"<td style='font-size:12px;'>{E(', '.join(s['secrets']) or '-')}</td><td class='num'>{s['timeout'] or '-'}</td><td>{'계속' if s['soft'] else '<b>중단</b>'}</td></tr>"
        for i, s in enumerate(steps))
    hist = [("training_bids.jsonl", "연수 입찰 12개월"), ("competitor_contracts.jsonl", "계약정보"), ("edu_contracts.jsonl", "학교·교육청 수의계약"),
            ("daily_stats.jsonl", "일일 지표"), ("rfp_analysis.jsonl", "제안요청서 AI 분석"), ("news_ai.jsonl", "브리핑 AI 요약"), ("competitor_new_courses.jsonl", "경쟁사 신규 강좌")]
    hist_rows = "".join(f"<tr><td><code>history/{E(f)}</code></td><td>{E(d)}</td><td class='num'>{_lines('history/' + f):,}</td></tr>" for f, d in hist)
    sched = [("매일 06:00", "대시보드 수집·분석·배포 (deploy.yml, cron " + ", ".join(cron) + ")"),
             ("매일 05:40", "조간 브리핑 발행 루틴 → news.yml 이 지면·위젯만 갱신"),
             ("매주 월 06:00", "경쟁사 강좌 카탈로그 전체 수집 (course_catalog.yml)"),
             ("수시", "API 키 빠른 점검 (key_test.yml, .github/key_test_trigger 변경 시)"),
             ("main 푸시", "코드 변경 즉시 전체 재배포(대기 중 실행은 최신 1건만 남김)")]
    guards = [("수집 실패 격리", "단계마다 continue-on-error·시간 상한 — 한 소스 장애가 전체를 막지 않음"),
              ("빈 데이터 배포 차단", "check_g2b_health.py: 나라장터 수집량이 임계치 미만이면 배포 생략(어제 화면 유지)"),
              ("AI 장애 대비", "gemini_client: 503이면 대체 모델 즉시 전환, 429는 모델 교체, 스크립트별 시간 상한, 실패 시 마지막 성공본"),
              ("개인정보", "시트는 화이트리스트 열만 읽음, 영업자 익명화, 소통은 숫자만, 수의계약 상대자 이름 미저장"),
              ("키 보호", "API 키는 GitHub Secret 에만, 로그 마스킹, 코드·history 에 미기록"),
              ("계획 수치", "2027 경영계획은 Secret PLAN_2027_JSON 에서만 읽어 이 관리 탭 암호문 안에만 실음(history·브리핑·공개 화면 미기록)"),
              ("접근 통제", "검색 차단(noindex) + 대시보드 비밀번호(AES-256-GCM) + 관리 탭 별도 비밀번호"),
              ("외부 사이트 예절", "robots.txt 확인 후 허용 경로만, 요청 간 0.6~1초 간격, S2B 는 자동 수집 안 함")]
    css = "<style>.adm table{width:100%;border-collapse:collapse;font-size:13px;} .adm th,.adm td{padding:7px 8px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top;} .adm th{color:var(--muted);font-weight:700;font-size:12px;} .adm .num{text-align:right;font-variant-numeric:tabular-nums;} .adm h4{margin:22px 0 8px;font-size:15px;} .adm code{font-size:11.5px;}</style>"
    sec = lambda t, d, body: f'<section class="panel"><div class="panel-head"><div><p class="panel-title">{t}</p><p class="panel-desc">{d}</p></div></div>{body}</section>'
    try:
        plan_html = __import__("plan2027").build_html(sec)
    except Exception as e:  # 계획 섹션 오류가 관리 탭 전체를 막지 않게
        print(f"[경고] 2027 경영계획 섹션 실패: {type(e).__name__}: {str(e)[:120]}")
        plan_html = ""
    go = lambda t, lab: f"""<a href="javascript:void 0" onclick="document.getElementById('{t}').scrollIntoView({{behavior:'smooth'}})" style="font-weight:800;">{lab}</a>"""
    nav = ("<div style='display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px;'>" + go("admPlan", "2027 경영계획")
           + "<span style='color:var(--muted);'>·</span>" + go("admSys", "시스템 구조·실행 상태") + "</div>")
    return (css + '<div class="adm">' + nav + f'<div id="admPlan">{plan_html}</div>'
            + "<h3 id='admSys' style='margin:22px 0 10px;'>시스템 구조 · 실행 상태</h3>"
            + sec("데이터 연계 다이어그램 (상세)", f"소스 → 수집 스크립트(저장 위치) → 분석 모듈 → 화면. 소스 테두리 색 = 마지막 실행 상태(초록 정상·주황 주의·회색 대기). 상자에 마우스를 올리면 스크립트·저장 파일·키 이름이 보이고, 오른쪽 탭을 누르면 이동합니다. 생성 {now} KST",
                  f'<div style="overflow-x:auto;">{diagram(st)}</div>')
            + sec("업무 플로우 실시간 현황", "지금 각 업무 단계에 몇 건이 있는지(콘텐츠DT·입찰DT·정산관리·26운영(블렌디드)·운영DT·영업소통DT).", live_board())
            + sec("업무 플로우 × 시스템 연계", "연수개발 · B2G 판매 · B2C·학교 판매 · 오프라인 연수 4개 업무 플로우를 단계별로 옮기고, 각 단계에서 쓰는 대시보드 화면과 아직 시스템 밖인 부분(갭)을 붙였습니다. 화면 쪽 패널 제목 옆 '업무' 배지도 같은 연계표에서 나옵니다.",
                  __import__("workflows").render())
            + sec("소스별 실행 상태", "마지막 수집일·건수·상태. 키는 GitHub Secret 이름만 표시합니다.",
                  f"<div class='tbl-wrap'><table><thead><tr><th>소스</th><th>키(시크릿 이름)</th><th class='num'>건수</th><th>마지막</th><th>상태</th><th>메모</th></tr></thead><tbody>{src_rows}</tbody></table></div>")
            + sec("배포 파이프라인 실행 순서", "deploy.yml 을 그대로 읽은 결과입니다(코드가 바뀌면 이 표도 자동으로 바뀝니다). '계속' = 실패해도 다음 단계 진행, '중단' = 실패 시 배포 중단.",
                  f"<div class='tbl-wrap'><table><thead><tr><th class='num'>#</th><th>구분</th><th>단계</th><th>스크립트</th><th>시크릿</th><th class='num'>상한(분)</th><th>실패 시</th></tr></thead><tbody>{step_rows}</tbody></table></div>")
            + sec("누적 데이터(history/)", "매일 배포 끝에 저장소로 커밋되는 누적 파일과 현재 행 수.",
                  f"<div class='tbl-wrap'><table><thead><tr><th>파일</th><th>내용</th><th class='num'>행</th></tr></thead><tbody>{hist_rows}</tbody></table></div>")
            + sec("실행 일정 · 안전장치", "",
                  "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px;'>"
                  + "<div><h4>일정</h4><table><tbody>" + "".join(f"<tr><td style='white-space:nowrap;'><b>{E(a)}</b></td><td>{E(b)}</td></tr>" for a, b in sched) + "</tbody></table></div>"
                  + "<div><h4>안전장치</h4><table><tbody>" + "".join(f"<tr><td style='white-space:nowrap;'><b>{E(a)}</b></td><td>{E(b)}</td></tr>" for a, b in guards) + "</tbody></table></div></div>")
            + "</div>")


def encrypted_blob(exec_sources=None):
    """ADMIN_PASSWORD 가 있으면 {s,i,c,n} 암호문, 없으면 None(내용 미게시)."""
    pw = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not pw:
        return None
    try:
        return _encrypt(build_html(exec_sources), pw)
    except Exception as e:  # 암호화 실패가 대시보드 조합 전체를 막지 않게(내용은 싣지 않음)
        print(f"[경고] 관리 탭 암호화 실패: {str(e)[:120]}")
        return None


def _encrypt(text, pw):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode())
    ct = AESGCM(key).encrypt(iv, text.encode("utf-8"), None)
    e = lambda b: base64.b64encode(b).decode()
    return {"s": e(salt), "i": e(iv), "c": e(ct), "n": ITER}


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "live/admin_preview.html"
    Path(out).write_text("<meta charset=utf-8>" + build_html(), encoding="utf-8")
    print("admin preview ->", out)
