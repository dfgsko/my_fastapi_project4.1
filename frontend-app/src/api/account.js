// Запросы раздела «Аккаунт» (лаб. № 8). Карточки безопасности сами загружают
// /auth/me (так их проще тестировать по отдельности), а getMe() склеивает
// одновременные вызовы в один HTTP-запрос.
import apiClient, { API_BASE_URL } from '@/api/client'

let inflight = null

export function getMe() {
  if (!inflight) {
    inflight = apiClient.get('/auth/me').finally(() => {
      inflight = null
    })
  }
  return inflight
}

/** Абсолютный URL аватара: avatar_url приходит относительным (/users/1/avatar?v=…). */
export function avatarSrc(url) {
  if (!url) return ''
  return /^https?:\/\//.test(url) ? url : `${API_BASE_URL}${url}`
}

export const accountApi = {
  updateProfile: (payload) => apiClient.patch('/users/me/profile', payload).then((r) => r.data),
  uploadAvatar(file) {
    const form = new FormData()
    form.append('file', file)
    // Content-Type задаём явно: иначе Axios сериализовал бы FormData в JSON
    // (у клиента по умолчанию application/json). Boundary браузер добавит сам.
    return apiClient
      .post('/users/me/avatar', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data)
  },
  deleteAvatar: () => apiClient.delete('/users/me/avatar'),
  changeUsername: (newUsername) =>
    apiClient.patch('/users/me/username', { new_username: newUsername }).then((r) => r.data),
  sessions: () => apiClient.get('/auth/sessions').then((r) => r.data),
  revokeSession: (id) => apiClient.delete(`/auth/sessions/${encodeURIComponent(id)}`),
  logoutAll: () => apiClient.post('/auth/logout-all'),
}

/** Проверка файла изображения до отправки (сервер всё равно проверит сам). */
export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export function validateImageFile(file, maxBytes = 5 * 1024 * 1024) {
  if (!file) return 'Выберите файл'
  if (!IMAGE_TYPES.includes(file.type)) return 'Допустимы только JPEG, PNG и WebP'
  if (file.size > maxBytes) return `Файл больше ${Math.round(maxBytes / 1024 / 1024)} МБ`
  return ''
}
