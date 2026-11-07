// Тест 4 из методички: VerifyEmailView — три состояния, обратный отсчёт и редирект.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import VerifyEmailView from '@/views/VerifyEmailView.vue'
import apiClient from '@/api/client'

const mockPush = vi.fn()
const mockQuery = { token: 'test-token' }

vi.mock('@/api/client')
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: mockQuery }),
  RouterLink: { template: '<a><slot /></a>' },
}))

describe('VerifyEmailView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockQuery.token = 'test-token'
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function mountView() {
    return mount(VerifyEmailView, {
      global: {
        plugins: [createTestingPinia({ createSpy: vi.fn })],
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
  }

  it('показывает счётчик ожидания, пока идёт запрос', async () => {
    // Управляем разрешением промиса вручную
    let resolveApi
    apiClient.get.mockReturnValue(
      new Promise((r) => {
        resolveApi = r
      }),
    )

    const wrapper = mountView()

    // Счётчик стартует с 0
    expect(wrapper.find('.counter').text()).toContain('0 сек.')

    // Прокручиваем 3 секунды — счётчик должен увеличиться
    await vi.advanceTimersByTimeAsync(3000)
    expect(wrapper.find('.counter').text()).toContain('3 сек.')

    // Теперь разрешаем запрос
    resolveApi({})
    await flushPromises()

    expect(wrapper.find('.checkmark').exists()).toBe(true)
  })

  it('отправляет токен из ссылки в GET /auth/verify-email', async () => {
    apiClient.get.mockResolvedValue({})
    mountView()
    await flushPromises()
    expect(apiClient.get).toHaveBeenCalledWith('/auth/verify-email', {
      params: { token: 'test-token' },
    })
  })

  it('после успеха показывает галочку и обратный отсчёт 5 → 0', async () => {
    apiClient.get.mockResolvedValue({})

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.checkmark').exists()).toBe(true)
    expect(wrapper.text()).toContain('Email подтверждён')
    expect(wrapper.find('.redirect-hint strong').text()).toBe('5')

    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.find('.redirect-hint strong').text()).toBe('3')

    await vi.advanceTimersByTimeAsync(3000)
    expect(wrapper.find('.redirect-hint strong').text()).toBe('0')
  })

  it('после отсчёта редиректит на главную', async () => {
    apiClient.get.mockResolvedValue({})

    mountView()
    await flushPromises()

    await vi.advanceTimersByTimeAsync(5100) // 5 секунд + запас
    expect(mockPush).toHaveBeenCalledWith('/')
  })

  it('при ошибке показывает сообщение и не редиректит', async () => {
    apiClient.get.mockRejectedValue({
      response: { data: { detail: 'Ссылка истекла' } },
    })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.cross').exists()).toBe(true)
    expect(wrapper.text()).toContain('Ссылка истекла')

    await vi.advanceTimersByTimeAsync(10000)
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('показывает кнопку возврата на логин при ошибке', async () => {
    apiClient.get.mockRejectedValue(new Error('Network'))

    const wrapper = mountView()
    await flushPromises()

    const btn = wrapper.find('button')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('Вернуться')

    await btn.trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/login')
  })

  it('без токена в ссылке — сразу ошибка, запрос не отправляется', async () => {
    mockQuery.token = undefined
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.cross').exists()).toBe(true)
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('таймеры очищаются при уходе со страницы (onUnmounted)', async () => {
    apiClient.get.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(10000)
    expect(mockPush).not.toHaveBeenCalled() // отсчёт не дотикал до router.push
    expect(vi.getTimerCount()).toBe(0)
  })
})
