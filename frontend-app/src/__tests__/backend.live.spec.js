/**
 * «Живые» сквозные тесты против НАСТОЯЩЕГО бэкенда FastAPI (не мок):
 *
 *   uvicorn app.main:app --port 8000      # бэкенд с bootstrap-админом
 *   python scripts/seed_demo.py           # демо-курсы и пользователь student
 *   npm run test:live
 *
 * jsdom работает с origin http://localhost:5173 и проверяет CORS, как браузер.
 * Без LIVE_API=1 тесты пропускаются (CI бэкенд не поднимает).
 */
import { describe, it, expect, vi } from 'vitest'

const ADMIN = [
  process.env.LIVE_ADMIN || 'admin',
  process.env.LIVE_ADMIN_PASSWORD || 'ChangeMe-Admin-2026',
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
    await app.wrapper.find('input#username').setValue(STUDENT[0])
    await app.wrapper.find('input#password').setValue('Wrong-passw0rd')
    await app.wrapper.find('form').trigger('submit')
    await waitFor(() => app.wrapper.find('.error').exists())
    expect(app.wrapper.find('.error').text()).toBe('Invalid username or password')
  })

  it('CRUD: создание → 422 → детали → редактирование → удаление', async () => {
    const app = await boot('/')
    await logIn(app, ADMIN)
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

  it('студент видит курсы, но не может их менять', async () => {
    const app = await boot('/')
    await logIn(app, STUDENT)
    await waitFor(() => app.wrapper.findAll('.course-card').length > 0)
    expect(button(app.wrapper, 'Добавить')).toBeUndefined()
    await app.router.push('/courses/create')
    await waitFor(() => app.router.currentRoute.value.name === 'home')
  })
})
