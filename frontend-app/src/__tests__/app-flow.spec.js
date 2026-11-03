/**
 * Сквозные сценарии в jsdom: настоящие App, Vue Router, Pinia, Axios-
 * перехватчики, экраны и компоненты. Подменён только транспорт Axios —
 * «фейковый бэкенд» с состоянием повторяет контракт FastAPI: form-urlencoded
 * на /auth/token, JWT на остальных, роли, 404, 422 в формате Pydantic v2.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const ADMIN_TOKEN = 'admin.jwt.token'
const USER_TOKEN = 'user.jwt.token'
const SEED = [
  {
    id: 1,
    title: 'Kubernetes',
    description: 'Оркестрация',
    instructor: 'Иванов',
    duration_hours: 16,
  },
  { id: 2, title: 'FastAPI', description: 'REST API', instructor: 'Петров', duration_hours: 12 },
]

let requests
let db
function fakeBackend(apiClient, { courses = SEED } = {}) {
  requests = []
  db = { courses: structuredClone(courses), nextId: 100 }
  apiClient.defaults.adapter = async (config) => {
    requests.push(config)
    const reply = (status, data) => {
      const response = { data, status, statusText: String(status), headers: {}, config }
      if (status >= 400) {
        const error = new Error(`status ${status}`)
        error.isAxiosError = true
        error.config = config
        error.response = response
        throw error
      }
      return response
    }
    const { url, method } = config
    if (url === '/auth/token') {
      const body = new URLSearchParams(config.data)
      const users = {
        admin: ['secret-pass-1', ADMIN_TOKEN],
        student: ['student-pass-1', USER_TOKEN],
      }
      const u = users[body.get('username')]
      return u && u[0] === body.get('password')
        ? reply(200, { access_token: u[1], token_type: 'bearer' })
        : reply(401, { detail: 'Incorrect username or password' })
    }
    const auth = config.headers.Authorization
    const role =
      auth === `Bearer ${ADMIN_TOKEN}` ? 'admin' : auth === `Bearer ${USER_TOKEN}` ? 'user' : null
    if (!role) return reply(401, { detail: 'Could not validate credentials' })
    if (url === '/auth/me')
      return reply(200, { username: role === 'admin' ? 'admin' : 'student', role })

    const match = url.match(/^\/courses(?:\/(\d+))?$/)
    if (!match) return reply(404, {})
    const id = match[1] && Number(match[1])
    const found = db.courses.find((c) => c.id === id)
    if (method === 'get' && !id) {
      const q = config.params?.instructor?.toLowerCase()
      return reply(
        200,
        q ? db.courses.filter((c) => c.instructor.toLowerCase().includes(q)) : db.courses,
      )
    }
    if (method === 'get')
      return found ? reply(200, found) : reply(404, { detail: 'Курс не найден' })
    if (role !== 'admin') return reply(403, { detail: 'Admin privileges required' })

    if (method === 'post' || method === 'put') {
      const body = JSON.parse(config.data)
      const errors = []
      if ('id' in body)
        errors.push({
          type: 'extra_forbidden',
          loc: ['body', 'id'],
          msg: 'Extra inputs are not permitted',
        })
      if (body.duration_hours > 1000)
        errors.push({
          type: 'less_than_equal',
          loc: ['body', 'duration_hours'],
          msg: '...',
          ctx: { le: 1000 },
        })
      if (errors.length) return reply(422, { detail: errors })
      if (method === 'post') {
        const created = { id: db.nextId++, ...body }
        db.courses.push(created)
        return reply(201, created)
      }
      if (!found) return reply(404, { detail: 'Курс не найден' })
      Object.assign(found, body)
      return reply(200, found)
    }
    if (method === 'delete') {
      if (!found) return reply(404, { detail: 'Курс не найден' })
      db.courses = db.courses.filter((c) => c.id !== id)
      return reply(204, null)
    }
    return reply(405, {})
  }
}

/** «Загрузка страницы»: свежий граф модулей, как при обновлении вкладки. */
async function boot(path = '/', { backend } = {}) {
  vi.resetModules()
  history.pushState({}, '', '/')
  document.body.innerHTML = ''
  const { mount, flushPromises } = await import('@vue/test-utils')
  const { createPinia } = await import('pinia')
  const { default: App } = await import('@/App.vue')
  const { default: router } = await import('@/router')
  const client = await import('@/api/client')
  const { useToast } = await import('@/composables/useToast')
  vi.spyOn(client.navigation, 'toLogin').mockImplementation(() => {})

  fakeBackend(client.default, backend)
  const wrapper = mount(App, {
    global: { plugins: [createPinia(), router] },
    attachTo: document.body,
  })
  await router.push(path)
  await flushPromises()
  // Ждём, пока стихнут промисы и загрузятся ленивые чанки маршрутов.
  const settle = async () => {
    for (let i = 0; i < 10; i++) {
      await flushPromises()
      await new Promise((r) => setTimeout(r, 10))
    }
  }
  return { wrapper, router, flushPromises, settle, toasts: () => useToast().toasts.value }
}

