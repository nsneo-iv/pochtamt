import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Конфигурация сборки фронтенда панели администрирования.
// В dev-режиме все запросы к /api проксируются на локальный бэкенд (FastAPI на 8000 порту).
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Готовую сборку отдаёт nginx из каталога frontend/dist
    outDir: 'dist',
    emptyOutDir: true,
  },
})
