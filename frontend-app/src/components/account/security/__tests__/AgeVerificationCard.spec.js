// Тест 1 из методички: AgeVerificationCard — состояния verified / not verified / hidden.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AgeVerificationCard from '@/components/account/security/AgeVerificationCard.vue'
import apiClient from '@/api/client'

const mockPush = vi.fn()
vi.mock('@/api/client')
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {} }),
}))

describe('AgeVerificationCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountCard() {
    return mount(AgeVerificationCard, {
      global: { plugins: [createTestingPinia({ createSpy: vi.fn })] },
    })
  }

  it('показывает кнопку «Подтвердить возраст», если верификация не пройдена', async () => {
    apiClient.get.mockResolvedValue({
      data: { age_verification_required: true, is_age_verified: false, age_verified_at: null },
    })

    const wrapper = mountCard()
    await flushPromises()

    expect(wrapper.text()).toContain('Не подтверждён')
    expect(wrapper.text()).toContain('Подтвердить возраст')
    expect(wrapper.text()).toContain('больше 18 лет')
  })

  it('показывает статус «Подтверждён» и дату, если верификация пройдена', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        age_verification_required: true,
        is_age_verified: true,
        age_verified_at: '2026-10-15T10:00:00Z',
      },
    })

    const wrapper = mountCard()
    await flushPromises()

    expect(wrapper.text()).toContain('Подтверждён')
    expect(wrapper.text()).toContain('15.10.2026')
    // Кнопка должна исчезнуть
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('скрывается, если верификация в системе не требуется', async () => {
    apiClient.get.mockResolvedValue({
      data: { age_verification_required: false, is_age_verified: false },
    })

    const wrapper = mountCard()
    await flushPromises()

    expect(wrapper.find('.security-card').exists()).toBe(false)
  })

  it('видна тому, кто пропустил проверку при регистрации (функция включена)', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        age_verification_required: false,
        age_verification_available: true,
        is_age_verified: false,
      },
    })
    const wrapper = mountCard()
    await flushPromises()
    expect(wrapper.find('.security-card').exists()).toBe(true)
    expect(wrapper.text()).toContain('Подтвердить возраст')
  })

  it('скрывается при ошибке запроса /auth/me', async () => {
    apiClient.get.mockRejectedValue(new Error('Network Error'))

    const wrapper = mountCard()
    await flushPromises()

    expect(wrapper.find('.security-card').exists()).toBe(false)
  })

  it('переходит на /verify-age при клике на кнопку', async () => {
    apiClient.get.mockResolvedValue({
      data: { age_verification_required: true, is_age_verified: false },
    })

    const wrapper = mountCard()
    await flushPromises()

    await wrapper.find('button').trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/verify-age')
  })
})
