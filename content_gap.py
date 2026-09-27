#!/usr/bin/env python3
"""
3사(티처빌·아이스크림·비바샘연수원) 연수 강좌를 공통 분류로 다시 나눠 콘텐츠 갭을 계산한다.

사이트마다 카테고리 체계가 다르고(티처빌 '인문·교양', 아이스크림 '인문소양'), 비바샘연수원은
목록 화면에 카테고리가 아예 없어서 원래 분류로는 3사를 나란히 비교할 수 없다. 그래서
강좌명 키워드 규칙을 모든 회사에 똑같이 적용하고(회사별 편향 방지), 키워드로 못 잡은
경우에만 사이트 원래 카테고리를 보조로 쓴다. 규칙 기반이라 오분류가 있을 수 있으니
대시보드에는 "자동 분류(검수 전)"로 표시한다.

- classify(title, site_category)  -> 공통 분류명
- topic_hits(title)                -> 강좌명에 들어간 주제 키워드 목록
- build(courses_by_company, new_rows, self_name) -> 대시보드용 갭 매트릭스·백로그·출시 추이
"""
import re
from collections import Counter, defaultdict
from datetime import date

# 순서가 중요하다: 앞 규칙이 먼저 맞으면 거기서 끝난다(예: '영어 수업'은 어학이 아니라
# 교수학습으로 보고 싶어서 '수업' 계열을 어학보다 앞에 두지 않고, 어학 규칙을 회화·원어민
# 같은 학습자 본인 어학 표현 위주로 좁혔다).
TAXONOMY = [
    ("AI·디지털", r"AI|인공지능|챗\s?GPT|ChatGPT|GPT|생성형|에듀테크|디지털|코딩|프로그래밍|파이썬|"
                 r"제미나이|Gemini|노코드|캔바|Canva|구글|Google|엑셀|노션|메타버스|영상\s?편집|유튜브|"
                 r"스마트\s?기기|하이러닝|데이터|클래스룸|패들렛|멘티미터|업무\s?자동화|앱\s?만들|"
                 r"파워\s?포인트|PPT|게더타운|미디어\s?리터러시|온라인\s?수업|원격\s?수업|갤럭시\s?탭|태블릿"),
    ("어학", r"영어\s?회화|회화|원어민|일본어|중국어|스페인어|프랑스어|토익|리얼클래스|야나두|어학|"
             r"영어\s?리터치|진짜\s?영어|English"),
    ("생활지도·상담", r"생활\s?지도|생활\s?교육|학급\s?경영|학급운영|상담|학교\s?폭력|회복적|갈등|인성|"
                    r"사회\s?정서|SEL|감정\s?코칭|교권|학부모|진로|성\s?교육|안전|응급|자살|위기|"
                    r"관계\s?맺기|훈육|마음\s?읽기|비폭력\s?대화|민주\s?시민|학생\s?자치|자녀\s?교육|폭력\s?예방|"
                    r"마약|약물|양성\s?평등|성인지|관계\s?공격|담임"),
    ("교수학습·평가", r"수업|교수|학습|평가|교육\s?과정|프로젝트|토론|문해력|독서\s?교육|IB|고교\s?학점제|"
                    r"기초\s?학력|교과|수학|과학|국어|사회과|미술\s?교육|음악\s?교육|체육|놀이\s?교육|"
                    r"교실|질문|발문|배움|서술형|성취\s?수준|학교\s?자율\s?시간|생활\s?기록부|생기부|대입|입시|"
                    r"교과서|생태\s?전환|창업|기업가|학점제|학종|학생부|한글|문해|숲\s?활동|직업계"),
    ("특수·유아·다문화", r"특수|통합\s?교육|유아|유치원|다문화|늘봄|돌봄|장애"),
    ("교육정책·행정", r"정책|행정|업무\s?경감|법률|법령|교원\s?능력|승진|공문|회계|예산|학교\s?운영|"
                     r"법정\s?(교육|연수)|의무\s?연수|청렴|개인정보|부정\s?청탁|부패|교직\s?실무|교무|업무"),
    ("교사 웰빙·성장", r"마음|명상|힐링|번아웃|스트레스|웰빙|요가|필라테스|건강|수면|심리|자존감|"
                     r"리더십|소통|코칭|회복탄력|행복|자기\s?돌봄|운동|연구\s?대회|퍼스널\s?브랜딩|브랜딩|시간\s?관리|"
                     r"말\s?연습|인생|지혜"),
    ("인문·교양·취미", r"인문|역사|철학|문학|미술|음악|예술|여행|요리|사진|드로잉|스케치|캘리|글쓰기|"
                     r"독서|영화|와인|커피|재테크|경제|금융|주식|부동산|교양|문화|클래식|공예|"
                     r"뜨개|원예|반려|베이킹|그림|악기|우쿨렐레|기타\s?연주|한국사|캠핑|머니|조리|자격\s?과정|고려|조선"),
]
_RULES = [(name, re.compile(pat, re.I)) for name, pat in TAXONOMY]
CATEGORIES = [name for name, _ in TAXONOMY] + ["기타"]

