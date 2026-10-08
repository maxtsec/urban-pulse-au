import { defineConfig } from '@playwright/test';
import local from './playwright.config';

const baseURL = process.env.URBANPULSE_SERVING_URL;
if (!baseURL || new URL(baseURL).hostname !== '127.0.0.1') {
  throw new Error(
    'URBANPULSE_SERVING_URL must identify the isolated loopback server',
  );
}

export default defineConfig({
  ...local,
  testDir: '.',
  testMatch: ['tests/explorer.spec.ts', 'tests-serving/**/*.spec.ts'],
  outputDir: 'test-results/serving',
  use: { ...local.use, baseURL },
  webServer: undefined,
});