async function logIn(app, user = 'admin', pass = 'secret-pass-1') {
  await app.wrapper.find('input#username').setValue(user)
  await app.wrapper.find('input#password').setValue(pass)
  await app.wrapper.find('form').trigger('submit')
  await app.settle()
}
const buttonByText = (wrapper, text) =>
  wrapper.findAll('button').find((b) => b.text().includes(text))
const modalButton = (text) =>
  [...document.body.querySelectorAll('[role="dialog"] button')].find((b) =>
    b.textContent.includes(text),
  )

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

describe('лаб. № 6: login → список → logout', () => {
  it('открытие / без входа ведёт на /login', async () => {
    const { wrapper, router } = await boot('/')
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.find('nav').text()).toContain('Login')
    expect(requests).toHaveLength(0)
  })

  it('неверный пароль: сообщение, токена нет', async () => {
    const app = await boot('/login')
    await logIn(app, 'admin', 'wrong')
    expect(app.wrapper.find('.error').text()).toBe('Invalid username or password')
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('верный пароль: список курсов, роль в шапке, запросы с JWT', async () => {
    const app = await boot('/login')
    await logIn(app)
    expect(app.router.currentRoute.value.name).toBe('home')
    expect(app.wrapper.findAll('.course-card')).toHaveLength(2)
    expect(app.wrapper.find('nav').text()).toContain('admin')
    const list = requests.find((r) => r.url === '/courses')
    expect(list.headers.Authorization).toBe(`Bearer ${ADMIN_TOKEN}`)
  })

  it('после перезагрузки страницы пользователь остаётся авторизованным, роль восстановлена', async () => {
    const first = await boot('/login')
    await logIn(first)
    first.wrapper.unmount()
    const second = await boot('/')
    expect(second.router.currentRoute.value.name).toBe('home')
    expect(second.wrapper.findAll('.course-card')).toHaveLength(2)
    expect(buttonByText(second.wrapper, 'Добавить')).toBeTruthy()
  })

  it('Logout очищает токен и возвращает на /login', async () => {
    const app = await boot('/login')
    await logIn(app)
    await buttonByText(app.wrapper, 'Logout').trigger('click')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('login')
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('после входа возвращает на страницу, куда шёл пользователь (?redirect)', async () => {
    const app = await boot('/courses/2')
    expect(app.router.currentRoute.value.query.redirect).toBe('/courses/2')
    await logIn(app)
    expect(app.router.currentRoute.value.name).toBe('course-detail')
    expect(app.wrapper.text()).toContain('FastAPI')
  })
})

describe('лаб. № 7: полный CRUD-сценарий', () => {
  it('создание → детали → редактирование → удаление, с toast на каждом шаге', async () => {
    const app = await boot('/login')
    await logIn(app)

    // 1. Создание
    await buttonByText(app.wrapper, 'Добавить').trigger('click')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('course-create')
    await app.wrapper.find('#title').setValue('Docker')
    await app.wrapper.find('#description').setValue('Контейнеры')
    await app.wrapper.find('#instructor').setValue('Сидоров')
    await app.wrapper.find('#duration_hours').setValue('8')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()

    expect(app.router.currentRoute.value.name).toBe('course-detail')
    expect(app.router.currentRoute.value.params.id).toBe('100')
    expect(app.toasts().at(-1).message).toBe('Курс «Docker» создан')
    expect(app.wrapper.text()).toContain('Сидоров')

    // 2. Редактирование
    await buttonByText(app.wrapper, 'Редактировать').trigger('click')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('course-edit')
    expect(app.wrapper.find('#title').element.value).toBe('Docker')
    await app.wrapper.find('#title').setValue('Docker и Compose')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()

    const put = requests.find((r) => r.method === 'put')
    expect(JSON.parse(put.data)).not.toHaveProperty('id')
    expect(app.router.currentRoute.value.name).toBe('course-detail')
    expect(app.wrapper.find('h1').text()).toBe('Docker и Compose')
    expect(app.toasts().at(-1).message).toBe('Изменения сохранены')

    // 3. Удаление с подтверждением
    await buttonByText(app.wrapper, 'Удалить').trigger('click')
    await app.flushPromises()
    modalButton('Да, удалить').click()
    await app.settle()

    expect(app.router.currentRoute.value.name).toBe('home')
    expect(app.toasts().at(-1).message).toBe('Курс «Docker и Compose» удалён')
    expect(db.courses.map((c) => c.title)).toEqual(['Kubernetes', 'FastAPI'])
    expect(app.wrapper.text()).not.toContain('Docker и Compose')
  })

  it('пустая форма — ошибки под полями, запрос не уходит', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)
    const app = await boot('/courses/create')
    await app.settle()
    await app.wrapper.find('#duration_hours').setValue('')
    await app.wrapper.find('form').trigger('submit')
    await app.flushPromises()
    expect(app.wrapper.findAll('.error-message').length).toBe(4)
    expect(requests.some((r) => r.method === 'post')).toBe(false)
  })

  it('3000 часов: FastAPI 422 → сообщение под полем «Длительность»', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)
    const app = await boot('/courses/create')
    await app.settle()
    await app.wrapper.find('#title').setValue('X')
    await app.wrapper.find('#description').setValue('Y')
    await app.wrapper.find('#instructor').setValue('Z')
    await app.wrapper.find('#duration_hours').setValue('3000')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()

    const field = app.wrapper.find('#duration_hours').element.closest('.base-input')
    expect(field.textContent).toContain('Значение должно быть не больше 1000')
    expect(app.router.currentRoute.value.name).toBe('course-create')
  })

  it('отмена удаления: модалка закрылась, курс на месте', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)
    const app = await boot('/courses/1')
    await app.settle()
    await buttonByText(app.wrapper, 'Удалить').trigger('click')
    await app.flushPromises()
    modalButton('Отмена').click()
    await app.settle()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    expect(db.courses).toHaveLength(2)
  })

  it('детали удалённого курса — «Запись не найдена»', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)
    const app = await boot('/courses/999')
    await app.settle()
    expect(app.wrapper.text()).toContain('Запись не найдена')
  })

  it('студент: видит курсы, но нет кнопок изменения и доступа к /courses/create', async () => {
    const app = await boot('/login')
    await logIn(app, 'student', 'student-pass-1')
    expect(buttonByText(app.wrapper, 'Добавить')).toBeUndefined()
    await app.router.push('/courses/1')
    await app.settle()
    expect(app.wrapper.text()).toContain('Kubernetes')
    expect(buttonByText(app.wrapper, 'Удалить')).toBeUndefined()
    await app.router.push('/courses/create')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('home')
  })

  it('поиск по преподавателю отправляет ?instructor= и сужает список', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)
    const app = await boot('/')
    await app.wrapper.find('#search').setValue('петр')
    await new Promise((r) => setTimeout(r, 350)) // debounce 300 мс
    await app.settle()
    expect(requests.at(-1).params).toEqual({ instructor: 'петр' })
    expect(app.wrapper.findAll('.course-card').map((c) => c.find('h3').text())).toEqual(['FastAPI'])
  })

  it('бэкенд недоступен: понятное сообщение, а не белый экран', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)
    vi.resetModules()
    const app = await boot('/')
    const client = await import('@/api/client')
    client.default.defaults.adapter = async () => {
      throw new Error('Network Error')
    }
    await buttonByText(app.wrapper, 'Logout') // шапка на месте
    await app.router.push('/courses/1')
    await app.settle()
    expect(app.wrapper.text()).toContain('Сервер недоступен')
  })
})
