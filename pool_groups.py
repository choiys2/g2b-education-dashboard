#!/usr/bin/env python3
"""
강사풀 아티팩트(비공개) 데이터 -> 교사 트렌드 2027 '교사단체·강사 공급' 패널용 파일 2개

  static_data/teacher_groups.json        공개 저장소에 커밋: 단체명·규모·활동 분야·비상 협력 여부·주제 매핑,
                                          강사풀 집계(등급·학교급·과목·권역 분포) - 개인 이름·연락처 없음
  static_data/pool_people.enc.json       개인 정보(핵심 강사·단체 대표·활동 상위 강사의 이름·소속·과목·권역·실적)
                                          를 strategy_pubkey.txt 로 암호화 - 배포 때 STRATEGY_KEY 로만 풀려
                                          로그인 뒤 화면에만 나온다. 연락처(전화)는 암호화본에도 넣지 않는다.

강사풀 아티팩트를 갱신했으면, 그 HTML 의 JSON 블록(dataBlob·researchBlob·assocBlob)을 한 폴더에 풀어 두고 다시 돌린다.
  python pool_groups.py <blob_dir>
"""
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote

import strategy_crypto
from mall_trends import TOPIC_NAME, topics_of

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
PUB_OUT = Path("static_data/teacher_groups.json")
ENC_OUT = Path("static_data/pool_people.enc.json")
COMPETITORS = ("미래엔", "테크빌", "티처빌", "아이스크림", "천재교육", "지학사", "동아출판")


def j(name):
    return json.loads((SRC / f"{name}.json").read_text(encoding="utf-8"))


def short(name):
    """'(사)좋은교사운동' -> '좋은교사운동', '참쌤스쿨' 그대로 - 뉴스 검색어용."""
    n = re.sub(r"\(사\)|\([^)]*\)|（[^）]*）", " ", name)
    return re.sub(r"\s+", " ", n).strip() or name


def news_url(name):
    return "https://search.naver.com/search.naver?where=news&sort=1&query=" + quote(f'"{short(name)}"')


def tp(*texts):
    return topics_of(" ".join(t for t in texts if t))


def ok_person(v):
    v = (v or "").strip()
    return v and not re.search(r"확인 필요|개별 확인|운영진|대표진|임원진|미상", v)


