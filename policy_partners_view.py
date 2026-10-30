#!/usr/bin/env python3
"""
연수원 3사 개인정보처리방침의 협력사(처리위탁 수탁사·제3자 제공처) -> 경쟁사 탭 패널 데이터.
combine_dashboard.py 에서 호출(수집은 policy_partners_scrape.py, 매주 월).

  - 표 한 칸에 여러 회사가 쉼표·줄바꿈으로 들어 있어 회사 단위로 나눈다.
  - 용도 분류: 사업 협력(공공·교육청 / 위탁연수 공급처 / 상품·콘텐츠 공급 / 제휴 서비스 / AI)과
    운영 인프라(결제 / 배송 / 메시지 / 본인인증 / 고객상담 / IT·서버·분석)로 나눈다.
"""
import json
import re
from pathlib import Path

SRC = Path(__file__).parent / "history" / "policy_partners.json"
ORDER = ["teacherville", "iscream", "vivasam"]
OWN = "vivasam"

BIZ = ["공공·교육청", "위탁연수 공급처", "상품·콘텐츠 공급", "제휴 서비스", "AI"]
INFRA = ["결제", "배송·물류", "메시지·알림", "본인인증", "고객상담·원격지원", "IT·서버·분석", "기타"]
COURIER = re.compile(r"택배|우체국|한진|로지스|CJ\s?대한|롯데글로벌|네오씨앤씨|북서브", re.I)
CORP = re.compile(r"\(주\)|㈜|주식회사|\(유\)|유한회사|\s+")
DROP = re.compile(r"^(외|등|전체\s?보기|상세\s?목록|이메일\s?:?|연락처|-|위탁업체.*)$")


def norm(n):
    return CORP.sub("", n or "").lower()


def split_names(cell):
    cell = re.sub(r"\[?\s*(상세\s?목록|전체\s?보기)\s*\]?|\(\s*전체\s?보기\s*\)", "", cell or "")
    cell = re.sub(r"\s외\s*$", "", cell.strip())
    out = []
    for p in re.split(r"\s*[|,，/·]\s*|\s{2,}", cell):
        p = re.sub(r"^(이메일|연락처)\s*:.*$", "", p.strip()).strip(" -")
        p = re.sub(r"\s+외$", "", p)
        if p and not DROP.match(p) and len(p) <= 60:
            out.append(p)
    return out


def category(name, task, group, kind):
    t = f"{group} {task}"
    if re.search(r"교육청|KERIS|학술정보원|공공기관|지원청", name + " " + t):
        return "공공·교육청"
    if re.search(r"연수\s?위탁|위탁운영|출석고사", t):
        return "위탁연수 공급처"
    if re.search(r"상담|고객\s?지원|원격\s?지원|CS", t):
        return "고객상담·원격지원"
    if re.search(r"openai|claude|gemini|\bAI\b|인공지능|챗봇", name + " " + t, re.I):
        return "AI"
    if re.search(r"결제", t):
        return "결제"
    if re.search(r"배송|제작", t):
        return "배송·물류" if COURIER.search(name) else "상품·콘텐츠 공급"
    if re.search(r"시스템 운영|서비스 개발", t):
        return "IT·서버·분석"
    if re.search(r"상품\s?공급|공급업체|라이선스|전자도서관|콘텐츠", t):
        return "상품·콘텐츠 공급"
    if re.search(r"복지몰|쇼핑몰|제휴|교수지원|어플", t):
        return "제휴 서비스"
    if re.search(r"SMS|문자|알림|메시지|메세지|팩스|푸시|쿠폰|기프티콘|080|발송", t, re.I):
        return "메시지·알림"
    if re.search(r"인증", t):
        return "본인인증"
    if re.search(r"서버|클라우드|유지보수|개발|시스템|분석|CRM|추천|호스팅", t, re.I):
        return "IT·서버·분석"
    return "기타"


def _col(head, pat, default=None, skip=()):
    for i, h in enumerate(head):
        if i not in skip and re.search(pat, h):
            return i
    return default


