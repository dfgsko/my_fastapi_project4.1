import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import HomeView from '@/views/HomeView.vue'
import apiClient from '@/api/client'
import { mountView } from '@/test-utils'

vi.mock('@/api/client')

const COURSES = [
  { id: 1, title: 'Book A', description: 'a', instructor: 'Иванов', duration_hours: 2 },
  { id: 2, title: 'Book B', description: 'b', instructor: 'Петров', duration_hours: 3 },
]

let wrapper
beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  wrapper?.unmount()
  vi.useRealTimers()
})

async function mountHome(opts) {
  const result = await mountView(HomeView, opts)
  wrapper = result.wrapper
  await flushPromises()
  return result
}

describe('HomeView', () => {
  it('показывает список данных после успешной загрузки', async () => {
    apiClient.get.mockResolvedValue({ data: COURSES })
    await mountHome()
    expect(wrapper.text()).toContain('Book A')
    expect(wrapper.text()).toContain('Book B')
    expect(wrapper.findAll('.course-card')).toHaveLength(2)
    expect(wrapper.find('.state.loading').exists()).toBe(false)
  })

  it('показывает ошибку и кнопку «Повторить», которая перезапрашивает список', async () => {
    apiClient.get.mockRejectedValueOnce(new Error('Network Error'))
    await mountHome()
    expect(wrapper.find('.state.error').text()).toContain('Сервер недоступен')

    apiClient.get.mockResolvedValue({ data: COURSES })
    await wrapper.find('.state.error button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.course-card')).toHaveLength(2)
  })

  it('показывает сообщение о пустом списке', async () => {
    apiClient.get.mockResolvedValue({ data: [] })
    await mountHome()
    expect(wrapper.find('.state.empty').text()).toBe('Пока нет ни одной записи')
  })

  it('пока данные грузятся, показывает «Загрузка…»', async () => {
    apiClient.get.mockReturnValue(new Promise(() => {}))
    await mountHome()
    expect(wrapper.find('.state.loading').text()).toBe('Загрузка…')
  })

  it('загружает курсы через useResource: GET /courses один раз', async () => {
    apiClient.get.mockResolvedValue({ data: [] })
    await mountHome()
    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(apiClient.get).toHaveBeenCalledWith('/courses', { params: {} })
  })

  it('кнопка «+ Добавить» видна только администратору и ведёт на создание', async () => {
    apiClient.get.mockResolvedValue({ data: [] })
    const { push } = await mountHome({ role: 'admin' })
    const add = wrapper.findAll('button').find((b) => b.text().includes('Добавить'))
    await add.trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'course-create' })
    wrapper.unmount()

    await mountHome({ role: 'user' })
    expect(wrapper.text()).not.toContain('Добавить')
  })

  it('карточка — ссылка на страницу деталей', async () => {
    apiClient.get.mockResolvedValue({ data: COURSES })
    await mountHome()
    expect(wrapper.find('.course-card a').attributes('href')).toBe('/courses/1')
  })

  it('поиск: запрос уходит после паузы 300 мс (debounce), а не на каждую букву', async () => {
    vi.useFakeTimers()
    apiClient.get.mockResolvedValue({ data: COURSES })
    await mountHome()
    apiClient.get.mockClear()

    const input = wrapper.find('#search')
    await input.setValue('И')
    await input.setValue('Ив')
    await input.setValue('Иванов')
    vi.advanceTimersByTime(299)
    expect(apiClient.get).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(apiClient.get).toHaveBeenCalledWith('/courses', { params: { instructor: 'Иванов' } })
  })

  it('пустой результат поиска — «Ничего не найдено»', async () => {
    vi.useFakeTimers()
    apiClient.get.mockResolvedValueOnce({ data: COURSES }).mockResolvedValue({ data: [] })
    await mountHome()
    await wrapper.find('#search').setValue('Нет такого')
    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(wrapper.find('.state.empty').text()).toBe('Ничего не найдено')
  })

  it('экранирует HTML из БД (нет XSS)', async () => {
    apiClient.get.mockResolvedValue({
      data: [
        {
          id: 1,
          title: '<img src=x onerror=alert(1)>',
          description: '<b>b</b>',
          instructor: 'i',
          duration_hours: 1,
        },
      ],
    })
    await mountHome()
    expect(wrapper.find('.items-list img').exists()).toBe(false)
    expect(wrapper.find('.course-card h3').text()).toBe('<img src=x onerror=alert(1)>')
  })

  it('«+ Добавить» видит модератор (лаб. № 8), клиент — нет', async () => {
    apiClient.get.mockResolvedValue({ data: COURSES })
    await mountHome({ role: 'moderator' })
    expect(wrapper.text()).toContain('Добавить')
    wrapper.unmount()
    await mountHome({ role: 'client' })
    expect(wrapper.text()).not.toContain('Добавить')
  })

  it('плашка «Скрыто курсов 18+» по заголовку X-Age-Restricted-Hidden', async () => {
    apiClient.get.mockResolvedValue({
      data: COURSES,
      headers: { 'x-age-restricted-hidden': '2' },
    })
    const { push } = await mountHome({ role: 'client' })
    expect(wrapper.find('.age-banner').text()).toContain('Скрыто курсов 18+: 2')
    await wrapper.find('.age-banner button').trigger('click')
    expect(push).toHaveBeenCalledWith('/verify-age')
  })

  it('без скрытых курсов плашки нет', async () => {
    apiClient.get.mockResolvedValue({ data: COURSES, headers: { 'x-age-restricted-hidden': '0' } })
    await mountHome({ role: 'client' })
    expect(wrapper.find('.age-banner').exists()).toBe(false)
  })
})
