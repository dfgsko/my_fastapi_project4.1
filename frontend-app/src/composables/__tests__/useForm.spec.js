import { describe, it, expect, vi } from 'vitest'
import { useForm } from '@/composables/useForm'

const required = (v) => (!v ? 'Required' : '')
const http422 = (detail) => ({ response: { status: 422, data: { detail } } })

describe('useForm', () => {
  it('валидирует поля', async () => {
    const onSubmit = vi.fn()
    const { errors, submit } = useForm({ title: '' }, { title: required }, onSubmit)
    const ok = await submit()
    expect(ok).toBe(false)
    expect(errors.value.title).toBe('Required')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('вызывает onSubmit при валидных данных', async () => {
    const onSubmit = vi.fn()
    const { submit } = useForm({ title: 'Book' }, { title: required }, onSubmit)
    expect(await submit()).toBe(true)
    expect(onSubmit).toHaveBeenCalledWith({ title: 'Book' })
  })

  it('раскладывает 422 ошибки FastAPI по полям', async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValue(http422([{ loc: ['body', 'title'], msg: 'Too short' }]))
    const { errors, submit } = useForm({ title: 'x' }, {}, onSubmit)
    expect(await submit()).toBe(false)
    expect(errors.value.title).toBe('Too short')
  })

  it('переводит типовые ошибки Pydantic v2 на русский по type и ctx', async () => {
    const onSubmit = vi.fn().mockRejectedValue(
      http422([
        {
          loc: ['body', 'duration_hours'],
          type: 'less_than_equal',
          msg: 'Input should be less than or equal to 1000',
          ctx: { le: 1000 },
        },
      ]),
    )
    const { errors, submit } = useForm({ duration_hours: 5000 }, {}, onSubmit)
    await submit()
    expect(errors.value.duration_hours).toBe('Значение должно быть не больше 1000')
  })

  it('ошибка 422 по полю, которого нет в форме, не теряется — уходит в общий текст', async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        http422([
          { loc: ['body', 'id'], type: 'extra_forbidden', msg: 'Extra inputs are not permitted' },
        ]),
      )
    const { errors, submitError, submit } = useForm({ title: 'x' }, {}, onSubmit)
    await submit()
    expect(errors.value).toEqual({})
    expect(submitError.value).toContain('id')
  })

  it('прочие ошибки (500, сеть) показываются общим сообщением', async () => {
    const { submitError, submit } = useForm(
      { title: 'x' },
      {},
      vi.fn().mockRejectedValue({ response: { status: 500, data: {} } }),
    )
    await submit()
    expect(submitError.value).toBe('Ошибка на сервере. Попробуйте позже.')
  })

  it('isSubmitting — true во время отправки; повторный submit игнорируется', async () => {
    let finish
    const onSubmit = vi.fn(() => new Promise((r) => (finish = r)))
    const { isSubmitting, submit } = useForm({ title: 'x' }, {}, onSubmit)
    const first = submit()
    expect(isSubmitting.value).toBe(true)
    expect(await submit()).toBe(false) // двойной клик
    finish()
    expect(await first).toBe(true)
    expect(isSubmitting.value).toBe(false)
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('работает с копией initialValues: объект родителя не меняется', () => {
    const parent = { title: 'Исходное', tags: ['a'] }
    const { values } = useForm(parent, {}, vi.fn())
    values.value.title = 'Изменено'
    values.value.tags.push('b')
    expect(parent).toEqual({ title: 'Исходное', tags: ['a'] })
  })

  it('isValid и isDirty реагируют на изменения', () => {
    const { values, isValid, isDirty } = useForm({ title: '' }, { title: required }, vi.fn())
    expect(isValid.value).toBe(false)
    expect(isDirty.value).toBe(false)
    values.value.title = 'Есть'
    expect(isValid.value).toBe(true)
    expect(isDirty.value).toBe(true)
  })

  it('validateField проверяет одно поле и снимает ошибку после исправления', () => {
    const { values, errors, validateField } = useForm(
      { title: '', other: '' },
      { title: required, other: required },
      vi.fn(),
    )
    validateField('title')
    expect(errors.value).toEqual({ title: 'Required' })
    values.value.title = 'ok'
    validateField('title')
    expect(errors.value).toEqual({})
  })

  it('валидатор получает все значения (для правил между полями)', async () => {
    const validators = { max: (v, all) => (v < all.min ? 'max < min' : '') }
    const { errors, submit } = useForm({ min: 5, max: 1 }, validators, vi.fn())
    await submit()
    expect(errors.value.max).toBe('max < min')
  })

  it('reset возвращает исходные значения и очищает ошибки', async () => {
    const { values, errors, submitError, submit, reset } = useForm(
      { title: '' },
      { title: required },
      vi.fn(),
    )
    await submit()
    values.value.title = 'x'
    reset()
    expect(values.value).toEqual({ title: '' })
    expect(errors.value).toEqual({})
    expect(submitError.value).toBeNull()
  })
})
