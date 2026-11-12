#!/usr/bin/env bash
# Cloudflare Pages 배포(로그인 관문 Cloudflare Access 뒤에 둘 사본).
# 시크릿 CLOUDFLARE_API_TOKEN · CLOUDFLARE_ACCOUNT_ID 가 없으면 아무것도 하지 않는다(기존 GitHub Pages 배포는 그대로).
# 프로젝트 이름은 저장소 변수 CF_PAGES_PROJECT(없으면 기본값). 토큰 값은 출력하지 않는다.
set -u -o pipefail
DIR="${1:-_site}"
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "Cloudflare 시크릿 없음 - Cloudflare Pages 배포 건너뜀"
  exit 0
fi
PROJECT="${CF_PAGES_PROJECT:-vs-insight}"
# 프로젝트가 없으면 만든다(이미 있으면 오류 무시)
npx --yes wrangler@3 pages project create "$PROJECT" --production-branch=main >/dev/null 2>&1 || true
# Cloudflare 주소의 첫 화면을 메인 대시보드(/full/)로: 첫 화면(/)만 /full/ 로 넘기고,
# 원래 첫 화면이던 나라장터 요약은 /summary/ 에서 연다
if [ -f "$DIR/index.html" ]; then mkdir -p "$DIR/summary" && cp "$DIR/index.html" "$DIR/summary/index.html"; fi
printf '/ /full/ 302\n' > "$DIR/_redirects"
npx --yes wrangler@3 pages deploy "$DIR" --project-name="$PROJECT" --branch=main --commit-dirty=true 2>&1 \
  | grep -v -i "token" | tail -5 > /tmp/cf_deploy.txt
# 미리보기 주소는 공개 로그에 남기지 않는다(해시 부분 가림)
sed -E 's#https://[a-z0-9]+\.([a-z0-9-]+)\.pages\.dev#https://********.\1.pages.dev#g' /tmp/cf_deploy.txt
echo "Cloudflare Pages: https://$PROJECT.pages.dev"
# 보안 실측: 로그인 없이 열면 Cloudflare Access 로그인으로 넘어가야 한다(본 주소·배포별 미리보기 주소 모두)
probe() {
  local u="$1" kind="${2:-main}" code loc
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$u" || echo 000)
  loc=$(curl -s -o /dev/null -w "%{redirect_url}" --max-time 15 "$u" || true)
  if [[ "$loc" == *cloudflareaccess.com* ]] || [ "$code" = "401" ] || [ "$code" = "403" ] || { [ "$kind" = "preview" ] && [ "$code" = "404" ]; }; then
    echo "Access 보호: 정상 ($code · $kind)"
  else
    echo "::warning::Access 보호 미적용으로 보임($code) - 로그인 없이 열리는 주소가 있습니다(페이지 암호는 유지). Cloudflare Zero Trust > Access 앱에 *.$PROJECT.pages.dev 를 추가하세요"
    echo "Access 보호: 미적용 ($code)"
  fi
}
probe "https://$PROJECT.pages.dev/full/"
PREV=$(grep -o -E "https://[a-z0-9]+\.$PROJECT\.pages\.dev" /tmp/cf_deploy.txt | head -1)
if [ -n "$PREV" ]; then probe "$PREV/full/" preview; probe "$PREV/full/report.pdf" preview; fi
