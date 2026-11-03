/**
 * «Живой» сквозной тест против НАСТОЯЩЕГО бэкенда (не мок):
 *
 *   uvicorn app.main:app --port 8000      # бэкенд (с bootstrap-админом)
 *   python scripts/seed_demo.py           # демо-курсы и пользователь student
 *   npm run test:live
 *
 * jsdom работает с origin http://localhost:5173 и выполняет запросы через
 * XMLHttpRequest с проверками CORS, как браузер: без CORS на бэкенде тест упадёт.
 * Без LIVE_API=1 тест пропускается (CI бэкенд не поднимает).
 */
import { describe, it, expect } from 'vitest'

const API = process.env.VITE_API_BASE_URL || 'http://localhost:8000'
const USER = process.env.LIVE_USER || 'student'
const PASSWORD = process.env.LIVE_PASSWORD || 'Student-passw0rd'

async function waitFor(check, timeout = 5000) {
  const start = Date.now()
  for (;;) {
    try {
      if (await check()) return
    } catch {
      /* повторяем */
    }
    if (Date.now() - start > timeout) throw new Error('waitFor: условие не выполнено')
    await new Promise((r) => setTimeout(r, 50))
  }
}

async function boot(path) {
  const { vi } = await import('vitest')
  vi.resetModules()
  history.pushState({}, '', '/')
  const { mount } = await import('@vue/test-utils')
  const { createPinia } = await import('pinia')
  const { default: App } = await import('@/App.vue')
  const { default: router } = await import('@/router')
  const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
  await router.push(path)
  return { wrapper, router }
}

describe.skipIf(!process.env.LIVE_API)('живой бэкенд FastAPI', { timeout: 20000 }, () => {
  it('страница загружена с origin dev-сервера Vite', () => {
    expect(window.location.origin).toBe('http://localhost:5173')
  })

  it('неверный пароль → сообщение формы, токен не сохранён', async () => {
    localStorage.clear()
    const { wrapper } = await boot('/login')
    await wrapper.find('input#username').setValue(USER)
    await wrapper.find('input#password').setValue('Wrong-passw0rd')
    await wrapper.find('form').trigger('submit')

    await waitFor(() => wrapper.find('.error').exists())
    expect(wrapper.find('.error').text()).toBe('Invalid username or password')
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('login → JWT → список курсов из БД → logout', async () => {
    localStorage.clear()
    const { wrapper, router } = await boot('/')
    expect(router.currentRoute.value.name).toBe('login') // guard

    await wrapper.find('input#username').setValue(USER)
    await wrapper.find('input#password').setValue(PASSWORD)
    await wrapper.find('form').trigger('submit')

    await waitFor(() => wrapper.findAll('.item-card').length > 0)
    expect(router.currentRoute.value.name).toBe('home')
    expect(localStorage.getItem('access_token')?.split('.')).toHaveLength(3) // настоящий JWT
    const titles = wrapper.findAll('.item-card h3').map((h) => h.text())
    expect(titles.length).toBeGreaterThan(0)
    console.info('курсы из БД:', titles.join(' | '))

    await wrapper.find('nav button').trigger('click')
    await waitFor(() => router.currentRoute.value.name === 'login')
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('данные действительно из БД: новый курс виден после обновления страницы', async () => {
    // Создаём курс напрямую через API под администратором (как в Swagger).
    const form = new URLSearchParams({
      username: process.env.LIVE_ADMIN || 'admin',
      password: process.env.LIVE_ADMIN_PASSWORD || 'ChangeMe-Admin-2026',
    })
    const tokenResp = await fetch(`${API}/auth/token`, { method: 'POST', body: form })
    const { access_token: adminToken } = await tokenResp.json()
    const title = `Live-курс ${Date.now()}`
    const created = await fetch(`${API}/courses`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        description: 'создан тестом',
        instructor: 'Тест',
        duration_hours: 1,
      }),
    })
    expect(created.status).toBe(201)

    // «Обновление страницы» под обычным пользователем.
    localStorage.clear()
    const { wrapper } = await boot('/login')
    await wrapper.find('input#username').setValue(USER)
    await wrapper.find('input#password').setValue(PASSWORD)
    await wrapper.find('form').trigger('submit')
    await waitFor(() => wrapper.text().includes(title))
    expect(wrapper.text()).toContain(title)
  })
})
