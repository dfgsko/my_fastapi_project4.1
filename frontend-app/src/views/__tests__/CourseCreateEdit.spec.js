import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import CourseCreateView from '@/views/CourseCreateView.vue'
import CourseEditView from '@/views/CourseEditView.vue'
import apiClient from '@/api/client'
import { useToast } from '@/composables/useToast'
import { mountView } from '@/test-utils'

vi.mock('@/api/client')

const VALID = {
  title: 'Docker',
  description: 'Контейнеры',
  instructor: 'Петров',
  duration_hours: 8,
}
let wrapper
beforeEach(() => {
  vi.clearAllMocks()
  useToast().clear()
})
afterEach(() => wrapper?.unmount())

async function fill(values) {
  for (const [field, value] of Object.entries(values)) {
    await wrapper.find(`#${field}`).setValue(String(value))
  }
}

describe('CourseCreateView', () => {
  it('POST /courses → toast «создан» → переход на детали нового курса', async () => {
    apiClient.post.mockResolvedValue({ data: { id: 42, ...VALID } })
    const result = await mountView(CourseCreateView, { path: '/courses/create' })
    wrapper = result.wrapper
    await fill(VALID)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiClient.post).toHaveBeenCalledWith('/courses', { ...VALID, min_age: 0 })
    expect(useToast().toasts.value[0].message).toBe('Курс «Docker» создан')
    expect(result.push).toHaveBeenCalledWith({ name: 'course-detail', params: { id: 42 } })
  })

  it('422 от сервера: перехода нет, ошибка под полем', async () => {
    apiClient.post.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: [{ loc: ['body', 'duration_hours'], type: 'less_than_equal', ctx: { le: 1000 } }],
        },
      },
    })
    const result = await mountView(CourseCreateView, { path: '/courses/create' })
    wrapper = result.wrapper
    await fill({ ...VALID, duration_hours: 3000 })
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Значение должно быть не больше 1000')
    expect(result.push).not.toHaveBeenCalledWith(expect.objectContaining({ name: 'course-detail' }))
    expect(useToast().toasts.value).toHaveLength(0)
  })
})

describe('CourseEditView', () => {
  const mountEdit = async () => {
    const result = await mountView(CourseEditView, { props: { id: '7' }, path: '/courses/7/edit' })
    wrapper = result.wrapper
    await flushPromises()
    return result
  }

  it('пока данные грузятся, форма не показывается (иначе поля были бы пустыми)', async () => {
    apiClient.get.mockReturnValue(new Promise(() => {}))
    await mountEdit()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('Загрузка…')
  })

  it('заполняет форму текущими данными и сохраняет через PUT', async () => {
    apiClient.get.mockResolvedValue({ data: { id: 7, ...VALID } })
    apiClient.put.mockResolvedValue({ data: { id: 7, ...VALID, title: 'Docker 2' } })
    const { push } = await mountEdit()

    expect(wrapper.find('#title').element.value).toBe('Docker')
    await fill({ title: 'Docker 2' })
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiClient.put).toHaveBeenCalledWith('/courses/7', {
      ...VALID,
      title: 'Docker 2',
      min_age: 0,
    })
    expect(useToast().toasts.value[0].message).toBe('Изменения сохранены')
    expect(push).toHaveBeenCalledWith({ name: 'course-detail', params: { id: '7' } })
  })

  it('открыли /edit удалённого курса — «Запись не найдена»', async () => {
    apiClient.get.mockRejectedValue({ response: { status: 404, data: {} } })
    await mountEdit()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('Запись не найдена')
  })

  it('курс удалили во время редактирования: PUT 404 → «не найдена» и toast', async () => {
    apiClient.get.mockResolvedValue({ data: { id: 7, ...VALID } })
    apiClient.put.mockRejectedValue({ response: { status: 404, data: {} } })
    await mountEdit()
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Запись не найдена')
    expect(useToast().toasts.value[0]).toMatchObject({ type: 'error' })
  })
})
