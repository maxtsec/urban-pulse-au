import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    {
      name: 'static-csp',
      apply: 'build',
      transformIndexHtml: {
        order: 'post',
        handler: () => [
          {
            tag: 'meta',
            attrs: {
              'http-equiv': 'Content-Security-Policy',
              content:
                "default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-src 'none'",
            },
            injectTo: 'head-prepend',
          },
        ],
      },
    },
  ],
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
