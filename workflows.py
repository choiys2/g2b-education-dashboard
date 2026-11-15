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
    "kanban": ("pipeline", "viz26", "사업 상태 칸반"),
    "leadtime": ("pipeline", "viz27", "사업 리드타임"),
    "reps": ("pipeline", "viz28", "영업 담당별 활동–성과"),
    "settle": ("pipeline", "viz29", "청구·계산서 경보"),
    "reports": ("pipeline", "viz30", "결과보고서 AI 초안"),
    "bids": ("pipeline", "viz31", "자사 입찰 결과 분석"),
    "blended": ("pipeline", "viz32", "집합연수 준비 현황판"),
    "c_stage": ("content", "viz33", "콘텐츠 인증·서비스 파이프라인"),
    "gantt": ("content", "viz34", "심사→오픈 타임라인"),
    "sales_heat": ("content", "viz35", "월×분야 콘텐츠 매출"),
    "pareto": ("content", "viz36", "과정별 매출 파레토"),
    "inst": ("content", "viz37", "분야별 강사 보유 수"),
    "ch_real": ("content", "viz38", "채널 매출 비교(실측)"),
    "quote": ("b2s", "viz39", "학교 견적 가이드"),
    "lifecycle": ("market", "viz40", "시도별 영업 생애주기"),
    "calendar": ("exec", "viz41", "연간 영업 캘린더"),
}

