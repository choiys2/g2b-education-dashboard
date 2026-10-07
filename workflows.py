#!/usr/bin/env python3
"""
업무 플로우 4종(연수개발 · B2G 판매 · B2C·학교 판매 · 오프라인 연수)과 대시보드 기능의 연계표.

- 관리 탭(admin_structure.py)이 이 데이터를 스윔레인으로 그리고, 단계마다 '이 단계에서 쓰는 화면'과
  '아직 자동화 안 된 부분(갭)'을 붙인다.
- badge_map() 은 화면 쪽 패널 제목에 '업무 단계' 배지를 붙일 때 쓴다(단계 이름만, 내부 문서 내용은 없음).

레인 표기(한 줄 = 한 갈래, ' > ' 로 순서):
  "태그:내용"            작업
  "?판단|Yes:다음|No:되돌림"  판단(마름모)
  "=플로우명"             다른 플로우로 연결
"""
import html

E = html.escape

# 연계 대상: (탭, 앵커 id, 라벨)
F = {
    "topics": ("g2bfull", "trainingTopicsPanel", "2027 연수 개발 추천"),
    "heat": ("g2bfull", "viz3", "월×주제 발주 히트맵"),
    "rfp": ("g2bfull", "rfpPanel", "제안요청서 AI 분석·참여 판정"),
    "funnel_rfp": ("g2bfull", "viz4", "제안요청서 판정 깔때기"),
    "early": ("g2bfull", "earlyWarnPanel", "발주 조기경보"),
    "drafts": ("g2bfull", "trainingTopicsPanel", "AI 기획서 초안"),
    "bubble": ("g2bfull", "viz5", "발주기관 버블"),
    "brief": ("exec", "aiBrief", "오늘의 AI 브리핑"),
    "story": ("exec", "exStory", "지표 스토리라인"),
    "channel": ("exec", "viz1", "채널 믹스 진척"),
    "signal": ("exec", "viz2", "경영 신호등"),
    "tile": ("market", "viz6", "17개 시도 공략 지도"),
    "issues": ("market", "viz8", "브리핑 이슈 흐름"),
    "news": ("market", "marketNewsPanel", "교육 뉴스·조간 브리핑"),
    "edu_cntr": ("school", "eduCntrPanel", "학교·교육청 연수 수의계약"),
    "edu_viz": ("school", "viz9", "학교 수의계약 3종(금액 구간)"),
    "contract": ("competitor", "contractPanel", "계약 기준 B2G 점유"),
    "share": ("competitor", "viz12", "계약 점유율 추이"),
    "price_dots": ("competitor", "viz13", "업체별 계약 단가"),
    "comp_only": ("competitor", "viz14", "경쟁사만 수주한 기관"),
    "gap": ("competitor", "contentGapPanel", "콘텐츠 갭 분석"),
    "catalog": ("competitor", "courseCatalogPanel", "경쟁사 강좌 카탈로그"),
    "bundle": ("competitor", "bundlePanel", "결합상품"),
    "new_courses": ("competitor", "viz15", "신규 강좌 출시 속도"),
    "pipe": ("pipeline", "pipeTable", "전체 사업 리스트"),
    "recruit": ("pipeline", "recruitPanel", "모집률 조기경보·AI 홍보 문구"),
    "recruit_sc": ("pipeline", "viz18", "모집 위험 구역"),
    "comms": ("pipeline", "commsPanel", "사업 진행 분석"),
    "conv": ("pipeline", "convPanel", "소통→수주 전환"),
    "sales_funnel": ("pipeline", "viz16", "영업 깔때기"),
    "budget": ("pipeline", "budgetPanel", "시도 예산 여력"),
    "recontract": ("pipeline", "recontractPanel", "재계약 캘린더"),
    "banner": ("pipeline", "bannerPanel", "연수 배너 시장"),
    "ops_plan": ("pipeline", "opsPlanPanel", "집합연수 운영 지원·체크리스트"),
    "venue": ("pipeline", "venuePanel", "집합연수 장소 찾기"),
    "venue_map": ("pipeline", "viz21", "연수 장소·날씨 지도"),
    "b2s_market": ("b2s", "b2sMarketPanel", "B2S 학교 잠재 수요"),
    "matrix": ("b2s", "viz22", "샘몰 상품 우선순위"),
    "treemap": ("b2s", "viz23", "B2S 시장 덩어리"),
    "price": ("b2s", "viz24", "가격대 비교"),
    "leading": ("leading", "viz11", "AI 중점·선도학교 교차"),
}

