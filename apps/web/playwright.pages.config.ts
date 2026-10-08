import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests-pages',
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: 'http://127.0.0.1:5182/urban-pulse-au/',
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
    launchOptions: { args: ['--enable-unsafe-swiftshader'] },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run preview -- --port 5182 --base=/urban-pulse-au/',
    url: 'http://127.0.0.1:5182/urban-pulse-au/',
    reuseExistingServer: false,
  },
});
