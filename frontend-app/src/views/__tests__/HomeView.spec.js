import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import HomeView from '@/views/HomeView.vue'
import apiClient from '@/api/client'

vi.mock('@/api/client')

describe('HomeView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mountWithPinia = () =>
    mount(HomeView, {
      global: { plugins: [createTestingPinia({ createSpy: vi.fn })] },
    })

  it('показывает список данных после успешной загрузки', async () => {
    apiClient.get.mockResolvedValue({
      data: [
        { id: 1, title: 'Book A' },
        { id: 2, title: 'Book B' },
      ],
    })

    const wrapper = mountWithPinia()
    await flushPromises()

    expect(wrapper.text()).toContain('Book A')
    expect(wrapper.text()).toContain('Book B')
    expect(wrapper.find('.items-list').exists()).toBe(true)
    expect(wrapper.find('.state.loading').exists()).toBe(false)
  })

  it('показывает сообщение об ошибке при неудачном запросе', async () => {
    apiClient.get.mockRejectedValue(new Error('Network Error'))
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    const wrapper = mountWithPinia()
    await flushPromises()

    expect(wrapper.find('.state.error').exists()).toBe(true)
    expect(wrapper.text()).toContain('Не удалось загрузить данные')
    expect(wrapper.find('.items-list').exists()).toBe(false)
    consoleError.mockRestore()
  })

  it('показывает сообщение о пустом списке', async () => {
    apiClient.get.mockResolvedValue({ data: [] })

    const wrapper = mountWithPinia()
    await flushPromises()

    expect(wrapper.find('.state.empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('Пока нет ни одной записи')
  })

  it('пока данные грузятся, показывает «Загрузка…», а не пустой список', async () => {
    apiClient.get.mockReturnValue(new Promise(() => {})) // запрос «висит»

    const wrapper = mountWithPinia()
    await flushPromises()

    expect(wrapper.find('.state.loading').text()).toBe('Загрузка…')
    expect(wrapper.find('.state.empty').exists()).toBe(false)
    expect(wrapper.find('.items-list').exists()).toBe(false)
  })

  it('запрашивает курсы с эндпоинта /courses ровно один раз', async () => {
    apiClient.get.mockResolvedValue({ data: [] })
    mountWithPinia()
    await flushPromises()
    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(apiClient.get).toHaveBeenCalledWith('/courses')
  })

  it('отображает поля курса: название, описание, преподавателя и часы', async () => {
    apiClient.get.mockResolvedValue({
      data: [
        {
          id: 7,
          title: 'Kubernetes',
          description: 'Основы оркестрации',
          instructor: 'Иванов И.И.',
          duration_hours: 16,
        },
      ],
    })
    const wrapper = mountWithPinia()
    await flushPromises()

    const card = wrapper.find('.item-card')
    expect(card.find('h3').text()).toBe('Kubernetes')
    expect(card.text()).toContain('Основы оркестрации')
    expect(card.text()).toContain('Иванов И.И.')
    expect(card.text()).toContain('16 ч')
  })

  it('экранирует HTML из БД (нет XSS)', async () => {
    apiClient.get.mockResolvedValue({
      data: [{ id: 1, title: '<img src=x onerror=alert(1)>', description: '<b>bold</b>' }],
    })
    const wrapper = mountWithPinia()
    await flushPromises()

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('.description b').exists()).toBe(false)
    expect(wrapper.find('h3').text()).toBe('<img src=x onerror=alert(1)>')
  })
})
