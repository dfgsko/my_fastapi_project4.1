import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CourseForm from '@/components/CourseForm.vue'

const VALID = {
  title: 'Kubernetes',
  description: 'Основы',
  instructor: 'Иванов',
  duration_hours: 16,
}

function mountForm(props = {}) {
  const onSubmit = props.onSubmit ?? vi.fn().mockResolvedValue({ id: 1 })
  const wrapper = mount(CourseForm, { props: { onSubmit, ...props } })
  return { wrapper, onSubmit }
}
async function fill(wrapper, values) {
  for (const [field, value] of Object.entries(values)) {
    const el = wrapper.find(`#${field}`)
    await el.setValue(String(value))
  }
}

describe('CourseForm', () => {
  it('submit с валидными данными вызывает onSubmit с данными курса и событие saved', async () => {
    const { wrapper, onSubmit } = mountForm()
    await fill(wrapper, VALID)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(onSubmit).toHaveBeenCalledWith({ ...VALID, min_age: 0 })
    expect(typeof onSubmit.mock.calls[0][0].duration_hours).toBe('number') // v-model.number
    expect(wrapper.emitted('saved')).toEqual([[{ id: 1 }]])
  })

  it('пустая форма: ошибки под полями, запрос не отправляется', async () => {
    const { wrapper, onSubmit } = mountForm()
    await fill(wrapper, { duration_hours: '' })
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Введите название')
    expect(text).toContain('Введите описание')
    expect(text).toContain('Введите преподавателя')
    expect(text).toContain('Введите длительность')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('пробелы вместо текста не проходят проверку; лишние пробелы обрезаются', async () => {
    const { wrapper, onSubmit } = mountForm()
    await fill(wrapper, { ...VALID, title: '   ' })
    await wrapper.find('form').trigger('submit')
    expect(wrapper.text()).toContain('Введите название')

    await fill(wrapper, { title: '  Docker  ' })
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(onSubmit.mock.calls[0][0].title).toBe('Docker')
  })

  it('дробное и нулевое число часов отклоняется на клиенте', async () => {
    const { wrapper, onSubmit } = mountForm()
    await fill(wrapper, { ...VALID, duration_hours: '1.5' })
    await wrapper.find('form').trigger('submit')
    expect(wrapper.text()).toContain('Введите целое число часов')
    await fill(wrapper, { duration_hours: '0' })
    await wrapper.find('form').trigger('submit')
    expect(wrapper.text()).toContain('Длительность должна быть больше 0')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('422 от FastAPI показывается под полем duration_hours', async () => {
    const onSubmit = vi.fn().mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: [
            {
              type: 'less_than_equal',
              loc: ['body', 'duration_hours'],
              msg: 'Input should be less than or equal to 1000',
              ctx: { le: 1000 },
            },
          ],
        },
      },
    })
    const { wrapper } = mountForm({ onSubmit })
    await fill(wrapper, { ...VALID, duration_hours: 5000 })
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const field = wrapper.find('#duration_hours').element.closest('.base-input')
    expect(field.textContent).toContain('Значение должно быть не больше 1000')
    expect(wrapper.find('#duration_hours').attributes('aria-invalid')).toBe('true')
  })

  it('ошибка сервера без полей — общее сообщение над кнопками', async () => {
    const onSubmit = vi.fn().mockRejectedValue({ response: { status: 403, data: {} } })
    const { wrapper } = mountForm({ onSubmit })
    await fill(wrapper, VALID)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.submit-error').text()).toBe('Недостаточно прав для этого действия')
  })

  it('кнопка показывает загрузку, пока идёт запрос', async () => {
    let finish
    const onSubmit = vi.fn(() => new Promise((r) => (finish = r)))
    const { wrapper } = mountForm({ onSubmit })
    await fill(wrapper, VALID)
    await wrapper.find('form').trigger('submit')

    const submitBtn = wrapper.find('button[type="submit"]')
    expect(submitBtn.attributes('disabled')).toBeDefined()
    expect(submitBtn.find('.spinner').exists()).toBe(true)
    finish()
    await flushPromises()
    expect(submitBtn.attributes('disabled')).toBeUndefined()
  })

  it('режим edit: поля заполнены, в отправку не попадает id (иначе 422 «extra field»)', async () => {
    const onSubmit = vi.fn().mockResolvedValue({})
    const { wrapper } = mountForm({ mode: 'edit', onSubmit, initialValues: { id: 7, ...VALID } })
    expect(wrapper.find('#title').element.value).toBe('Kubernetes')
    expect(wrapper.find('button[type="submit"]').text()).toBe('Сохранить')

    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('id')
    expect(onSubmit.mock.calls[0][0]).toEqual({ ...VALID, min_age: 0 })
  })

  it('не мутирует initialValues родителя', async () => {
    const initial = { id: 7, ...VALID }
    const { wrapper } = mountForm({ mode: 'edit', initialValues: initial })
    await fill(wrapper, { title: 'Другое' })
    expect(initial.title).toBe('Kubernetes')
  })

  it('ошибка поля появляется при потере фокуса (blur)', async () => {
    const { wrapper } = mountForm()
    await wrapper.find('#title').trigger('blur')
    expect(wrapper.text()).toContain('Введите название')
  })

  it('«Отмена» отправляет событие cancel', async () => {
    const { wrapper } = mountForm()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Отмена')
      .trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})

describe('CourseForm: возрастное ограничение (лаб. № 8)', () => {
  it('по умолчанию «Для всех», можно выбрать 18+', async () => {
    const { wrapper, onSubmit } = mountForm()
    await fill(wrapper, VALID)
    await wrapper.find('#min_age').setValue('18')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(onSubmit).toHaveBeenCalledWith({ ...VALID, min_age: 18 })
  })
})