WORKFLOWS = [
    {"id": "dev", "name": "연수(콘텐츠) 개발", "owner": "샘크리에이티브", "phases": [
        {"name": "콘텐츠 개발 계획 수립", "lanes": [
            "분석:시장 및 경쟁사 분석 > 분석:교사 요구사항·트렌드 분석 > 조사:신규 연수 아이템 발굴 > 문서작성:B2G/B2C 개발 대상 과정 선정 > 선정:개발 우선순위 선정 > 기획:연간 콘텐츠 개발 계획 > 결재:예산 수립·품의 상신 > 기타:개발 단가 기준 관리"],
         "links": [("topics", "auto"), ("heat", "auto"), ("gap", "auto"), ("new_courses", "auto"), ("matrix", "auto"), ("pareto", "part"), ("issues", "part")],
         "gaps": ["개발 단가 기준표가 시스템 밖(엑셀)에 있음 → 경쟁사 가격대·차시 단가와 나란히 보이게 연동 가능"]},
        {"name": "콘텐츠 기획", "lanes": [
            "분석:콘텐츠 개발 요구 분석 > 조사:협업부서 제작 요청 수렴 > 문서작성:개별 콘텐츠 품의서 > ?품의 승인|Yes:SME 섭외|No:품의안 수정·재협의",
            "선정:SME 섭외 > 기획:킥오프 미팅 > 기획:커리큘럼·학습목표 설계 > 기획:과정 유형·제작 방식 검토 > 선정:개발사 선정 > 기획:홍보·판매 방향 수립"],
         "links": [("drafts", "auto"), ("catalog", "auto"), ("inst", "part"), ("rfp", "part")],
         "gaps": ["강사 Pool 은 분야별 인원 수까지만(이름 비공개) → 섭외 이력·평가가 필요하면 별도 'SME DT' 시트"]},
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
         "links": [("c_stage", "auto"), ("gantt", "auto")], "gaps": ["원고·촬영·검수 세부 단계는 시트에 없음(심사접수·인증·서비스까지만 추적)"]},
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
         "links": [("pareto", "auto"), ("sales_heat", "auto"), ("share", "auto"), ("new_courses", "auto"), ("signal", "part")],
         "gaps": ["수강 후기·만족도 미연동 → LMS 연동 시 과정별 만족도 순위 가능"]},
    ]},
    {"id": "b2g", "name": "B2G 판매", "owner": "샘브릿지", "phases": [
        {"name": "사업 발굴 협의", "lanes": [
            "선정:경쟁사 분석 > 문서작성:연수개발 요구안", "회의:교육청 정책+예산 분석 > 문서작성:연수개발 요구안",
            "?개발 유무|Yes:=연수(콘텐츠) 개발|No:요구안 재작성"],
         "links": [("contract", "auto"), ("comp_only", "auto"), ("budget", "auto"), ("tile", "auto"), ("recontract", "auto"), ("early", "auto"), ("conv", "auto"), ("bubble", "auto"), ("lifecycle", "auto"), ("calendar", "auto")],
         "gaps": []},
        {"name": "연수 제안", "lanes": ["회의:교육청 협의 > 선정:연수 과정 선택 > 문서작성:운영 계획서"],
         "links": [("rfp", "auto"), ("funnel_rfp", "auto"), ("drafts", "auto"), ("topics", "auto"), ("comms", "part")], "gaps": []},
        {"name": "계약 및 사업확정", "lanes": [
            "계약:계약 초안 > 문서작성:나라장터 / 학교장터 / 수의계약 > 문서작성:보증보험·인지세 처리 > 문서작성:운영 계획서"],
         "links": [("bids", "auto"), ("contract", "auto"), ("edu_cntr", "auto"), ("price_dots", "auto"), ("pipe", "part")],
         "gaps": ["보증보험·인지세 처리 체크 없음"]},
        {"name": "연수 운영", "lanes": [
            "개발:온라인 배너 개설 > 운영:연수 모집·홍보 > ?모집 결과|Yes:사업 운영|No:모집현황 보고",
            "회의:모집현황 보고 > 운영:추가 홍보 > ?목표 달성|Yes:모집 마감 → 이수 독려|No:추가 홍보"],
         "links": [("recruit", "auto"), ("recruit_sc", "auto"), ("kanban", "auto"), ("comms", "auto"), ("reps", "part"), ("banner", "part")], "gaps": []},
        {"name": "결과보고", "lanes": ["운영:결과보고서 정리 > 운영:장학사 보고 > 운영:전자계약 완수 처리 > 기타:계산서 발행"],
         "links": [("reports", "auto"), ("pipe", "part")], "gaps": ["이수 인원·만족도는 초안에 빈칸 — 이수 현황 시트(26년분) 연동 시 자동 채움"]},
        {"name": "정산 및 매출관리", "lanes": ["등록:나이스(NEIS) 등재 > 정산:정산 및 입금 > 등록:사업 종결"],
         "links": [("settle", "auto"), ("leadtime", "auto"), ("pipe", "auto"), ("channel", "auto"), ("sales_funnel", "part")], "gaps": ["입금일 열이 없어 계산서·전표까지만 추적"]},
    ]},
    {"id": "b2c", "name": "B2C·학교 판매", "owner": "샘콜라보", "phases": [
        {"name": "기획 및 설계", "lanes": [
            "기획:연수 수요 조사 > 기획:목표 수립 > 설계:기수 설계(직무·상시·자율) > 설계:운영 방식(기간별·실시간) > 검토:검토·피드백"],
         "links": [("b2s_market", "auto"), ("treemap", "auto"), ("edu_viz", "auto"), ("leading", "auto"), ("matrix", "auto"), ("quote", "part")], "gaps": []},
        {"name": "준비 및 홍보", "lanes": ["준비:모집 공고·접수 > 준비:학습 환경 구성 > 홍보:사전 안내 > 설계:수강신청"],
         "links": [("issues", "part"), ("bundle", "part")], "gaps": []},
        {"name": "연수 운영·평가", "lanes": [
            "운영:학습 진행 > 운영:학습평가 > 운영:학습관리", "운영:소통·지원 > 운영:질의응답", "운영:참여도 제고 > 운영:출결·진도율 관리"],
         "links": [], "gaps": ["LMS 진도율·출결 미연동 → 연동 시 이탈 위험 학습자 경보 가능"]},
        {"name": "문의 대응", "lanes": [
            "기타:문의 접수 > 기타:내용 확인 > 기타:응대 > 기타:결과 기록·공유",
            "기타:학교 단체 문의 > 발송:견적서 > 운영:결제 방식 협의 > 운영:결제 후 입과 처리 > 운영:입과 안내 문자"],
         "links": [("quote", "auto"), ("edu_viz", "auto"), ("price", "auto")], "gaps": []},
        {"name": "운영 지원", "lanes": ["기타:요청사항 확인 > 발송:교재 배송 / 그라운드 문자 / 이수 통보 > 기타:진행 확인"], "links": [], "gaps": []},
        {"name": "매출 데이터 관리", "lanes": [
            "문서작성:매출자료 수집 > 문서작성:매출파일 일별 작성 > 기타:데이터 관리 > 정산:월말 수익쉐어·튜터비 정산 > 정산:계산서·지출결의 > 검토:검토·공유"],
         "links": [("sales_heat", "auto"), ("ch_real", "auto"), ("pareto", "auto"), ("channel", "part")], "gaps": ["일별 매출(26매출합뷰)은 집계 뷰라 미연동 — 월별 과정 매출로 대체"]},
        {"name": "이수 및 환류", "lanes": ["운영:이수 처리 > 운영:증빙자료 발급 > 운영:사후 관리", "운영:결과보고"], "links": [], "gaps": []},
    ]},
    {"id": "off", "name": "오프라인(집합) 연수", "owner": "샘브릿지·운영", "phases": [
        {"name": "기획 및 착수", "lanes": [
            "분석:발주처 요구 분석 > 기획:연수 기획 > 결재:예산 수립 > 문서작성:품의서 > 결재:품의 결재 > 결재:프로젝트 코드 요청",
            "섭외:강사 섭외 > 회의:강사 협의 > 문서작성:공문 발송 > 계약:계약서 작성",
            "섭외:장소(대관) 확보 > 조사:교육장 서치 > 이동:사전 답사 > ?교육장 적합도|Yes:교육장 확정 → 계약·협의|No:교육장 재서치",
            "준비:관련 장비 대여 > ?장비 유무|Yes:신청서 → 내부 대여 수령|No:외부 리스트 선정 → 계약 → 수령"],
         "links": [("blended", "auto"), ("ops_plan", "auto"), ("venue", "auto"), ("venue_map", "auto"), ("rfp", "part")], "gaps": []},
        {"name": "홍보 및 연수생 모집", "lanes": [
            "홍보:모집 공고·홍보 > ?모집 인원 확인|Yes:명단 확정|No:재홍보",
            "제작:사전 역량 진단 설문 > 발송:설문 배포 > 분석:결과 취합·분석", "운영:안내문자 작성 > 발송:안내문자 발송"],
         "links": [("recruit", "auto"), ("recruit_sc", "auto")], "gaps": []},
        {"name": "교재 및 물품 준비", "lanes": [
            "검수:강의 자료 수급 > 검토:원고 검토 > 제작:교재화 > 제작:제작 의뢰 > 제작:교재 수령",
            "디자인:현수막·배너 > 제작:제작 의뢰 > 제작:물품 수령",
            "운영:최종 인원 확인 > 준비:답례품·다과·운영 물품 > 기타:수량 확인·차량 적재 > 이동:연수장 이동",
            "제작:만족도 조사 설문"],
         "links": [("blended", "auto"), ("ops_plan", "part")], "gaps": ["교재·답례품 수량 열은 미연동(식사·다과·운영준비 상태까지만)"]},
        {"name": "현장 운영 및 실행", "lanes": [
            "세팅:현장 세팅(전일·당일) > 리허설:강사·운영진 리허설 > 운영:등록·접수 > 운영:연수 진행 > 운영:현장 응대 > 운영:폐회·정리 > 이동:복귀 > 기타:물품 정리",
            "배포:만족도 설문 배포"],
         "links": [("ops_plan", "auto"), ("venue_map", "auto")], "gaps": []},
        {"name": "사후 관리 및 정산", "lanes": [
            "정산:강사비 정산 > 등록:강사 거래처 등록 > 지출결의:강사료·수당 지급",
            "지출결의:정산 > 기타:영수증 취합 > 지출결의:지출 결의서",
            "운영:이수 처리·사후 지원 > 제출:이수자 명단 전달 > 제출:이수 처리 보고",
            "분석:만족도 결과 분석 > 문서작성:연수 결과 보고"],
         "links": [("settle", "auto"), ("blended", "part")], "gaps": ["만족도 결과 미연동 → 설문 결과 시트가 생기면 사업별 비교 가능"]},
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


# ---------------------------------------------------------------- AI 자동화 판정(2026-11-16 사용자 요청)
# (정규식, 수준, 방법, 지금 쓸 수 있는 것, 다음 연결) - 위에서부터 먼저 맞는 규칙 하나만 적용
#   수준: "자동화" = 사람 승인만 남기고 AI·스크립트가 처리 / "AI 보조" = AI 초안·추천 + 사람이 판단·수정
AI_RULES = [
    (r"경쟁사 분석|시장 및 경쟁사", "자동화", "경쟁사 과정·가격·낙찰·신규 출시를 매일 수집하고, 주 1회 변화 요약을 자동 작성", "경쟁사 연수 분석 탭 · 핫토픽 선점 경보 · 가격 포지셔닝", "주간 요약을 결정 보드에 자동 게시"),
    (r"교사 요구|트렌드 분석|수요 조사", "자동화", "교사 관심 검색 추세·크리에이터·기사에서 뜨는 주제를 매주 자동 집계", "교사 트렌드 2027 · B2C 매출 전략(이번 주 라이브 후보)", "만족도·문의 내용까지 합치면 수요 근거 완성"),
    (r"정책\+?예산 분석|정책.*분석", "자동화", "교육청 기사·발주계획·지난해 공고로 시도별 발주 가능성 점수를 자동 계산", "교육청 인사이트(발주 예측·정책 신호)", "교육청 2027 업무계획 원문(1~2월) 자동 반영"),
    (r"아이템 발굴|과정 선정|우선순위|과정 선택", "AI 보조", "수요·관심·공백·보유 과정을 점수로 정렬한 후보 목록을 AI가 제시, 최종 선정은 회의", "샘몰 SET 후보 · 2027 연수 개발 추천", "선정 결과를 결정 보드에 기록하면 다음 점수에 반영"),
    (r"커리큘럼|학습목표|차시명|과정명", "AI 보조", "주제·대상(L1~L3)을 넣으면 차시 구성·학습목표 초안을 생성", "AI 기획서 초안", "자사 과정 목록과 중복 검사 자동화"),
    (r"품의|계획서|요구안|제안서|공문|연간 콘텐츠 개발 계획|운영 계획", "AI 보조", "양식(HWPX)에 맞춰 근거 수치·문단을 AI가 채운 초안 → 담당자 검토·결재", "제안요청서 AI 분석 · AI 기획서 초안", "공문·품의 HWPX 자동 작성 연결"),
    (r"결과보고|결과 보고|결과서|성과 분석", "AI 보조", "운영 데이터·이수 인원·만족도로 결과보고서 초안을 자동 작성", "결과보고서 AI 초안", "이수 현황·만족도 시트 연동 시 빈칸 자동 채움"),
    (r"원고 검토|검수|저작권|초상권", "AI 보조", "맞춤법·용어 통일·출처 누락·이미지 저작권 의심 항목을 AI가 1차 표시", "없음", "검수 체크리스트를 문서 업로드 한 번으로 자동 생성"),
    (r"홍보|마케팅|이벤트|공고|배너|과정소개", "AI 보조", "과정 정보로 홍보 문구·배너 카피·SNS 문안을 자동 생성, 게시는 사람 승인", "모집률 조기경보·AI 홍보 문구 · 연수 배너 시장", "채널별 반응(조회·신청)으로 문구 자동 개선"),
    (r"안내문자|문자|이수 통보|입과 안내", "자동화", "일정·대상이 정해지면 안내 문자를 템플릿으로 자동 작성·예약, 발송만 승인", "없음", "문자 발송 시스템 연결(발송 전 승인 단계 유지)"),
    (r"모집현황|모집 결과|목표 달성|모집 인원", "자동화", "신청률·경과율을 매일 계산해 경보·주간 모집 보고를 자동 작성", "모집률 조기경보 · 모집 위험 구역", "보고 문서를 주간보고에 자동 첨부"),
    (r"만족도|설문|진단|결과 취합", "자동화", "설문 폼 자동 생성 → 응답 자동 집계 → AI가 주관식 의견을 주제별로 요약", "없음", "설문 도구 연결(무료 폼) 후 결과를 관리 탭에 표시"),
    (r"문의|응대|질의응답|CS", "AI 보조", "자주 묻는 질문은 AI 챗봇이 1차 응대, 어려운 문의만 담당자에게 넘김(기록 자동)", "없음(비바샘 AI 챗봇 오픈)", "문의 기록을 주간 수요 분석에 연결"),
    (r"견적", "자동화", "학교 규모·과정 선택으로 견적서를 자동 생성", "학교 견적 가이드", "견적서 파일(PDF) 자동 발급"),
    (r"출결|진도율|이수 독려|참여도", "자동화", "진도율이 낮은 학습자를 자동으로 찾아 독려 문자 후보를 만든다", "없음", "LMS 진도 데이터 연동 필요"),
    (r"교육장|장소|대관", "자동화", "지역·인원·날짜로 연수 장소 후보와 날씨를 자동 추천", "집합연수 장소 찾기 · 장소·날씨 지도", "견적 요청 메일 초안 자동 작성"),
    (r"강사 섭외|SME 섭외|강사 협의", "AI 보조", "주제에 맞는 강사 후보를 강사풀에서 추천(경력·지역·이력)", "강사풀 집계", "섭외 이력·평가 기록 시트 연결"),
    (r"매출자료|매출파일|데이터 관리|매출 관리", "자동화", "매출 시트를 자동 집계해 일·월 매출과 채널 비중을 계산", "월×분야 콘텐츠 매출 · 채널 매출 비교", "일별 매출 시트 연동"),
    (r"세금계산서|계산서|지출결의|정산|입금", "AI 보조", "청구·계산서·전표 누락을 규칙으로 자동 경보, 서류 작성은 사람", "청구·계산서 경보", "ERP 연동 시 상태 자동 갱신"),
    (r"LMS|등록|등재|거래처|탑재", "AI 보조", "반복 입력은 자동 입력(RPA) 후보 — 입력값 목록을 자동으로 준비", "없음", "입력 대상 시스템별 자동 입력 검토"),
    (r"회의|킥오프|협의", "AI 보조", "회의록을 AI가 요약하고 결정·할 일을 뽑아 결정 보드·셀 지시에 제안", "결정 보드 · 27 전략실", "회의 기록 도구 연결"),
    (r"백업|데이터 수급|이력 관리", "자동화", "정해진 주기로 자동 백업·이력 기록", "없음", "저장 위치 지정"),
    (r"보증보험|인지세", "자동화", "계약 확정 시 보증보험·인지세 처리 체크를 자동 생성하고 기한 경보", "없음", "계약 시트에 처리 여부 열 추가"),
    (r"이수자 명단|이수자료", "자동화", "LMS 이수 데이터에서 명단·이수자료를 양식대로 자동 추출", "없음", "LMS 이수 데이터 연동"),
    (r"단가 기준", "AI 보조", "경쟁사 15차시 환산 가격·차시 단가와 자사 개발 단가를 나란히 비교", "가격·할인·SET 포지셔닝", "개발 단가 기준표(엑셀) 연동"),
    (r"요청 수렴|요구 분석", "AI 보조", "부서별 제작 요청을 한 양식으로 모으고 AI가 중복·우선순위를 정리", "없음", "요청 접수 폼 연결"),
    (r"개발사 선정|외주", "AI 보조", "개발사 견적·이력·과거 품질을 비교표로 자동 정리", "없음", "개발사 이력 시트 연결"),
    (r"계약 초안|전자계약|나라장터|학교장터|수의계약", "AI 보조", "공고문·과업지시서를 AI가 읽고 제출 서류 체크리스트와 계약서 초안을 준비", "제안요청서 AI 분석 · 자사 입찰 결과 분석", "입찰 서류 폴더와 연결"),
    (r"스토리보드|프로토타입|UI 검토", "AI 보조", "원고로 스토리보드·화면 구성 초안을 생성", "없음", "제작 템플릿 연결"),
    (r"장학사 보고|차기 연수", "AI 보조", "운영 결과를 장학사 보고용 요약과 차년도 제안으로 자동 정리", "결과보고서 AI 초안(장학사 보고 요지·차년도 제안)", "이수·만족도 데이터 연동"),
]
_AIR = [(__import__("re").compile(r), lv, how, now, nxt) for r, lv, how, now, nxt in AI_RULES]


def ai_of(text):
    for rx, lv, how, now, nxt in _AIR:
        if rx.search(text or ""):
            return {"lv": lv, "how": how, "now": now, "next": nxt}
    return None


def _tasks(lane):
    """레인 한 줄에서 작업 이름들(판단 노드는 질문만)."""
    out = []
    for tok in lane.split(" > "):
        tok = tok.strip()
        if tok.startswith("="):
            continue
        if tok.startswith("?"):
            parts = tok[1:].split("|")
            out.append(parts[0])
            for b in parts[1:]:
                out += [x.strip() for x in (b.split(":", 1)[1] if ":" in b else "").split("→") if x.strip() and not x.strip().startswith("=")]
            continue
        out.append(tok.partition(":")[2] or tok)
    return out


def ai_summary():
    rows = []
    for w in WORKFLOWS:
        seen, a, b, n = set(), 0, 0, 0
        for p in w["phases"]:
            for ln in p["lanes"]:
                for t in _tasks(ln):
                    if t in seen:
                        continue
                    seen.add(t)
                    n += 1
                    r = ai_of(t)
                    a += bool(r and r["lv"] == "자동화")
                    b += bool(r and r["lv"] == "AI 보조")
        rows.append({"id": w["id"], "name": w["name"], "n": n, "auto": a, "assist": b})
    return rows


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
    ai = ai_of(txt)
    mark = (f'<span class="wf-ai-m {"a" if ai["lv"] == "자동화" else "b"}" title="{E(ai["lv"])}">AI</span>' if ai else "")
    return f'<span class="wf-n">{f"<span class=wf-t style=background:{c}>{E(tag)}</span>" if tag else ""}{E(txt)}{mark}</span>'


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
.wf-ai-m{font-size:9.5px;font-weight:800;color:#fff;border-radius:4px;padding:0 4px;margin-left:2px;} .wf-ai-m.a{background:#10b981;} .wf-ai-m.b{background:#3b82f6;}
.wf-aibox{margin-top:6px;font-size:12px;} .wf-aibox > summary{cursor:pointer;font-weight:700;color:var(--ink-2);}
.wf-aiit{margin:4px 0 0 4px;border-left:3px solid var(--border);padding-left:8px;} .wf-aiit > summary{cursor:pointer;}
.wf-aiit[open]{border-left-color:var(--accent);} .wf-aiit .bd{margin:4px 0 6px;line-height:1.6;color:var(--ink-2);}
@media (max-width:900px){.wf-ph{grid-template-columns:1fr;}}
</style>"""
    cov = coverage()
    covh = "".join(
        f'<div class="rfp-card"><div class="t">{E(c["name"])}</div><div style="display:flex;height:12px;gap:2px;margin:8px 0;border-radius:4px;overflow:hidden;">'
        f'<span style="flex:{c["auto"]};background:#10b981;"></span><span style="flex:{c["part"]};background:#f59e0b;"></span><span style="flex:{c["none"]};background:var(--surface-2);"></span></div>'
        f'<div style="font-size:12px;color:var(--muted);">단계 {c["n"]}개 · 자동 연계 {c["auto"]} · 부분 {c["part"]} · 미연계 {c["none"]}</div></div>' for c in cov)
    body = [css, '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:10px;">' + covh + "</div>",
            '<div style="margin:4px 0 12px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;">'
            '<div style="font-weight:800;font-size:13.5px;margin-bottom:6px;">🤖 AI 자동화 가능 업무</div>'
            + "".join(f'<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin:3px 0;"><span style="width:130px;">{E(r["name"])}</span>'
                      f'<span style="flex:1;display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--surface-2);">'
                      f'<span style="width:{r["auto"] / max(1, r["n"]) * 100:.0f}%;background:#10b981;"></span><span style="width:{r["assist"] / max(1, r["n"]) * 100:.0f}%;background:#3b82f6;"></span></span>'
                      f'<span style="width:190px;color:var(--muted);">업무 {r["n"]} · 자동화 {r["auto"]} · AI 보조 {r["assist"]}</span></div>' for r in ai_summary())
            + '<div style="font-size:12px;color:var(--muted);margin-top:6px;"><span class="wf-ai-m a">AI</span> 자동화(승인만 남김) · <span class="wf-ai-m b">AI</span> AI 보조(초안·추천). '
              '각 단계 아래 \'🤖 AI 자동화 후보\'를 누르면 업무별 방법·지금 쓸 수 있는 화면·다음 연결이 펼쳐집니다.</div></div>'
            '<div style="font-size:12px;margin-bottom:14px;"><span class="wf-lk auto">자동 연계</span> 이 단계 판단에 바로 쓰는 화면 · <span class="wf-lk part">부분 연계</span> 참고용 · '
            '<span style="border-left:3px solid #ef4444;padding-left:6px;">갭</span> 아직 시스템 밖(연동 후보). 초록·주황 칩을 누르면 해당 화면으로 이동합니다.</div>']
    for w in WORKFLOWS:
        body.append(f'<div class="wf-w"><h4 style="margin:6px 0;font-size:16px;">{E(w["name"])} <span style="font-size:12px;color:var(--muted);font-weight:600;">주관 {E(w["owner"])}</span></h4>')
        for p in w["phases"]:
            lanes = "".join('<div class="wf-lane">' + '<span class="wf-ar">→</span>'.join(_node(t) for t in ln.split(" > ")) + "</div>" for ln in p["lanes"])
            links = "".join(f'<span class="wf-lk {lvl}" data-goto="{F[k][0]}" data-anchor="{F[k][1]}">{E(F[k][2])}</span>' for k, lvl in p["links"]) or '<span style="font-size:12px;color:var(--muted);">연계 화면 없음</span>'
            gaps = "".join(f'<div class="wf-gap">{E(g)}</div>' for g in p["gaps"])
            seen, items = set(), []
            for ln in p["lanes"]:
                for t in _tasks(ln):
                    r = ai_of(t)
                    if r and t not in seen:
                        seen.add(t)
                        items.append((t, r))
            if items:
                items.sort(key=lambda x: x[1]["lv"] != "자동화")
                lanes += (f'<details class="wf-aibox"><summary>🤖 AI 자동화 후보 {len(items)}건 (자동화 {sum(1 for _, r in items if r["lv"] == "자동화")} · AI 보조 {sum(1 for _, r in items if r["lv"] == "AI 보조")}) — 눌러서 방법 보기</summary>'
                          + "".join(f'<details class="wf-aiit"><summary><span class="wf-ai-m {"a" if r["lv"] == "자동화" else "b"}">{E(r["lv"])}</span> {E(t)}</summary>'
                                    f'<div class="bd"><b>방법</b> {E(r["how"])}<br><b>지금 쓸 수 있는 것</b> {E(r["now"])}<br><b>다음 연결</b> {E(r["next"])}</div></details>' for t, r in items)
                          + "</details>")
            body.append(f'<div class="wf-ph"><div class="wf-pn">{E(p["name"])}</div><div>{lanes}</div><div><div style="font-size:11.5px;color:var(--muted);margin-bottom:3px;">시스템 연계</div>{links}{gaps}</div></div>')
        body.append("</div>")
    return "".join(body)


if __name__ == "__main__":
    import json
    print(json.dumps(coverage(), ensure_ascii=False))
    print(len(badge_map()), "anchors")
