import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PasswordChangeCard from '@/components/account/security/PasswordChangeCard.vue'
import EmailVerificationCard from '@/components/account/security/EmailVerificationCard.vue'
import apiClient from '@/api/client'

vi.mock('@/api/client')
beforeEach(() => vi.clearAllMocks())

const fieldText = (wrapper, id) => wrapper.find(`#${id}`).element.closest('.base-input').textContent

describe('PasswordChangeCard', () => {
  async function fillAndSubmit(
    wrapper,
    { old = 'Old-passw0rd-1', next = 'New-passw0rd-22', again } = {},
  ) {
    await wrapper.find('#oldPassword').setValue(old)
    await wrapper.find('#newPassword').setValue(next)
    await wrapper.find('#confirmNewPassword').setValue(again ?? next)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
  }

  it('показывает дату последней смены пароля', async () => {
    apiClient.get.mockResolvedValue({ data: { password_changed_at: '2026-11-01T10:00:00Z' } })
    const wrapper = mount(PasswordChangeCard)
    await flushPromises()
    expect(wrapper.text()).toContain('01.11.2026')
  })

  it('отправляет текущий и новый пароль, после успеха очищает форму', async () => {
    apiClient.get.mockResolvedValue({ data: {} })
    apiClient.post.mockResolvedValue({})
    const wrapper = mount(PasswordChangeCard)
    await fillAndSubmit(wrapper)
    expect(apiClient.post).toHaveBeenCalledWith('/auth/change-password', {
      current_password: 'Old-passw0rd-1',
      new_password: 'New-passw0rd-22',
    })
    expect(wrapper.find('#oldPassword').element.value).toBe('')
  })

  it('неверный текущий пароль (400) — ошибка под полем', async () => {
    apiClient.get.mockResolvedValue({ data: {} })
    apiClient.post.mockRejectedValue({
      response: { status: 400, data: { detail: 'Текущий пароль неверен' } },
    })
    const wrapper = mount(PasswordChangeCard)
    await fillAndSubmit(wrapper)
    expect(fieldText(wrapper, 'oldPassword')).toContain('Неверный текущий пароль')
  })

  it('короткий и несовпадающий новый пароль — без запроса', async () => {
    apiClient.get.mockResolvedValue({ data: {} })
    const wrapper = mount(PasswordChangeCard)
    await fillAndSubmit(wrapper, { next: 'short', again: 'other' })
    expect(fieldText(wrapper, 'newPassword')).toContain('Минимум 12 символов')
    expect(fieldText(wrapper, 'confirmNewPassword')).toContain('Пароли не совпадают')
    expect(apiClient.post).not.toHaveBeenCalled()
  })
})

describe('EmailVerificationCard', () => {
  it('подтверждён — зелёный статус, дата, без кнопки', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        email: 'a@example.com',
        is_email_verified: true,
        email_verified_at: '2026-11-02T00:00:00Z',
      },
    })
    const wrapper = mount(EmailVerificationCard)
    await flushPromises()
    expect(wrapper.find('.badge-on').text()).toContain('Подтверждён')
    expect(wrapper.text()).toContain('02.11.2026')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('не подтверждён — предупреждение и повторная отправка', async () => {
    apiClient.get.mockResolvedValue({ data: { email: 'a@example.com', is_email_verified: false } })
    apiClient.post.mockResolvedValue({})
    const wrapper = mount(EmailVerificationCard)
    await flushPromises()
    expect(wrapper.find('.badge-off').exists()).toBe(true)
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/auth/resend-verification')
  })
})
