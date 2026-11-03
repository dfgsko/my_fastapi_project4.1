/**
 * Сквозной сценарий лабораторной (шаг 9) в jsdom: настоящие App, Vue Router,
 * Pinia, Axios-интерцепторы и страницы. Подменён только транспорт Axios —
 * «фейковый бэкенд» повторяет контракт FastAPI: /auth/token принимает
 * form-urlencoded, /courses требует заголовок Authorization.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const COURSES = [
  {
    id: 1,
    title: 'Kubernetes',
    description: 'Оркестрация',
    instructor: 'Иванов',
    duration_hours: 16,
  },
  { id: 2, title: 'FastAPI', description: 'REST API', instructor: 'Петров', duration_hours: 12 },
]
const VALID_TOKEN = 'valid.jwt.token'

let requests
function fakeBackend(apiClient, { courses = COURSES } = {}) {
  requests = []
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
    if (config.url === '/auth/token') {
      const type = String(config.headers.get('Content-Type'))
      if (!type.includes('application/x-www-form-urlencoded')) return reply(422, {})
      const body = new URLSearchParams(config.data)
      if (body.get('username') === 'admin' && body.get('password') === 'secret-pass-1')
        return reply(200, { access_token: VALID_TOKEN, refresh_token: 'r', token_type: 'bearer' })
      return reply(401, { detail: 'Incorrect username or password' })
    }
    if (config.url === '/courses') {
      return config.headers.Authorization === `Bearer ${VALID_TOKEN}`
        ? reply(200, courses)
        : reply(401, { detail: 'Could not validate credentials' })
    }
    return reply(404, {})
  }
}

/**
 * «Загрузка страницы»: свежий граф модулей (новые Vue, Pinia, роутер, клиент),
 * как при обновлении вкладки. localStorage переживает «перезагрузку».
 * beforeMount позволяет подменить что-то в свежем модуле client до старта.
 */
async function boot(path = '/', { backend, beforeMount } = {}) {
  vi.resetModules()
  history.pushState({}, '', '/')
  const { mount, flushPromises } = await import('@vue/test-utils')
  const { createPinia } = await import('pinia')
  const { default: App } = await import('@/App.vue')
  const { default: router } = await import('@/router')
  const client = await import('@/api/client')

  fakeBackend(client.default, backend)
  beforeMount?.(client)
  const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
  await router.push(path)
  await flushPromises()
  return { wrapper, router, flushPromises }
}

async function logIn({ wrapper, flushPromises }, user = 'admin', pass = 'secret-pass-1') {
  await wrapper.find('input#username').setValue(user)
  await wrapper.find('input#password').setValue(pass)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('сквозной сценарий: login → список → logout', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(console, 'error').mockImplementation(() => {}) // HomeView логирует ошибки
  })
  afterEach(() => vi.restoreAllMocks())

  it('открытие / без входа ведёт на /login', async () => {
    const { wrapper, router } = await boot('/')
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.find('form').exists()).toBe(true)
    expect(wrapper.find('nav').text()).toContain('Login')
    expect(wrapper.find('nav').text()).not.toContain('Logout')
    expect(requests).toHaveLength(0) // данные защищённой страницы не запрашивались
  })

  it('неверный пароль: сообщение об ошибке, токена нет, остаёмся на /login', async () => {
    const app = await boot('/login')
    await logIn(app, 'admin', 'wrong')

    expect(app.wrapper.find('.error').text()).toBe('Invalid username or password')
    expect(app.router.currentRoute.value.name).toBe('login')
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('верный пароль: токен сохранён, открыт главный экран со списком', async () => {
    const app = await boot('/login')
    await logIn(app)

    expect(app.router.currentRoute.value.name).toBe('home')
    expect(localStorage.getItem('access_token')).toBe(VALID_TOKEN)
    const cards = app.wrapper.findAll('.item-card')
    expect(cards).toHaveLength(2)
    expect(cards[0].text()).toContain('Kubernetes')
    expect(cards[1].text()).toContain('FastAPI')
    expect(app.wrapper.find('nav').text()).toContain('Logout')
    const list = requests.find((r) => r.url === '/courses')
    expect(list.headers.Authorization).toBe(`Bearer ${VALID_TOKEN}`)
  })

  it('вход отправляет форму в формате form-urlencoded (иначе FastAPI вернёт 422)', async () => {
    const app = await boot('/login')
    await logIn(app)
    const login = requests.find((r) => r.url === '/auth/token')
    expect(String(login.headers.get('Content-Type'))).toContain('application/x-www-form-urlencoded')
    expect(new URLSearchParams(login.data).get('username')).toBe('admin')
  })

  it('после перезагрузки страницы пользователь остаётся авторизованным', async () => {
    const first = await boot('/login')
    await logIn(first)
    first.wrapper.unmount()

    const second = await boot('/') // новая «загрузка»: токен только в localStorage
    expect(second.router.currentRoute.value.name).toBe('home')
    expect(second.wrapper.findAll('.item-card')).toHaveLength(2)
  })

  it('Logout очищает токен и возвращает на /login', async () => {
    const app = await boot('/login')
    await logIn(app)
    expect(app.router.currentRoute.value.name).toBe('home')

    await app.wrapper.find('nav button').trigger('click')
    await app.flushPromises()

    expect(app.router.currentRoute.value.name).toBe('login')
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(app.wrapper.find('nav').text()).toContain('Login')
    expect(app.wrapper.find('nav').text()).not.toContain('Logout')

    await app.router.push('/') // снова на защищённую страницу не попасть
    expect(app.router.currentRoute.value.name).toBe('login')
  })

  it('вошедший пользователь не видит страницу входа', async () => {
    localStorage.setItem('access_token', VALID_TOKEN)
    const { router } = await boot('/login')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('истёкший токен: 401 от API очищает токен и отправляет на /login', async () => {
    localStorage.setItem('access_token', 'stale.jwt.token')
    let toLogin
    const { wrapper } = await boot('/', {
      beforeMount: (client) => {
        toLogin = vi.spyOn(client.navigation, 'toLogin').mockImplementation(() => {})
      },
    })

    expect(toLogin).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(wrapper.find('.state.error').exists()).toBe(true)
  })

  it('данные берутся с бэкенда: изменённый ответ виден после обновления страницы', async () => {
    localStorage.setItem('access_token', VALID_TOKEN)
    const first = await boot('/')
    expect(first.wrapper.text()).toContain('Kubernetes')
    first.wrapper.unmount()

    const changed = [
      { id: 9, title: 'Docker', description: 'd', instructor: 'i', duration_hours: 4 },
    ]
    const second = await boot('/', { backend: { courses: changed } })
    expect(second.wrapper.text()).toContain('Docker')
    expect(second.wrapper.text()).not.toContain('Kubernetes')
  })

  it('неизвестный адрес показывает страницу 404', async () => {
    const { wrapper } = await boot('/no/such/page')
    expect(wrapper.text()).toContain('404')
  })
})