def extract(site):
    """수집 결과 1곳 -> [{kind, name, task, group, cat}] (회사 단위, 중복 제거)"""
    out, seen = [], set()
    for kind, key in (("위탁", "consign_tables"), ("제공", "third_tables")):
        for t in site.get(key) or []:
            head = t.get("head") or []
            hs = " ".join(head)
            overseas = "국외" in (t.get("ctx") or "") or "국가" in hs
            if kind == "위탁":
                ni = _col(head, r"수탁")
                if ni is None and head[:2] == ["구분", "목적"]:  # 비바샘: 머리글이 실제 열과 어긋나 있음(구분|수탁사|업무)
                    ni, ti, gi = 1, 2, 0
                elif ni is None:
                    continue
                else:
                    ti, gi = _col(head, r"업무|목적", ni + 1, (ni,)), _col(head, r"구분", None, (ni,))
            else:
                ni = _col(head, r"받는\s?자|제공처")
                if ni is None:
                    continue
                ti, gi = _col(head, r"목적", ni + 1, (ni,)), _col(head, r"구분", None, (ni,))
            for r in t.get("rows") or []:
                if ni >= len(r):
                    continue
                task = r[ti] if ti is not None and ti < len(r) else ""
                group = r[gi] if gi is not None and gi < len(r) else ""
                cell = r[ni]
                if overseas and "/" in cell:  # '미국 (US) / openAI / 이메일:'
                    parts = [p.strip() for p in cell.split("/")]
                    cell, group = (parts[1] if len(parts) > 1 else parts[0]), f"국외 이전({parts[0]})"
                names = split_names(cell)
                ext = next((x["text"] for x in site.get("expand") or [] if x.get("near") and cell.startswith(x["near"][:12])), "")
                if ext:
                    names += [n for n in split_names(re.sub(r"\n", "|", ext)) if 2 <= len(n) <= 25 and not re.search(r"닫기|보기|목록|개인정보|제공|공급", n)]
                for n in names:
                    k = (kind, norm(n), task)
                    if k in seen:
                        continue
                    seen.add(k)
                    out.append({"kind": "국외 이전" if overseas else kind, "name": n, "task": task, "group": group,
                                "cat": category(n, task, group, kind), "listed": bool(ext) and n not in split_names(r[ni])})
    return out


def build():
    try:
        src = json.loads(SRC.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"available": False}
    sites = src.get("sites") or {}
    ent = {k: extract(sites[k]) for k in ORDER if k in sites}
    if not any(ent.values()):
        return {"available": False}
    names = {k: {norm(e["name"]) for e in v} for k, v in ent.items()}
    for k, v in ent.items():
        for e in v:
            e["shared"] = [o for o in ent if o != k and norm(e["name"]) in names[o]]
    cats = BIZ + INFRA
    matrix = []
    for c in cats:
        row = {"cat": c, "biz": c in BIZ}
        for k in ent:
            row[k] = [{"n": e["name"], "t": e["task"], "g": e["group"], "kind": e["kind"], "shared": e["shared"], "listed": e.get("listed")}
                      for e in ent[k] if e["cat"] == c]
        if any(row.get(k) for k in ent):
            matrix.append(row)
    summary = []
    for k in ent:
        s = sites[k]
        v = ent[k]
        summary.append({"key": k, "name": s.get("name"), "own": k == OWN, "url": s.get("url"), "effective": s.get("effective"),
                        "captured": s.get("captured"), "notices": s.get("notices") or [],
                        "n_consign": sum(1 for e in v if e["kind"] != "제공"), "n_third": sum(1 for e in v if e["kind"] == "제공"),
                        "n_biz": sum(1 for e in v if e["cat"] in BIZ), "error": s.get("last_error")})
    # 경쟁사만 쓰는 사업 협력처(자사와 겹치지 않음) - 협의·벤치마크 후보
    comp_only = [{"site": sites[k]["name"], "name": e["name"], "cat": e["cat"], "task": e["task"], "group": e["group"]}
                 for k in ent if k != OWN for e in ent[k] if e["cat"] in BIZ and OWN not in e["shared"]]
    return {"available": True, "updated": src.get("updated"), "summary": summary, "matrix": matrix,
            "comp_only": comp_only, "changes": (src.get("changes") or [])[-30:][::-1],
            "insights": insights(ent, sites)}


def insights(ent, sites):
    out = []
    nm = lambda k: sites[k]["name"]
    for k in ent:
        if k == OWN:
            continue
        own_n = sum(1 for e in ent.get(OWN, []) if e["cat"] == "위탁연수 공급처")
        tr = [e["name"] for e in ent[k] if e["cat"] == "위탁연수 공급처"]
        if len(tr) > own_n:
            out.append(f"<b>{nm(k)}</b>는 위탁연수 공급처 {len(tr)}곳을 공개(자사 {own_n}곳) — {', '.join(tr[:6])}{' 외' if len(tr) > 6 else ''}. "
                       "공공기관·재단·기업의 교원 대상 위탁 운영이 B2G 입찰 밖의 수주 경로입니다.")
        goods = [e["name"] for e in ent[k] if e["cat"] == "상품·콘텐츠 공급"]
        if len(goods) >= 3:
            out.append(f"<b>{nm(k)}</b> 상품·콘텐츠 공급처 {len(goods)}곳 — 샘몰 입점 협의 후보와 겹치는지 '샘몰 협력사 우선 협의 리스트'와 대조하세요.")
        ai = [e["name"] for e in ent[k] if e["cat"] == "AI"]
        if ai:
            out.append(f"<b>{nm(k)}</b>는 학습자 데이터를 AI 서비스({', '.join(ai)})에 제공·위탁 — AI 챗봇·생성 기능을 이미 운영 중입니다.")
    return out


if __name__ == "__main__":
    o = build()
    print(json.dumps({k: o.get(k) for k in ("summary", "insights")}, ensure_ascii=False, indent=1))
    for r in o.get("matrix", []):
        print(r["cat"], {k: [x["n"] for x in r.get(k, [])] for k in ORDER})
