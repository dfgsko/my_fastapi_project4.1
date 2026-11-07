import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import RegisterView from '@/views/RegisterView.vue'
import apiClient from '@/api/client'

const push = vi.fn()
vi.mock('@/api/client')
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

const stubs = { RouterLink: { template: '<a><slot /></a>' } }
function mountView() {
  return mount(RegisterView, {
    global: { plugins: [createTestingPinia({ createSpy: vi.fn })], stubs },
  })
}
async function fill(wrapper, values) {
  const v = {
    username: 'anna_s',
    email: 'anna@example.com',
    password: 'Long-passw0rd',
    confirmPassword: 'Long-passw0rd',
    ...values,
  }
  for (const [id, value] of Object.entries(v)) await wrapper.find(`#${id}`).setValue(value)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}
const fieldText = (wrapper, id) => wrapper.find(`#${id}`).element.closest('.base-input').textContent

describe('RegisterView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('валидация на клиенте: длина пароля ≥ 12, совпадение, формат email', async () => {
    const wrapper = mountView()
    await fill(wrapper, {
      username: 'a',
      email: 'not-an-email',
      password: 'short1',
      confirmPassword: 'other',
    })
    expect(fieldText(wrapper, 'username')).toContain('Минимум 3 символа')
    expect(fieldText(wrapper, 'email')).toContain('Некорректный email')
    expect(fieldText(wrapper, 'password')).toContain('Минимум 12 символов')
    expect(fieldText(wrapper, 'confirmPassword')).toContain('Пароли не совпадают')
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('отправляет JSON без confirmPassword', async () => {
    apiClient.post.mockResolvedValue({ data: { requires_age_verification: true } })
    await fill(mountView())
    expect(apiClient.post).toHaveBeenCalledWith('/auth/register', {
      username: 'anna_s',
      email: 'anna@example.com',
      password: 'Long-passw0rd',
    })
  })

  it('requires_age_verification → /verify-age?registration=true', async () => {
    apiClient.post.mockResolvedValue({ data: { requires_age_verification: true } })
    await fill(mountView())
    expect(push).toHaveBeenCalledWith({ name: 'verify-age', query: { registration: 'true' } })
  })

  it('без проверки возраста → «Проверьте почту»', async () => {
    apiClient.post.mockResolvedValue({
      data: { requires_age_verification: false, email: 'anna@example.com' },
    })
    await fill(mountView())
    expect(push).toHaveBeenCalledWith({
      name: 'check-email',
      query: { email: 'anna@example.com' },
    })
  })

  it('409 по email — сообщение под полем email', async () => {
    apiClient.post.mockRejectedValue({
      response: { status: 409, data: { detail: 'Этот email уже зарегистрирован', field: 'email' } },
    })
    const wrapper = mountView()
    await fill(wrapper)
    expect(fieldText(wrapper, 'email')).toContain('Этот email уже зарегистрирован')
    expect(push).not.toHaveBeenCalled()
  })

  it('409 по логину — сообщение под полем username', async () => {
    apiClient.post.mockRejectedValue({
      response: { status: 409, data: { detail: 'Этот логин уже занят', field: 'username' } },
    })
    const wrapper = mountView()
    await fill(wrapper)
    expect(fieldText(wrapper, 'username')).toContain('Этот логин уже занят')
  })
})
