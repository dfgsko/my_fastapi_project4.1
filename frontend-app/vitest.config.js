import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config.js'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // Тот же origin, что у dev-сервера Vite: в «живом» тесте jsdom выполняет
      // CORS-проверки как браузер, и бэкенд должен разрешать именно этот origin.
      environmentOptions: { jsdom: { url: 'http://localhost:5173/' } },
      exclude: [...configDefaults.exclude, 'e2e/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
