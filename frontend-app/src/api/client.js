// Единая точка обращения к API: все запросы идут через apiClient.
import axios from 'axios'

export const TOKEN_KEY = 'access_token'

// Вынесено в объект, чтобы переход на /login можно было подменить в тестах
// (jsdom не позволяет переопределить window.location).
export const navigation = {
  toLogin() {
    window.location.href = '/login'
  },
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
})

// Перед каждым запросом подставляем JWT: компоненты о токене не знают.
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 401 обрабатываем централизованно: токен истёк или недействителен —
// очищаем его и отправляем пользователя на страницу входа.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      // На /login не перенаправляем: там 401 означает «неверный пароль»,
      // и ошибку должна показать сама форма (иначе страница перезагрузится).
      if (window.location.pathname !== '/login') navigation.toLogin()
    }
    return Promise.reject(error)
  },
)

export default apiClient
