# 뉴스 공개 JSON (영업용 앱 연동)

조간 브리핑(`briefings/*.json`)을 외부 앱이 `fetch`로 바로 쓸 수 있게 평문 JSON으로 내보낸다.
매일 06:00 KST 대시보드 배포와, 브리핑이 새로 올라올 때(`news.yml`) 함께 갱신된다.

| 주소 | 내용 |
|---|---|
| `https://choiys2.github.io/g2b-education-dashboard/api/news/latest.json` | 최신 1개 호 전체 + 신선도 메타 |
| `https://choiys2.github.io/g2b-education-dashboard/api/news/index.json` | 전체 호 목록(최신순) |
| `https://choiys2.github.io/g2b-education-dashboard/api/news/YYYY-MM-DD.json` | 해당 날짜 호 |

## latest.json
```json
{
  "generated_at": "2026-09-28T16:20+09:00",
  "latest_date": "2026-09-06",
  "age_days": 22,
  "stale": true,                     // 3일 넘게 새 호가 없으면 true → 위젯에 '발행 중단' 표시 권장
  "tag_list": ["예산","AI·디지털","교원연수","정책","교권·생활지도","고교학점제·평가","늘봄·돌봄","경쟁사","자사"],
  "issue": {
    "date": "2026-09-06", "issue_no": 21, "url": ".../news/2026-09-06.html",
    "lead": { "kicker": "...", "headline": "...", "sub": "...", "summary": "...",
              "facts": [{"label": "...", "text": "..."}], "tags": ["예산","정책"] },
    "sections": [{ "id": "education", "name": "교육",
                   "items": [{"title": "...", "summary": "...", "tags": ["..."], "priority": true}] }],
    "implications": [{ "news": "...", "sales_point": "영업에 주는 시사점", "tags": ["..."] }],
    "indices": [{"label": "코스피", "value": "...", "delta": "...", "dir": "up"}],
    "sources": "..."
  }
}
```
- 모든 문자열은 HTML 태그를 제거한 평문이다(그대로 화면에 넣어도 안전).
- `sales_point`는 브리핑의 '비바샘 시사점'으로, 영업 토킹포인트로 쓰기에 가장 적합한 필드다.

## CORS
GitHub Pages는 `Access-Control-Allow-Origin: *`를 보내므로 브라우저에서 직접 `fetch` 가능하다.
막히는 환경이면 Netlify 앱의 `netlify.toml`에 프록시를 두고 같은 도메인으로 부른다.

```toml
[[redirects]]
  from = "/api/news/*"
  to = "https://choiys2.github.io/g2b-education-dashboard/api/news/:splat"
  status = 200
```
→ 앱에서는 `fetch("/api/news/latest.json")`
