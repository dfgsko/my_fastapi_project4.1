import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'

// Guard запрашивает /auth/me, если роль ещё неизвестна.
vi.mock('@/api/client')

// Роутер — синглтон: guard берёт Pinia из ПЕРВОГО приложения, в котором он
// установлен. Поэтому приложение и Pinia создаём один раз, а между тестами
// только сбрасываем токен и уходим на нейтральную страницу.
const app = createApp({ render: () => null })
const pinia = createPinia()
app.use(pinia)
app.use(router)
const auth = useAuthStore(pinia)

beforeEach(async () => {
  apiClient.get.mockResolvedValue({ data: { username: 'u', role: 'user' } })
  localStorage.clear()
  auth.token = null
  auth.user = null
  await router.replace('/definitely-missing') // 404, публичная
  await router.isReady()
})

describe('router guard', () => {
  it('описывает маршруты: / защищён, /login публичный', () => {
    expect(router.resolve('/').meta.requiresAuth).toBe(true)
    expect(router.resolve('/login').meta.requiresAuth).toBeFalsy()
    expect(router.resolve('/login').name).toBe('login')
  })

  it('неавторизованного отправляет с / на /login', async () => {
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('авторизованного пускает на /', async () => {
    auth.token = 'jwt'
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('авторизованного со страницы /login возвращает на главную', async () => {
    auth.token = 'jwt'
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('неавторизованный может открыть /login', async () => {
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('неизвестный адрес открывает страницу 404', async () => {
    await router.push('/no/such/page')
    expect(router.currentRoute.value.name).toBe('not-found')
  })

  it('после выхода (токен сброшен) защита снова срабатывает', async () => {
    auth.token = 'jwt'
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('home')

    auth.token = null
    await router.push('/login')
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('login')
  })
})

describe('маршруты CRUD (лаб. № 7)', () => {
  it('/courses/create не воспринимается как /courses/:id', () => {
    expect(router.resolve('/courses/create').name).toBe('course-create')
    expect(router.resolve('/courses/12').name).toBe('course-detail')
    expect(router.resolve('/courses/12').params.id).toBe('12')
    expect(router.resolve('/courses/12/edit').name).toBe('course-edit')
    expect(router.resolve('/courses/abc').name).toBe('not-found') // id только из цифр
  })

  it('все страницы курсов защищены requiresAuth, create/edit — ещё и requiresAdmin', () => {
    for (const path of ['/courses/create', '/courses/1', '/courses/1/edit']) {
      expect(router.resolve(path).meta.requiresAuth).toBe(true)
    }
    expect(router.resolve('/courses/create').meta.requiresAdmin).toBe(true)
    expect(router.resolve('/courses/1/edit').meta.requiresAdmin).toBe(true)
    expect(router.resolve('/courses/1').meta.requiresAdmin).toBeFalsy()
  })

  it('гость на /courses/create попадает на /login с redirect', async () => {
    await router.push('/courses/create')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/courses/create')
  })

  it('обычный пользователь не попадает на создание и редактирование', async () => {
    auth.token = 'jwt'
    auth.user = { username: 'u', role: 'user' }
    await router.push('/courses/create')
    expect(router.currentRoute.value.name).toBe('home')
    await router.push('/courses/3')
    expect(router.currentRoute.value.name).toBe('course-detail')
  })

  it('администратор открывает создание', async () => {
    auth.token = 'jwt'
    auth.user = { username: 'a', role: 'admin' }
    await router.push('/courses/create')
    expect(router.currentRoute.value.name).toBe('course-create')
  })
})
