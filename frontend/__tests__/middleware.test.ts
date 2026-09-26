/**
 * @jest-environment node
 */
// AG1: the Next server adds its own API token to the /api requests it proxies, so the
// iPad never holds one. NextResponse.next({ request: { headers } }) hands the rewritten
// headers to the rewrite through x-middleware-request-* response headers.
import { NextRequest } from 'next/server'

import { config, middleware, withProxyToken } from '@/middleware'

const ORIGINAL = process.env.KYOKKI_PROXY_TOKEN

afterEach(() => {
  if (ORIGINAL === undefined) delete process.env.KYOKKI_PROXY_TOKEN
  else process.env.KYOKKI_PROXY_TOKEN = ORIGINAL
})

function forwardedAuthorization(response: Response): string | null {
  return response.headers.get('x-middleware-request-authorization')
}

describe('withProxyToken', () => {
  it('adds the bearer token', () => {
    const headers = withProxyToken(new Headers({ accept: 'application/json' }), 'abc')
    expect(headers.get('authorization')).toBe('Bearer abc')
    expect(headers.get('accept')).toBe('application/json')
  })

  it('overwrites an authorization header sent by the browser', () => {
    const headers = withProxyToken(new Headers({ authorization: 'Bearer evil' }), 'abc')
    expect(headers.get('authorization')).toBe('Bearer abc')
  })

  it('leaves the headers unchanged without a token', () => {
    const incoming = new Headers({ accept: 'application/json' })
    const headers = withProxyToken(incoming, undefined)
    expect(headers.get('authorization')).toBeNull()
    expect(headers.get('accept')).toBe('application/json')
    expect(withProxyToken(incoming, '').get('authorization')).toBeNull()
  })

  it('does not modify the incoming headers object', () => {
    const incoming = new Headers({ authorization: 'Bearer evil' })
    withProxyToken(incoming, 'abc')
    expect(incoming.get('authorization')).toBe('Bearer evil')
  })
})

describe('middleware', () => {
  it('forwards the token read from the environment at request time', () => {
    process.env.KYOKKI_PROXY_TOKEN = 'first'
    const request = new NextRequest('http://localhost:3000/api/inventory', {
      headers: { authorization: 'Bearer from-browser' },
    })
    expect(forwardedAuthorization(middleware(request))).toBe('Bearer first')

    process.env.KYOKKI_PROXY_TOKEN = 'second'
    expect(forwardedAuthorization(middleware(request))).toBe('Bearer second')
  })

  it('adds no authorization when the token is unset', () => {
    delete process.env.KYOKKI_PROXY_TOKEN
    const request = new NextRequest('http://localhost:3000/api/inventory')
    const response = middleware(request)
    expect(forwardedAuthorization(response)).toBeNull()
  })

  it('keeps multipart uploads streaming: the body is not touched', () => {
    process.env.KYOKKI_PROXY_TOKEN = 'abc'
    const request = new NextRequest('http://localhost:3000/api/receipts/scan', {
      method: 'POST',
      headers: { 'content-type': 'multipart/form-data; boundary=x' },
      body: '--x--',
    })
    const response = middleware(request)
    expect(forwardedAuthorization(response)).toBe('Bearer abc')
    expect(response.headers.get('x-middleware-request-content-type')).toBe(
      'multipart/form-data; boundary=x'
    )
    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  it('runs only for /api', () => {
    expect(config.matcher).toEqual(['/api/:path*'])
  })
})
