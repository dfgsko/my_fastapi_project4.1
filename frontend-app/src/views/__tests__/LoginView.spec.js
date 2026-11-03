import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import LoginView from '@/views/LoginView.vue'
import { useAuthStore } from '@/stores/auth'

// Store вызывает useRouter(); в изолированном тесте компонента роутера нет.
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal()),
  useRouter: () => ({ push: vi.fn() }),
}))

function mountView() {
  const wrapper = mount(LoginView, {
    global: { plugins: [createTestingPinia({ createSpy: vi.fn, stubActions: true })] },
  })
  return { wrapper, store: useAuthStore() }
}

async function fillAndSubmit(wrapper, user = 'testuser', pass = 'testpass') {
  await wrapper.find('input#username').setValue(user)
  await wrapper.find('input#password').setValue(pass)
  await wrapper.find('form').trigger('submit')
}

describe('LoginView', () => {
  it('вызывает store.login при отправке формы', async () => {
    const { wrapper, store } = mountView()

    await fillAndSubmit(wrapper)

    expect(store.login).toHaveBeenCalledWith('testuser', 'testpass')
    expect(store.login).toHaveBeenCalledTimes(1)
  })

  it('обрезает пробелы в логине, но не трогает пароль', async () => {
    const { wrapper, store } = mountView()
    await fillAndSubmit(wrapper, '  anna  ', ' pass with spaces ')
    expect(store.login).toHaveBeenCalledWith('anna', ' pass with spaces ')
  })

  it('блокирует кнопку и меняет подпись, пока идёт запрос', async () => {
    const { wrapper, store } = mountView()
    let finish
    store.login.mockReturnValue(new Promise((resolve) => (finish = resolve)))

    await fillAndSubmit(wrapper)

    const button = wrapper.find('button[type="submit"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toBe('Logging in…')

    finish()
    await flushPromises()
    expect(button.attributes('disabled')).toBeUndefined()
    expect(button.text()).toBe('Login')
  })

  it('показывает «Invalid username or password» при 401', async () => {
    const { wrapper, store } = mountView()
    store.login.mockRejectedValue({ response: { status: 401 } })

    await fillAndSubmit(wrapper)
    await flushPromises()

    expect(wrapper.find('.error').text()).toBe('Invalid username or password')
    expect(wrapper.find('button').attributes('disabled')).toBeUndefined()
  })

  it('отличает блокировку по числу попыток (429)', async () => {
    const { wrapper, store } = mountView()
    store.login.mockRejectedValue({ response: { status: 429 } })

    await fillAndSubmit(wrapper)
    await flushPromises()

    expect(wrapper.find('.error').text()).toContain('Слишком много попыток')
  })

  it('сообщает, что сервер недоступен (нет ответа)', async () => {
    const { wrapper, store } = mountView()
    store.login.mockRejectedValue(new Error('Network Error'))

    await fillAndSubmit(wrapper)
    await flushPromises()

    expect(wrapper.find('.error').text()).toContain('Сервер недоступен')
  })

  it('очищает прошлую ошибку при повторной отправке', async () => {
    const { wrapper, store } = mountView()
    store.login.mockRejectedValueOnce({ response: { status: 401 } })
    await fillAndSubmit(wrapper)
    await flushPromises()
    expect(wrapper.find('.error').exists()).toBe(true)

    store.login.mockResolvedValue(undefined)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.error').exists()).toBe(false)
  })

  it('поля обязательны, пароль скрыт', () => {
    const { wrapper } = mountView()
    expect(wrapper.find('input#username').attributes('required')).toBeDefined()
    expect(wrapper.find('input#password').attributes('required')).toBeDefined()
    expect(wrapper.find('input#password').attributes('type')).toBe('password')
  })
})
