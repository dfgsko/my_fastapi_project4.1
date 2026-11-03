import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import apiClient, { navigation } from '@/api/client'

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

describe('apiClient', () => {
  beforeEach(() => {
    localStorage.clear()
    history.pushState({}, '', '/')
  })
  afterEach(() => vi.restoreAllMocks())

  it('использует базовый URL бэкенда', () => {
    expect(apiClient.defaults.baseURL).toBe('http://localhost:8000')
  })

  it('request interceptor добавляет Authorization: Bearer из localStorage', async () => {
    localStorage.setItem('access_token', 'abc.def.ghi')
    const adapter = respondWith(ok)

    await apiClient.get('/courses')

    expect(adapter.mock.calls[0][0].headers.Authorization).toBe('Bearer abc.def.ghi')
  })

  it('без токена заголовок Authorization не отправляется', async () => {
    const adapter = respondWith(ok)
    await apiClient.get('/courses')
    expect(adapter.mock.calls[0][0].headers.Authorization).toBeUndefined()
  })

  it('токен подхватывается на каждый запрос (после логина без пересоздания клиента)', async () => {
    const adapter = respondWith(ok)
    await apiClient.get('/a')
    localStorage.setItem('access_token', 'new-token')
    await apiClient.get('/b')

    expect(adapter.mock.calls[0][0].headers.Authorization).toBeUndefined()
    expect(adapter.mock.calls[1][0].headers.Authorization).toBe('Bearer new-token')
  })

  it('при 401 удаляет токен и отправляет на /login', async () => {
    localStorage.setItem('access_token', 'expired')
    respondWith(httpError(401))
    const toLogin = vi.spyOn(navigation, 'toLogin').mockImplementation(() => {})

    await expect(apiClient.get('/courses')).rejects.toBeTruthy()

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(toLogin).toHaveBeenCalledTimes(1)
  })

  it('при 401 на странице /login не перезагружает страницу (ошибку покажет форма)', async () => {
    history.pushState({}, '', '/login')
    respondWith(httpError(401))
    const toLogin = vi.spyOn(navigation, 'toLogin').mockImplementation(() => {})

    await expect(apiClient.post('/auth/token')).rejects.toBeTruthy()

    expect(toLogin).not.toHaveBeenCalled()
  })

  it.each([403, 404, 429, 500])('при %i токен сохраняется и редиректа нет', async (status) => {
    localStorage.setItem('access_token', 'keep-me')
    respondWith(httpError(status))
    const toLogin = vi.spyOn(navigation, 'toLogin').mockImplementation(() => {})

    await expect(apiClient.get('/x')).rejects.toBeTruthy()

    expect(localStorage.getItem('access_token')).toBe('keep-me')
    expect(toLogin).not.toHaveBeenCalled()
  })

  it('ошибка без ответа (сервер недоступен) пробрасывается, токен не трогаем', async () => {
    localStorage.setItem('access_token', 'keep-me')
    respondWith(() => {
      throw new Error('Network Error')
    })
    await expect(apiClient.get('/x')).rejects.toThrow('Network Error')
    expect(localStorage.getItem('access_token')).toBe('keep-me')
  })
})
