import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'

// Guard при первом переходе вызывает auth.init() → GET /auth/me.
vi.mock('@/api/client')

// Роутер — синглтон: guard берёт Pinia из ПЕРВОГО приложения, в котором он
// установлен. Поэтому приложение и Pinia создаём один раз, а между тестами
// только меняем пользователя и уходим на нейтральную страницу.
const app = createApp({ render: () => null })
const pinia = createPinia()
app.use(pinia)
app.use(router)
const auth = useAuthStore(pinia)

const client = { username: 'u', role: 'client' }
const moderator = { username: 'm', role: 'moderator' }

beforeEach(async () => {
  apiClient.get.mockRejectedValue({ response: { status: 401 } }) // гость
  auth.user = null
  await router.replace('/definitely-missing') // 404, публичная
  await router.isReady()
})

describe('router guard (лаб. № 8)', () => {
  it('«/» публичный: гость видит лендинг, а не /login', async () => {
    expect(router.resolve('/').meta.requiresAuth).toBeFalsy()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('/register, /verify-email, /check-email, /verify-age доступны гостю', async () => {
    for (const [path, name] of [
      ['/register', 'register'],
      ['/verify-email?token=x', 'verify-email'],
      ['/check-email', 'check-email'],
      ['/verify-age?registration=true', 'verify-age'],
    ]) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe(name)
    }
  })

  it('/account требует входа', async () => {
    await router.push('/account')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/account')
    auth.user = client
    await router.push('/account')
    expect(router.currentRoute.value.name).toBe('account')
  })

  it('вошедшего со страниц /login и /register возвращает на главную', async () => {
    auth.user = client
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('home')
    await router.push('/register')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('/moderation — только moderator/admin', async () => {
    auth.user = client
    await router.push('/moderation')
    expect(router.currentRoute.value.name).toBe('home')
    auth.user = moderator
    await router.push('/moderation')
    expect(router.currentRoute.value.name).toBe('moderation')
  })

  it('неизвестный адрес открывает страницу 404', async () => {
    await router.push('/no/such/page')
    expect(router.currentRoute.value.name).toBe('not-found')
  })

  it('после выхода защита снова срабатывает', async () => {
    auth.user = client
    await router.push('/courses/1')
    expect(router.currentRoute.value.name).toBe('course-detail')
    auth.user = null
    await router.push('/courses/2')
    expect(router.currentRoute.value.name).toBe('login')
  })
})

describe('маршруты CRUD', () => {
  it('/courses/create не воспринимается как /courses/:id', () => {
    expect(router.resolve('/courses/create').name).toBe('course-create')
    expect(router.resolve('/courses/12').name).toBe('course-detail')
    expect(router.resolve('/courses/12').params.id).toBe('12')
    expect(router.resolve('/courses/12/edit').name).toBe('course-edit')
    expect(router.resolve('/courses/abc').name).toBe('not-found') // id только из цифр
  })

  it('страницы курсов требуют входа, create/edit — ещё и роли модератора', () => {
    for (const path of ['/courses/create', '/courses/1', '/courses/1/edit']) {
      expect(router.resolve(path).meta.requiresAuth).toBe(true)
    }
    expect(router.resolve('/courses/create').meta.requiresModerator).toBe(true)
    expect(router.resolve('/courses/1/edit').meta.requiresModerator).toBe(true)
    expect(router.resolve('/courses/1').meta.requiresModerator).toBeFalsy()
  })

  it('гость на /courses/create попадает на /login с redirect', async () => {
    await router.push('/courses/create')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/courses/create')
  })

  it('клиент не попадает на создание и редактирование', async () => {
    auth.user = client
    await router.push('/courses/create')
    expect(router.currentRoute.value.name).toBe('home')
    await router.push('/courses/3')
    expect(router.currentRoute.value.name).toBe('course-detail')
  })

  it('модератор открывает создание', async () => {
    auth.user = moderator
    await router.push('/courses/create')
    expect(router.currentRoute.value.name).toBe('course-create')
  })
})
