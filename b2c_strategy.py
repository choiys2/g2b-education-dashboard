#!/usr/bin/env python3
"""
B2C(개인) 매출 전략 - 🔒 관리 탭 'B2C 매출 전략' 칸 (2026-11-15 사용자 결정: 관리 탭, 수치는 추정 표시)

  주제: 학점 연수 중심 → '실시간 핫토픽 빠른 심화' 모델 + AI 역량 격차(경력·MZ) 세분화 상품
  구조: ① 핵심요약 ② 분석(자동 갱신 수치) ③ 전략 옵션(상품 4종 × 역량 3단계) ④ 실행 로드맵 ⑤ KPI ⑥ 조직·리스크
  자동 갱신 근거(외부 호출 없음, 비용 0): 경쟁 3사 신규 과정 속도·AI 비중(history/competitor_new_courses.jsonl),
    학점 카탈로그 내 실시간 과정 수·가격(history/competitor_course_catalog.json), 교사 관심 추세(samall_set._interest),
    샘몰 SET 점수(samall_set.scores). 고정 근거(공개 보도)는 PUBLIC 에 출처와 함께 둔다.
  추정치는 화면에 '추정'으로 표시한다.
"""
import html
import json
import re
import statistics
from datetime import date, timedelta
from pathlib import Path

import training_topics

HERE = Path(__file__).parent
E = html.escape
NOTE = "color:var(--muted);font-size:12.5px;"
OWN, RIVALS = "비바샘연수원", ("티처빌", "아이스크림")
LIVE = re.compile(r"실시간|라이브|LIVE|ZOOM|Zoom|줌으로|화상|쌍방향|웨비나")
TOPIC_NAME = {t[0]: t[1] for t in training_topics.TOPICS}
PUBLIC = [  # (내용, 출처 이름, 주소) - 공개 보도
    ("초·중·고 교사 10명 중 6명 이상이 수업·평가에 생성형 AI 활용(고교 7명 이상) — 한국교육과정평가원 조사(2026.9 보도)",
     "한국교육신문", "https://hangyo.com/news/article.html?no=109133"),
    ("교사 90% 이상이 생성형 AI 부작용을 걱정하지만 관련 교육을 한 교사는 절반 미만(2026.1 보도)",
     "다음 뉴스", "https://v.daum.net/v/20260111071208949"),
]


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return d


def facts():
    cat = (_j("history/competitor_course_catalog.json") or {}).get("companies") or {}
    out = {"catalog": {}, "new": {}, "hot": [], "ai_mom": None, "new_ai_titles": []}
    for co, v in cat.items():
        cs = v.get("courses") or []
        pr = [c["price"] for c in cs if isinstance(c.get("price"), (int, float)) and c["price"] > 0]
        ok = [c for c in cs if (c.get("title") or "").strip() not in ("", "상세보기")]
        good = len(ok) >= len(cs) * 0.5  # 제목이 제대로 수집된 경우만 주제·실시간 집계
        out["catalog"][co] = {"n": len(cs), "live": sum(1 for c in ok if LIVE.search(c["title"])) if good else None,
                              "ai": sum(1 for c in ok if "ai" in training_topics.classify_topics(c["title"])) if good else None,
                              "price": int(statistics.median(pr)) if pr else None}
    cut = (date.today() - timedelta(days=90)).isoformat()
    p = HERE / "history" / "competitor_new_courses.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if (r.get("first_seen") or "") < cut:
                continue
            co = r.get("company") or ""
            d = out["new"].setdefault(co, {"n": 0, "ai": 0})
            d["n"] += 1
            if "ai" in training_topics.classify_topics(r.get("title") or ""):
                d["ai"] += 1
                if co in RIVALS:
                    out["new_ai_titles"].append((co, r.get("title") or ""))
    try:
        ss = __import__("samall_set")
        intr, _ = ss._interest()
        out["hot"] = sorted(((v["mom"], k) for k, v in intr.items() if k != "subject"), reverse=True)[:5]
        out["ai_mom"] = intr.get("ai", {}).get("mom")
        out["set"] = [r for r in ss.scores()[0] if r["kind"] == "즉시 SET"][:3]
    except Exception:  # noqa: BLE001
        out["set"] = []
    return out


