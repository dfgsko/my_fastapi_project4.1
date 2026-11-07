import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AgeVerificationView from '@/views/AgeVerificationView.vue'
import AgeVerificationWidget from '@/components/AgeVerificationWidget.vue'
import apiClient from '@/api/client'

const push = vi.fn()
const query = { registration: 'true' }
vi.mock('@/api/client')
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query }),
}))

const stubs = { RouterLink: { template: '<a><slot /></a>' } }
const photo = (type = 'image/jpeg', size = 1000) => {
  const f = new File(['x'.repeat(size)], 'me.jpg', { type })
  return f
}
async function choose(wrapper, file) {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

beforeEach(() => {
  vi.clearAllMocks()
  query.registration = 'true'
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview')
  globalThis.URL.revokeObjectURL = vi.fn()
})

describe('AgeVerificationWidget', () => {
  it('показывает превью и отправляет multipart/form-data с полем photo', async () => {
    apiClient.post.mockResolvedValue({ data: { verified: true, estimator: 'mock' } })
    const wrapper = mount(AgeVerificationWidget)
    await choose(wrapper, photo())
    expect(wrapper.find('.preview img').attributes('src')).toBe('blob:preview')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    const [url, body, config] = apiClient.post.mock.calls[0]
    expect(url).toBe('/auth/verify-age')
    expect(body.get('photo')).toBeInstanceOf(File)
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
    expect(wrapper.emitted('success')[0][0]).toEqual({ verified: true, estimator: 'mock' })
  })

  it('отклоняет SVG и слишком большие файлы ещё до отправки', async () => {
    const wrapper = mount(AgeVerificationWidget)
    await choose(wrapper, photo('image/svg+xml'))
    expect(wrapper.find('.error').text()).toContain('JPEG, PNG и WebP')
    await choose(wrapper, photo('image/png', 11 * 1024 * 1024))
    expect(wrapper.find('.error').text()).toContain('больше 10 МБ')
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('403 от бэкенда (младше 18) — показывает detail', async () => {
    apiClient.post.mockRejectedValue({
      response: { status: 403, data: { detail: 'Возраст не подтверждён: оценка 16.0 лет' } },
    })
    const wrapper = mount(AgeVerificationWidget)
    await choose(wrapper, photo())
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.error').text()).toContain('оценка 16.0 лет')
    expect(wrapper.emitted('success')).toBeUndefined()
  })
})

describe('AgeVerificationView', () => {
  function mountView() {
    return mount(AgeVerificationView, {
      global: { plugins: [createTestingPinia({ createSpy: vi.fn })], stubs },
    })
  }

  it('в регистрации после успеха вызывает complete-registration и ведёт на «Проверьте почту»', async () => {
    apiClient.post.mockResolvedValue({ data: { email: 'anna@example.com', email_sent: true } })
    const wrapper = mountView()
    wrapper.findComponent(AgeVerificationWidget).vm.$emit('success', { verified: true })
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/auth/complete-registration', {
      skip_age_verification: false,
    })
    expect(push).toHaveBeenCalledWith({
      name: 'check-email',
      query: { email: 'anna@example.com' },
    })
  })

  it('«Пропустить» — регистрация без проверки возраста', async () => {
    apiClient.post.mockResolvedValue({ data: { email: 'a@b.c' } })
    const wrapper = mountView()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Пропустить')
      .trigger('click')
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/auth/complete-registration', {
      skip_age_verification: true,
    })
  })

  it('из настроек: после успеха обновляет профиль и возвращает в «Безопасность»', async () => {
    query.registration = undefined
    const wrapper = mountView()
    expect(wrapper.text()).not.toContain('Пропустить')
    wrapper.findComponent(AgeVerificationWidget).vm.$emit('success', { verified: true })
    await flushPromises()
    expect(apiClient.post).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith({ name: 'account', query: { tab: 'security' } })
  })

  it('истекла cookie регистрации (401) — понятное сообщение', async () => {
    apiClient.post.mockRejectedValue({ response: { status: 401 } })
    const wrapper = mountView()
    wrapper.findComponent(AgeVerificationWidget).vm.$emit('success', { verified: true })
    await flushPromises()
    expect(wrapper.find('.error').text()).toContain('Сессия регистрации истекла')
  })
})
