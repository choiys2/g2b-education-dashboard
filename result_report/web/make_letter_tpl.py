"""결과보고 공문(HWPX) 양식 만들기 — 그룹웨어 공문 PDF(VS-2026-965 형식)를 본떠 자리표시(【…】)를 둔다.

머리 배너(로고·슬로건·청록 선)와 직인 문구(주식회사 비상교육 / 대표이사 양태회)는 공문 PDF에서 그림으로 뽑아 쓴다.
브라우저(app.html)가 【문서번호】 같은 자리표시를 실제 값으로 바꾼다.
  python make_letter_tpl.py 공문.pdf 출력.hwpx
"""

import io
import os
import subprocess
import sys
import tempfile
import warnings

from PIL import Image
from hwpx import HwpxDocument

warnings.filterwarnings("ignore", category=DeprecationWarning)

MM = 283.465   # HWPUNIT / mm
TEXT_W = int(170 * MM)
FONT = "맑은 고딕"


def pdf_images(pdf):
    """공문 PDF의 그림 2개(머리 배너, 직인 문구)를 투명 마스크까지 합쳐 PNG 바이트로."""
    d = tempfile.mkdtemp()
    subprocess.run(["pdfimages", "-all", pdf, os.path.join(d, "im")], check=True)
    files = sorted(os.listdir(d))
    imgs, i = [], 0
    while i < len(files):
        base = Image.open(os.path.join(d, files[i])).convert("RGB")
        if i + 1 < len(files) and Image.open(os.path.join(d, files[i + 1])).mode == "L":
            mask = Image.open(os.path.join(d, files[i + 1])).convert("L")
            bg = Image.new("RGB", base.size, "white")
            bg.paste(base, mask=mask)
            base, i = bg, i + 2
        else:
            i += 1
        buf = io.BytesIO()
        base.save(buf, "PNG")
        imgs.append((buf.getvalue(), base.size))
    return imgs


def build(pdf, out):
    imgs = pdf_images(pdf)
    head, sign = imgs[0], imgs[1]
    d = HwpxDocument.new()
    st = d.styles
    d.set_page_margins(left=int(20 * MM), right=int(20 * MM), top=int(12 * MM), bottom=int(12 * MM), header=0, footer=0)
    body = st.ensure_run(size=11, font=FONT)
    bold = st.ensure_run(size=11, bold=True, font=FONT)
    small = st.ensure_run(size=9.5, font=FONT)
    small_b = st.ensure_run(size=10.5, bold=True, font=FONT)

    def para(text="", run=body, **fmt):
        p = d.add_paragraph(text, para_pr_id_ref=0, char_pr_id_ref=run)
        if fmt:
            st.apply_paragraph_format(paragraph_index=len(d.paragraphs) - 1, **fmt)
        return p

    def runs(parts, **fmt):
        p = para(parts[0][0], parts[0][1], **fmt)
        for t, r in parts[1:]:
            p.add_run(t, char_pr_id_ref=r)
        return p

    # 머리 배너(로고·슬로건·청록 선)
    w, h = head[1]
    d.add_picture(head[0], "png", width_mm=170, height_mm=170 * h / w, para_pr_id_ref=0)
    para("", spacing_after_pt=4)
    for label, key in [("문 서 번 호 : ", "문서번호"), ("발 행 일 자 : ", "발행일자"), ("수          신 : ", "수신"),
                       ("참          조 : ", "참조"), ("제          목 : ", "제목")]:
        runs([(label, small_b), (f"【{key}】", small)], spacing_after_pt=3)
    para("", bottom_border=True, border_color="#000000", border_width="0.4 mm", spacing_after_pt=6)
    for t in ["1. 귀 기관의 무궁한 발전을 기원합니다.",
              "2. ㈜비상교육은 「교원 등의 연수에 관한 규정」 제2조에 의거, 인가번호 제02-9호 비바샘 원격교육연수원을 인가 받아 교원직무연수를 실시하고 있습니다.",
              "3. 추진하신 위탁사업에 관한 결과를 아래와 같이 보고 드립니다."]:
        para(t, indent_left_mm=6, spacing_after_pt=4, line_spacing_percent=160)
    para("")
    for label, key in [("가. 사 업 명", "사업명"), ("나. 연수기간", "연수기간"), ("다. 연수종별", "연수종별"), ("라. 연수대상", "연수대상")]:
        runs([(label, bold), (f" : 【{key}】", body)], indent_left_mm=10, spacing_after_pt=3)
    runs([("마. 연수결과 및 청구금액", bold)], indent_left_mm=10, spacing_after_pt=6)

    # 연수결과 표
    head_fill = st.ensure_border_fill(border_color="#000000", fill_color="#C6D9F1")
    cell_fill = st.ensure_border_fill(border_color="#000000")
    t = d.add_table(2, 7, width=TEXT_W, char_pr_id_ref=body)
    t.set_column_widths([6, 33, 12, 12, 11, 10, 16])
    centre = None
    for j, v in enumerate(["순", "연수과정", "신청인원", "이수인원", "이수율", "만족도", "청구금액"]):
        t.set_cell_text(0, j, v)
        t.set_cell_border_fill(0, j, head_fill)
    for j, v in enumerate(["1", "【대표과정】", "【신청인원】", "【이수인원】", "【이수율】", "【만족도】", "【청구금액】"]):
        t.set_cell_text(1, j, v)
        t.set_cell_border_fill(1, j, cell_fill)
    # 가운데 정렬·굵게(연수과정 칸은 왼쪽)
    p = para("", alignment="CENTER")
    centre = p.para_pr_id_ref
    for i in range(2):
        for j in range(7):
            for cp in t.cell(i, j).paragraphs:
                if not (i == 1 and j == 1):
                    cp.para_pr_id_ref = centre
                for r in cp.runs:
                    r.char_pr_id_ref = bold if (i == 0 or j != 1) else body
    para("")
    para("붙임) 1. 결과보고서", indent_left_mm=6)
    for x in ["2. 이수자 명단", "3. 청구서", "4. 사업자등록증", "5. 통장사본"]:
        para(x, indent_left_mm=17)
    para("")
    para("")
    sw, sh = sign[1]
    d.add_picture(sign[0], "png", width_mm=75, height_mm=75 * sh / sw, para_pr_id_ref=centre)
    para("")
    # 아래 정보(주관부서·담당자·결재라인·주소)
    para("", bottom_border=True, border_color="#000000", border_width="0.2 mm")
    runs([("주관부서 : 【주관부서】      담당자 : 【담당자】      E-mail : 【이메일】      Tel : 【전화】", small)], spacing_after_pt=2)
    runs([("결재라인 : 【결재라인】", small)], spacing_after_pt=2)
    para("", bottom_border=True, border_color="#000000", border_width="0.2 mm")
    runs([("13824 경기 과천시 과천대로2길 54 (갈현동) 그라운드브이 14층", small)])
    d.save_to_path(out)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
    print("ok", sys.argv[2])