# 키워드로 못 잡았을 때만 쓰는 사이트 원래 카테고리 대응표
SITE_CATEGORY_MAP = {
    "디지털활용": "AI·디지털", "디지털역량": "AI·디지털",
    "어학": "어학",
    "생활지도": "생활지도·상담", "생활교육": "생활지도·상담",
    "학습지도": "교수학습·평가", "교과지도": "교수학습·평가", "교수학습": "교수학습·평가",
    "교육정책": "교육정책·행정",
    "인문·교양": "인문·교양·취미", "인문소양": "인문·교양·취미",
}

# 주제 공백 백로그용 주제 사전. 너무 넓은 말(수업·학습·교육)은 변별력이 없어 뺐다.
TOPICS = [
    "문해력", "학급경영", "학교폭력", "회복적", "교권", "학부모", "상담", "사회정서", "감정코칭",
    "인성", "진로", "성교육", "안전", "응급처치", "기초학력", "IB", "고교학점제", "과정중심평가",
    "서술형", "프로젝트", "토론", "질문", "독서", "글쓰기", "놀이", "체육", "수학", "과학", "영어",
    "국어", "사회", "역사", "미술", "음악", "다문화", "특수", "통합교육", "유아", "늘봄",
    "챗GPT", "생성형", "에듀테크", "코딩", "파이썬", "엑셀", "노션", "캔바", "구글", "메타버스",
    "영상", "유튜브", "디지털교과서", "데이터", "업무자동화",
    "영어회화", "일본어", "중국어", "스페인어",
    "명상", "마음챙김", "번아웃", "스트레스", "요가", "필라테스", "건강", "심리", "자존감",
    "리더십", "소통", "코칭", "회복탄력성",
    "인문학", "철학", "문학", "여행", "요리", "사진", "드로잉", "캘리그라피", "와인", "커피",
    "재테크", "경제", "금융", "영화", "클래식", "공예", "베이킹", "반려",
    "법정", "청렴", "개인정보", "행정",
]
# 표기 흔들림 흡수(예: '챗 GPT', 'ChatGPT' -> 챗GPT)
TOPIC_ALIASES = {
    "챗GPT": r"챗\s?GPT|ChatGPT", "영어회화": r"영어\s?회화|회화", "업무자동화": r"업무\s?자동화",
    "과정중심평가": r"과정\s?중심\s?평가", "학급경영": r"학급\s?경영|학급\s?운영",
    "사회정서": r"사회\s?정서|SEL", "감정코칭": r"감정\s?코칭", "통합교육": r"통합\s?교육",
    "디지털교과서": r"디지털\s?교과서|AIDT", "캘리그라피": r"캘리", "회복탄력성": r"회복\s?탄력",
    "마음챙김": r"마음\s?챙김", "인문학": r"인문", "법정": r"법정\s?(교육|연수)|의무\s?연수",
}
_TOPIC_RE = [(t, re.compile(TOPIC_ALIASES.get(t, re.escape(t)), re.I)) for t in TOPICS]


def classify(title, site_category=None):
    t = title or ""
    for name, rx in _RULES:
        if rx.search(t):
            return name
    return SITE_CATEGORY_MAP.get((site_category or "").strip(), "기타")


def topic_hits(title):
    t = title or ""
    return [name for name, rx in _TOPIC_RE if rx.search(t)]


