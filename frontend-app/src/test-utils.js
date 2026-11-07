// Помощники для тестов компонентов (импортируются только из *.spec.js).
import { mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import { createMemoryHistory, createRouter } from 'vue-router'
import { vi } from 'vitest'
import { routes } from '@/router'

/** Роутер в памяти с маршрутами приложения, но без guard'ов. */
export async function makeRouter(path = '/') {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return router
}

/**
 * Монтирует компонент с роутером и тестовой Pinia.
 * role: null (гость) | 'client' | 'moderator' | 'admin' — состояние auth-store.
 * ('user' из лаб. № 6–7 считается клиентом.)
 */
export async function mountView(component, { props = {}, path = '/', role = 'admin' } = {}) {
  const router = await makeRouter(path)
  const push = vi.spyOn(router, 'push')
  const wrapper = mount(component, {
    props,
    attachTo: document.body, // для Teleport (модалки) и фокуса
    global: {
      plugins: [
        router,
        createTestingPinia({
          createSpy: vi.fn,
          initialState: {
            auth: {
              initialized: true,
              user: role ? { username: 'tester', role: role === 'user' ? 'client' : role } : null,
            },
          },
        }),
      ],
    },
  })
  return { wrapper, router, push }
}
