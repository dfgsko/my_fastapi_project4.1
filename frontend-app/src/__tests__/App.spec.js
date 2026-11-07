import { describe, it, expect, vi } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import App from '@/App.vue'
import { useAuthStore } from '@/stores/auth'

// Store вызывает useRouter(); в изолированном тесте компонента роутера нет.
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal()),
  useRouter: () => ({ push: vi.fn() }),
}))

function mountApp(user) {
  const wrapper = mount(App, {
    attachTo: document.body,
    global: {
      plugins: [
        createTestingPinia({
          createSpy: vi.fn,
          initialState: { auth: { user, initialized: true } },
        }),
      ],
      stubs: { RouterLink: RouterLinkStub, RouterView: true },
    },
  })
  return { wrapper, store: useAuthStore() }
}

describe('App.vue', () => {
  it('для гостя показывает «Войти» и «Регистрация»', () => {
    const nav = mountApp(null).wrapper.find('nav').text()
    expect(nav).toContain('Войти')
    expect(nav).toContain('Регистрация')
    expect(nav).not.toContain('Выйти')
  })

  it('для вошедшего показывает меню с ником, без «Войти»', () => {
    const nav = mountApp({ username: 'anna', display_name: 'Анна', role: 'client' }).wrapper.find(
      'nav',
    )
    expect(nav.text()).toContain('Анна')
    expect(nav.text()).not.toContain('Войти')
    expect(nav.find('.user-menu').exists()).toBe(true)
  })

  it('пункт «Модерация» виден только модератору и администратору', () => {
    expect(mountApp({ username: 'c', role: 'client' }).wrapper.text()).not.toContain('Модерация')
    expect(mountApp({ username: 'm', role: 'moderator' }).wrapper.text()).toContain('Модерация')
  })

  it('«Выйти» в меню вызывает store.logout', async () => {
    const { wrapper, store } = mountApp({ username: 'anna', role: 'client' })
    await wrapper.find('.user-menu .trigger').trigger('click')
    const logout = wrapper.findAll('.dropdown button').find((b) => b.text() === 'Выйти')
    await logout.trigger('click')
    expect(store.logout).toHaveBeenCalledTimes(1)
  })

  it('аватар-заглушка показывает первую букву ника', () => {
    const { wrapper } = mountApp({ username: 'anna', display_name: 'Борис', role: 'client' })
    expect(wrapper.find('.avatar-placeholder').text()).toBe('Б')
  })

  it('содержит <router-view> для страниц', () => {
    const { wrapper } = mountApp(null)
    expect(wrapper.find('main').exists()).toBe(true)
    expect(wrapper.html()).toContain('router-view')
  })
})
