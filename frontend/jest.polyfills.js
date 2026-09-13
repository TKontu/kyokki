/**
 * Globals that msw v2 needs but jsdom does not provide.
 * Loaded through `setupFiles`, before the test framework and before any test imports msw.
 * Recipe: https://mswjs.io/docs/migrations/1.x-to-2.x#requestresponsetextencoder-is-not-defined-jest
 * Uses require() so these assignments run before undici is evaluated.
 */
const { TextDecoder, TextEncoder } = require('node:util')
const { ReadableStream, TransformStream, WritableStream } = require('node:stream/web')
const { BroadcastChannel, MessageChannel, MessagePort } = require('node:worker_threads')
const { clearImmediate, setImmediate } = require('node:timers')
const { performance } = require('node:perf_hooks')
const { Blob, File } = require('node:buffer')

Object.defineProperties(globalThis, {
  TextDecoder: { value: TextDecoder, configurable: true, writable: true },
  TextEncoder: { value: TextEncoder, configurable: true, writable: true },
  ReadableStream: { value: ReadableStream, configurable: true, writable: true },
  TransformStream: { value: TransformStream, configurable: true, writable: true },
  WritableStream: { value: WritableStream, configurable: true, writable: true },
  BroadcastChannel: { value: BroadcastChannel, configurable: true, writable: true },
  MessageChannel: { value: MessageChannel, configurable: true, writable: true },
  MessagePort: { value: MessagePort, configurable: true, writable: true },
  setImmediate: { value: setImmediate, configurable: true, writable: true },
  clearImmediate: { value: clearImmediate, configurable: true, writable: true },
  performance: { value: performance, configurable: true, writable: true },
  Blob: { value: Blob, configurable: true, writable: true },
  File: { value: File, configurable: true, writable: true },
})

const { fetch, Headers, FormData, Request, Response } = require('undici')

Object.defineProperties(globalThis, {
  fetch: { value: fetch, configurable: true, writable: true },
  Headers: { value: Headers, configurable: true, writable: true },
  FormData: { value: FormData, configurable: true, writable: true },
  Request: { value: Request, configurable: true, writable: true },
  Response: { value: Response, configurable: true, writable: true },
})
