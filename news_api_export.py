#!/usr/bin/env python3
"""
briefings/*.json -> 외부 앱이 가져다 쓰는 공개 뉴스 JSON (live/api/news/)

비상 영업용 앱(v-edu-board)의 뉴스 위젯이 fetch 로 읽는 용도다. 신문 지면(news/*.html)과
달리 화면 구성 없이 데이터만 내보내며, 본문 HTML 태그는 전부 벗겨 평문으로 준다
(받는 쪽이 innerHTML 로 넣어도 스크립트가 섞일 여지를 없애기 위해).

  api/news/latest.json   최신 1개 호: 헤드라인·핵심 사실·섹션별 기사·영업 시사점
  api/news/index.json    최근 호 목록(날짜·헤드라인·지면 URL)
  api/news/YYYY-MM-DD.json  호별 전체

사용: python news_api_export.py [briefings_dir] [out_dir]
"""
import html
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SITE = "https://choiys2.github.io/g2b-education-dashboard"
KST = timezone(timedelta(hours=9))
STALE_DAYS = 3   # 이보다 오래된 호면 stale=true - 위젯이 '발행 중단' 안내를 띄울 수 있게

# 영업 담당 분야별 필터용 태그. 헤드라인·시사점 문구에 들어 있으면 붙인다.
TOPIC_TAGS = {
    "예산": r"예산|교부금|재정|추경",
    "AI·디지털": r"AI|인공지능|AIDT|디지털|에듀테크|하이러닝|생성형",
    "교원연수": r"연수|직무|교원\s?역량|자격",
    "정책": r"정책|교육부|법안|국회|시행령|개정",
    "교권·생활지도": r"교권|학교\s?폭력|생활\s?지도|학부모|상담",
    "고교학점제·평가": r"고교\s?학점제|평가|수능|입시|대입",
    "늘봄·돌봄": r"늘봄|돌봄|방과후",
    "경쟁사": r"티처빌|아이스크림|테크빌|한국교원연수원|천재|웅진|메가스터디|NE능률",
    "자사": r"비상교육|비바샘|올비아|UNI-VERS",
}
_TAG_RE = {k: re.compile(v, re.I) for k, v in TOPIC_TAGS.items()}


def text(s):
    """HTML 태그를 벗기고 엔티티를 푼 평문."""
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def tags_for(*parts):
    blob = " ".join(text(p) for p in parts)
    return [k for k, rx in _TAG_RE.items() if rx.search(blob)]


def convert(d):
    day = d.get("date")
    lead = d.get("lead") or {}
    sections = []
    for sec in d.get("sections") or []:
        items = [{
            "title": text(it.get("title")),
            "summary": text(it.get("body")),
            "tags": list(dict.fromkeys((it.get("tags") or []) + tags_for(it.get("title"), it.get("body")))),
            "priority": bool(it.get("priority")),
        } for it in sec.get("items") or []]
        sections.append({"id": sec.get("id"), "name": sec.get("name"), "items": items})
    implications = [{
        "news": text(im.get("news")),
        "sales_point": text(im.get("impact")),   # 브리핑의 '비바샘 시사점' = 영업 토킹포인트
        "tags": tags_for(im.get("news"), im.get("impact")),
    } for im in d.get("implications") or []]
    return {
        "date": day,
        "weekday": d.get("weekday"),
        "url": f"{SITE}/news/{day}.html",
        "lead": {
            "kicker": text(lead.get("kicker")),
            "headline": text(lead.get("headline")),
            "sub": text(lead.get("sub")),
            "summary": text(lead.get("lede")),
            "facts": [{"label": text(f.get("label")), "text": text(f.get("text"))} for f in lead.get("facts") or []],
            "tags": tags_for(lead.get("headline"), lead.get("sub"), lead.get("lede")),
        },
        "indices": [{k: text(v) for k, v in i.items()} for i in d.get("indices") or []],
        "sections": sections,
        "implications": implications,
        "sources": text(d.get("sources")),
    }


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "briefings")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "live/api/news")
    files = sorted(src.glob("????-??-??.json"))
    if not files:
        print("브리핑 없음 - 건너뜀")
        return
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    issues = []
    for n, f in enumerate(files, 1):
        issue = convert(json.loads(f.read_text(encoding="utf-8")))
        issue["issue_no"] = n
        (out / f"{issue['date']}.json").write_text(json.dumps(issue, ensure_ascii=False, indent=1), encoding="utf-8")
        issues.append(issue)

    latest = issues[-1]
    age = (now.date() - date.fromisoformat(latest["date"])).days
    meta = {"generated_at": now.isoformat(timespec="minutes"), "latest_date": latest["date"],
            "age_days": age, "stale": age > STALE_DAYS, "tag_list": list(TOPIC_TAGS)}
    (out / "latest.json").write_text(json.dumps({**meta, "issue": latest}, ensure_ascii=False, indent=1), encoding="utf-8")
    def issue_tags(i):
        ts = list(i["lead"]["tags"])
        for sec in i["sections"]:
            for it in sec["items"]:
                ts += [t for t in it["tags"] if t in TOPIC_TAGS]
        return list(dict.fromkeys(ts))

    # titles: 지난 호 검색용(호마다 파일을 다 받지 않고 목록만으로 기사 제목·시사점까지 검색)
    index = [{"date": i["date"], "issue_no": i["issue_no"], "headline": i["lead"]["headline"],
              "kicker": i["lead"]["kicker"], "tags": issue_tags(i), "url": i["url"],
              "json": f"{SITE}/api/news/{i['date']}.json",
              "titles": [it["title"] for sec in i["sections"] for it in sec["items"]] +
                        [im["news"] for im in i["implications"]]}
             for i in reversed(issues)]
    (out / "index.json").write_text(json.dumps({**meta, "issues": index}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"news api: {len(issues)}개 호 -> {out} (최신 {latest['date']}, {age}일 전{' · stale' if meta['stale'] else ''})")


if __name__ == "__main__":
    main()
