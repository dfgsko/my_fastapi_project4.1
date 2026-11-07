// Методы API для курсов (вариант 8). Компоненты не знают об URL и Axios.
import apiClient from '@/api/client'

const BASE = '/courses'

export const coursesApi = {
  list: (params = {}) => apiClient.get(BASE, { params }).then((r) => r.data),
  getById: (id) => apiClient.get(`${BASE}/${id}`).then((r) => r.data),
  create: (payload) => apiClient.post(BASE, payload).then((r) => r.data),
  update: (id, payload) => apiClient.put(`${BASE}/${id}`, payload).then((r) => r.data),
  remove: (id) => apiClient.delete(`${BASE}/${id}`),
}

/** Поля, которые API принимает в POST/PUT. Остальное (id) отбрасывается. */
export const COURSE_FIELDS = ['title', 'description', 'instructor', 'duration_hours', 'min_age']

export function toCoursePayload(values) {
  return {
    title: String(values.title ?? '').trim(),
    description: String(values.description ?? '').trim(),
    instructor: String(values.instructor ?? '').trim(),
    duration_hours: values.duration_hours,
    // 0 — для всех, 18 — только для подтвердивших возраст (лаб. № 8).
    min_age: Number(values.min_age) > 0 ? 18 : 0,
  }
}
