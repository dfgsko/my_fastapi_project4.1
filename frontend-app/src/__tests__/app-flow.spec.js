/**
 * Сквозные сценарии в jsdom: настоящие App, Vue Router, Pinia, Axios-
 * перехватчики, экраны и компоненты. Подменён только транспорт Axios —
 * «фейковый бэкенд» с состоянием повторяет контракт FastAPI лаб. № 8:
 * сессия в httpOnly cookie (JS её не видит — здесь это переменная session),
 * CSRF double-submit, 2FA с temp_token, роли client/moderator/admin, курсы 18+.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const SEED = [
  {
    id: 1,
    title: 'Kubernetes',
    description: 'Оркестрация',
    instructor: 'Иванов',
    duration_hours: 16,
    min_age: 0,
  },
  {
    id: 2,
    title: 'FastAPI',
    description: 'REST API',
    instructor: 'Петров',
    duration_hours: 12,
    min_age: 0,
  },
  {
    id: 3,
    title: 'Сомелье',
    description: 'Дегустация вин',
    instructor: 'Винный',
    duration_hours: 6,
    min_age: 18,
  },
]
const USERS = {
  admin: { password: 'secret-pass-12', role: 'admin', ageOk: true },
  moder: { password: 'moder-pass-12', role: 'moderator', ageOk: true },
  student: { password: 'student-pass-1', role: 'client', ageOk: false },
  twofa: { password: 'twofa-pass-123', role: 'client', ageOk: false, totp: '123456' },
}

let requests
let db
// «httpOnly cookie»: живёт в «браузере» между перезагрузками страницы, но
// приложение не может её прочитать — только сервер (фейковый адаптер).
let session = null
let accessExpired = false

function setCsrfCookie(value) {
  document.cookie = value ? `csrf_token=${value}; path=/` : 'csrf_token=; max-age=0; path=/'
}

function fakeBackend(apiClient, { courses = SEED } = {}) {
  requests = []
  db = { courses: structuredClone(courses), nextId: 100, registered: ['taken@example.com'] }
  apiClient.defaults.adapter = async (config) => {
    requests.push(config)
    const reply = (status, data, headers = {}) => {
      const response = { data, status, statusText: String(status), headers, config }
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
    const body = () => (typeof config.data === 'string' ? JSON.parse(config.data || '{}') : {})
    const startSession = (name) => {
      session = { name, ...USERS[name] }
      setCsrfCookie(`csrf-${name}`)
      return { message: 'Logged in', user: me() }
    }
    const me = () => ({
      id: 7,
      username: session.name,
      display_name: null,
      role: session.role,
      is_email_verified: true,
      is_age_verified: session.ageOk,
      totp_enabled: !!session.totp,
    })

    if (url === '/auth/token') {
      const form = new URLSearchParams(config.data)
      const user = USERS[form.get('username')]
      if (!user || user.password !== form.get('password'))
        return reply(401, { detail: 'Incorrect username or password' })
      if (user.totp) return reply(200, { '2fa_required': true, temp_token: 'tmp-123' })
      return reply(200, startSession(form.get('username')))
    }
    if (url === '/auth/2fa/verify') {
      const { temp_token, code } = body()
      if (temp_token !== 'tmp-123') return reply(401, { detail: 'expired' })
      if (code !== USERS.twofa.totp) return reply(400, { detail: 'Неверный код' })
      return reply(200, startSession('twofa'))
    }
    if (url === '/auth/register') {
      const data = body()
      if (db.registered.includes(data.email))
        return reply(409, { detail: 'Этот email уже зарегистрирован', field: 'email' })
      return reply(201, { id: 9, requires_age_verification: true, email: data.email })
    }

    // Изменяющие запросы с cookie-сессией требуют X-CSRF-Token (double submit).
    if (session && method !== 'get' && config.headers['X-CSRF-Token'] !== `csrf-${session.name}`)
      return reply(403, { detail: 'CSRF token missing or invalid' })

    if (url === '/auth/refresh') {
      if (!session) return reply(401, { detail: 'Refresh token missing' })
      accessExpired = false
      return reply(200, { message: 'Refreshed' })
    }
    if (url === '/auth/logout') {
      session = null
      setCsrfCookie(null)
      return reply(204, null)
    }
    if (!session || accessExpired) return reply(401, { detail: 'Not authenticated' })
    if (url === '/auth/me') return reply(200, me())

    const match = url.match(/^\/courses(?:\/(\d+))?$/)
    if (!match) return reply(404, {})
    const id = match[1] && Number(match[1])
    const found = db.courses.find((c) => c.id === id)
    const adult = session.ageOk || session.role !== 'client'
    if (method === 'get' && !id) {
      const q = config.params?.instructor?.toLowerCase()
      let list = q ? db.courses.filter((c) => c.instructor.toLowerCase().includes(q)) : db.courses
      const hidden = adult ? 0 : list.filter((c) => c.min_age > 0).length
      if (!adult) list = list.filter((c) => !c.min_age)
      return reply(200, list, { 'x-age-restricted-hidden': String(hidden) })
    }
    if (method === 'get') {
      if (!found) return reply(404, { detail: 'Курс не найден' })
      if (found.min_age > 0 && !adult)
        return reply(
          403,
          { detail: 'Для доступа подтвердите возраст' },
          { 'x-error-code': 'age_verification_required' },
        )
      return reply(200, found)
    }
    if (session.role === 'client') return reply(403, { detail: 'Insufficient permissions' })

    if (method === 'post' || method === 'put') {
      const data = body()
      const errors = []
      if ('id' in data)
        errors.push({
          type: 'extra_forbidden',
          loc: ['body', 'id'],
          msg: 'Extra inputs are not permitted',
        })
      if (data.duration_hours > 1000)
        errors.push({
          type: 'less_than_equal',
          loc: ['body', 'duration_hours'],
          msg: '...',
          ctx: { le: 1000 },
        })
      if (errors.length) return reply(422, { detail: errors })
      if (method === 'post') {
        const created = { id: db.nextId++, ...data }
        db.courses.push(created)
        return reply(201, created)
      }
      if (!found) return reply(404, { detail: 'Курс не найден' })
      Object.assign(found, data)
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
  await settle()
  return { wrapper, router, flushPromises, settle, toasts: () => useToast().toasts.value }
}

async function logIn(app, user = 'admin', pass = USERS[user].password) {
  if (app.router.currentRoute.value.name !== 'login') {
    await app.router.push('/login')
    await app.settle()
  }
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
  session = null
  accessExpired = false
  setCsrfCookie(null)
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

describe('лаб. № 8: лендинг, вход, сессия в cookie', () => {
  it('гость на «/» видит лендинг с «Войти» и «Создать аккаунт»', async () => {
    const { wrapper, router } = await boot('/')
    expect(router.currentRoute.value.name).toBe('home')
    expect(wrapper.text()).toContain('Курсы и студенты в одном месте')
    expect(buttonByText(wrapper, 'Создать аккаунт')).toBeTruthy()
    expect(wrapper.find('nav').text()).toContain('Войти')
    // Курсы гостю не запрашивались: только попытка восстановить сессию.
    expect(requests.map((r) => r.url)).not.toContain('/courses')
  })

  it('неверный пароль: сообщение, сессии нет', async () => {
    const app = await boot('/login')
    await logIn(app, 'admin', 'wrong')
    expect(app.wrapper.find('.error').text()).toContain('Неверный логин или пароль')
    expect(session).toBeNull()
  })

  it('вход: список курсов, аватар-меню в шапке, токенов в localStorage нет', async () => {
    const app = await boot('/login')
    await logIn(app)
    expect(app.router.currentRoute.value.name).toBe('home')
    expect(app.wrapper.findAll('.course-card')).toHaveLength(3)
    expect(app.wrapper.find('.user-menu').text()).toContain('admin')
    expect(localStorage.length).toBe(0)
    const list = requests.find((r) => r.url === '/courses')
    expect(list.headers.Authorization).toBeUndefined() // токен идёт в cookie
    expect(list.withCredentials).toBe(true)
  })

  it('после перезагрузки сессия восстанавливается через /auth/me', async () => {
    const first = await boot('/login')
    await logIn(first)
    first.wrapper.unmount()
    const second = await boot('/')
    expect(second.router.currentRoute.value.name).toBe('home')
    expect(second.wrapper.findAll('.course-card')).toHaveLength(3)
    expect(buttonByText(second.wrapper, 'Добавить')).toBeTruthy()
  })

  it('выход из меню: сессия отозвана, снова лендинг-доступ и /login', async () => {
    const app = await boot('/login')
    await logIn(app)
    await app.wrapper.find('.user-menu .trigger').trigger('click')
    await buttonByText(app.wrapper, 'Выйти').trigger('click')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('login')
    expect(session).toBeNull()
    expect(requests.find((r) => r.url === '/auth/logout').headers['X-CSRF-Token']).toBe(
      'csrf-admin',
    )
  })

  it('после входа возвращает на страницу, куда шёл пользователь (?redirect)', async () => {
    const app = await boot('/courses/2')
    expect(app.router.currentRoute.value.query.redirect).toBe('/courses/2')
    await logIn(app)
    expect(app.router.currentRoute.value.name).toBe('course-detail')
    expect(app.wrapper.text()).toContain('FastAPI')
  })

  it('истёкший access-токен: один тихий refresh и повтор запроса', async () => {
    const app = await boot('/login')
    await logIn(app)
    const before = requests.length // при загрузке гостем уже была попытка refresh
    accessExpired = true
    await app.router.push('/courses/1')
    await app.settle()
    expect(app.wrapper.text()).toContain('Kubernetes')
    const after = requests.slice(before).map((r) => `${r.method} ${r.url}`)
    expect(after).toEqual(['get /courses/1', 'post /auth/refresh', 'get /courses/1'])
  })

  it('refresh не удался → на /login с redirect', async () => {
    const app = await boot('/login')
    await logIn(app)
    session = null // сессию отозвали на другом устройстве
    await app.router.push('/courses/1')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('login')
    expect(app.router.currentRoute.value.query.redirect).toBe('/courses/1')
  })
})

describe('лаб. № 8: регистрация и 2FA', () => {
  it('регистрация: занятый email → 409 под полем email', async () => {
    const app = await boot('/register')
    await app.wrapper.find('#username').setValue('newbie')
    await app.wrapper.find('#email').setValue('taken@example.com')
    await app.wrapper.find('#password').setValue('Long-passw0rd')
    await app.wrapper.find('#confirmPassword').setValue('Long-passw0rd')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()
    const field = app.wrapper.find('#email').element.closest('.base-input')
    expect(field.textContent).toContain('Этот email уже зарегистрирован')
  })

  it('регистрация: успех → страница проверки возраста', async () => {
    const app = await boot('/register')
    await app.wrapper.find('#username').setValue('newbie')
    await app.wrapper.find('#email').setValue('new@example.com')
    await app.wrapper.find('#password').setValue('Long-passw0rd')
    await app.wrapper.find('#confirmPassword').setValue('Long-passw0rd')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('verify-age')
    expect(app.router.currentRoute.value.query.registration).toBe('true')
    expect(app.wrapper.text()).toContain('Подтверждение возраста')
  })

  it('регистрация: несовпадающие пароли — ошибка, запрос не уходит', async () => {
    const app = await boot('/register')
    await app.wrapper.find('#username').setValue('newbie')
    await app.wrapper.find('#email').setValue('new@example.com')
    await app.wrapper.find('#password').setValue('Long-passw0rd')
    await app.wrapper.find('#confirmPassword').setValue('Other-passw0rd')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()
    expect(app.wrapper.text()).toContain('Пароли не совпадают')
    expect(requests.some((r) => r.url === '/auth/register')).toBe(false)
  })

  it('вход с 2FA: второй шаг с кодом, temp_token не попадает в storage', async () => {
    const app = await boot('/login')
    await logIn(app, 'twofa')
    expect(app.wrapper.text()).toContain('Двухфакторная аутентификация')
    expect(session).toBeNull() // после пароля сессии ещё нет
    await app.wrapper.find('#code').setValue('000000')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()
    expect(app.wrapper.find('.error').text()).toContain('Неверный код')
    await app.wrapper.find('#code').setValue('123456')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('home')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
})

describe('лаб. № 8: роли и курсы 18+', () => {
  it('клиент: нет «+ Добавить», плашка о скрытых курсах 18+, нет доступа к /courses/create', async () => {
    const app = await boot('/login')
    await logIn(app, 'student')
    expect(buttonByText(app.wrapper, 'Добавить')).toBeUndefined()
    expect(app.wrapper.findAll('.course-card')).toHaveLength(2)
    expect(app.wrapper.find('.age-banner').text()).toContain('Скрыто курсов 18+: 1')
    await app.router.push('/courses/1')
    await app.settle()
    expect(app.wrapper.text()).toContain('Kubernetes')
    expect(buttonByText(app.wrapper, 'Удалить')).toBeUndefined()
    await app.router.push('/courses/create')
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('home')
  })

  it('клиент открывает курс 18+ по ссылке → заглушка «подтвердите возраст»', async () => {
    const app = await boot('/login')
    await logIn(app, 'student')
    await app.router.push('/courses/3')
    await app.settle()
    expect(app.wrapper.find('.age-lock').text()).toContain('Для доступа подтвердите возраст')
    expect(app.wrapper.text()).not.toContain('Дегустация')
  })

  it('модератор видит «+ Добавить», пункт «Модерация» и курсы 18+', async () => {
    const app = await boot('/login')
    await logIn(app, 'moder')
    expect(buttonByText(app.wrapper, 'Добавить')).toBeTruthy()
    expect(app.wrapper.find('nav').text()).toContain('Модерация')
    expect(app.wrapper.findAll('.course-card')).toHaveLength(3)
  })
})

describe('лаб. № 7: CRUD (теперь от модератора, с CSRF)', () => {
  it('создание → детали → редактирование → удаление, с toast на каждом шаге', async () => {
    const app = await boot('/login')
    await logIn(app, 'moder')

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
    const post = requests.find((r) => r.method === 'post' && r.url === '/courses')
    expect(post.headers['X-CSRF-Token']).toBe('csrf-moder')
    expect(JSON.parse(post.data).min_age).toBe(0)

    await buttonByText(app.wrapper, 'Редактировать').trigger('click')
    await app.settle()
    await app.wrapper.find('#title').setValue('Docker и Compose')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()
    const put = requests.find((r) => r.method === 'put')
    expect(JSON.parse(put.data)).not.toHaveProperty('id')
    expect(app.wrapper.find('h1').text()).toBe('Docker и Compose')

    await buttonByText(app.wrapper, 'Удалить').trigger('click')
    await app.flushPromises()
    modalButton('Да, удалить').click()
    await app.settle()
    expect(app.router.currentRoute.value.name).toBe('home')
    expect(app.toasts().at(-1).message).toBe('Курс «Docker и Compose» удалён')
    expect(db.courses.map((c) => c.title)).toEqual(['Kubernetes', 'FastAPI', 'Сомелье'])
  })

  it('3000 часов: FastAPI 422 → сообщение под полем «Длительность»', async () => {
    const app = await boot('/login')
    await logIn(app, 'moder')
    await app.router.push('/courses/create')
    await app.settle()
    await app.wrapper.find('#title').setValue('X')
    await app.wrapper.find('#description').setValue('Y')
    await app.wrapper.find('#instructor').setValue('Z')
    await app.wrapper.find('#duration_hours').setValue('3000')
    await app.wrapper.find('form').trigger('submit')
    await app.settle()
    const field = app.wrapper.find('#duration_hours').element.closest('.base-input')
    expect(field.textContent).toContain('Значение должно быть не больше 1000')
  })

  it('детали удалённого курса — «Запись не найдена»', async () => {
    const app = await boot('/login')
    await logIn(app)
    await app.router.push('/courses/999')
    await app.settle()
    expect(app.wrapper.text()).toContain('Запись не найдена')
  })

  it('поиск по преподавателю отправляет ?instructor= и сужает список', async () => {
    const app = await boot('/login')
    await logIn(app)
    await app.wrapper.find('#search').setValue('петр')
    await new Promise((r) => setTimeout(r, 350)) // debounce 300 мс
    await app.settle()
    expect(requests.at(-1).params).toEqual({ instructor: 'петр' })
    expect(app.wrapper.findAll('.course-card').map((c) => c.find('h3').text())).toEqual(['FastAPI'])
  })

  it('бэкенд недоступен: понятное сообщение, а не белый экран', async () => {
    const app = await boot('/login')
    await logIn(app)
    const client = await import('@/api/client')
    client.default.defaults.adapter = async () => {
      throw new Error('Network Error')
    }
    await app.router.push('/courses/1')
    await app.settle()
    expect(app.wrapper.text()).toContain('Сервер недоступен')
  })
})
