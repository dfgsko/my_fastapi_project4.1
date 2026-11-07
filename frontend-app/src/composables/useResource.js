// Универсальный CRUD-composable: состояние загрузки и ошибок для одного ресурса.
import { ref } from 'vue'
import apiClient from '@/api/client'
import { describeError } from '@/api/errors'

export function useResource(endpoint) {
  // '/courses/' и '/courses' дают одинаковые URL (без двойного слэша).
  const base = endpoint.replace(/\/+$/, '')

  const items = ref([])
  const item = ref(null)
  const isLoading = ref(false)
  const error = ref(null)
  const notFound = ref(false)
  // Лаб. № 8: заголовки ответа списка (X-Age-Restricted-Hidden) и код ошибки
  // карточки (X-Error-Code: age_verification_required).
  const listHeaders = ref({})
  const errorCode = ref(null)

  // Номер последнего запроса списка: если пользователь быстро меняет фильтр,
  // ответ на устаревший запрос не перезапишет более новый.
  let listRequest = 0

  async function fetchList(params = {}) {
    const requestId = ++listRequest
    isLoading.value = true
    error.value = null
    try {
      const { data, headers } = await apiClient.get(base, { params })
      if (requestId === listRequest) {
        items.value = data
        listHeaders.value = headers || {}
      }
    } catch (e) {
      if (requestId === listRequest) error.value = describeError(e, 'Не удалось загрузить данные')
    } finally {
      if (requestId === listRequest) isLoading.value = false
    }
  }

  async function fetchOne(id) {
    isLoading.value = true
    error.value = null
    notFound.value = false
    errorCode.value = null
    try {
      const { data } = await apiClient.get(`${base}/${id}`)
      item.value = data
      return data
    } catch (e) {
      item.value = null
      notFound.value = e.response?.status === 404
      errorCode.value = e.response?.headers?.['x-error-code'] || null
      error.value = describeError(e, 'Не удалось загрузить запись')
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function create(payload) {
    const { data } = await apiClient.post(base, payload)
    items.value = [...items.value, data]
    return data
  }

  async function update(id, payload) {
    const { data } = await apiClient.put(`${base}/${id}`, payload)
    item.value = data
    items.value = items.value.map((x) => (x.id === data.id ? data : x))
    return data
  }

  // Оптимистичное удаление: запись сразу исчезает из списка, а при ошибке
  // возвращается на место, ошибка пробрасывается вызывающему коду.
  async function remove(id) {
    const snapshot = items.value
    items.value = items.value.filter((x) => String(x.id) !== String(id))
    try {
      await apiClient.delete(`${base}/${id}`)
      if (item.value && String(item.value.id) === String(id)) item.value = null
    } catch (e) {
      items.value = snapshot
      throw e
    }
  }

  return {
    items,
    item,
    isLoading,
    error,
    notFound,
    errorCode,
    listHeaders,
    fetchList,
    fetchOne,
    create,
    update,
    remove,
  }
}
