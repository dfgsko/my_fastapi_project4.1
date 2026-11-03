import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import apiClient, { TOKEN_KEY } from '@/api/client'

// После входа возвращаем туда, куда пользователь шёл (?redirect=/courses/5).
// Только внутренние пути: «//evil.example» или «https://…» — открытый редирект.
export function safeRedirect(target) {
  return typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')
    ? target
    : '/'
}

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter()

  // Токен читаем из localStorage: при перезагрузке страницы Pinia обнуляется,
  // а localStorage — нет, поэтому пользователь остаётся авторизованным.
  const token = ref(localStorage.getItem(TOKEN_KEY) || null)
  // Данные о себе (роль) — из GET /auth/me. Роль в JWT не используем:
  // бэкенд проверяет права по БД, интерфейс просто прячет недоступные кнопки.
  const user = ref(null)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function fetchMe() {
    if (!token.value) return null
    try {
      const response = await apiClient.get('/auth/me')
      user.value = response.data
    } catch {
      user.value = null // 401 обработает перехватчик клиента
    }
    return user.value
  }

  async function login(username, password) {
    // FastAPI OAuth2PasswordRequestForm ждёт form-urlencoded, а не JSON
    // (иначе ответ 422).
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)

    const response = await apiClient.post('/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })

    // refresh_token в MVP намеренно не сохраняется (риск при XSS).
    token.value = response.data.access_token
    localStorage.setItem(TOKEN_KEY, token.value)
    await fetchMe()
    await router.push(safeRedirect(router.currentRoute?.value?.query?.redirect))
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    router.push('/login')
  }

  return { token, user, isAuthenticated, isAdmin, fetchMe, login, logout }
})