def _week_start(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    dt = date(y, m, d)
    return date.fromordinal(dt.toordinal() - dt.weekday()).isoformat()


def build(courses_by_company, new_rows, self_name):
    companies = list(courses_by_company)
    comps = [c for c in companies if c != self_name]

    # ---- 1) 공통 분류 갭 매트릭스 ----
    counts = {c: Counter() for c in companies}
    for c, rows in courses_by_company.items():
        for r in rows:
            r["std"] = classify(r.get("title"), r.get("category"))
            counts[c][r["std"]] += 1
    matrix = []
    for cat in CATEGORIES:
        row = {"category": cat, "counts": {c: counts[c][cat] for c in companies}}
        total = sum(row["counts"].values())
        own = row["counts"].get(self_name, 0)
        comp_avg = sum(row["counts"][c] for c in comps) / len(comps) if comps else 0
        row["total"] = total
        row["self_share"] = round(own / total * 100, 1) if total else 0.0
        # 규모 지수: 자사 강좌 수 / 경쟁사 평균(목록 규모 차이가 그대로 반영됨)
        row["self_vs_comp"] = round(own / comp_avg, 2) if comp_avg else None
        matrix.append(row)
    totals = {c: len(courses_by_company[c]) for c in companies}
    # 비중 비교: 자사 목록이 경쟁사의 1/3 규모라 건수로는 전 분야가 열세로 나온다.
    # "각 사 목록에서 그 분야가 차지하는 비중"을 비교해야 포트폴리오의 강·약점이 보인다.
    for row in matrix:
        pct = {c: (row["counts"][c] / totals[c] * 100 if totals[c] else 0.0) for c in companies}
        comp_pct = sum(pct[c] for c in comps) / len(comps) if comps else 0.0
        row["pct"] = {c: round(v, 1) for c, v in pct.items()}
        row["comp_pct_avg"] = round(comp_pct, 1)
        row["share_gap_pp"] = round(pct.get(self_name, 0.0) - comp_pct, 1)
        own = row["counts"].get(self_name, 0)
        row["verdict"] = ("공백" if own == 0 and comp_pct > 0 else
                          "강점" if row["share_gap_pp"] >= 5 else
                          "약점" if row["share_gap_pp"] <= -5 else "비슷")

    # ---- 2) 주제 공백 백로그: 경쟁사 2곳 모두 다루는데 자사엔 없는 주제 ----
    topic_counts = {c: Counter() for c in companies}
    topic_examples = defaultdict(list)
    for c, rows in courses_by_company.items():
        for r in rows:
            for tp in topic_hits(r.get("title")):
                topic_counts[c][tp] += 1
                if c != self_name and sum(1 for e in topic_examples[tp] if e.startswith(f"[{c}]")) < 2:
                    topic_examples[tp].append(f"[{c}] {r.get('title')}")  # 회사별 최대 2건씩 고르게
    backlog = []
    for tp in TOPICS:
        comp_n = {c: topic_counts[c][tp] for c in comps}
        own = topic_counts.get(self_name, Counter())[tp]
        covered_by = sum(1 for v in comp_n.values() if v > 0)
        if covered_by == len(comps) and comps and own == 0:
            status = "공백"
        elif comps and own > 0 and own < min(comp_n.values()) / 3:
            status = "열세"   # 자사도 있지만 경쟁사 최소치의 1/3 미만
        else:
            continue
        backlog.append({
            "topic": tp, "status": status, "self": own, "comp": comp_n,
            "comp_total": sum(comp_n.values()), "examples": topic_examples[tp],
        })
    backlog.sort(key=lambda b: (b["status"] != "공백", -b["comp_total"]))
    backlog = backlog[:30]

    # ---- 4) 신규 출시 추이(주 단위, 월요일 시작) ----
    by_week = defaultdict(lambda: Counter())
    by_week_cat = defaultdict(lambda: Counter())
    for r in new_rows:
        if not r.get("first_seen"):
            continue
        wk = _week_start(r["first_seen"])
        by_week[wk][r.get("company")] += 1
        by_week_cat[wk][classify(r.get("title"), r.get("category"))] += 1
    weeks = sorted(by_week)
    velocity = [{"week": w, "counts": dict(by_week[w]), "by_category": dict(by_week_cat[w])} for w in weeks]

    return {
        "categories": CATEGORIES, "companies": companies, "self": self_name,
        "totals": totals, "matrix": matrix, "backlog": backlog, "velocity": velocity,
        "method": "강좌명 키워드 규칙 자동 분류(검수 전) · 키워드 미해당 시 사이트 원래 카테고리 보조",
    }
