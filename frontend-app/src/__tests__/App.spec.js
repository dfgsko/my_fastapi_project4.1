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

function mountApp(isAuthenticated) {
  const wrapper = mount(App, {
    global: {
      plugins: [
        createTestingPinia({
          createSpy: vi.fn,
          initialState: { auth: { token: isAuthenticated ? 'jwt' : null } },
        }),
      ],
      stubs: { RouterLink: RouterLinkStub, RouterView: true },
    },
  })
  return { wrapper, store: useAuthStore() }
}

describe('App.vue', () => {
  it('для гостя показывает только Login', () => {
    const nav = mountApp(false).wrapper.find('nav').text()
    expect(nav).toContain('Login')
    expect(nav).not.toContain('Logout')
    expect(nav).not.toContain('Главная')
  })

  it('для авторизованного показывает «Главная» и Logout вместо Login', () => {
    const nav = mountApp(true).wrapper.find('nav').text()
    expect(nav).toContain('Главная')
    expect(nav).toContain('Logout')
    expect(nav).not.toContain('Login')
  })

  it('кнопка Logout вызывает store.logout', async () => {
    const { wrapper, store } = mountApp(true)
    await wrapper.find('nav button').trigger('click')
    expect(store.logout).toHaveBeenCalledTimes(1)
  })

  it('содержит <router-view> для страниц', () => {
    const { wrapper } = mountApp(false)
    expect(wrapper.find('main').exists()).toBe(true)
    expect(wrapper.html()).toContain('router-view')
  })
})
