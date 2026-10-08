import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const python = resolve(
  root,
  process.platform === 'win32'
    ? '.venv/Scripts/python.exe'
    : '.venv/bin/python',
);

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    viewport: { width: 1440, height: 1100 },
    reducedMotion: 'reduce',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: { args: ['--enable-unsafe-swiftshader'] },
  },
  webServer: [
    {
      command: `"${python}" -m urbanpulse.adapters.city_store migrate && "${python}" -m urbanpulse.adapters.city_store import && "${python}" -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8011`,
      cwd: root,
      url: 'http://127.0.0.1:8011/health/live',
      env: {
        URBANPULSE_MODE: 'fixture',
        RAW_STORAGE_PATH: '.local/raw/city-e2e',
        DATABASE_URL:
          process.env.URBANPULSE_TEST_DATABASE_URL ??
          'postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse',
      },
      reuseExistingServer: false,
    },
    {
      command:
        'npm run build:test && npm run preview -- --outDir dist-test --port 5174',
      url: 'http://127.0.0.1:5174',
      env: { VITE_API_PROXY: 'http://127.0.0.1:8011' },
      reuseExistingServer: false,
    },
  ],
});
