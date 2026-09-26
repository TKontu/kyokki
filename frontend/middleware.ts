// AG1: the iPad never holds an API token. Every browser request to /api/* passes through
// here on the Next server, which sets its own token before the next.config.mjs rewrite
// proxies the request to the backend.
//
// KYOKKI_PROXY_TOKEN is a runtime environment variable of the frontend container (never
// NEXT_PUBLIC_, never a build arg): it is read on every request, so the prebuilt image
// needs no rebuild when the token changes, and it never reaches the browser bundle.
import { NextResponse, type NextRequest } from 'next/server'

/** Headers to forward: the proxy token replaces any Authorization from the browser. */
export function withProxyToken(incoming: Headers, token: string | undefined): Headers {
  const headers = new Headers(incoming)
  if (token) {
    headers.set('authorization', `Bearer ${token}`)
  }
  return headers
}

export function middleware(request: NextRequest): NextResponse {
  const token = process.env.KYOKKI_PROXY_TOKEN
  if (!token) {
    // No token configured: forward the request exactly as before AG1.
    return NextResponse.next()
  }
  return NextResponse.next({
    request: { headers: withProxyToken(request.headers, token) },
  })
}

export const config = {
  matcher: ['/api/:path*'],
}
