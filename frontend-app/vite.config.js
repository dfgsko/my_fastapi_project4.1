import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  // NO_DEVTOOLS=1 — без плавающей панели Vue DevTools (для скриншотов).
  plugins: [vue(), !process.env.NO_DEVTOOLS && vueDevTools()].filter(Boolean),
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: 'localhost',
    port: 5173,
    // Порт 5173 прописан в CORS бэкенда. Если он занят, Vite по умолчанию
    // молча выберет 5174 — и браузер заблокирует все запросы к API.
    strictPort: true,
  },
})