def main():
    data, research, assoc = j("dataBlob"), j("researchBlob"), j("assocBlob")
    people = {"core": [], "leaders": [], "top": [], "generated": date.today().isoformat()}

    national = []
    for o in assoc.get("national_orgs", []):
        note = o.get("note") or ""
        mou = (o.get("visang_mou") or "").strip()
        comp = [c for c in COMPETITORS if c in note and "비상" not in c]
        national.append({
            "name": o["name"], "scale": o.get("scale") or "", "focus": o.get("focus") or "",
            "mou": bool(mou) and "미체결" not in mou, "mou_note": re.sub(r"\(.*?\)", "", mou).strip()[:40],
            "friendly": str(o.get("visang_friendly")) == "True", "comp": comp,
            "contest": int(o.get("contest_participants") or 0), "stamps": int(o.get("contest_stamps") or 0),
            "unverified": (o.get("scale") or "").startswith("확인 필요"),
            "topics": tp(o.get("focus"), o["name"]), "news": news_url(o["name"]),
        })
        if ok_person(o.get("leader")):
            people["leaders"].append({"org": o["name"], "leader": o["leader"]})

    regional = [{"authority": o.get("authority") or "", "name": o["name"], "scale": o.get("scale") or "",
                 "focus": o.get("focus") or "", "result": o.get("result") or "",
                 "topics": tp(o.get("focus")), "news": news_url(o["name"])} for o in assoc.get("regional_orgs", [])]

    groups = []
    for g in research.get("groups", []):
        groups.append({
            "sido": g.get("sido") or "", "region": g.get("region") or "", "name": g["name"], "theme": g.get("theme") or "",
            "tier": g.get("tier") or "", "score": int(g.get("score") or 0), "verify": g.get("verify") or "",
            "confirmed": g.get("confirmed_date") or "", "collab": g.get("collab") or "",
            "url": g["url"] if str(g.get("url") or "").startswith("http") else "",
            "topics": tp(g.get("theme"), g.get("collab")), "news": news_url(g["name"]),
        })
        if ok_person(g.get("person")):
            people["leaders"].append({"org": g["name"], "leader": g["person"]})
    groups.sort(key=lambda g: -g["score"])

    for c in assoc.get("core_instructors", []):
        people["core"].append({k: c.get(k) or "" for k in ("field", "tier", "name", "title", "org", "career")})

    ins = data.get("instructors", [])
    for i in sorted(ins, key=lambda i: (-(i.get("total") or 0), i.get("name") or ""))[:80]:
        people["top"].append({
            "name": i.get("name"), "aff": i.get("affiliation") or "", "tier": i.get("tier") or "",
            "levels": i.get("levels") or [], "subjects": [s for s in (i.get("subjects") or []) if s not in ("초등",)][:4],
            "regions": (i.get("regions") or [])[:3], "total": i.get("total") or 0, "main": i.get("main") or 0,
            "online": i.get("online") or 0, "offline": i.get("offline") or 0, "biz": len(i.get("businesses") or []),
            "y2026": (i.get("year_totals") or {}).get("2026", 0),
            "flag": "승급 후보" if i.get("promotion_candidate") else ("휴면 핵심" if i.get("dormant_core") else ""),
        })

    # 공고 매칭용 전체 강사(이름·소속·등급·학교급·과목·시도·실적·AI 연수 경험) - 연락처 없음, 암호문에만
    team = j("teamBlob") if (SRC / "teamBlob.json").exists() else {}
    gg = {r["region"] for r in team.get("regions_meta", []) if r.get("group") == "경기 교육지원청"}
    def sido(r):
        if r in gg or r.startswith("경기") or r.endswith("교육지원청"):
            return "경기"
        if r == "전국":
            return "*"
        if r.startswith("전남광주"):
            return "전남·광주"
        return r.split("(")[0]
    for i in ins:
        sd = sorted({x for r in (i.get("regions") or []) for x in sido(r).split("·")})
        people["all"] = people.get("all", [])
        people["all"].append([i.get("name"), i.get("affiliation") or "", i.get("tier") or "",
                              "".join(l[0] for l in (i.get("levels") or [])), [x for x in (i.get("subjects") or []) if x != "초등"][:4], sd,
                              i.get("total") or 0, i.get("main") or 0,
                              int(any("인공지능" in b or "AI" in b for b in (i.get("businesses") or []))),
                              (i.get("year_totals") or {}).get("2026", 0)])

    # 주제별 공급원: 2027 트렌드 주제마다 맞는 단체 수(전국 협회 + 시도 연구회 + 교육청 연구회)
    sup = {tid: {"id": tid, "name": nm, "n": 0, "names": []} for tid, nm in TOPIC_NAME.items()}
    for o in national + regional + groups:
        for t in o["topics"]:
            if t in sup:
                sup[t]["n"] += 1
                if len(sup[t]["names"]) < 6:
                    sup[t]["names"].append(o["name"])

    tier = Counter(i.get("tier") for i in ins)
    lv = Counter(l for i in ins for l in i.get("levels") or [])
    subj = Counter(s for i in ins for s in i.get("subjects") or [] if s not in ("초등",))
    reg = Counter(r for i in ins for r in i.get("regions") or [])
    biz = Counter(b for i in ins for b in i.get("businesses") or [])
    meta = research.get("meta", {})
    out = {
        "generated": date.today().isoformat(), "survey_date": meta.get("survey_date", ""),
        "source": "비바샘 강사풀(사내 비공개 아티팩트) · 공개·공식 출처로 확인한 교사단체 조사",
        "principles": (meta.get("key_conclusions") or [])[:4] + (meta.get("sales_principles") or [])[:3],
        "national": national, "regional": regional, "groups": groups,
        "sido_priority": [{k: s.get(k) for k in ("rank", "sido", "support_count", "anchor_theme", "priority")}
                          for s in research.get("sido_priority", [])],
        "books": [{"title": b["title"], "publisher": b.get("publisher", ""), "date": b.get("pub_date", ""),
                   "authors": int(b.get("author_count") or 0), "teachers": int(b.get("teacher_author_count") or 0),
                   "pool": int(b.get("pool_match_count") or 0),
                   "keywords": b["keywords"] if isinstance(b.get("keywords"), list) else re.findall(r"'([^']+)'", str(b.get("keywords"))),
                   "url": b.get("url", "")} for b in research.get("books", [])],
        "supply": sorted(sup.values(), key=lambda s: -s["n"]),
        "pool": {"kpi": data.get("kpi", {}), "n": len(ins), "tier": tier.most_common(), "levels": lv.most_common(),
                 "subjects": subj.most_common(10), "regions": reg.most_common(12), "biz": biz.most_common(),
                 "online": sum((i.get("online") or 0) > 0 for i in ins), "offline": sum((i.get("offline") or 0) > 0 for i in ins)},
    }
    blob = json.dumps(out, ensure_ascii=False)
    assert not re.search(r"010-|\d{2,3}-\*{3,4}-\d{4}", blob), "공개 파일에 전화번호 형식이 섞였습니다"
    for p in people["core"] + people["leaders"]:
        nm = (p.get("name") or p.get("leader") or "").split("(")[0].strip()
        if len(nm) >= 2 and nm in blob and nm not in ("TOUCH 교사단 핵심 강사진",):
            print(f"  [주의] 공개 파일에 개인 이름이 남음: {nm[:1]}**", file=sys.stderr)
    PUB_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    pp = json.dumps(people, ensure_ascii=False)
    assert not re.search(r"010-|\d{2,3}-\*{3,4}-\d{4}", pp), "개인 파일에 전화번호가 섞였습니다"
    ENC_OUT.write_text(json.dumps(strategy_crypto.encrypt(people)), encoding="utf-8")
    print(f"공개 {PUB_OUT}: 전국 {len(national)} · 교육청 {len(regional)} · 연구회 {len(groups)} · 도서 {len(out['books'])}")
    print(f"암호화 {ENC_OUT}: 핵심 {len(people['core'])} · 대표 {len(people['leaders'])} · 상위 {len(people['top'])} · 매칭용 {len(people.get('all', []))}")


if __name__ == "__main__":
    main()