WORKFLOWS = [
    {"id": "dev", "name": "연수(콘텐츠) 개발", "owner": "샘크리에이티브", "phases": [
        {"name": "콘텐츠 개발 계획 수립", "lanes": [
            "분석:시장 및 경쟁사 분석 > 분석:교사 요구사항·트렌드 분석 > 조사:신규 연수 아이템 발굴 > 문서작성:B2G/B2C 개발 대상 과정 선정 > 선정:개발 우선순위 선정 > 기획:연간 콘텐츠 개발 계획 > 결재:예산 수립·품의 상신 > 기타:개발 단가 기준 관리"],
         "links": [("topics", "auto"), ("heat", "auto"), ("gap", "auto"), ("new_courses", "auto"), ("matrix", "auto"), ("issues", "part")],
         "gaps": ["개발 단가 기준표가 시스템 밖(엑셀)에 있음 → 경쟁사 가격대·차시 단가와 나란히 보이게 연동 가능"]},
        {"name": "콘텐츠 기획", "lanes": [
            "분석:콘텐츠 개발 요구 분석 > 조사:협업부서 제작 요청 수렴 > 문서작성:개별 콘텐츠 품의서 > ?품의 승인|Yes:SME 섭외|No:품의안 수정·재협의",
            "선정:SME 섭외 > 기획:킥오프 미팅 > 기획:커리큘럼·학습목표 설계 > 기획:과정 유형·제작 방식 검토 > 선정:개발사 선정 > 기획:홍보·판매 방향 수립"],
         "links": [("drafts", "auto"), ("catalog", "auto"), ("rfp", "part")],
         "gaps": ["SME·강사 Pool 이 시스템에 없음 → 구글시트 'SME DT' 를 만들면 주제별 섭외 후보 자동 추천 가능"]},
        {"name": "제작 방식 판단", "lanes": ["?내부 제작 여부|Yes:내부 제작|No:외주 제작"], "links": [], "gaps": []},
        {"name": "계약 및 등록", "lanes": [
            "계약:SME·개발사·협력사 계약 > 등록:거래처 등록 > 정산:세금계산서 요청 > 지출결의:선금 지출결의서 상신",
            "세팅:LMS 과정 개설", "문서작성:공문 발송"], "links": [], "gaps": ["계약·선금 진행 상태 추적 없음(ERP 영역)"]},
        {"name": "콘텐츠 개발 및 심사", "lanes": [
            "기획:직무·자율·실시간 제작 계획 > 기획:커리큘럼 확정 > 검토:원고 검토 > 검수:저작권·초상권 검토 > ?저작권 승인|Yes:과정명·차시명 확정|No:대체 자료 요청·수정",
            "?실시간 연수 여부|Yes:모집페이지 기획·탑재 → KERIS 운영계획서 → ZOOM 세팅 → 리허설 → 연수 진행 → 만족도 → KERIS 운영결과서 → 이수자 명단|No:UI 검토 → 프로토타입 → 스토리보드",
            "촬영:영상 촬영(온라인·오프라인) > 검수:1차 개발본 검수 > ?수정 필요|Yes:개발물 검수·수정|No:LMS 탑재",
            "?KERIS 인증 필요|Yes:심사서류 작성·등록 → 심사 결과 → LMS 합격 정보 등록 → 서비스 오픈|No:상시연수 심사 → 상시연수 서비스 오픈",
            "정산:개발사 세금계산서 > 지출결의:잔금 지출결의"],
         "links": [], "gaps": ["제작 진척(원고·촬영·검수·심사) 단계 추적 없음 → 구글시트 '콘텐츠DT' 연동 시 지연 경보 자동화 가능(시트 이미 존재, 미연동)"]},
        {"name": "오픈 준비", "lanes": [
            "기획:홍보·마케팅 전략 > 검토:이벤트 게시 검토",
            "기획:과정소개 페이지·배너 기획 > 검토:디자인 검토 > 등록:LMS 등록",
            "발송:이수자료 요청 > 검토:이수자료 검토 > 등록:LMS 등록",
            "문서작성:영업용 연수 제안서", "등록:계약·정산 운영자료 전달"],
         "links": [("banner", "auto"), ("price", "auto"), ("bundle", "auto"), ("issues", "part")], "gaps": []},
        {"name": "운영 및 성과 분석", "lanes": [
            "사후업무:SME·개발사 이력 관리 > 사후업무:제작 데이터 수급 > 사후업무:최종 데이터 백업",
            "운영:CS 응대·유지보수 > 검수:수정본 검수 > 탑재:LMS 업로드",
            "분석:수강 후기·만족도 성과 분석 > 기획:차기 연수 기획 반영",
            "운영:교사 연구회·SME·강사 Pool·CP 제휴 관리 > 분석:운영 과정 매출 관리"],
         "links": [("share", "auto"), ("new_courses", "auto"), ("signal", "part")],
         "gaps": ["수강 후기·만족도·과정별 매출이 없음 → LMS/매출 데이터 연동 시 과정별 성과 순위 자동화"]},
    ]},
    {"id": "b2g", "name": "B2G 판매", "owner": "샘브릿지", "phases": [
        {"name": "사업 발굴 협의", "lanes": [
            "선정:경쟁사 분석 > 문서작성:연수개발 요구안", "회의:교육청 정책+예산 분석 > 문서작성:연수개발 요구안",
            "?개발 유무|Yes:=연수(콘텐츠) 개발|No:요구안 재작성"],
         "links": [("contract", "auto"), ("comp_only", "auto"), ("budget", "auto"), ("tile", "auto"), ("recontract", "auto"), ("early", "auto"), ("conv", "auto"), ("bubble", "auto")],
         "gaps": []},
        {"name": "연수 제안", "lanes": ["회의:교육청 협의 > 선정:연수 과정 선택 > 문서작성:운영 계획서"],
         "links": [("rfp", "auto"), ("funnel_rfp", "auto"), ("drafts", "auto"), ("topics", "auto"), ("comms", "part")], "gaps": []},
        {"name": "계약 및 사업확정", "lanes": [
            "계약:계약 초안 > 문서작성:나라장터 / 학교장터 / 수의계약 > 문서작성:보증보험·인지세 처리 > 문서작성:운영 계획서"],
         "links": [("contract", "auto"), ("edu_cntr", "auto"), ("price_dots", "auto"), ("pipe", "part")],
         "gaps": ["입찰 마감 .ics 캘린더 피드는 있으나 보증보험·인지세 처리 체크 없음"]},
        {"name": "연수 운영", "lanes": [
            "개발:온라인 배너 개설 > 운영:연수 모집·홍보 > ?모집 결과|Yes:사업 운영|No:모집현황 보고",
            "회의:모집현황 보고 > 운영:추가 홍보 > ?목표 달성|Yes:모집 마감 → 이수 독려|No:추가 홍보"],
         "links": [("recruit", "auto"), ("recruit_sc", "auto"), ("comms", "auto"), ("banner", "part")], "gaps": []},
        {"name": "결과보고", "lanes": ["운영:결과보고서 정리 > 운영:장학사 보고 > 운영:전자계약 완수 처리 > 기타:계산서 발행"],
         "links": [("pipe", "part")], "gaps": ["결과보고서 초안 자동 생성(운영DT 인원·이수율 + Gemini) 가능 — 미구현"]},
        {"name": "정산 및 매출관리", "lanes": ["등록:나이스(NEIS) 등재 > 정산:정산 및 입금 > 등록:사업 종결"],
         "links": [("pipe", "auto"), ("channel", "auto"), ("sales_funnel", "part")], "gaps": ["입금 여부가 운영DT에 없음 → 열 추가 시 미수금 경보 가능"]},
    ]},
    {"id": "b2c", "name": "B2C·학교 판매", "owner": "샘콜라보", "phases": [
        {"name": "기획 및 설계", "lanes": [
            "기획:연수 수요 조사 > 기획:목표 수립 > 설계:기수 설계(직무·상시·자율) > 설계:운영 방식(기간별·실시간) > 검토:검토·피드백"],
         "links": [("b2s_market", "auto"), ("treemap", "auto"), ("edu_viz", "auto"), ("leading", "auto"), ("matrix", "auto")], "gaps": []},
        {"name": "준비 및 홍보", "lanes": ["준비:모집 공고·접수 > 준비:학습 환경 구성 > 홍보:사전 안내 > 설계:수강신청"],
         "links": [("issues", "part"), ("bundle", "part")], "gaps": []},
        {"name": "연수 운영·평가", "lanes": [
            "운영:학습 진행 > 운영:학습평가 > 운영:학습관리", "운영:소통·지원 > 운영:질의응답", "운영:참여도 제고 > 운영:출결·진도율 관리"],
         "links": [], "gaps": ["LMS 진도율·출결 미연동 → 연동 시 이탈 위험 학습자 경보 가능"]},
        {"name": "문의 대응", "lanes": [
            "기타:문의 접수 > 기타:내용 확인 > 기타:응대 > 기타:결과 기록·공유",
            "기타:학교 단체 문의 > 발송:견적서 > 운영:결제 방식 협의 > 운영:결제 후 입과 처리 > 운영:입과 안내 문자"],
         "links": [("edu_viz", "auto"), ("price", "auto")], "gaps": ["학교 견적 단가 기준 → 학교 수의계약 금액 구간(100~500만원 중심)과 연결해 견적 가이드 제공 가능"]},
        {"name": "운영 지원", "lanes": ["기타:요청사항 확인 > 발송:교재 배송 / 그라운드 문자 / 이수 통보 > 기타:진행 확인"], "links": [], "gaps": []},
        {"name": "매출 데이터 관리", "lanes": [
            "문서작성:매출자료 수집 > 문서작성:매출파일 일별 작성 > 기타:데이터 관리 > 정산:월말 수익쉐어·튜터비 정산 > 정산:계산서·지출결의 > 검토:검토·공유"],
         "links": [("channel", "part")], "gaps": ["일별 매출파일 미연동 → 시트 연동 시 B2C 실제 비중으로 채널 믹스(목표 60%) 정확도 향상"]},
        {"name": "이수 및 환류", "lanes": ["운영:이수 처리 > 운영:증빙자료 발급 > 운영:사후 관리", "운영:결과보고"], "links": [], "gaps": []},
    ]},
    {"id": "off", "name": "오프라인(집합) 연수", "owner": "샘브릿지·운영", "phases": [
        {"name": "기획 및 착수", "lanes": [
            "분석:발주처 요구 분석 > 기획:연수 기획 > 결재:예산 수립 > 문서작성:품의서 > 결재:품의 결재 > 결재:프로젝트 코드 요청",
            "섭외:강사 섭외 > 회의:강사 협의 > 문서작성:공문 발송 > 계약:계약서 작성",
            "섭외:장소(대관) 확보 > 조사:교육장 서치 > 이동:사전 답사 > ?교육장 적합도|Yes:교육장 확정 → 계약·협의|No:교육장 재서치",
            "준비:관련 장비 대여 > ?장비 유무|Yes:신청서 → 내부 대여 수령|No:외부 리스트 선정 → 계약 → 수령"],
         "links": [("ops_plan", "auto"), ("venue", "auto"), ("venue_map", "auto"), ("rfp", "part")], "gaps": []},
        {"name": "홍보 및 연수생 모집", "lanes": [
            "홍보:모집 공고·홍보 > ?모집 인원 확인|Yes:명단 확정|No:재홍보",
            "제작:사전 역량 진단 설문 > 발송:설문 배포 > 분석:결과 취합·분석", "운영:안내문자 작성 > 발송:안내문자 발송"],
         "links": [("recruit", "auto"), ("recruit_sc", "auto")], "gaps": []},
        {"name": "교재 및 물품 준비", "lanes": [
            "검수:강의 자료 수급 > 검토:원고 검토 > 제작:교재화 > 제작:제작 의뢰 > 제작:교재 수령",
            "디자인:현수막·배너 > 제작:제작 의뢰 > 제작:물품 수령",
            "운영:최종 인원 확인 > 준비:답례품·다과·운영 물품 > 기타:수량 확인·차량 적재 > 이동:연수장 이동",
            "제작:만족도 조사 설문"],
         "links": [("ops_plan", "part")], "gaps": ["물품 체크리스트가 D-day 기준 일반 항목뿐 → 사업별 물품·수량 체크 연동 가능"]},
        {"name": "현장 운영 및 실행", "lanes": [
            "세팅:현장 세팅(전일·당일) > 리허설:강사·운영진 리허설 > 운영:등록·접수 > 운영:연수 진행 > 운영:현장 응대 > 운영:폐회·정리 > 이동:복귀 > 기타:물품 정리",
            "배포:만족도 설문 배포"],
         "links": [("ops_plan", "auto"), ("venue_map", "auto")], "gaps": []},
        {"name": "사후 관리 및 정산", "lanes": [
            "정산:강사비 정산 > 등록:강사 거래처 등록 > 지출결의:강사료·수당 지급",
            "지출결의:정산 > 기타:영수증 취합 > 지출결의:지출 결의서",
            "운영:이수 처리·사후 지원 > 제출:이수자 명단 전달 > 제출:이수 처리 보고",
            "분석:만족도 결과 분석 > 문서작성:연수 결과 보고"],
         "links": [], "gaps": ["만족도·정산 결과 미연동 → 집합연수 사업별 손익·만족도 비교표 가능"]},
    ]},
]


