import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      'meshoptimizer/decoder': fileURLToPath(
        new URL('./src/explorer/meshopt-disabled.ts', import.meta.url),
      ),
    },
  },
  build: {
    assetsInlineLimit: 0,
    ...(mode === 'test'
      ? {
          outDir: 'dist-test',
          rolldownOptions: { input: ['index.html', 'tests/scenario.html'] },
        }
      : {}),
  },
  server: {
    strictPort: true,
    proxy: {
      '/api': process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000',
      '/health': process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000',
    },
  },
}));
