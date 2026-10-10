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
# Cloudflare 주소의 첫 화면을 메인 대시보드(/full/)로: 첫 화면(/)만 /full/ 로 넘긴다
printf '/ /full/ 302\n' > "$DIR/_redirects"
npx --yes wrangler@3 pages deploy "$DIR" --project-name="$PROJECT" --branch=main --commit-dirty=true 2>&1 \
  | grep -v -i "token" | tail -5
echo "Cloudflare Pages: https://$PROJECT.pages.dev"
