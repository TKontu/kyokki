// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom'

// Polyfills for test environment
import { TextEncoder, TextDecoder } from 'util'
import 'whatwg-fetch'

global.TextEncoder = TextEncoder
global.TextDecoder = TextDecoder
