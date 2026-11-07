// Тест 2 из методички: AccountView — переключение вкладок и шапка с username.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AccountView from '@/views/AccountView.vue'

// Мокаем дочерние компоненты, чтобы тест проверял только логику вкладок.
vi.mock('@/components/account/AccountProfileTab.vue', () => ({
  default: { template: '<div data-testid="tab-profile">Profile</div>' },
}))
vi.mock('@/components/account/AccountSettingsTab.vue', () => ({
  default: { template: '<div data-testid="tab-settings">Settings</div>' },
}))
vi.mock('@/components/account/AccountSecurityTab.vue', () => ({
  default: { template: '<div data-testid="tab-security">Security</div>' },
}))
vi.mock('@/components/account/AccountSessionsTab.vue', () => ({
  default: { template: '<div data-testid="tab-sessions">Sessions</div>' },
}))
// Роутер: ?tab= отсутствует, replace — заглушка.
const replace = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace, push: vi.fn() }),
}))

describe('AccountView', () => {
  function mountView() {
    return mount(AccountView, {
      global: {
        plugins: [
          createTestingPinia({
            createSpy: vi.fn,
            initialState: {
              auth: { user: { username: 'testuser', display_name: 'Test User', role: 'client' } },
            },
          }),
        ],
      },
    })
  }

  it('по умолчанию открыта вкладка «Профиль»', () => {
    const wrapper = mountView()
    expect(wrapper.find('[data-testid="tab-profile"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tab-settings"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="tab-security"]').exists()).toBe(false)
  })

  it('переключается на «Безопасность» по клику', async () => {
    const wrapper = mountView()
    const buttons = wrapper.findAll('.tab')
    const securityBtn = buttons.find((b) => b.text() === 'Безопасность')
    await securityBtn.trigger('click')

    expect(wrapper.find('[data-testid="tab-security"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tab-profile"]').exists()).toBe(false)
    // Активная вкладка попадает в адрес (?tab=security) — на неё можно дать ссылку.
    expect(replace).toHaveBeenCalledWith({ query: { tab: 'security', age: undefined } })
  })

  it('есть четыре вкладки, включая «Сессии»', async () => {
    const wrapper = mountView()
    expect(wrapper.findAll('.tab').map((b) => b.text())).toEqual([
      'Профиль',
      'Настройки',
      'Безопасность',
      'Сессии',
    ])
    await wrapper.findAll('.tab').at(3).trigger('click')
    expect(wrapper.find('[data-testid="tab-sessions"]').exists()).toBe(true)
  })

  it('показывает username в шапке', () => {
    const wrapper = mountView()
    expect(wrapper.text()).toContain('@testuser')
    expect(wrapper.text()).toContain('Test User')
  })

  it('показывает инициал в аватаре-заглушке, если avatar_url пуст', () => {
    const wrapper = mountView()
    expect(wrapper.find('.avatar-placeholder').text()).toBe('T')
  })
})
