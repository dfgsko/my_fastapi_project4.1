import { describe, it, expect, beforeEach } from 'vitest'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'

// Роутер — синглтон: guard берёт Pinia из ПЕРВОГО приложения, в котором он
// установлен. Поэтому приложение и Pinia создаём один раз, а между тестами
// только сбрасываем токен и уходим на нейтральную страницу.
const app = createApp({ render: () => null })
const pinia = createPinia()
app.use(pinia)
app.use(router)
const auth = useAuthStore(pinia)

beforeEach(async () => {
  localStorage.clear()
  auth.token = null
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
