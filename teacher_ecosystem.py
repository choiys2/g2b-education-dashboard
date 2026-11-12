#!/usr/bin/env python3
"""
교사 생태계 비교 수집(주 1회, teacher_ecosystem.yml) - 출판사·교사 플랫폼의 교사 서비스 구성

  - 각 서비스 첫 화면 + 라이브·연수·강의로 보이는 링크 몇 개를 열어 메뉴·제목·기능 키워드를 모은다(공개 페이지)
  - 공개 출력 history/teacher_ecosystem.json : 서비스별 메뉴 글자·기능 키워드 유무·강사 수(집계)·강의 수
  - 강사 이름은 공개키로 암호화해 history/teacher_ecosystem_people.enc.json 에만(로그인 뒤 화면)
  - 개인 연락처·회원 정보는 수집하지 않는다. 로그인 필요한 화면은 열지 않는다.
  python teacher_ecosystem.py
"""
import json
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "history" / "teacher_ecosystem.json"
OUT_ENC = HERE / "history" / "teacher_ecosystem_people.enc.json"
OUT_CHG = HERE / "history" / "teacher_eco_changes.jsonl"   # 주간 변화(새 메뉴·제목) - 이름류는 걸러서
OUT_SCORE = HERE / "history" / "teacher_eco_scores.json"   # 9축 구성 점수 주별 기록
MATRIX = HERE / "static_data" / "teacher_ecosystem.json"
TARGETS = [
    ("비상", "비바샘", "https://www.vivasam.com"),
    ("비상", "비바샘원격교육연수원", "https://t.vivasam.com"),
    ("미래엔", "엠티처", "https://www.m-teacher.co.kr"),
    ("미래엔", "엠티처 라이브·OTT", "https://g.m-teacher.co.kr/pages/live/ott/Main.mrn"),
    ("천재", "T셀파", "https://www.tsherpa.co.kr"),
    ("동아", "두클래스", "https://www.douclass.com"),
    ("아이스크림", "아이스크림S", "https://www.i-scream.co.kr"),
    ("아이스크림", "아이스크림원격교육연수원", "https://teacher.i-scream.co.kr"),
    ("지학사", "지학사 교과서", "https://textbook.jihak.co.kr"),
    ("YBM", "YBM 교과서", "https://www.ybmbooks.com"),
    ("금성", "금성출판사", "https://www.kumsung.co.kr"),
    ("티처빌", "티처빌", "https://www.teacherville.co.kr"),
    ("티처빌", "쌤동네(엠티처 채널)", "https://www.teacherville.co.kr/ssam/channel/tabContents.edu?channelId=mteacher"),
    ("인디스쿨", "인디스쿨", "https://indischool.com"),
]
FEATURES = {
    "수업자료": r"수업\s?자료|자료실|PPT|활동지|학습지|차시",
    "평가": r"평가|문항|시험지|채점",
    "디지털·AI": r"AI|인공지능|디지털|에듀테크|플랫폼|코스웨어",
    "라이브·OTT": r"라이브|LIVE|Live|OTT|생방송|실시간",
    "연수·학점": r"연수|학점|직무|자격|이수",
    "커뮤니티": r"커뮤니티|게시판|모임|라운지|카페|나눔",
    "크리에이터": r"크리에이터|작가|파트너|콘텐츠\s?제작|강사\s?모집",
    "쇼핑·몰": r"몰|스토어|SHOP|Shop|구매|장바구니|굿즈",
    "앱": r"앱\s?다운|App|앱스토어|플레이스토어",
    "학급운영": r"학급|출결|알림장|생활기록|업무",
}
LINK_RE = re.compile(r"라이브|LIVE|OTT|연수|강의|강좌|클래스|세미나|크리에이터")
# 공개 출력에서 빼는 항목: 개인 채널명·별칭(OO쌤·OO선생님 등) -> 암호문 쪽으로만
PERSONAL_RE = re.compile(r"쌤|선생|교사|강사|작가|교수|박사|[가-힣]{2,4}\s?(TV|tv)\b|@")
NAME_RE = re.compile(r"([가-힣]{2,4})\s?(선생님|쌤|교사|강사|교수|작가|박사)(?![가-힣])")
STOP = set("우리 모든 현직 초등 중등 고등 담임 신규 예비 교과 수석 전문 대표 우수 담당 학교 학급 국어 수학 영어 과학 사회 미술 음악 체육 도덕 "
           "기술 가정 정보 한국 세계 역사 진로 상담 특수 보건 사서 영양 유치원 교육 연수 학습 수업 연구 지역 우리반 모두의 함께 나의 "
           "멘토 원어민 외부 선배 동료 강의 담임교 선생 우리학교 학생 학부모 행복한 좋은 최고의 인기".split())


