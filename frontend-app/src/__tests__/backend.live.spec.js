/**
 * «Живые» сквозные тесты против НАСТОЯЩЕГО бэкенда FastAPI (не мок):
 *
 *   uvicorn app.main:app --port 8000      # бэкенд с bootstrap-админом
 *   python scripts/seed_demo.py           # демо-курсы, student (client), moder (moderator)
 *   npm run test:live
 *
 * Лаб. № 8: сессия живёт в httpOnly cookie — jsdom хранит их в своём cookie
 * jar и отправляет с withCredentials, как настоящий браузер.
 *
 * jsdom работает с origin http://localhost:5173 и проверяет CORS, как браузер.
 * Без LIVE_API=1 тесты пропускаются (CI бэкенд не поднимает).
 */
import { describe, it, expect, vi } from 'vitest'

const MODER = [
  process.env.LIVE_MODER || 'moder',
  process.env.LIVE_MODER_PASSWORD || 'Moder-passw0rd-1',
]
const STUDENT = [
  process.env.LIVE_USER || 'student',
  process.env.LIVE_PASSWORD || 'Student-passw0rd',
]

async function waitFor(check, timeout = 8000) {
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
  vi.resetModules()
  history.pushState({}, '', '/')
  document.body.innerHTML = ''
  localStorage.clear()
  // Новая «вкладка» без сессии. httpOnly-cookie прошлого теста из JS не
  // стереть (в этом и смысл) — просим сервер завершить сессию.
  const client = await import('@/api/client')
  await client.default.post('/auth/logout').catch(() => {})
  const { mount } = await import('@vue/test-utils')
  const { createPinia } = await import('pinia')
  const { default: App } = await import('@/App.vue')
  const { default: router } = await import('@/router')
  const { useToast } = await import('@/composables/useToast')
  const wrapper = mount(App, {
    global: { plugins: [createPinia(), router] },
    attachTo: document.body,
  })
  await router.push(path)
  return { wrapper, router, toasts: () => useToast().toasts.value }
}

async function logIn({ wrapper, router }, [user, pass]) {
  // Первый переход ждёт GET /auth/me (восстановление сессии) — форма появится после.
  await waitFor(() => wrapper.find('input#username').exists())
  await wrapper.find('input#username').setValue(user)
  await wrapper.find('input#password').setValue(pass)
  await wrapper.find('form').trigger('submit')
  await waitFor(() => router.currentRoute.value.name !== 'login')
}
const button = (wrapper, text) => wrapper.findAll('button').find((b) => b.text().includes(text))
async function fillCourse(wrapper, values) {
  for (const [field, value] of Object.entries(values)) {
    await waitFor(() => wrapper.find(`#${field}`).exists())
    await wrapper.find(`#${field}`).setValue(String(value))
  }
}

describe.skipIf(!process.env.LIVE_API)('живой бэкенд FastAPI', { timeout: 30000 }, () => {
  it('неверный пароль → сообщение формы', async () => {
    const app = await boot('/login')
    await waitFor(() => app.wrapper.find('input#username').exists())
    await app.wrapper.find('input#username').setValue(STUDENT[0])
    await app.wrapper.find('input#password').setValue('Wrong-passw0rd')
    await app.wrapper.find('form').trigger('submit')
    await waitFor(() => app.wrapper.find('.error').exists())
    expect(app.wrapper.find('.error').text()).toBe('Неверный логин или пароль')
  })

  it('CRUD: создание → 422 → детали → редактирование → удаление', async () => {
    const app = await boot('/login')
    await logIn(app, MODER)
    await waitFor(() => app.wrapper.findAll('.course-card').length > 0)
    const title = `Live-курс ${Date.now()}`

    // Создание: сначала 3000 часов — сервер вернёт 422 (le=1000).
    await app.router.push('/courses/create')
    await fillCourse(app.wrapper, {
      title,
      description: 'создан тестом',
      instructor: 'Тестов',
      duration_hours: 3000,
    })
    await app.wrapper.find('form').trigger('submit')
    await waitFor(() => app.wrapper.text().includes('Значение должно быть не больше 1000'))
    expect(app.router.currentRoute.value.name).toBe('course-create')

    await fillCourse(app.wrapper, { duration_hours: 10 })
    await app.wrapper.find('form').trigger('submit')
    await waitFor(() => app.router.currentRoute.value.name === 'course-detail')
    const id = app.router.currentRoute.value.params.id
    await waitFor(() => app.wrapper.text().includes(title))
    expect(app.toasts().at(-1).message).toBe(`Курс «${title}» создан`)

    // Редактирование (PUT).
    await button(app.wrapper, 'Редактировать').trigger('click')
    await waitFor(() => app.wrapper.find('#title').exists())
    expect(app.wrapper.find('#title').element.value).toBe(title)
    await fillCourse(app.wrapper, { title: `${title} (изм.)`, duration_hours: 12 })
    await app.wrapper.find('form').trigger('submit')
    await waitFor(
      () => app.wrapper.text().includes(`${title} (изм.)`) && app.wrapper.text().includes('12 ч'),
    )
    expect(app.toasts().at(-1).message).toBe('Изменения сохранены')

    // Удаление через модалку.
    await button(app.wrapper, 'Удалить').trigger('click')
    await waitFor(() => document.body.querySelector('[role="dialog"]'))
    ;[...document.body.querySelectorAll('[role="dialog"] button')]
      .find((b) => b.textContent.includes('Да, удалить'))
      .click()
    await waitFor(() => app.router.currentRoute.value.name === 'home')
    expect(app.toasts().at(-1).message).toBe(`Курс «${title} (изм.)» удалён`)

    // Детали удалённого курса — «Запись не найдена» (реальный 404 от API).
    await app.router.push(`/courses/${id}`)
    await waitFor(() => app.wrapper.text().includes('Запись не найдена'))
  })

  it('студент (client) видит курсы без 18+, не может их менять; прямой POST → 403', async () => {
    const app = await boot('/login')
    await logIn(app, STUDENT)
    await waitFor(() => app.wrapper.findAll('.course-card').length > 0)
    expect(button(app.wrapper, 'Добавить')).toBeUndefined()
    await waitFor(() => app.wrapper.find('.age-banner').exists())
    expect(app.wrapper.find('.age-banner').text()).toContain('Скрыто курсов 18+')
    await app.router.push('/courses/create')
    await waitFor(() => app.router.currentRoute.value.name === 'home')
    // Обход интерфейса: запрос напрямую, с cookie сессии и CSRF-токеном.
    const { default: apiClient } = await import('@/api/client')
    const err = await apiClient
      .post('/courses', { title: 'x', description: 'y', instructor: 'z', duration_hours: 1 })
      .catch((e) => e)
    expect(err.response.status).toBe(403)
    expect(err.response.data.detail).toBe('Insufficient permissions')
  })

  it('после выхода cookie очищены и /auth/me → 401', async () => {
    const app = await boot('/login')
    await logIn(app, STUDENT)
    const { default: apiClient } = await import('@/api/client')
    expect((await apiClient.get('/auth/me')).status).toBe(200)
    expect(document.cookie).not.toContain('access_token') // httpOnly — JS её не видит
    expect(document.cookie).toContain('csrf_token')
    await app.wrapper.find('.user-menu .trigger').trigger('click')
    await button(app.wrapper, 'Выйти').trigger('click')
    await waitFor(() => app.router.currentRoute.value.name === 'login')
    const err = await apiClient.get('/auth/me').catch((e) => e)
    expect(err.response.status).toBe(401)
  })
})
