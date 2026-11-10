#!/usr/bin/env python3
"""
비상교육 교과서 채택(과목별 학교별 주문 명세) -> '교과서 채택' 탭 + '지역 총판' 탭 연계 데이터

  변환(로컬, 채택 파일이 바뀔 때만):  python textbook_adoption.py convert <비상교육_채택교과서.xlsx>
    - 시트 '원본'(학교 x 도서 주문 부수), '비바샘 소속정보'(전체 초·중·고 + 주소·비바샘 회원 수),
      '학교알리미_맵핑데이터'(초등 교원 수), '비바샘이간다'(교사 단체 채택)를 묶어
      static_data/textbook_adoption.enc.json 으로 암호화(STRATEGY_KEY 로 배포 때만 복호화 -> 로그인 뒤 화면).
    - 학교별 채택 여부·주문 부수는 내부 영업 정보이므로 공개 저장소에는 아무것도 평문으로 남기지 않는다.
  분모: 비바샘 소속정보의 '일반' 초·중·고(대안·해외 제외). 채택 = 해당 학교가 비상 교과서를 1권 이상 주문.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
LV = {"초": 0, "중": 1, "고": 2, "초등": 0, "중학": 1, "고등": 2}
LV_NAME = ["초", "중", "고"]


def _row(name, lv, sd, g, a, members, teachers, general):
    """학교 1행: [이름, 학교급, 시도, 시군구 코드, 교육청(지원청), 비바샘 회원, 교원, 교과 비트, 교과서 부수, 지도서, 전자책, 분모 여부]"""
    bits = sum(1 << k for k in a["subj"]) if a else 0
    return [name, lv, sd, g, a["office"] if a else "", members, teachers, bits,
            a["copies"] if a else 0, a["guide"] if a else 0, a["ebook"] if a else 0, 1 if general else 0]


def convert(xlsx):
    import openpyxl
    sys.path.insert(0, str(HERE))
    import branch_network as bn
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    rows = [r[1:20] for r in wb["원본"].iter_rows(min_row=5, values_only=True) if r[1]]
    univ = [x for x in wb["비바샘 소속정보(26.02.09)"].iter_rows(min_row=4, values_only=True) if x[2] in ("초등", "중학", "고등")]
    period = ""
    try:
        for x in wb["XLR_NoRangeSheet"].iter_rows(values_only=True):
            if x and x[0] == "xlrParams":
                period = str(x[1])
    except KeyError:
        pass
    # 원본 고유 코드 -> 비바샘 소속코드(교과서 행에만 있음)
    vcode = {}
    # 고유 코드(=학교급&시도코드&교육청코드&학교코드)는 지도서·전자책 행에 계산값이 없어 직접 만든다
    rows = [r if r[8] else r[:8] + ("".join(str(v or "") for v in (r[0], r[2], r[4], r[6])),) + r[9:] for r in rows]
    for r in rows:
        if isinstance(r[9], int):
            vcode[r[8]] = r[9]
    # 학교별 채택 집계
    subj_names, sidx = [], {}

    def si(s):
        if s not in sidx:
            sidx[s] = len(subj_names)
            subj_names.append(s)
        return sidx[s]

    ad = defaultdict(lambda: {"subj": Counter(), "guide": 0, "ebook": 0, "copies": 0, "office": "", "sido": "", "lv": 0, "name": ""})
    for r in rows:
        lv, sido, office, sname, key, kind, subj, qty = LV.get(r[1], 0), r[3], r[5], r[7], r[8], r[11], r[13], r[18] or 0
        if not key or not sname:  # 합계·빈 행
            continue
        a = ad[vcode.get(key) or ("x" + str(key))]
        a.update(lv=lv, sido=sido, office=office, name=a["name"] or sname)
        if kind == "교과서":
            a["subj"][si(subj or "기타")] += qty
            a["copies"] += qty
        elif kind == "지도서":
            a["guide"] += qty
        elif kind == "전자책등":
            a["ebook"] += qty
    tch = {}
    try:
        for x in wb["학교알리미_맵핑데이터"].iter_rows(min_row=5, values_only=True):
            if x[0] and x[10] == "Y" and isinstance(x[7], (int, float)):
                tch[x[0]] = int(x[7])
    except KeyError:
        pass
    groups = Counter()
    try:
        for x in wb["비바샘이간다"].iter_rows(min_row=3, values_only=True):
            if x[0] and x[0] != "Master_1":
                groups[(x[0], x[9])] += 1
    except KeyError:
        pass
    # 학교 목록(전체 일반 초·중·고 + 채택만 있고 소속정보에 없는 학교)
    schools, seen = [], set()
    for x in univ:
        code, lv, name, kind, addr, members = x[0], LV[x[2]], x[3], x[6], x[10], x[11] or 0
        a = ad.get(code)
        if kind != "일반" and not a:
            continue
        seen.add(code)
        sd = bn.SIDO_FULL.get((addr or "").split(" ")[0].replace("\xa0", " ").split(" ")[0]) or (a["sido"] if a else "")
        schools.append(_row(name, lv, sd or "", bn.addr_code((addr or "").replace("\xa0", " ")) or "", a, members, tch.get(code, 0), kind == "일반"))
    for code, a in ad.items():
        if code not in seen:
            schools.append(_row(a["name"], a["lv"], a["sido"], "", a, 0, 0, False))
    # 교과별 주문 부수(학교급 x 시도) - 학교 행에는 교과 비트만 둔다
    copies = defaultdict(int)
    for a in ad.values():
        for k, v in a["subj"].items():
            copies[f"{a['lv']}|{a['sido']}|{k}"] += v
    # 교과(국어·수학 …) 묶음: '교과 테이블'은 원본 행에 이미 들어 있음(r[13])
    return {"as_of": "2026-02-09", "period": period, "subjects": subj_names, "copies": dict(copies),
            "cols": ["이름", "학교급", "시도", "시군구", "교육청", "비바샘회원", "교원", "교과비트", "교과서부수", "지도서", "전자책", "분모"], "schools": schools,
            "groups": [{"group": g, "school": s} for (g, s), _ in groups.items()]}


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "convert":
        import strategy_crypto
        d = convert(sys.argv[2])
        S = d["schools"]
        txt = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        assert not re.search(r"01[016789]-\d{3,4}-\d{4}", txt), "휴대폰 번호가 섞였습니다"
        (HERE / "static_data/textbook_adoption.enc.json").write_text(json.dumps(strategy_crypto.encrypt(d)), encoding="utf-8")
        adopt = [s for s in S if s[8]]
        print(f"학교 {len(S)}곳(분모 일반 {sum(s[11] for s in S)}) · 채택 {len(adopt)}곳 · 교과 {len(d['subjects'])}개 · "
              f"지도 위치 {sum(1 for s in S if s[3])}곳 · 평문 {len(txt) // 1024}KB -> 암호문 저장")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
