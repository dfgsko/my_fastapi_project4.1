import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import RootView from '@/views/RootView.vue'
import LandingView from '@/views/LandingView.vue'
import ModerationView from '@/views/ModerationView.vue'
import apiClient from '@/api/client'
import { mountView } from '@/test-utils'

vi.mock('@/api/client')

let wrapper
beforeEach(() => vi.clearAllMocks())
afterEach(() => wrapper?.unmount())

describe('LandingView / RootView', () => {
  it('гость на «/» видит лендинг, курсы не запрашиваются', async () => {
    ;({ wrapper } = await mountView(RootView, { role: null }))
    await flushPromises()
    expect(wrapper.find('.landing').exists()).toBe(true)
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('вошедший на «/» видит список курсов', async () => {
    apiClient.get.mockResolvedValue({ data: [] })
    ;({ wrapper } = await mountView(RootView, { role: 'client' }))
    await flushPromises()
    expect(wrapper.find('.landing').exists()).toBe(false)
    expect(wrapper.find('h1').text()).toBe('Курсы')
  })

  it('кнопки ведут на /register и /login', async () => {
    const { wrapper: w, push } = await mountView(LandingView, { role: null })
    wrapper = w
    const btn = (t) => w.findAll('button').find((b) => b.text() === t)
    await btn('Создать аккаунт').trigger('click')
    await btn('Войти').trigger('click')
    expect(push.mock.calls.map((c) => c[0])).toEqual(['/register', '/login'])
  })
})

const USERS = [
  { id: 1, username: 'admin', role: 'admin', is_active: true, email: 'a@x', totp_enabled: true },
  { id: 2, username: 'moder', role: 'moderator', is_active: true, email: 'm@x' },
  { id: 3, username: 'student', role: 'client', is_active: true, email: 's@x' },
]

async function mountModeration(role, me) {
  apiClient.get.mockResolvedValue({ data: structuredClone(USERS) })
  const result = await mountView(ModerationView, { role })
  wrapper = result.wrapper
  // id текущего пользователя для правила «не к себе»
  const { useAuthStore } = await import('@/stores/auth')
  useAuthStore().user = { ...useAuthStore().user, id: me }
  await flushPromises()
  return result
}
const row = (username) => wrapper.findAll('tbody tr').find((r) => r.text().includes(`@${username}`))

describe('ModerationView', () => {
  it('модератор может наказать клиента, но не модератора и не админа; ролей не меняет', async () => {
    await mountModeration('moderator', 2)
    expect(row('student').findAll('button')).toHaveLength(2)
    expect(row('admin').findAll('button')).toHaveLength(0)
    expect(row('moder').findAll('button')).toHaveLength(0)
    expect(wrapper.find('select').exists()).toBe(false)
  })

  it('сброс username клиента — через подтверждение', async () => {
    await mountModeration('moderator', 2)
    apiClient.post.mockResolvedValue({ data: { ...USERS[2], username: 'user3' } })
    await row('student').findAll('button')[0].trigger('click')
    const confirm = [...document.body.querySelectorAll('[role="dialog"] button')].find(
      (b) => b.textContent.trim() === 'Подтвердить',
    )
    confirm.click()
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/users/3/reset-username')
    expect(row('user3')).toBeTruthy()
  })

  it('администратор меняет роль через select (кроме своей)', async () => {
    await mountModeration('admin', 1)
    apiClient.patch.mockResolvedValue({ data: { ...USERS[2], role: 'moderator' } })
    expect(row('admin').find('select').exists()).toBe(false)
    await row('student').find('select').setValue('moderator')
    await flushPromises()
    expect(apiClient.patch).toHaveBeenCalledWith('/users/3', { role: 'moderator' })
  })
})
