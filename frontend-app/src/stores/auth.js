import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import apiClient, { TOKEN_KEY } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter()

  // Токен читаем из localStorage: при перезагрузке страницы Pinia обнуляется,
  // а localStorage — нет, поэтому пользователь остаётся авторизованным.
  const token = ref(localStorage.getItem(TOKEN_KEY) || null)
  const isAuthenticated = computed(() => !!token.value)

  async function login(username, password) {
    // FastAPI OAuth2PasswordRequestForm ждёт form-urlencoded, а не JSON
    // (иначе ответ 422).
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)

    const response = await apiClient.post('/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })

    // Бэкенд возвращает и refresh_token; в этом MVP он намеренно не сохраняется
    // (долгоживущий токен в localStorage — лишний риск при XSS). По истечении
    // access-токена (30 мин) пользователь входит заново.
    token.value = response.data.access_token
    localStorage.setItem(TOKEN_KEY, token.value)
    await router.push('/')
  }

  function logout() {
    token.value = null
    localStorage.removeItem(TOKEN_KEY)
    router.push('/login')
  }

  return { token, isAuthenticated, login, logout }
})
