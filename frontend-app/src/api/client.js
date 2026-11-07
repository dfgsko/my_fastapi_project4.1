// Единая точка обращения к API: все запросы идут через apiClient.
//
// Лабораторная № 8: токены больше НЕ хранятся в localStorage. Сервер кладёт
// их в httpOnly cookie, которые JavaScript прочитать не может (и XSS-скрипт
// тоже), а браузер сам прикладывает их к запросам — нужно лишь
// withCredentials: true. Для защиты от CSRF к изменяющим запросам добавляется
// заголовок X-CSRF-Token со значением из (не httpOnly) cookie csrf_token.
import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
export const CSRF_COOKIE = 'csrf_token'
export const CSRF_HEADER = 'X-CSRF-Token'

// Вынесено в объект, чтобы переход на /login можно было подменить в тестах
// (jsdom не позволяет переопределить window.location).
export const navigation = {
  toLogin() {
    window.location.href = '/login'
  },
}

/** Значение cookie по имени (только не-httpOnly cookie видны из JS). */
export function readCookie(name) {
  const prefix = `${name}=`
  const found = document.cookie.split('; ').find((c) => c.startsWith(prefix))
  return found ? decodeURIComponent(found.slice(prefix.length)) : ''
}

const SAFE_METHODS = ['get', 'head', 'options']

function withCsrf(config) {
  const method = (config.method || 'get').toLowerCase()
  if (!SAFE_METHODS.includes(method)) {
    const token = readCookie(CSRF_COOKIE)
    if (token) {
      config.headers = config.headers || {}
      config.headers[CSRF_HEADER] = token
    }
  }
  return config
}

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // <-- браузер отправляет cookie на API
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use(withCsrf)

// Запросы, на которые 401 означает «неверные данные», а не «сессия истекла»:
// для них обновлять токен бессмысленно.
const NO_REFRESH = [
  '/auth/token',
  '/auth/refresh',
  '/auth/2fa/verify',
  '/auth/register',
  '/auth/logout',
]

// Одновременно несколько запросов могут получить 401 — refresh выполняется
// ОДИН раз, остальные ждут его результата (иначе второй refresh предъявил бы
// уже использованный токен, и reuse detection отозвал бы всю сессию).
let refreshPromise = null

export function refreshSession() {
  if (!refreshPromise) {
    // Через тот же apiClient (CSRF-заголовок добавит перехватчик). /auth/refresh
    // в NO_REFRESH — его собственный 401 не запускает refresh по кругу.
    refreshPromise = apiClient.post('/auth/refresh').finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

// Кто реагирует на окончательную потерю сессии (store: очистить user и,
// если страница закрытая, увести на /login). По умолчанию — переход на /login.
let onSessionLost = () => {
  if (window.location.pathname !== '/login') navigation.toLogin()
}

export function setSessionLostHandler(handler) {
  onSessionLost = handler
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error
    const url = config?.url || ''
    if (response?.status === 401 && config && !config._retry && !NO_REFRESH.includes(url)) {
      config._retry = true
      try {
        await refreshSession() // новый access_token придёт в cookie
        return apiClient(config) // повторяем исходный запрос
      } catch {
        onSessionLost(error)
      }
    }
    return Promise.reject(error)
  },
)

export default apiClient