def _tile(lab, val, sub=""):
    return (f"<div style='flex:1;min-width:150px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;'>"
            f"<div style='{NOTE}'>{E(lab)}</div><div style='font-size:21px;font-weight:800;margin-top:2px;'>{val}</div>"
            f"<div style='{NOTE}'>{E(sub)}</div></div>")


def _hbar(rows, unit=""):
    mx = max([v for _, v in rows] + [1])
    return "".join(f"<div style='display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12.5px;'><span style='width:96px;'>{E(k)}</span>"
                   f"<span style='flex:1;height:10px;background:var(--surface-2);border-radius:5px;'><span style='display:block;height:100%;width:{v / mx * 100:.0f}%;"
                   f"background:{'var(--accent)' if k == OWN else '#94a3b8'};border-radius:5px;'></span></span><b style='width:56px;text-align:right;'>{v}{E(unit)}</b></div>"
                   for k, v in rows)


def _tbl(head, rows):
    return ("<div class='tbl-wrap'><table><thead><tr>" + "".join(f"<th>{E(h)}</th>" for h in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>")


def _box(txt):
    return f"<div style='margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--surface-2);border-radius:6px;font-size:13px;'>{txt}</div>"


def build(sec):
    F = facts()
    nw = F["new"]
    own_new = nw.get(OWN, {}).get("n", 0)
    riv_new = sum(nw.get(c, {}).get("n", 0) for c in RIVALS)
    gap_x = (riv_new / 2 / own_new) if own_new else None
    live_all = sum(v["live"] for v in F["catalog"].values() if v["live"] is not None)
    n_all = sum(v["n"] for v in F["catalog"].values() if v["live"] is not None)
    hot = F["hot"]
    hot_txt = " · ".join(f"{TOPIC_NAME.get(k, k)} {'+' if m >= 0 else ''}{round(m * 100)}%" for m, k in hot[:3])
    aim = F["ai_mom"]

    # ① 핵심요약
    tiles = ("<div style='display:flex;gap:10px;flex-wrap:wrap;'>"
             + _tile("신규 과정 출시(최근 90일)", f"{own_new} vs {riv_new // 2 if riv_new else 0}",
                     f"자사 vs 경쟁 1사 평균 · 약 {gap_x:.0f}배 차이" if gap_x else "자사 vs 경쟁 1사 평균")
             + _tile("학점 카탈로그 속 실시간 과정", f"{live_all}/{n_all:,}", "제목 확인된 연수원 합계 · 실시간 시장은 비어 있음")
             + _tile("지금 뜨는 주제(4주 관심)", E(TOPIC_NAME.get(hot[0][1], hot[0][1])) if hot else "-", hot_txt)
             + _tile("AI 기초 검색 관심", (f"{'+' if aim >= 0 else ''}{round(aim * 100)}%" if aim is not None else "-"), "입문은 포화 → 심화·실전으로 이동")
             + "</div>")
    summary = _box(
        "<b>결론</b> — 개인 매출의 다음 성장축은 <b>'학점 과정 수를 늘리는 경쟁'이 아니라 '뜨는 주제를 2주 안에 라이브로 먼저 여는 속도 경쟁'</b>입니다. "
        "경쟁사는 학점 카탈로그를 빠르게 늘리고 있지만(자사 대비 약 10배 속도) 실시간 과정은 사실상 없어, 라이브 심화는 아직 빈 시장입니다. "
        "여기에 AI 활용이 교사 절반 이상으로 퍼졌지만 교육을 받은 교사는 절반 미만이라 <b>역량 격차</b>가 커지고 있어, "
        "같은 주제를 <b>역량 3단계(첫걸음·실전·설계)</b>로 나눠 파는 구조가 객단가와 재구매를 동시에 올립니다.<br>"
        "<b>운영 원칙</b>: ① 핫토픽 → 2주 내 60~90분 라이브 특강 ② 반응 좋은 주제만 2~4주 심화 코호트로 확장(학점 전환 옵션) "
        "③ 매달 라이브를 묶은 구독 멤버십으로 재구매 고정 ④ 실습형 주제는 샘몰 키트와 SET.")
    s1 = sec("① 핵심요약", "개인(B2C) 매출 전략 — 실시간 핫토픽 심화 × AI 역량 격차 세분화. 수치는 매주 자동 갱신, 매출 수치는 추정.", tiles + summary)

    # ② 분석
    pace = _hbar([(c, nw.get(c, {}).get("n", 0)) for c in (OWN,) + RIVALS], "개")
    ai_new = _hbar([(c, nw.get(c, {}).get("ai", 0)) for c in (OWN,) + RIVALS], "개")
    cat_rows = [[f"<b>{E(co)}</b>", f"{v['n']:,}", ("확인 불가" if v["ai"] is None else str(v["ai"])), ("확인 불가" if v["live"] is None else str(v["live"])), (f"{v['price']:,}원" if v["price"] else "-")]
                for co, v in F["catalog"].items()]
    titles = "".join(f"<li>{E(co)} · {E(t[:60])}</li>" for co, t in F["new_ai_titles"][:6])
    hot_rows = "".join(f"<li><b>{E(TOPIC_NAME.get(k, k))}</b> {'+' if m >= 0 else ''}{round(m * 100)}%</li>" for m, k in hot)
    pub = "".join(f"<li>{E(t)} <a href='{E(u)}' target='_blank' rel='noopener noreferrer'>[{E(n)}]</a></li>" for t, n, u in PUBLIC)
    s2 = sec("② 분석 — 속도·빈 시장·격차", "경쟁사 출시 속도와 AI 신규 비중, 학점 카탈로그의 실시간 공백, 교사 관심 이동, AI 활용 격차.",
             "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;'>"
             f"<div><h4>신규 과정 출시(최근 90일)</h4>{pace}<h4>그중 AI 주제</h4>{ai_new}"
             f"<p style='{NOTE}'>경쟁사 AI 신규는 '도구 이름'이 제목에 바로 붙습니다(최신 도구를 몇 주 안에 과정화).</p><ul style='font-size:12.5px;margin:4px 0 0 16px;'>{titles}</ul></div>"
             f"<div><h4>3사 카탈로그 구조</h4>{_tbl(['연수원', '과정', 'AI', '실시간', '가격 중앙값'], cat_rows)}"
             f"<p style='{NOTE}'>카탈로그는 학점 과정 중심이라 실시간 과정이 거의 잡히지 않습니다. 비학점 라이브(별도 메뉴)는 확인 범위 밖이니 '빈 시장'은 학점 카탈로그 기준입니다.</p>"
             f"<h4>교사 관심 상승 주제(최근 4주 vs 직전 8주)</h4><ul style='font-size:13px;margin:4px 0 0 16px;'>{hot_rows}</ul></div></div>"
             f"<h4>AI 활용 격차 — 공개 조사</h4><ul style='font-size:13px;margin:4px 0 0 16px;'>{pub}</ul>"
             + _box("<b>해석</b> — 교사 과반(60%대)이 이미 AI를 쓰지만 관련 교육을 받은 교사는 절반 미만입니다. 쓰는 교사와 못 쓰는 교사로 갈라지는 구간이라, "
                    "<b>연령보다 '활용 단계'로 나누는 것이 정확</b>합니다(연령별 수치는 공개 조사에 없음 → 자체 진단으로 측정). "
                    "경력 교사는 '수업 설계 노하우는 있고 도구가 낯선' 집단, MZ 교사는 '도구는 익숙하고 수업·평가 설계 연결이 약한' 집단이라는 가설로 상품을 나누고 진단 데이터로 검증합니다."))

    # ③ 전략 옵션 - 상품 4종 × 역량 3단계
    prod = [
        ["<b>단기 라이브 특강</b>", "핫토픽 발생 → 2주 내 개설, 60~90분 + 다시보기 7일", "1.9~2.9만원", "회당 150~300명(추정)", "획득·검증용(반응 측정)"],
        ["<b>라이브 심화 코호트</b>", "2~4주·주 1회 라이브 + 과제·피드백, 정원 30~50명, 수료증 / 학점 전환 옵션", "15~25만원", "기수당 30~50명(추정)", "객단가·충성도"],
        ["<b>구독 멤버십</b>", "월 2회 핫토픽 라이브 + 자료실 + 커뮤니티, 연간 할인", "월 1.49만원 / 연 14.9만원", "첫해 1,000~2,000명(추정)", "재구매 고정·LTV"],
        ["<b>연수+상품 SET</b>", "실습형 라이브 + 샘몰 키트·도구 이용권 동봉", "과정가 + 키트 1~3만원", "SET 전환 20~30%(추정)", "객단가·샘몰 연결"],
    ]
    lv = [
        ["<b>L1 첫걸음</b><div style='" + NOTE + "'>도구가 낯선 교사(경력 교사 다수 가설)</div>",
         "‘내 수업 1차시를 AI로 바꿔보기’ — 한 도구·한 장면·따라 하기, 소규모 실습방, 조교 1:15", "안심 설계: 녹화본 반복, 막히면 바로 질문, 결과물 1개 완성"],
        ["<b>L2 실전</b><div style='" + NOTE + "'>쓰긴 쓰는데 수업·평가 연결이 약한 교사</div>",
         "교과별 AI 수업안·평가 루브릭·생기부 활용 실전, 과제 피드백", "학교에서 바로 쓰는 산출물(수업안·루브릭) 중심"],
        ["<b>L3 설계</b><div style='" + NOTE + "'>도구에 능숙한 교사(MZ 다수 가설)</div>",
         "최신 도구·에이전트·바이브코딩으로 수업 도구 제작, 동료 연수 강사 트랙", "크리에이터·강사 육성 → 자사 강사풀 편입(공급 확대)"],
    ]
    gen = _box("<b>세대 짝꿍 코호트(차별화 상품)</b> — L1 경력 교사 + L3 MZ 교사를 2인 1조로 묶어 ‘AI 도구(MZ) × 수업 설계·학급 운영 노하우(경력)’를 서로 가르치는 4주 코호트. "
               "격차를 약점이 아니라 상품으로 만들고, 학교 단위 단체 신청(B2S)으로도 이어집니다. 연령 표기 없이 ‘활용 단계’로만 모집합니다.")
    s3 = sec("③ 전략 옵션 — 상품 4종 × AI 역량 3단계", "같은 핫토픽을 형식(특강→코호트→구독→SET)과 단계(L1→L3)로 나눠 판다. 가격·물량은 추정.",
             _tbl(["상품", "구성", "가격(추정)", "규모(추정)", "역할"], prod)
             + "<h4>AI 역량 3단계 — 진단으로 배정(연령이 아니라 활용 단계)</h4>"
             + _tbl(["단계", "같은 주제의 상품 설계", "설계 원칙"], lv) + gen
             + f"<p style='{NOTE}margin-top:8px;'>진단: 연수원몰 가입·결제 직전 5문항(사용 도구·빈도·수업 적용·평가 적용·제작 경험)으로 L1~L3 자동 배정 → 추천 과정 노출. 응답은 익명 집계만 저장.</p>")

    # 핫토픽 → 라이브 파이프라인 (이번 주 후보 자동)
    cand = [f"<b>{E(TOPIC_NAME.get(k, k))}</b> (관심 {'+' if m >= 0 else ''}{round(m * 100)}%)" for m, k in hot[:3]]
    sets = [f"<b>{E(r['name'])}</b>" for r in F.get("set") or []]
    pipe = _tbl(["단계", "기간", "내용", "담당"], [
        ["1. 감지", "매주 월", "교사 관심 급등 주제 · 경쟁사 신규 과정 · 조간 브리핑 이슈 · 정책 발표", "전략(대시보드 자동)"],
        ["2. 결정", "화", "주간 회의에서 라이브 1~2개 확정(강사·제목·L단계)", "사업총괄"],
        ["3. 개설", "+7일", "강사 섭외·랜딩·연수원몰 상품 등록·채널 공지", "1셀 기획 · 마케팅"],
        ["4. 라이브", "+14일", "특강 진행 · 다시보기 · 만족도·전환 측정", "운영"],
        ["5. 확장", "+30일", "반응 상위 주제만 심화 코호트·학점 과정 개발로 전환", "1셀·2셀"],
    ])
    s3b = sec("핫토픽 → 2주 라이브 파이프라인", "‘먼저 여는 속도’를 체계로 만든다. 아래 후보는 매주 자동으로 바뀝니다.",
              pipe + _box(f"<b>이번 주 라이브 후보</b> — {' · '.join(cand) or '-'}"
                          + (f"<br><b>SET로 바로 묶을 주제</b>(샘몰 SET 후보 칸) — {' · '.join(sets)}" if sets else "")))

    # ④ 로드맵 ⑤ KPI ⑥ 조직·리스크
    road = _tbl(["시기", "할 일", "완료 기준"], [
        ["2026.12", "라이브 특강 파일럿 3회(L1·L2·L3 각 1) · 역량 진단 5문항 · 연수원몰 라이브 상품 유형 추가", "회당 신청 150명, 진단 응답 500건"],
        ["2027.1~2 (방학)", "심화 코호트 2기 · ‘세대 짝꿍’ 1기 · 멤버십 사전 모집", "코호트 완주율 70%, 멤버십 사전 신청 300명"],
        ["2027.3~6", "멤버십 정식 출시(월 2회 라이브) · 반응 상위 주제 학점 과정 전환 · SET 3종", "유료 회원 1,000명, SET 전환 20%"],
        ["2027.7~12", "샘몰 연동 SET 확대 · L3 수료자 강사 트랙 → 강사풀 편입 · 학교 단체(B2S) 패키지", "B2C 신규 매출 비중 목표 달성 기여 확인"],
    ])
    kpi = _tbl(["지표", "정의", "목표(추정)"], [
        ["핫토픽 리드타임", "주제 감지 → 라이브 개설 일수", "14일 이내"],
        ["라이브 전환율", "특강 참가자 중 코호트·멤버십·학점 과정 구매 비율", "15% 이상"],
        ["멤버십 유지율", "3개월 뒤 유지", "60% 이상"],
        ["재구매율", "연 2회 이상 구매 개인 비율", "현재 대비 +10%p"],
        ["객단가", "개인 1인당 연 결제액", "현재 대비 +30%"],
        ["단계 상승률", "L1 → L2 이동(진단 재응답)", "수료자 40%"],
    ])
    risk = _tbl(["구분", "내용", "대응"], [
        ["조직", "라이브는 매주 운영 — 기존 학점 과정 개발과 인력이 겹침", "1셀에 ‘라이브 스쿼드’(기획 1·운영 1·마케팅 0.5) 전담, 학점 과정은 반응 검증된 주제만"],
        ["강사", "핫토픽 강사 확보 속도가 병목", "L3 수료자·현장 교사 크리에이터 풀을 미리 계약(건당 강사료), 강사풀 관리 화면과 연동"],
        ["품질", "속도 우선이 품질 논란으로 번질 위험", "특강은 ‘미리보기’로 표기, 심화·학점은 검수 절차 유지"],
        ["수요", "비학점이라 결제 동기 약함", "수료증·다시보기·자료 제공, 반응 좋으면 학점 과정 전환 약속"],
        ["카니발", "멤버십이 기존 학점 과정 매출을 잠식", "멤버십은 라이브·자료 중심, 학점은 회원 할인으로 연결"],
        ["사람", "‘경력 교사 = 느림’ 낙인", "연령 표기 금지, ‘활용 단계’ 언어만 사용, 세대 짝꿍으로 상호 존중 설계"],
    ])
    s4 = sec("④ 실행 로드맵 · ⑤ KPI · ⑥ 조직·리스크", "12월 파일럿 → 방학 코호트 → 2027 멤버십·SET. 목표치는 추정이며 파일럿 결과로 다시 잡습니다.",
             "<h4>④ 로드맵</h4>" + road + "<h4>⑤ KPI</h4>" + kpi + "<h4>⑥ 조직·리스크</h4>" + risk
             + _box("<b>사람 쪽 제언</b> — 라이브는 ‘빨리 시도하고 빨리 접는’ 문화가 필요합니다. 실패한 특강도 학습으로 기록하고(결정 보드), "
                    "잘 된 주제를 기획한 구성원이 코호트·학점 과정까지 이어 맡도록 해 성취를 체감하게 하세요."))
    return s1 + s2 + s3 + s3b + s4


if __name__ == "__main__":
    print(json.dumps({k: v for k, v in facts().items() if k != "set"}, ensure_ascii=False, indent=1)[:1500])
