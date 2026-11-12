// 배포별 미리보기 주소(<해시>.vs-insight.pages.dev, 브랜치 별칭 등)는 로그인 관문(Cloudflare Access) 밖이라 막는다.
// 대시보드는 로그인 관문이 걸린 본 주소(vs-insight.pages.dev)에서만 열린다.
export async function onRequest(context) {
  const host = new URL(context.request.url).hostname.toLowerCase();
  if (host.endsWith('.pages.dev') && host.split('.').length > 3) {
    return new Response('Not found', {status: 404, headers: {'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex', 'Content-Type': 'text/plain; charset=utf-8'}});
  }
  return context.next();
}