def coverage():
    out = []
    for w in WORKFLOWS:
        n = len(w["phases"])
        auto = sum(1 for p in w["phases"] if any(l == "auto" for _, l in p["links"]))
        part = sum(1 for p in w["phases"] if p["links"] and not any(l == "auto" for _, l in p["links"]))
        out.append({"id": w["id"], "name": w["name"], "n": n, "auto": auto, "part": part, "none": n - auto - part})
    return out


def badge_map():
    """앵커 id -> ['B2G 판매 · 연수 운영', ...] (화면 패널 제목 옆 배지용)"""
    m = {}
    for w in WORKFLOWS:
        for p in w["phases"]:
            for key, lvl in p["links"]:
                tab, anchor, _ = F[key]
                lab = f"{w['name']} · {p['name']}"
                m.setdefault(anchor, {"tab": tab, "steps": []})
                if lab not in m[anchor]["steps"]:
                    m[anchor]["steps"].append(lab)
    return m


TAGC = {"분석": "#4f8cff", "조사": "#4f8cff", "기획": "#8b5cf6", "설계": "#8b5cf6", "문서작성": "#64748b", "결재": "#64748b", "선정": "#14b8a6",
        "계약": "#f59e0b", "정산": "#f59e0b", "지출결의": "#f59e0b", "등록": "#0ea5e9", "운영": "#10b981", "홍보": "#ec4899", "제작": "#eab308"}


