#!/usr/bin/env python3
"""
시군구 경계(통계청 2018, southkorea-maps 공개본) -> 대시보드용 경량 지도 static_data/sigungu_geo.json
'지역 총판' 탭의 입체 지도(총판 담당 구역·지사 위치·AI 중점·선도학교 막대)에 쓴다.
  python sigungu_geo.py <skorea-municipalities-2018-geo.json>
좌표는 화면 평면(경도 x cos36°, 위도 반전)으로 투영한 정수(1단위 ≈ 0.6km), 더글러스-포커 단순화.
"""
import json
import math
import sys
from pathlib import Path

SIDO_CODE = {"11": "서울", "21": "부산", "22": "대구", "23": "인천", "24": "광주", "25": "대전", "26": "울산", "29": "세종",
             "31": "경기", "32": "강원", "33": "충북", "34": "충남", "35": "전북", "36": "전남", "37": "경북", "38": "경남", "39": "제주"}
K, LON0, LAT0, COS = 180.0, 124.5, 38.7, math.cos(math.radians(36))
TOL = 0.9  # 단순화 허용 오차(투영 단위)


def proj(lon, lat):
    return ((lon - LON0) * COS * K, (LAT0 - lat) * K)


def _dp(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1e-9
        best, bi = -1, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / L
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def _simplify(ring, tol):
    """닫힌 고리는 시작점에서 가장 먼 점으로 둘로 나눠 단순화(시작=끝이면 기준선 길이가 0이 되므로)."""
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    if far in (0, len(ring) - 1):
        return ring
    return _dp(ring[:far + 1], tol)[:-1] + _dp(ring[far:], tol)


def _area(r):
    return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2


def main():
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    feats = []
    for f in src["features"]:
        pr = f["properties"]
        code = str(pr.get("code") or pr.get("SIG_CD"))
        sd = SIDO_CODE.get(code[:2])
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings, big = [], (0, None)
        for poly in polys:
            ring = [proj(*p[:2]) for p in poly[0]]
            a = _area(ring)
            if a > big[0]:
                big = (a, ring)
            if a < 2:  # 아주 작은 섬은 생략(시군구 대표 고리는 아래에서 보존)
                continue
            s = _simplify(ring, TOL)
            if len(s) >= 4:
                rings.append(s)
        if not rings and big[1]:
            s = _simplify(big[1], TOL / 4)
            rings.append(s if len(s) >= 4 else big[1])
        # 중심점: 가장 큰 고리의 면적 가중 무게중심
        main_r = max(rings, key=_area)
        A = cx = cy = 0.0
        for i in range(len(main_r)):
            (x0, y0), (x1, y1) = main_r[i - 1], main_r[i]
            c = x0 * y1 - x1 * y0
            A += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
        cx, cy = (cx / (3 * A), cy / (3 * A)) if A else main_r[0]
        feats.append({"c": code, "sd": sd, "n": pr.get("name") or pr.get("SIG_KOR_NM"),
                      "xy": [round(cx), round(cy)],
                      "r": [[v for p in r for v in (round(p[0]), round(p[1]))] for r in rings]})
    out = {"source": "통계청 2018 시군구 경계(southkorea-maps 공개본) - 단순화", "proj": {"k": K, "lon0": LON0, "lat0": LAT0, "cos": round(COS, 5)},
           "features": feats}
    p = Path(__file__).parent / "static_data/sigungu_geo.json"
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"시군구 {len(feats)}개 · 점 {sum(len(r) // 2 for f in feats for r in f['r'])}개 · {p.stat().st_size // 1024}KB -> {p}")


if __name__ == "__main__":
    main()
