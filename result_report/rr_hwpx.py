"""교육청 결과보고 — 한글(HWPX) 공문 + 결과보고서 생성.

구성(인계서 '결과보고서 작성' 2-8~2-14쪽 기준)
  [공문]  수신·제목·1~3항, 가.사업명 나.연수기간 다.연수종별 라.연수대상 마.연수결과 및 청구금액, 붙임
  [붙임1] 결과보고서
          Ⅰ. 연수 개요  Ⅱ. 이수 현황(총괄·전 과정)  Ⅲ. 이수자 분석(학교급·학교구분·직위·학점·상위5과정·학교별)
          Ⅳ. 연수 만족도  Ⅴ. 연수 후기  Ⅵ. 청구 내역
숫자는 모두 rr_stats 계산값 — 청구서·분석양식과 같은 값이 들어간다.
"""

import warnings

from hwpx import HwpxDocument

warnings.filterwarnings("ignore", category=DeprecationWarning)

PAGE_W = 48190  # A4 본문 폭(약 170mm, HWPUNIT)
HEAD_FILL = "#DCE6F1"
TOTAL_FILL = "#FFF2CC"


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def won(x):
    return f"{x:,}원"


def bar(ratio, width=20):
    n = round(ratio * width)
    return "■" * n + "□" * (width - n)


class Doc:
    def __init__(self):
        self.d = HwpxDocument.new()
        st = self.d.styles
        self.r_title = st.ensure_run(bold=True, size=20, font="맑은 고딕")
        self.r_h1 = st.ensure_run(bold=True, size=14, font="맑은 고딕")
        self.r_h2 = st.ensure_run(bold=True, size=12, font="맑은 고딕")
        self.r_body = st.ensure_run(size=11, font="맑은 고딕")
        self.r_small = st.ensure_run(size=9.5, font="맑은 고딕")
        self.r_small_b = st.ensure_run(size=9.5, bold=True, font="맑은 고딕")
        self.r_red = st.ensure_run(size=11, color="#C00000", font="맑은 고딕")
        self.r_bold = st.ensure_run(size=11, bold=True, font="맑은 고딕")
        self._center_pr = None

    def _last(self):
        return len(self.d.paragraphs) - 1

    def para(self, text="", run=None, align=None, before=None, after=None, page_break=False, indent=None):
        # 기본 문단모양(0)에서 시작해야 앞 문단의 들여쓰기·쪽나눔이 따라오지 않는다
        p = self.d.add_paragraph(text, para_pr_id_ref=0, char_pr_id_ref=run or self.r_body)
        kw = {}
        if align:
            kw["alignment"] = align
        if before is not None:
            kw["spacing_before_pt"] = before
        if after is not None:
            kw["spacing_after_pt"] = after
        if page_break:
            kw["page_break_before"] = True
        if indent is not None:
            kw["indent_left_mm"] = indent
        if kw:
            self.d.styles.apply_paragraph_format(paragraph_index=self._last(), **kw)
        return p

    def runs(self, parts, **kw):
        """parts: [(text, run_id), ...] 한 문단에 굵게/빨강 등 섞기."""
        p = self.para(parts[0][0], run=parts[0][1], **kw)
        for text, rid in parts[1:]:
            p.add_run(text, char_pr_id_ref=rid)
        return p

    def title(self, text, page_break=False):
        self.para(text, self.r_title, align="CENTER", after=12, page_break=page_break)

    def h1(self, text):
        self.para(text, self.r_h1, before=14, after=4)

    def h2(self, text):
        self.para(f"□ {text}", self.r_h2, before=8, after=2)

    def item(self, text, level=1):
        mark = {1: "○ ", 2: "- ", 3: "※ "}[level]
        self.para(mark + text, indent=4 * level)

    def center_pr(self):
        if self._center_pr is None:
            p = self.para("")
            self.d.styles.apply_paragraph_format(paragraph_index=self._last(), alignment="CENTER")
            self._center_pr = p.para_pr_id_ref
        return self._center_pr

    def table(self, rows, widths=None, header_rows=1, total_last=False, left_cols=(), merges=()):
        cp = self.center_pr()
        n_r, n_c = len(rows), len(rows[0])
        t = self.d.add_table(n_r, n_c, width=PAGE_W, char_pr_id_ref=self.r_small)
        if widths:
            t.set_column_widths(widths)
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                if v is None:
                    continue
                t.set_cell_text(i, j, str(v))
                head = i < header_rows or (total_last and i == n_r - 1)
                for p in t.cell(i, j).paragraphs:
                    if j not in left_cols or i < header_rows:
                        p.para_pr_id_ref = cp
                    for r in p.runs:
                        r.char_pr_id_ref = self.r_small_b if head else self.r_small
                if i < header_rows:
                    t.set_cell_shading(i, j, HEAD_FILL)
                elif total_last and i == n_r - 1:
                    t.set_cell_shading(i, j, TOTAL_FILL)
        for m in merges:
            self.d.tables.merge_cells(t, m)
        self.para("", self.r_small)
        return t

    def save(self, path):
        self.d.save_to_path(path)