EV_WORD = re.compile(r"라이브|LIVE|Live|강연|세미나|특강|웨비나|연수|토크|설명회|박람회|워크숍|모집|신청")
DATE_RES = [re.compile(r"(20\d\d)\s?[.\-/년]\s?(\d{1,2})\s?[.\-/월]\s?(\d{1,2})"), re.compile(r"(?<![\d.])(\d{1,2})\s?월\s?(\d{1,2})\s?일"),
            re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\s?\((?:월|화|수|목|금|토|일)\)")]
MASK = re.compile(r"[가-힣]{2,4}\s?(쌤|선생님|교사|강사|교수|작가|박사)")


def events(body, co, svc, today):
    """화면 글자에서 날짜가 붙은 라이브·강연·연수 줄을 뽑는다(최근 30일~앞으로 120일). 개인 이름·별칭은 OO 로 가린다."""
    out, seen = [], set()
    for line in body.splitlines():
        t = re.sub(r"\s+", " ", line).strip()
        if not (6 <= len(t) <= 120) or not EV_WORD.search(t):
            continue
        d = None
        for i, rx in enumerate(DATE_RES):
            m = rx.search(t)
            if not m:
                continue
            try:
                if i == 0:
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    mo, dd = int(m.group(1)), int(m.group(2))
                    d = date(today.year, mo, dd)
                    if (d - today).days < -200:
                        d = date(today.year + 1, mo, dd)
            except ValueError:
                d = None
            break
        if not d or not (-30 <= (d - today).days <= 120):
            continue
        t = MASK.sub(lambda m: "OO" + m.group(1), t)[:90]
        k = (d.isoformat(), t[:40])
        if k in seen:
            continue
        seen.add(k)
        out.append({"co": co, "svc": svc, "d": d.isoformat(), "t": t})
    return out[:30]


def grab(page):
    return page.evaluate("""() => {
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const txt = e => (e.innerText || '').replace(/\\s+/g, ' ').trim();
      const nav = [...document.querySelectorAll('header a, nav a, [class*=gnb] a, [class*=menu] a')].filter(vis).map(txt).filter(t => t && t.length <= 20);
      const heads = [...document.querySelectorAll('h1,h2,h3,h4,strong,[class*=title]')].filter(vis).map(txt).filter(t => t && t.length <= 60);
      const links = [...document.querySelectorAll('a[href]')].filter(vis).map(a => ({t: txt(a).slice(0, 40), h: a.href})).filter(x => x.t);
      return {title: document.title, url: location.href, nav: [...new Set(nav)].slice(0, 80), heads: [...new Set(heads)].slice(0, 120),
              links: links.slice(0, 400), body: (document.body ? document.body.innerText : '').slice(0, 60000)};
    }""")


def youtube(chan_all):
    """쌤OTT 등 교사 채널 후보 -> 유튜브 공개 통계(구독자·영상 수). 키 없으면 건너뜀. 결과는 암호문 쪽에만 이름과 함께."""
    import os
    import urllib.parse
    import urllib.request
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        print("유튜브: 키 미설정 - 건너뜀")
        return []
    def get(path, **q):
        q["key"] = key
        with urllib.request.urlopen("https://www.googleapis.com/youtube/v3/" + path + "?" + urllib.parse.urlencode(q), timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    res, used = [], 0
    # 미래엔 쌤OTT 등 경쟁 플랫폼 채널을 먼저(검색 한도 안에서 비교 대상 우선), 자사는 뒤로
    for svc, chans in sorted(chan_all.items(), key=lambda kv: (0 if "OTT" in kv[0] or "채널" in kv[0] else 2 if kv[0].startswith("비바샘") else 1)):
        for c in [x for x in chans if 2 <= len(x) <= 25 and not re.search(r"[#|\[\]]", x)][:25]:
            if used >= 45:  # 검색 1회 100단위 - 하루 한도 안에서 넉넉히
                break
            try:
                used += 1
                it = (get("search", part="snippet", type="channel", maxResults=1, q=c).get("items") or [])
                if not it:
                    continue
                cid = it[0]["snippet"]["channelId"]
                st = (get("channels", part="statistics,snippet", id=cid).get("items") or [{}])[0]
                s_ = st.get("statistics", {})
                res.append({"svc": svc, "q": c, "title": st.get("snippet", {}).get("title", "")[:60], "subs": int(s_.get("subscriberCount", 0) or 0),
                            "videos": int(s_.get("videoCount", 0) or 0), "views": int(s_.get("viewCount", 0) or 0)})
            except Exception as e:  # noqa: BLE001 - 키·한도 문제는 값 없이 이유만
                print("유튜브 조회 중단:", getattr(e, "code", type(e).__name__))
                return res
    print(f"유튜브: 채널 {len(res)}개 통계")
    return res


def diff(prev, out):
    """지난 수집 대비 새로 생긴/사라진 메뉴, 새 제목(공개 가능 항목만)."""
    old = {r.get("svc"): r for r in (prev.get("services") or []) if r.get("ok")}
    items = []
    for r in out:
        o = old.get(r["svc"])
        if not r.get("ok") or not o:
            continue
        nn, on = set(r.get("nav") or []), set(o.get("nav") or [])
        nh = [x for x in (r.get("heads") or []) + [y for sb in r.get("subs") or [] for y in sb.get("heads", [])]
              if x not in set((o.get("heads") or []) + [y for sb in o.get("subs") or [] for y in sb.get("heads", [])]) and 6 <= len(x) <= 60]
        if nn - on or on - nn or nh:
            items.append({"co": r["co"], "svc": r["svc"], "new_nav": sorted(nn - on)[:15], "gone_nav": sorted(on - nn)[:15], "new_titles": nh[:12]})
    return items


def snapshot_scores():
    """정리표(9축) 구성 점수를 주별로 기록 - 비상 격차 추이."""
    try:
        m = json.loads(MATRIX.read_text(encoding="utf-8"))
        sc = {c["co"]: round(sum(1 if c["m"].get(k) == "O" else 0.5 if c["m"].get(k) == "△" else 0 for k, _ in m["axes"]), 1) for c in m["companies"]}
        hist = json.loads(OUT_SCORE.read_text(encoding="utf-8")) if OUT_SCORE.exists() else {}
        hist[date.today().isoformat()] = sc
        OUT_SCORE.write_text(json.dumps(dict(sorted(hist.items())[-52:]), ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print("점수 기록 생략:", type(e).__name__)


def main():
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(HERE))
    out, people, t0, chan_all, evs = [], {}, time.time(), {}, []
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(locale="ko-KR", viewport={"width": 1366, "height": 900},
                             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")
        for co, svc, url in TARGETS:
            rec = {"co": co, "svc": svc, "url": url, "ok": False}
            pg = ctx.new_page()
            try:
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception:  # noqa: BLE001 - 느린 사이트는 첫 응답만 받고 진행
                    pg.goto(url, wait_until="commit", timeout=60000)
                    pg.wait_for_timeout(8000)
                try:
                    pg.wait_for_load_state("networkidle", timeout=12000)
                except Exception:  # noqa: BLE001
                    pass
                pg.wait_for_timeout(2500)
                g = grab(pg)
                body = g["body"]
                subs = []
                host = re.sub(r"^https?://", "", g["url"]).split("/")[0]
                cand = [l for l in g["links"] if LINK_RE.search(l["t"]) and host.split(".")[-2] in l["h"] and l["h"].startswith("http")]
                for l in cand[:3]:  # 라이브·연수 링크 한 단계만
                    try:
                        pg.goto(l["h"], wait_until="domcontentloaded", timeout=25000)
                        pg.wait_for_timeout(2500)
                        s = grab(pg)
                        subs.append({"t": l["t"], "url": s["url"], "heads": s["heads"][:40]})
                        body += "\n" + s["body"]
                    except Exception:  # noqa: BLE001
                        continue
                feats = {k: len(re.findall(v, body)) for k, v in FEATURES.items()}
                names = Counter(m.group(1) for m in NAME_RE.finditer(body) if m.group(1) not in STOP and not re.search(r"[0-9]", m.group(1)))
                pub = lambda xs: [x for x in xs if not PERSONAL_RE.search(x)]
                chans = sorted({x for x in g["nav"] + g["heads"] + [y for sb in subs for y in sb["heads"]] if PERSONAL_RE.search(x) and len(x) <= 30})
                people[svc] = [n for n, _ in names.most_common(60)] + [c for c in chans if c not in names][:60]
                raw_titles = g["heads"] + [y for sb in subs for y in sb["heads"]]
                try:
                    import training_topics as tt
                    tc = Counter(t for x in raw_titles for t in tt.classify_topics(x))
                except Exception:  # noqa: BLE001
                    tc = Counter()
                rec["topics"] = dict(tc)
                evs.extend(events(body, co, svc, date.today()))
                chan_all[svc] = chans
                for sb in subs:
                    sb["heads"] = pub(sb["heads"])
                rec.update(ok=True, final=g["url"], title=g["title"][:80], nav=pub(g["nav"])[:40], heads=pub(g["heads"])[:50],
                           subs=subs, features=feats, n_people=len(people[svc]), n_channels=len(chans), chars=len(body))
            except Exception as e:  # noqa: BLE001
                rec["error"] = type(e).__name__ + ": " + str(e)[:80]
            finally:
                pg.close()
            out.append(rec)
            print(f"  {svc}: {'ok' if rec['ok'] else rec.get('error')} · 강사 후보 {rec.get('n_people', 0)}", flush=True)
        br.close()
    yt = youtube(chan_all)
    for r in out:
        y = [c for c in yt if c["svc"] == r["svc"]]
        if y:
            subs_ = sorted(c["subs"] for c in y)
            r["yt"] = {"n": len(y), "subs_sum": sum(subs_), "subs_med": subs_[len(subs_) // 2], "videos_sum": sum(c["videos"] for c in y)}
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    changes = diff(prev, out)
    if changes:
        with OUT_CHG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"d": date.today().isoformat(), "items": changes}, ensure_ascii=False) + "\n")
        lines = OUT_CHG.read_text(encoding="utf-8").splitlines()[-26:]
        OUT_CHG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    snapshot_scores()
    OUT.write_text(json.dumps({"generated": date.today().isoformat(), "sec": round(time.time() - t0), "services": out, "changes": changes, "events": sorted(evs, key=lambda e: e["d"]),
                               "note": "공개 첫 화면·라이브/연수 링크 1단계의 메뉴·제목·기능 키워드 빈도. 강사 이름은 암호문에만."},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        import strategy_crypto
        OUT_ENC.write_text(json.dumps(strategy_crypto.encrypt({"generated": date.today().isoformat(), "people": people, "yt": yt}), ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print("강사 이름 암호화 생략:", type(e).__name__)
    print(f"교사 생태계: {sum(1 for r in out if r['ok'])}/{len(out)} 서비스 · {round(time.time() - t0)}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
