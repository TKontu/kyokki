const nextJest = require('next/jest')

/** @type {import('jest').Config} */
const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files in your test environment
  dir: './',
})

// Add any custom config to be passed to Jest
const config = {
  coverageProvider: 'v8',
  testEnvironment: 'jsdom',
  // Room for the 5 s asyncUtilTimeout set in jest.setup.js: a waitFor that runs out should fail
  // with its own "unable to find ..." message, not with jest's unhelpful test timeout (H06).
  testTimeout: 20000,
  // msw v2 resolves its Node build only with the default export condition
  testEnvironmentOptions: {
    customExportConditions: [''],
  },
  // Fetch API, streams and TextEncoder globals for msw (must run before test imports)
  setupFiles: ['<rootDir>/jest.polyfills.js'],
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
  },
  testMatch: [
    '**/__tests__/**/*.[jt]s?(x)',
    '**/?(*.)+(spec|test).[jt]s?(x)',
  ],
  collectCoverageFrom: [
    'app/**/*.{js,jsx,ts,tsx}',
    'components/**/*.{js,jsx,ts,tsx}',
    'lib/**/*.{js,jsx,ts,tsx}',
    'hooks/**/*.{js,jsx,ts,tsx}',
    '!**/*.d.ts',
    '!**/node_modules/**',
    '!**/__tests__/**',
  ],
}

// ESM-only packages pulled in by msw that Jest must transform. next/jest sets its own
// transformIgnorePatterns, so they are adjusted after it resolves the config.
const esmPackages = ['until-async']

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = async () => {
  const resolved = await createJestConfig(config)()
  return {
    ...resolved,
    transformIgnorePatterns: resolved.transformIgnorePatterns.map((pattern) =>
      pattern === '/node_modules/'
        ? `/node_modules/(?!(${esmPackages.join('|')})/)`
        : pattern
    ),
  }
}
