import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AccountSessionsTab from '@/components/account/AccountSessionsTab.vue'
import AccountProfileTab from '@/components/account/AccountProfileTab.vue'
import AccountSettingsTab from '@/components/account/AccountSettingsTab.vue'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'

const push = vi.fn()
vi.mock('@/api/client')
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ query: {} }) }))
beforeEach(() => vi.clearAllMocks())

const SESSIONS = [
  {
    id: 'cur',
    user_agent: 'Mozilla/5.0 (Windows NT 10.0) Chrome/130.0',
    ip_address: '10.0.0.1',
    started_at: '2026-11-06T10:00:00',
    last_active_at: '2026-11-06T11:00:00',
    current: true,
  },
  {
    id: 'phone',
    user_agent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1',
    ip_address: '10.0.0.2',
    started_at: '2026-11-05T09:00:00',
    last_active_at: '2026-11-05T09:30:00',
    current: false,
  },
]

function withPinia(component, user = { username: 'anna', role: 'client' }) {
  return mount(component, {
    global: {
      plugins: [createTestingPinia({ createSpy: vi.fn, initialState: { auth: { user } } })],
    },
  })
}

describe('AccountSessionsTab', () => {
  it('показывает сессии: устройство, IP, «Это устройство»', async () => {
    apiClient.get.mockResolvedValue({ data: SESSIONS })
    const wrapper = withPinia(AccountSessionsTab)
    await flushPromises()
    const items = wrapper.findAll('.session')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('Chrome · Windows')
    expect(items[0].text()).toContain('Это устройство')
    expect(items[1].text()).toContain('Safari · iOS')
    expect(items[1].text()).toContain('10.0.0.2')
  })

  it('отзыв чужой сессии убирает её из списка', async () => {
    apiClient.get.mockResolvedValue({ data: SESSIONS })
    apiClient.delete.mockResolvedValue({})
    const wrapper = withPinia(AccountSessionsTab)
    await flushPromises()
    await wrapper.findAll('.session')[1].find('button').trigger('click')
    await flushPromises()
    expect(apiClient.delete).toHaveBeenCalledWith('/auth/sessions/phone')
    expect(wrapper.findAll('.session')).toHaveLength(1)
    expect(push).not.toHaveBeenCalled()
  })

  it('отзыв текущей сессии = выход на /login', async () => {
    apiClient.get.mockResolvedValue({ data: SESSIONS })
    apiClient.delete.mockResolvedValue({})
    const wrapper = withPinia(AccountSessionsTab)
    await flushPromises()
    await wrapper.findAll('.session')[0].find('button').trigger('click')
    await flushPromises()
    expect(useAuthStore().clearSession).toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/login')
  })

  it('«Выйти со всех устройств» вызывает POST /auth/logout-all', async () => {
    apiClient.get.mockResolvedValue({ data: SESSIONS })
    apiClient.post.mockResolvedValue({})
    const wrapper = withPinia(AccountSessionsTab)
    await flushPromises()
    await wrapper.find('.head button').trigger('click')
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/auth/logout-all')
    expect(push).toHaveBeenCalledWith('/login')
  })
})

describe('AccountProfileTab', () => {
  const verified = {
    id: 1,
    username: 'anna',
    display_name: 'Анна',
    role: 'moderator',
    is_email_verified: true,
    email: 'anna@example.com',
  }

  it('карточка профиля: ник, @username, роль', () => {
    const wrapper = withPinia(AccountProfileTab, verified)
    expect(wrapper.find('.profile-card h2').text()).toBe('Анна')
    expect(wrapper.find('.username').text()).toBe('@anna')
    expect(wrapper.find('.role-badge').text()).toBe('Модератор')
  })

  it('без подтверждённого email — только карточка и баннер, без редактирования', () => {
    const wrapper = withPinia(AccountProfileTab, { ...verified, is_email_verified: false })
    expect(wrapper.find('.info-banner').text()).toContain('Аккаунт не активирован')
    expect(wrapper.find('#display_name').exists()).toBe(false)
  })

  it('кулдаун смены username: дата следующей смены, кнопка выключена', () => {
    const wrapper = withPinia(AccountProfileTab, {
      ...verified,
      next_username_change_at: '2099-05-01T00:00:00',
    })
    expect(wrapper.text()).toContain('Следующая смена доступна 01.05.2099')
    const btn = wrapper.findAll('button').find((b) => b.text() === 'Сменить')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('429 от сервера при смене username показывается под полем', async () => {
    apiClient.patch.mockRejectedValue({
      response: { status: 429, data: { detail: 'Username можно менять раз в 6 месяцев.' } },
    })
    const wrapper = withPinia(AccountProfileTab, verified)
    await wrapper.find('#new_username').setValue('anna_new')
    await wrapper.findAll('form').at(1).trigger('submit')
    await flushPromises()
    expect(apiClient.patch).toHaveBeenCalledWith('/users/me/username', { new_username: 'anna_new' })
    expect(wrapper.text()).toContain('раз в 6 месяцев')
  })
})

describe('AccountSettingsTab', () => {
  it('тема применяется к <html data-theme>', async () => {
    const wrapper = withPinia(AccountSettingsTab)
    await wrapper.find('#theme').setValue('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    await wrapper.find('#theme').setValue('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
