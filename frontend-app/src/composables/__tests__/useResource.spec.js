import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useResource } from '@/composables/useResource'
import apiClient from '@/api/client'

vi.mock('@/api/client')
beforeEach(() => vi.clearAllMocks())

const httpError = (status, detail) => ({ response: { status, data: { detail } } })

describe('useResource', () => {
  it('нормализует слэш: /courses/ → /courses, детали — /courses/5 (без //)', async () => {
    apiClient.get.mockResolvedValue({ data: [] })
    const r = useResource('/courses/')
    await r.fetchList()
    await r.fetchOne(5)
    expect(apiClient.get).toHaveBeenNthCalledWith(1, '/courses', { params: {} })
    expect(apiClient.get).toHaveBeenNthCalledWith(2, '/courses/5')
  })

  it('fetchList: состояния загрузки и параметры фильтра', async () => {
    let resolve
    apiClient.get.mockReturnValue(new Promise((r) => (resolve = r)))
    const r = useResource('/courses')
    const pending = r.fetchList({ instructor: 'Иван' })
    expect(r.isLoading.value).toBe(true)
    resolve({ data: [{ id: 1 }] })
    await pending
    expect(r.isLoading.value).toBe(false)
    expect(r.items.value).toEqual([{ id: 1 }])
    expect(apiClient.get).toHaveBeenCalledWith('/courses', { params: { instructor: 'Иван' } })
  })

  it('ответ на устаревший запрос не перезаписывает более новый (гонка при поиске)', async () => {
    const resolvers = []
    apiClient.get.mockImplementation(() => new Promise((r) => resolvers.push(r)))
    const r = useResource('/courses')
    const older = r.fetchList({ instructor: 'И' })
    const newer = r.fetchList({ instructor: 'Иванов' })
    resolvers[1]({ data: [{ id: 2, title: 'новый' }] })
    await newer
    resolvers[0]({ data: [{ id: 1, title: 'старый' }] })
    await older
    expect(r.items.value).toEqual([{ id: 2, title: 'новый' }])
  })

  it('fetchList: понятная ошибка при недоступном сервере', async () => {
    apiClient.get.mockRejectedValue(new Error('Network Error'))
    const r = useResource('/courses')
    await r.fetchList()
    expect(r.error.value).toContain('Сервер недоступен')
    expect(r.isLoading.value).toBe(false)
  })

  it('fetchOne: 404 → notFound и null', async () => {
    apiClient.get.mockRejectedValue(httpError(404, 'Курс не найден'))
    const r = useResource('/courses')
    expect(await r.fetchOne(99)).toBeNull()
    expect(r.notFound.value).toBe(true)
    expect(r.error.value).toBe('Запись не найдена')
  })

  it('fetchOne: 500 — ошибка, но не «не найдено»', async () => {
    apiClient.get.mockRejectedValue(httpError(500))
    const r = useResource('/courses')
    await r.fetchOne(1)
    expect(r.notFound.value).toBe(false)
    expect(r.error.value).toContain('Ошибка на сервере')
  })

  it('create и update возвращают данные и обновляют локальный список', async () => {
    const r = useResource('/courses')
    r.items.value = [{ id: 1, title: 'A' }]
    apiClient.post.mockResolvedValue({ data: { id: 2, title: 'B' } })
    apiClient.put.mockResolvedValue({ data: { id: 1, title: 'A2' } })

    expect(await r.create({ title: 'B' })).toEqual({ id: 2, title: 'B' })
    await r.update(1, { title: 'A2' })

    expect(apiClient.post).toHaveBeenCalledWith('/courses', { title: 'B' })
    expect(apiClient.put).toHaveBeenCalledWith('/courses/1', { title: 'A2' })
    expect(r.items.value.map((x) => x.title)).toEqual(['A2', 'B'])
  })

  it('remove: оптимистично убирает запись из списка', async () => {
    let finish
    apiClient.delete.mockReturnValue(new Promise((r) => (finish = r)))
    const r = useResource('/courses')
    r.items.value = [{ id: 1 }, { id: 2 }]
    const pending = r.remove('1') // id из URL — строка
    expect(r.items.value).toEqual([{ id: 2 }]) // ещё до ответа сервера
    finish()
    await pending
    expect(apiClient.delete).toHaveBeenCalledWith('/courses/1')
  })

  it('remove: при ошибке возвращает запись и пробрасывает ошибку', async () => {
    apiClient.delete.mockRejectedValue(httpError(403))
    const r = useResource('/courses')
    r.items.value = [{ id: 1 }, { id: 2 }]
    await expect(r.remove(1)).rejects.toEqual(httpError(403))
    expect(r.items.value).toEqual([{ id: 1 }, { id: 2 }])
  })

  it('create пробрасывает ошибку (форма покажет 422 под полями)', async () => {
    apiClient.post.mockRejectedValue(httpError(422, []))
    await expect(useResource('/courses').create({})).rejects.toEqual(httpError(422, []))
  })
})