def _rate_rows(groups, order=None, total=True):
    rows = [["구분", "참여(건)", "이수(건)", "미이수(건)", "이수율", "참여 비중"]]
    keys = order or list(groups)
    all_n = sum(groups[k]["참여"] for k in keys) or 1
    for k in keys:
        g = groups[k]
        if not g["참여"]:
            continue
        rows.append([k, f"{g['참여']:,}", f"{g['이수']:,}", f"{g['미이수']:,}", pct(g["이수율"]), pct(g["참여"] / all_n)])
    if total:
        p = sum(groups[k]["참여"] for k in keys)
        d = sum(groups[k]["이수"] for k in keys)
        rows.append(["계", f"{p:,}", f"{d:,}", f"{p - d:,}", pct(d / p if p else 0), "100.0%"])
    return rows


def build(path, basic, s, sv, inv, reviews):
    doc = Doc()
    tot = s["총"]
    period = ", ".join(s["연수기간"])
    credits = sorted({c["학점"] for c in s["과정"]})
    hours = ", ".join(sorted({c["연수시간"] for c in s["과정"]}))
    kind = f"{basic.get('연수종별') or '직무연수'} / {hours}"
    sat = sv["종합"]

    # ── 공문 ───────────────────────────────────────────────
    doc.runs([("문 서 번 호 : ", doc.r_bold), ("결재 시 자동생성", doc.r_red)])
    doc.runs([("발 행 일 자 : ", doc.r_bold), ("결재 시 자동생성", doc.r_red)])
    doc.runs([("수       신 : ", doc.r_bold), (f"{basic.get('수신처', '')}", doc.r_body)])
    doc.runs([("참       조 : ", doc.r_bold), (f"{basic.get('참조') or ''}", doc.r_body)])
    doc.runs([("제       목 : ", doc.r_bold), (f"{basic.get('사업명', '')} 결과 보고", doc.r_body)], after=8)
    doc.para("1. 귀 기관의 무궁한 발전을 기원합니다.")
    doc.para("2. ㈜비상교육은 「교원 등의 연수에 관한 규정」 제2조에 의거, 인가번호 제02-9호 비상 티스쿨 "
             "원격교육연수원을 인가받아 교원직무연수를 실시하고 있습니다.")
    doc.para("3. 추진하신 위탁사업에 관한 결과를 아래와 같이 보고드립니다.", after=6)
    doc.para(f"가. 사 업 명 : {basic.get('사업명', '')}", indent=4)
    doc.para(f"나. 연수기간 : {period}", indent=4)
    doc.para(f"다. 연수종별 : {kind}", indent=4)
    doc.para(f"라. 연수대상 : {basic.get('연수대상') or ''}", indent=4)
    doc.para("마. 연수결과 및 청구금액", indent=4, after=4)
    rows = [["순", "연수과정", "신청(건)", "이수(건)", "이수율", "만족도", "청구금액"]]
    for i, cr in enumerate(credits, 1):
        cs = [c for c in s["과정"] if c["학점"] == cr]
        p, d = sum(c["참여"] for c in cs), sum(c["이수"] for c in cs)
        rows.append([str(i), f"{cr}학점 과정 {len(cs)}개", f"{p:,}", f"{d:,}", pct(d / p if p else 0),
                     pct(sat["백분율"]) if i == 1 else None, won(inv["청구금액"]) if i == 1 else None])
    if len(credits) > 1:
        rows.append(["", "합계", f"{tot['참여']:,}", f"{tot['이수']:,}", pct(tot["이수율"]), None, None])
    merges = [f"F2:F{len(rows)}", f"G2:G{len(rows)}"] if len(rows) > 2 else []
    doc.table(rows, widths=[5, 33, 11, 11, 11, 11, 18], merges=merges)
    doc.para("붙임  1. 결과보고서 1부.", before=4)
    doc.para("2. 이수자 명단 1부.", indent=12)
    doc.para("3. 청구서 1부.  끝.", indent=12)

    # ── 붙임1 결과보고서 ────────────────────────────────────
    doc.title(basic.get("사업명", ""), page_break=True)
    doc.title("결과보고서")

    doc.h1("Ⅰ. 연수 개요")
    doc.table([["구분", "내용"],
               ["사 업 명", basic.get("사업명", "")],
               ["연수기간", period],
               ["연수대상", basic.get("연수대상") or ""],
               ["연수종별", kind],
               ["운영과정", f"{len(s['과정'])}개 과정 (원격 직무연수)"],
               ["연수기관", "㈜비상교육 비상 티스쿨 원격교육연수원"],
               ["수강 규모", f"신청 {tot['참여']:,}건(실인원 {s['인원']['신청인원']:,}명) / "
                           f"이수 {tot['이수']:,}건(실인원 {s['인원']['이수인원']:,}명)"]],
              widths=[18, 82], left_cols=(1,))

    doc.h1("Ⅱ. 이수 현황")
    doc.h2("총 이수 현황")
    doc.table([["구분", "인원(건)", "비율"],
               ["참여자", f"{tot['참여']:,}", "100.0%"],
               ["이수자", f"{tot['이수']:,}", pct(tot["이수율"])],
               ["미이수자", f"{tot['미이수']:,}", pct(1 - tot["이수율"])]], widths=[34, 33, 33])
    doc.item(f"전체 {tot['참여']:,}건 중 {tot['이수']:,}건 이수, 이수율 {pct(tot['이수율'])}")
    doc.item(f"1인당 평균 {s['인원']['1인당과정수']:.2f}개 과정 수강 "
             f"(실인원 {s['인원']['신청인원']:,}명 중 {s['인원']['이수인원']:,}명 1개 과정 이상 이수)")

    doc.h2("과정별 이수 현황 (전 과정)")
    rows = [["순", "과정명", "학점", "참여", "이수", "미이수", "이수율"]]
    for i, c in enumerate(s["과정"], 1):
        rows.append([str(i), c["과정명"].strip(), f"{c['학점']}", f"{c['참여']:,}", f"{c['이수']:,}",
                     f"{c['미이수']:,}", pct(c["이수율"])])
    rows.append(["", "합계", "", f"{tot['참여']:,}", f"{tot['이수']:,}", f"{tot['미이수']:,}", pct(tot["이수율"])])
    doc.table(rows, widths=[5, 51, 7, 9, 9, 9, 10], total_last=True, left_cols=(1,))

    doc.h1("Ⅲ. 이수자 분석")
    doc.h2("학교급별")
    doc.table(_rate_rows(s["학교급"]), widths=[20, 16, 16, 16, 16, 16], total_last=True)
    doc.h2("학교 구분별(설립)")
    doc.table(_rate_rows(s["학교구분"]), widths=[20, 16, 16, 16, 16, 16], total_last=True)
    doc.h2("직위별")
    doc.table(_rate_rows(s["직위"]), widths=[20, 16, 16, 16, 16, 16], total_last=True)
    doc.h2("학점별")
    doc.table(_rate_rows(s["학점"]), widths=[20, 16, 16, 16, 16, 16], total_last=True)

    doc.h2("수강 상위 5개 과정")
    top5 = sorted(s["과정"], key=lambda c: (-c["참여"], -c["이수"]))[:5]
    mx = max(c["참여"] for c in top5) if top5 else 1
    rows = [["순위", "과정명", "참여", "이수", "이수율", "참여 규모"]]
    for i, c in enumerate(top5, 1):
        rows.append([str(i), c["과정명"].strip(), f"{c['참여']:,}", f"{c['이수']:,}", pct(c["이수율"]),
                     bar(c["참여"] / mx, 12)])
    doc.table(rows, widths=[7, 45, 9, 9, 10, 20], left_cols=(1, 5))
    share = sum(c["참여"] for c in top5) / tot["참여"] if tot["참여"] else 0
    doc.item(f"상위 5개 과정이 전체 참여의 {pct(share)} 차지 — "
             f"'{top5[0]['과정명'].strip()}' 과정 참여가 가장 많음({top5[0]['참여']:,}건)")

    doc.h2("학교별 이수 현황 (학교급별 최다 참여 학교)")
    rows = [["학교급", "학교명", "참여", "이수", "미이수", "이수율"]]
    for lvl, c in s["학교급별_최다학교"].items():
        rows.append([lvl, c["학교명"], f"{c['참여']:,}", f"{c['이수']:,}", f"{c['미이수']:,}", pct(c["이수율"])])
    doc.table(rows, widths=[16, 36, 12, 12, 12, 12])
    doc.item(f"참여 학교(기관) 수 {len(s['학교']):,}곳")

    doc.h1("Ⅳ. 연수 만족도")
    doc.para(f"○ 조사방법 : 온라인 원격 설문   ○ 조사기간 : 연수 종료 7일 전 ~ 종료일   "
             f"○ 응답인원 : {sv['조사인원'] or 0:,}명", run=doc.r_small)
    rows = [["구분", "매우 그렇다", "그렇다", "보통", "그렇지 않다", "매우 그렇지 않다", "평균(5점)", "환산(%)"]]
    for it in sv["항목"]:
        rows.append([it["구분"]] + [f"{n:,}명\n({pct(r)})" for n, r in zip(it["응답"], it["비율"])]
                    + [f"{it['점수']:.2f}", pct(it["백분율"])])
    rows.append(["종합"] + [pct(r) for r in sat["비율"]] + [f"{sat['점수']:.2f}", pct(sat["백분율"])])
    doc.table(rows, widths=[16, 12, 12, 12, 12, 12, 12, 12], total_last=True)
    doc.item(f"학습자는 본 연수를 내용 전문성과 현장 적용성이 높아 추천할 만한 연수로 인식했으며, "
             f"전체 응답의 {pct(sat['만족비율'])}가 '만족(매우 그렇다+그렇다)'으로 응답함. "
             f"5점 만점 기준 {sat['점수']:.2f}점({pct(sat['백분율'])})의 높은 만족도를 보임")
    best = max(sv["항목"], key=lambda i: i["점수"])
    doc.item(f"항목별로는 '{best['구분']}'이 {best['점수']:.2f}점으로 가장 높음", level=2)

    doc.h1("Ⅴ. 연수 후기")
    if reviews:
        for r in reviews:
            doc.item(f"“{r}”")
    else:
        doc.item("(입력값.xlsx '연수후기' 시트에 강의평가 통계 8번 응답을 붙여넣으면 자동 반영)")

    doc.h1("Ⅵ. 청구 내역")
    rows = [["순", "학점", "연수과정", "인원(명)", "단가(원)", "금액(원)"]]
    for i, l in enumerate(inv["내역"], 1):
        rows.append([str(i), f"{l['학점']}학점", l["과정명"].strip(), f"{l['인원']:,}", f"{l['단가']:,}", f"{l['금액']:,}"])
    rows.append(["", "", "산정 금액(이수 인원 × 단가)", f"{inv['총이수']:,}", "", f"{inv['산정금액']:,}"])
    if inv["교육기부"]:
        rows.append(["", "", "교육기부(계약금액 초과분)", "", "", f"{inv['교육기부']:,}"])
    rows.append(["", "", "청구 금액", "", "", f"{inv['청구금액']:,}"])
    doc.table(rows, widths=[5, 9, 50, 11, 11, 14], total_last=True, left_cols=(2,))
    if inv["교육기부"]:
        doc.item(f"계약금액 {won(inv['예산'])}을 초과한 {won(-inv['교육기부'])}은 교육기부로 처리", level=3)

    doc.save(path)
    return doc
