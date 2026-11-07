import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import apiClient, { setSessionLostHandler } from '@/api/client'

// После входа возвращаем туда, куда пользователь шёл (?redirect=/courses/5).
// Только внутренние пути: «//evil.example» или «https://…» — открытый редирект.
export function safeRedirect(target) {
  return typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')
    ? target
    : '/'
}

export const ROLE_LABELS = { client: 'Клиент', moderator: 'Модератор', admin: 'Администратор' }

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter()

  // Токена в JS больше нет (он в httpOnly cookie). Признак входа — профиль,
  // полученный от GET /auth/me при старте приложения.
  const user = ref(null)
  const initialized = ref(false)
  let initPromise = null

  const isAuthenticated = computed(() => !!user.value)
  const role = computed(() => user.value?.role ?? null)
  const isAdmin = computed(() => role.value === 'admin')
  const isModerator = computed(() => ['moderator', 'admin'].includes(role.value))
  // Создание / редактирование / удаление курсов — модератор и администратор.
  // Это UX: настоящая проверка — require_role на бэкенде (403).
  const canManageContent = isModerator
  const displayName = computed(() => user.value?.display_name || user.value?.username || '')

  async function fetchMe() {
    try {
      const { data } = await apiClient.get('/auth/me')
      user.value = data
    } catch {
      user.value = null
    }
    return user.value
  }

  /** Один раз при старте: восстанавливает сессию по cookie. */
  function init() {
    if (!initPromise) {
      initPromise = fetchMe().finally(() => {
        initialized.value = true
      })
    }
    return initPromise
  }

  function setUser(data) {
    user.value = data
    initialized.value = true
  }

  async function goAfterLogin() {
    await router.push(safeRedirect(router.currentRoute?.value?.query?.redirect))
  }

  /** Ответ /auth/token или /auth/2fa/verify с {"user": ...}: сессия уже в cookie. */
  async function handleLoginSuccess(data) {
    setUser(data?.user ?? (await fetchMe()))
    await goAfterLogin()
  }

  /**
   * Первый шаг входа. Возвращает { twoFactor: true, tempToken } если включена
   * 2FA (тогда LoginView показывает поле для кода), иначе завершает вход.
   */
  async function login(username, password) {
    // FastAPI OAuth2PasswordRequestForm ждёт form-urlencoded, а не JSON.
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    const { data } = await apiClient.post('/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    if (data?.['2fa_required']) return { twoFactor: true, tempToken: data.temp_token }
    await handleLoginSuccess(data)
    return { twoFactor: false }
  }

  /** Второй шаг: temp_token живёт только в памяти компонента, не в storage. */
  async function verifyTwoFactor(tempToken, code) {
    const { data } = await apiClient.post('/auth/2fa/verify', { temp_token: tempToken, code })
    await handleLoginSuccess(data)
  }

  function clearSession() {
    user.value = null
  }

  async function logout() {
    try {
      await apiClient.post('/auth/logout') // сервер отзовёт сессию и сотрёт cookie
    } catch {
      // даже если сервер недоступен — локально выходим
    }
    clearSession()
    await router.push('/login')
  }

  // Сессию не удалось продлить (refresh истёк или отозван): забываем профиль
  // и уводим на вход, только если текущая страница требует авторизации.
  setSessionLostHandler(() => {
    const wasLoggedIn = !!user.value
    clearSession()
    const route = router.currentRoute?.value
    if (wasLoggedIn && route?.meta?.requiresAuth) {
      router.push({ name: 'login', query: { redirect: route.fullPath } })
    }
  })

  return {
    user,
    initialized,
    isAuthenticated,
    role,
    isAdmin,
    isModerator,
    canManageContent,
    displayName,
    init,
    fetchMe,
    setUser,
    login,
    verifyTwoFactor,
    handleLoginSuccess,
    logout,
    clearSession,
  }
})
