import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'

// Мокаем apiClient и useRouter: тест проверяет только логику store.
const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('@/api/client')
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('login сохраняет токен и перенаправляет', async () => {
    const fakeToken = 'fake-jwt-token'
    apiClient.post.mockResolvedValue({ data: { access_token: fakeToken } })

    const store = useAuthStore()
    await store.login('user', 'pass')

    expect(apiClient.post).toHaveBeenCalledWith('/auth/token', expect.any(URLSearchParams), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    expect(store.token).toBe(fakeToken)
    expect(localStorage.getItem('access_token')).toBe(fakeToken)
    expect(store.isAuthenticated).toBe(true)
    expect(push).toHaveBeenCalledWith('/')
  })

  it('login отправляет поля username и password в теле form-urlencoded', async () => {
    apiClient.post.mockResolvedValue({ data: { access_token: 't' } })
    await useAuthStore().login('anna', 's3cret&=')

    const body = apiClient.post.mock.calls[0][1]
    expect(body.get('username')).toBe('anna')
    expect(body.get('password')).toBe('s3cret&=') // спецсимволы кодируются корректно
    expect(body.toString()).toContain('username=anna')
  })

  it('неудачный login не сохраняет токен и не перенаправляет', async () => {
    apiClient.post.mockRejectedValue({ response: { status: 401 } })
    const store = useAuthStore()

    await expect(store.login('user', 'bad')).rejects.toBeTruthy()

    expect(store.token).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(push).not.toHaveBeenCalled()
  })

  it('logout очищает токен и localStorage и ведёт на /login', () => {
    localStorage.setItem('access_token', 'fake')
    const store = useAuthStore()
    store.token = 'fake'

    store.logout()

    expect(store.token).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(push).toHaveBeenCalledWith('/login')
  })

  it('при создании читает токен из localStorage (сессия переживает перезагрузку)', () => {
    localStorage.setItem('access_token', 'saved-token')
    const store = useAuthStore()
    expect(store.token).toBe('saved-token')
    expect(store.isAuthenticated).toBe(true)
  })

  it('без сохранённого токена пользователь не авторизован', () => {
    expect(useAuthStore().isAuthenticated).toBe(false)
  })
})
