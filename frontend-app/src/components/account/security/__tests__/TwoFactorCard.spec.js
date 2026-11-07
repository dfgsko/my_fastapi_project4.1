// Тест 3 из методички: TwoFactorCard — включение 2FA через модалку с QR-кодом.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import TwoFactorCard from '@/components/account/security/TwoFactorCard.vue'
import apiClient from '@/api/client'

vi.mock('@/api/client')

describe('TwoFactorCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountCard() {
    return mount(TwoFactorCard, {
      global: {
        plugins: [createTestingPinia({ createSpy: vi.fn })],
        // BaseModal рендерится через <Teleport to="body">: заглушка оставляет
        // содержимое модалки внутри wrapper, иначе wrapper.find его не увидит.
        stubs: { teleport: true },
      },
    })
  }

  it('показывает статус «Выключена», если 2FA не включена', async () => {
    apiClient.get.mockResolvedValue({ data: { totp_enabled: false } })

    const wrapper = mountCard()
    await flushPromises()

    expect(wrapper.find('.badge-off').exists()).toBe(true)
    expect(wrapper.text()).toContain('Включить')
  })

  it('показывает статус «Включена» и дату, если 2FA активна', async () => {
    apiClient.get.mockResolvedValue({
      data: { totp_enabled: true, totp_enabled_at: '2026-09-01T00:00:00Z' },
    })

    const wrapper = mountCard()
    await flushPromises()

    expect(wrapper.find('.badge-on').exists()).toBe(true)
    expect(wrapper.text()).toContain('Отключить')
    expect(wrapper.text()).toContain('01.09.2026')
  })

  it('открывает модалку с QR-кодом при клике «Включить»', async () => {
    apiClient.get.mockResolvedValue({ data: { totp_enabled: false } })
    apiClient.post.mockResolvedValue({
      data: { qr_code: 'FAKE_QR_BASE64', secret: 'SECRET123' },
    })

    const wrapper = mountCard()
    await flushPromises()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(apiClient.post).toHaveBeenCalledWith('/auth/2fa/enable')
    expect(wrapper.find('img').attributes('src')).toContain('FAKE_QR_BASE64')
    expect(wrapper.text()).toContain('SECRET123')
  })

  it('включает 2FA после подтверждения кода', async () => {
    apiClient.get.mockResolvedValue({ data: { totp_enabled: false } })
    apiClient.post
      .mockResolvedValueOnce({ data: { qr_code: 'QR', secret: 'SEC' } })
      .mockResolvedValueOnce({ data: { detail: '2FA enabled' } })

    const wrapper = mountCard()
    await flushPromises()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    // Находим поле для кода внутри модалки и вводим код
    const codeInput = wrapper.findAll('input').at(-1)
    await codeInput.setValue('123456')

    // Кнопка «Подтвердить» — последняя в модалке
    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text() === 'Подтвердить')
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(apiClient.post).toHaveBeenCalledWith('/auth/2fa/confirm', { code: '123456' })
    expect(wrapper.find('.badge-on').exists()).toBe(true)
  })

  it('после подтверждения показывает коды восстановления один раз', async () => {
    apiClient.get.mockResolvedValue({ data: { totp_enabled: false } })
    apiClient.post
      .mockResolvedValueOnce({ data: { qr_code: 'QR', secret: 'SEC' } })
      .mockResolvedValueOnce({ data: { recovery_codes: ['aaa-111', 'bbb-222'] } })
    const wrapper = mountCard()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    await wrapper.findAll('input').at(-1).setValue('123456')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Подтвердить')
      .trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.codes li').map((li) => li.text())).toEqual(['aaa-111', 'bbb-222'])
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Я сохранил коды')
      .trigger('click')
    expect(wrapper.find('.codes').exists()).toBe(false)
  })

  it('неверный код — сообщение «Неверный код», 2FA остаётся выключенной', async () => {
    apiClient.get.mockResolvedValue({ data: { totp_enabled: false } })
    apiClient.post
      .mockResolvedValueOnce({ data: { qr_code: 'QR', secret: 'SEC' } })
      .mockRejectedValueOnce({ response: { status: 400 } })
    const wrapper = mountCard()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    await wrapper.findAll('input').at(-1).setValue('000000')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Подтвердить')
      .trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Неверный код')
    expect(wrapper.find('.badge-off').exists()).toBe(true)
  })

  it('отключение требует код', async () => {
    apiClient.get.mockResolvedValue({ data: { totp_enabled: true } })
    apiClient.post.mockResolvedValue({ data: { detail: '2FA disabled' } })
    const wrapper = mountCard()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Отключить')
      .trigger('click')
    await wrapper.find('#disableCode').setValue('654321')
    const buttons = wrapper.findAll('button').filter((b) => b.text() === 'Отключить')
    await buttons.at(-1).trigger('click')
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/auth/2fa/disable', { code: '654321' })
    expect(wrapper.find('.badge-off').exists()).toBe(true)
  })
})
