import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import CourseDetailView from '@/views/CourseDetailView.vue'
import apiClient from '@/api/client'
import { useToast } from '@/composables/useToast'
import { mountView } from '@/test-utils'

vi.mock('@/api/client')

const COURSE = {
  id: 5,
  title: 'Kubernetes',
  description: 'Основы',
  instructor: 'Иванов',
  duration_hours: 16,
}
let wrapper

beforeEach(() => {
  vi.clearAllMocks()
  useToast().clear()
})
afterEach(() => {
  wrapper?.unmount()
  useToast().clear()
})

async function mountDetail(role = 'admin') {
  const result = await mountView(CourseDetailView, { props: { id: '5' }, path: '/courses/5', role })
  wrapper = result.wrapper
  await flushPromises()
  return result
}
const button = (text) => wrapper.findAll('button').find((b) => b.text().includes(text))
const modalButton = (text) =>
  [...document.body.querySelectorAll('[role="dialog"] button')].find((b) =>
    b.textContent.includes(text),
  )

describe('CourseDetailView', () => {
  it('загружает курс по id из маршрута и показывает все поля', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    await mountDetail()
    expect(apiClient.get).toHaveBeenCalledWith('/courses/5')
    const text = wrapper.text()
    for (const v of ['Kubernetes', 'Основы', 'Иванов', '16 ч']) expect(text).toContain(v)
  })

  it('«Удалить» открывает модалку подтверждения, а не удаляет сразу', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    await mountDetail()
    await button('Удалить').trigger('click')
    await nextTick()
    expect(document.body.querySelector('[role="dialog"]').textContent).toContain(
      'Удалить «Kubernetes»?',
    )
    expect(apiClient.delete).not.toHaveBeenCalled()
  })

  it('«Отмена» закрывает модалку, курс остаётся', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    await mountDetail()
    await button('Удалить').trigger('click')
    await nextTick()
    modalButton('Отмена').click()
    await flushPromises()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    expect(apiClient.delete).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Kubernetes')
  })

  it('подтверждение удаляет курс, показывает toast и ведёт на список', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    apiClient.delete.mockResolvedValue({ status: 204 })
    const { push } = await mountDetail()
    await button('Удалить').trigger('click')
    await nextTick()
    modalButton('Да, удалить').click()
    await flushPromises()

    expect(apiClient.delete).toHaveBeenCalledWith('/courses/5')
    expect(useToast().toasts.value[0]).toMatchObject({
      type: 'success',
      message: 'Курс «Kubernetes» удалён',
    })
    expect(push).toHaveBeenCalledWith({ name: 'home' })
  })

  it('во время DELETE кнопка показывает загрузку, окно не закрывается по Escape', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    apiClient.delete.mockReturnValue(new Promise(() => {}))
    await mountDetail()
    await button('Удалить').trigger('click')
    await nextTick()
    modalButton('Да, удалить').click()
    await nextTick()

    expect(modalButton('Да, удалить').disabled).toBe(true)
    expect(modalButton('Да, удалить').querySelector('.spinner')).not.toBeNull()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
  })

  it('ошибка удаления: toast с причиной, модалка остаётся открытой', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    apiClient.delete.mockRejectedValue({ response: { status: 403, data: {} } })
    const { push } = await mountDetail()
    await button('Удалить').trigger('click')
    await nextTick()
    modalButton('Да, удалить').click()
    await flushPromises()

    expect(useToast().toasts.value[0]).toMatchObject({
      type: 'error',
      message: 'Недостаточно прав для этого действия',
    })
    expect(push).not.toHaveBeenCalledWith({ name: 'home' })
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
  })

  it('«Редактировать» ведёт на страницу редактирования', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    const { push } = await mountDetail()
    await button('Редактировать').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'course-edit', params: { id: '5' } })
  })

  it('удалённый курс (404) — «Запись не найдена»', async () => {
    apiClient.get.mockRejectedValue({ response: { status: 404, data: { detail: 'not found' } } })
    await mountDetail()
    expect(wrapper.find('.state.error h1').text()).toBe('Запись не найдена')
  })

  it('обычный пользователь видит курс, но без кнопок изменения', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    await mountDetail('user')
    expect(wrapper.text()).toContain('Kubernetes')
    expect(button('Удалить')).toBeUndefined()
    expect(button('Редактировать')).toBeUndefined()
  })

  it('курс 18+ без подтверждённого возраста (403 + X-Error-Code) — заглушка, а не ошибка', async () => {
    apiClient.get.mockRejectedValue({
      response: {
        status: 403,
        data: { detail: 'Для доступа подтвердите возраст' },
        headers: { 'x-error-code': 'age_verification_required' },
      },
    })
    const { wrapper, push } = await mountDetail('client')
    await flushPromises()
    expect(wrapper.find('.age-lock').text()).toContain('Для доступа подтвердите возраст')
    await wrapper.find('.age-lock button').trigger('click')
    expect(push).toHaveBeenCalledWith('/verify-age')
  })

  it('клиент не видит «Редактировать» и «Удалить», модератор — видит', async () => {
    apiClient.get.mockResolvedValue({ data: COURSE })
    const client = await mountDetail('client')
    await flushPromises()
    expect(client.wrapper.text()).not.toContain('Удалить')
    client.wrapper.unmount()
    const moder = await mountDetail('moderator')
    await flushPromises()
    expect(moder.wrapper.text()).toContain('Удалить')
    moder.wrapper.unmount()
  })
})
