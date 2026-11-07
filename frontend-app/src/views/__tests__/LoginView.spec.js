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
    expect(button.text()).toBe('Входим…')

    finish()
    await flushPromises()
    expect(button.attributes('disabled')).toBeUndefined()
    expect(button.text()).toBe('Войти')
  })

  it('показывает «Неверный логин или пароль» при 401', async () => {
    const { wrapper, store } = mountView()
    store.login.mockRejectedValue({ response: { status: 401 } })

    await fillAndSubmit(wrapper)
    await flushPromises()

    expect(wrapper.find('.error').text()).toBe('Неверный логин или пароль')
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

  it('email не подтверждён (403): сообщение и ссылка на повторную отправку', async () => {
    const { wrapper, store } = mountView()
    store.login.mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail: 'Email not verified. Please check your inbox.',
          code: 'email_not_verified',
        },
      },
    })
    await fillAndSubmit(wrapper)
    await flushPromises()
    expect(wrapper.find('.error').text()).toContain('Email not verified')
    expect(wrapper.find('.error').text()).toContain('Отправить письмо ещё раз')
  })

  it('не пройдена проверка возраста (403): кнопка «Пройти проверку возраста»', async () => {
    const { wrapper, store } = mountView()
    store.login.mockRejectedValue({
      response: {
        status: 403,
        data: { detail: 'Пройдите верификацию', code: 'age_verification_required' },
      },
    })
    await fillAndSubmit(wrapper)
    await flushPromises()
    expect(wrapper.find('.error button').text()).toContain('Пройти проверку возраста')
  })
})

describe('LoginView: второй шаг 2FA', () => {
  async function toSecondStep() {
    const ctx = mountView()
    ctx.store.login.mockResolvedValue({ twoFactor: true, tempToken: 'tmp-1' })
    await fillAndSubmit(ctx.wrapper, 'anna', 'pass-1234567')
    await flushPromises()
    return ctx
  }

  it('после пароля показывает поле для 6-значного кода, пароль стирается из формы', async () => {
    const { wrapper } = await toSecondStep()
    expect(wrapper.text()).toContain('Двухфакторная аутентификация')
    const code = wrapper.find('input#code')
    expect(code.attributes('maxlength')).toBe('6')
    expect(code.attributes('inputmode')).toBe('numeric')
    expect(wrapper.find('input#password').exists()).toBe(false)
  })

  it('отправляет temp_token и код в store.verifyTwoFactor', async () => {
    const { wrapper, store } = await toSecondStep()
    await wrapper.find('input#code').setValue('123456')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(store.verifyTwoFactor).toHaveBeenCalledWith('tmp-1', '123456')
  })

  it('неверный код (400) — сообщение, остаёмся на шаге кода', async () => {
    const { wrapper, store } = await toSecondStep()
    store.verifyTwoFactor.mockRejectedValue({ response: { status: 400 } })
    await wrapper.find('input#code').setValue('000000')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.error').text()).toContain('Неверный код')
    expect(wrapper.find('input#code').exists()).toBe(true)
  })

  it('истёк temp_token (401) — возврат на шаг пароля', async () => {
    const { wrapper, store } = await toSecondStep()
    store.verifyTwoFactor.mockRejectedValue({ response: { status: 401 } })
    await wrapper.find('input#code').setValue('123456')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('input#password').exists()).toBe(true)
    expect(wrapper.find('.error').text()).toContain('Время на ввод кода истекло')
  })

  it('можно переключиться на код восстановления', async () => {
    const { wrapper } = await toSecondStep()
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Нет доступа'))
      .trigger('click')
    expect(wrapper.find('input#code').attributes('maxlength')).toBe('20')
    expect(wrapper.text()).toContain('Код восстановления')
  })
})
