import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import apiClient, { navigation, readCookie, setSessionLostHandler } from '@/api/client'

// Подменяем транспорт Axios: сеть не нужна, интерцепторы выполняются как в браузере.
function respondWith(handler) {
  const adapter = vi.fn(async (config) => handler(config))
  apiClient.defaults.adapter = adapter
  return adapter
}
const ok = (config) => ({ data: {}, status: 200, statusText: 'OK', headers: {}, config })
function httpError(status) {
  return (config) => {
    const error = new Error(`Request failed with status code ${status}`)
    error.isAxiosError = true
    error.config = config
    error.response = { status, data: {}, headers: {}, config }
    throw error
  }
}
const setCookie = (v) => (document.cookie = `csrf_token=${v}; path=/`)
const clearCookie = () => (document.cookie = 'csrf_token=; max-age=0; path=/')

describe('apiClient (лаб. № 8: httpOnly cookie + CSRF)', () => {
  beforeEach(() => {
    localStorage.clear()
    clearCookie()
    history.pushState({}, '', '/')
    setSessionLostHandler(() => {
      if (window.location.pathname !== '/login') navigation.toLogin()
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it('использует базовый URL бэкенда и отправляет cookie (withCredentials)', () => {
    expect(apiClient.defaults.baseURL).toBe('http://localhost:8000')
    expect(apiClient.defaults.withCredentials).toBe(true)
  })

  it('никогда не ставит Authorization из localStorage', async () => {
    localStorage.setItem('access_token', 'abc.def.ghi') // «старый» токен из лаб. № 6
    const adapter = respondWith(ok)
    await apiClient.get('/courses')
    expect(adapter.mock.calls[0][0].headers.Authorization).toBeUndefined()
  })

  it('POST/PUT/DELETE получают X-CSRF-Token из cookie, GET — нет', async () => {
    setCookie('csrf-123')
    const adapter = respondWith(ok)
    await apiClient.get('/courses')
    await apiClient.post('/courses', {})
    await apiClient.delete('/courses/1')
    const headers = adapter.mock.calls.map((c) => c[0].headers['X-CSRF-Token'])
    expect(headers).toEqual([undefined, 'csrf-123', 'csrf-123'])
  })

  it('readCookie читает только свою cookie', () => {
    document.cookie = 'other=1; path=/'
    setCookie('abc')
    expect(readCookie('csrf_token')).toBe('abc')
    expect(readCookie('missing')).toBe('')
  })

  it('при 401 один раз обновляет сессию и повторяет запрос', async () => {
    let expired = true
    const adapter = respondWith((config) => {
      if (config.url === '/auth/refresh') {
        expired = false
        return ok(config)
      }
      return expired ? httpError(401)(config) : ok(config)
    })
    await expect(apiClient.get('/courses')).resolves.toBeTruthy()
    expect(adapter.mock.calls.map((c) => c[0].url)).toEqual([
      '/courses',
      '/auth/refresh',
      '/courses',
    ])
  })

  it('параллельные 401 → ровно один refresh (иначе сработал бы reuse detection)', async () => {
    let expired = true
    const adapter = respondWith(async (config) => {
      if (config.url === '/auth/refresh') {
        await new Promise((r) => setTimeout(r, 5))
        expired = false
        return ok(config)
      }
      return expired ? httpError(401)(config) : ok(config)
    })
    await Promise.all([apiClient.get('/a'), apiClient.get('/b'), apiClient.get('/c')])
    expect(adapter.mock.calls.filter((c) => c[0].url === '/auth/refresh')).toHaveLength(1)
  })

  it('refresh не удался → отправляет на /login', async () => {
    respondWith(httpError(401))
    const toLogin = vi.spyOn(navigation, 'toLogin').mockImplementation(() => {})
    await expect(apiClient.get('/courses')).rejects.toBeTruthy()
    expect(toLogin).toHaveBeenCalledTimes(1)
  })

  it('401 на /auth/token не запускает refresh (это «неверный пароль»)', async () => {
    history.pushState({}, '', '/login')
    const adapter = respondWith(httpError(401))
    const toLogin = vi.spyOn(navigation, 'toLogin').mockImplementation(() => {})
    await expect(apiClient.post('/auth/token')).rejects.toBeTruthy()
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(toLogin).not.toHaveBeenCalled()
  })

  it.each([403, 404, 429, 500])('при %i refresh и редиректа нет', async (status) => {
    const adapter = respondWith(httpError(status))
    const toLogin = vi.spyOn(navigation, 'toLogin').mockImplementation(() => {})
    await expect(apiClient.get('/x')).rejects.toBeTruthy()
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(toLogin).not.toHaveBeenCalled()
  })

  it('ошибка без ответа (сервер недоступен) пробрасывается', async () => {
    respondWith(() => {
      throw new Error('Network Error')
    })
    await expect(apiClient.get('/x')).rejects.toThrow('Network Error')
  })
})
