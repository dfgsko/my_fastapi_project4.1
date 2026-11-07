import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore, safeRedirect } from '@/stores/auth'
import apiClient from '@/api/client'

// Мокаем apiClient и useRouter: тест проверяет только логику store.
const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('@/api/client')
vi.mock('vue-router', () => ({
  useRouter: () => ({ push, currentRoute: { value: { query: {}, meta: {} } } }),
}))

const ME = { id: 1, username: 'anna', role: 'client', display_name: 'Анна' }

describe('Auth Store (лаб. № 8: сессия в httpOnly cookie)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('login отправляет form-urlencoded, берёт профиль из ответа и перенаправляет', async () => {
    apiClient.post.mockResolvedValue({ data: { message: 'Logged in', user: ME } })
    const store = useAuthStore()
    const result = await store.login('anna', 's3cret&=')

    expect(apiClient.post).toHaveBeenCalledWith('/auth/token', expect.any(URLSearchParams), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    const body = apiClient.post.mock.calls[0][1]
    expect(body.get('username')).toBe('anna')
    expect(body.get('password')).toBe('s3cret&=') // спецсимволы кодируются корректно
    expect(result).toEqual({ twoFactor: false })
    expect(store.user).toEqual(ME)
    expect(store.isAuthenticated).toBe(true)
    expect(push).toHaveBeenCalledWith('/')
  })

  it('токены нигде в JS не сохраняются', async () => {
    apiClient.post.mockResolvedValue({ data: { message: 'Logged in', user: ME } })
    await useAuthStore().login('anna', 'p')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(Object.keys(useAuthStore().$state)).not.toContain('token')
  })

  it('при включённой 2FA login возвращает temp_token и НЕ входит', async () => {
    apiClient.post.mockResolvedValue({ data: { '2fa_required': true, temp_token: 'tmp' } })
    const store = useAuthStore()
    const result = await store.login('anna', 'p')
    expect(result).toEqual({ twoFactor: true, tempToken: 'tmp' })
    expect(store.isAuthenticated).toBe(false)
    expect(push).not.toHaveBeenCalled()
  })

  it('verifyTwoFactor отправляет temp_token и код, затем входит', async () => {
    apiClient.post.mockResolvedValue({ data: { message: 'Logged in', user: ME } })
    const store = useAuthStore()
    await store.verifyTwoFactor('tmp', '123456')
    expect(apiClient.post).toHaveBeenCalledWith('/auth/2fa/verify', {
      temp_token: 'tmp',
      code: '123456',
    })
    expect(store.isAuthenticated).toBe(true)
  })

  it('неудачный login не входит и не перенаправляет', async () => {
    apiClient.post.mockRejectedValue({ response: { status: 401 } })
    const store = useAuthStore()
    await expect(store.login('user', 'bad')).rejects.toBeTruthy()
    expect(store.isAuthenticated).toBe(false)
    expect(push).not.toHaveBeenCalled()
  })

  it('init восстанавливает сессию по cookie через /auth/me (один раз)', async () => {
    apiClient.get.mockResolvedValue({ data: ME })
    const store = useAuthStore()
    await Promise.all([store.init(), store.init()])
    await store.init()
    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(apiClient.get).toHaveBeenCalledWith('/auth/me')
    expect(store.isAuthenticated).toBe(true)
    expect(store.initialized).toBe(true)
  })

  it('init без сессии: гость, но initialized = true', async () => {
    apiClient.get.mockRejectedValue({ response: { status: 401 } })
    const store = useAuthStore()
    await store.init()
    expect(store.isAuthenticated).toBe(false)
    expect(store.initialized).toBe(true)
  })

  it('logout вызывает POST /auth/logout, сбрасывает профиль и ведёт на /login', async () => {
    apiClient.post.mockResolvedValue({})
    const store = useAuthStore()
    store.user = ME
    await store.logout()
    expect(apiClient.post).toHaveBeenCalledWith('/auth/logout')
    expect(store.user).toBeNull()
    expect(push).toHaveBeenCalledWith('/login')
  })

  it('logout работает, даже если сервер недоступен', async () => {
    apiClient.post.mockRejectedValue(new Error('Network Error'))
    const store = useAuthStore()
    store.user = ME
    await store.logout()
    expect(store.user).toBeNull()
  })

  it.each([
    ['client', false, false],
    ['moderator', true, false],
    ['admin', true, true],
  ])('роль %s: canManageContent=%s, isAdmin=%s', (role, canManage, admin) => {
    const store = useAuthStore()
    store.user = { ...ME, role }
    expect(store.canManageContent).toBe(canManage)
    expect(store.isAdmin).toBe(admin)
  })

  it.each([
    ['/courses/5', '/courses/5'],
    [undefined, '/'],
    ['//evil.example', '/'],
    ['https://evil.example', '/'],
  ])('safeRedirect(%s) → %s (нет открытого редиректа)', (target, expected) => {
    expect(safeRedirect(target)).toBe(expected)
  })
})
