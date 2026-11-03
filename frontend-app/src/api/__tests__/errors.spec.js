import { describe, it, expect } from 'vitest'
import { describeError, parseValidationErrors, translateValidationError } from '@/api/errors'

describe('parseValidationErrors', () => {
  it('loc[1] — имя поля в теле запроса', () => {
    const { fields, other } = parseValidationErrors([
      { loc: ['body', 'title'], type: 'string_too_short', msg: '...', ctx: { min_length: 1 } },
    ])
    expect(fields).toEqual({ title: 'Минимум символов: 1' })
    expect(other).toEqual([])
  })

  it('ошибки без поля и из query/path — в other', () => {
    const { fields, other } = parseValidationErrors([
      { loc: ['body'], type: 'model_attributes_type', msg: 'Input should be an object' },
      { loc: ['query', 'min_duration'], type: 'greater_than_equal', ctx: { ge: 0 }, msg: '' },
    ])
    expect(fields).toEqual({})
    expect(other).toEqual(['Input should be an object', 'Значение должно быть не меньше 0'])
  })

  it('на одно поле берётся первая ошибка', () => {
    const { fields } = parseValidationErrors([
      { loc: ['body', 'x'], type: 'missing', msg: '' },
      { loc: ['body', 'x'], type: 'int_parsing', msg: '' },
    ])
    expect(fields.x).toBe('Обязательное поле')
  })

  it('detail-строка (например, 422 из бизнес-логики) не ломает разбор', () => {
    expect(parseValidationErrors('Что-то не так').other).toEqual(['Что-то не так'])
  })
})

describe('translateValidationError / describeError', () => {
  it('неизвестный тип ошибки оставляет исходное msg', () => {
    expect(translateValidationError({ type: 'weird', msg: 'Original' })).toBe('Original')
  })

  it.each([
    [undefined, 'Сервер недоступен'],
    [403, 'Недостаточно прав'],
    [404, 'Запись не найдена'],
    [429, 'Слишком много запросов'],
    [503, 'Ошибка на сервере'],
  ])('статус %s → понятное сообщение', (status, text) => {
    const error = status ? { response: { status, data: {} } } : new Error('Network Error')
    expect(describeError(error)).toContain(text)
  })

  it('для 400 показывает detail от сервера', () => {
    const error = { response: { status: 400, data: { detail: 'min_duration > max_duration' } } }
    expect(describeError(error)).toBe('min_duration > max_duration')
  })
})