def _node(tok):
    tok = tok.strip()
    if tok.startswith("?"):
        parts = tok[1:].split("|")
        branches = "".join(
            f'<span style="font-size:11px;margin-left:6px;"><b style="color:{"#10b981" if b.startswith("Yes") else "#ef4444"};">{E(b.split(":", 1)[0])}</b> {E(b.split(":", 1)[1] if ":" in b else "")}</span>'
            for b in parts[1:])
        return (f'<span class="wf-n wf-d"><span style="display:inline-block;transform:rotate(45deg);width:8px;height:8px;background:#ec4899;margin-right:6px;"></span>'
                f'{E(parts[0])}{branches}</span>')
    if tok.startswith("="):
        return f'<span class="wf-n" style="border-style:dashed;">↪ {E(tok[1:])} 플로우</span>'
    tag, _, txt = tok.partition(":")
    if not txt:
        tag, txt = "", tag
    c = TAGC.get(tag, "#94a3b8")
    return f'<span class="wf-n">{f"<span class=wf-t style=background:{c}>{E(tag)}</span>" if tag else ""}{E(txt)}</span>'


def render():
    css = """<style>
.wf-w{margin-bottom:26px;} .wf-ph{display:grid;grid-template-columns:150px 1fr 280px;gap:12px;padding:10px 0;border-top:1px solid var(--border);}
.wf-pn{font-weight:800;font-size:13px;padding:8px 10px;border-radius:8px;background:color-mix(in srgb,#f59e0b 16%,var(--surface));border:1px solid color-mix(in srgb,#f59e0b 45%,var(--border));height:fit-content;}
.wf-lane{display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin:3px 0;} .wf-ar{color:var(--muted);font-size:12px;}
.wf-n{display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:4px 8px;border-radius:6px;background:color-mix(in srgb,#eab308 12%,var(--surface));border:1px solid color-mix(in srgb,#eab308 40%,var(--border));}
.wf-d{background:color-mix(in srgb,#ec4899 10%,var(--surface));border-color:color-mix(in srgb,#ec4899 45%,var(--border));}
.wf-t{color:#fff;font-size:10px;font-weight:700;padding:1px 5px;border-radius:4px;}
.wf-lk{display:inline-block;font-size:11.5px;margin:2px 3px 2px 0;padding:2px 8px;border-radius:999px;cursor:pointer;border:1px solid var(--border);}
.wf-lk.auto{background:color-mix(in srgb,#10b981 18%,transparent);border-color:#10b981;} .wf-lk.part{background:color-mix(in srgb,#f59e0b 16%,transparent);border-color:#f59e0b;}
.wf-gap{font-size:11.5px;color:var(--muted);margin-top:6px;padding-left:8px;border-left:3px solid #ef4444;}
@media (max-width:900px){.wf-ph{grid-template-columns:1fr;}}
</style>"""
    cov = coverage()
    covh = "".join(
        f'<div class="rfp-card"><div class="t">{E(c["name"])}</div><div style="display:flex;height:12px;gap:2px;margin:8px 0;border-radius:4px;overflow:hidden;">'
        f'<span style="flex:{c["auto"]};background:#10b981;"></span><span style="flex:{c["part"]};background:#f59e0b;"></span><span style="flex:{c["none"]};background:var(--surface-2);"></span></div>'
        f'<div style="font-size:12px;color:var(--muted);">단계 {c["n"]}개 · 자동 연계 {c["auto"]} · 부분 {c["part"]} · 미연계 {c["none"]}</div></div>' for c in cov)
    body = [css, '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:10px;">' + covh + "</div>",
            '<div style="font-size:12px;margin-bottom:14px;"><span class="wf-lk auto">자동 연계</span> 이 단계 판단에 바로 쓰는 화면 · <span class="wf-lk part">부분 연계</span> 참고용 · '
            '<span style="border-left:3px solid #ef4444;padding-left:6px;">갭</span> 아직 시스템 밖(연동 후보). 초록·주황 칩을 누르면 해당 화면으로 이동합니다.</div>']
    for w in WORKFLOWS:
        body.append(f'<div class="wf-w"><h4 style="margin:6px 0;font-size:16px;">{E(w["name"])} <span style="font-size:12px;color:var(--muted);font-weight:600;">주관 {E(w["owner"])}</span></h4>')
        for p in w["phases"]:
            lanes = "".join('<div class="wf-lane">' + '<span class="wf-ar">→</span>'.join(_node(t) for t in ln.split(" > ")) + "</div>" for ln in p["lanes"])
            links = "".join(f'<span class="wf-lk {lvl}" data-goto="{F[k][0]}" data-anchor="{F[k][1]}">{E(F[k][2])}</span>' for k, lvl in p["links"]) or '<span style="font-size:12px;color:var(--muted);">연계 화면 없음</span>'
            gaps = "".join(f'<div class="wf-gap">{E(g)}</div>' for g in p["gaps"])
            body.append(f'<div class="wf-ph"><div class="wf-pn">{E(p["name"])}</div><div>{lanes}</div><div><div style="font-size:11.5px;color:var(--muted);margin-bottom:3px;">시스템 연계</div>{links}{gaps}</div></div>')
        body.append("</div>")
    return "".join(body)


if __name__ == "__main__":
    import json
    print(json.dumps(coverage(), ensure_ascii=False))
    print(len(badge_map()), "anchors")
