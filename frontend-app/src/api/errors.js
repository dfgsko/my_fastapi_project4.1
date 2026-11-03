// Человекочитаемые сообщения об ошибках API (FastAPI + Pydantic v2).

const PYDANTIC_MESSAGES = {
  missing: () => 'Обязательное поле',
  string_too_short: (c) => `Минимум символов: ${c.min_length}`,
  string_too_long: (c) => `Максимум символов: ${c.max_length}`,
  greater_than: (c) => `Значение должно быть больше ${c.gt}`,
  greater_than_equal: (c) => `Значение должно быть не меньше ${c.ge}`,
  less_than: (c) => `Значение должно быть меньше ${c.lt}`,
  less_than_equal: (c) => `Значение должно быть не больше ${c.le}`,
  int_parsing: () => 'Введите целое число',
  int_type: () => 'Введите целое число',
  string_type: () => 'Введите текст',
  extra_forbidden: () => 'Лишнее поле (сервер его не принимает)',
}

/** Переводит одну ошибку валидации FastAPI; неизвестный тип — исходное msg. */
export function translateValidationError(err) {
  const make = PYDANTIC_MESSAGES[err?.type]
  return make ? make(err.ctx || {}) : err?.msg || 'Некорректное значение'
}

/**
 * Разбирает 422 FastAPI: { detail: [{ loc: ['body', 'field'], type, msg, ctx }] }.
 * loc[0] — где лежал параметр (body/query/path), loc[1] — имя поля.
 * Возвращает { fields: {field: msg}, other: [msg] } — ошибки без поля
 * (например, loc: ['body']) идут в other.
 */
export function parseValidationErrors(detail) {
  const fields = {}
  const other = []
  if (!Array.isArray(detail)) {
    if (detail) other.push(String(detail))
    return { fields, other }
  }
  for (const err of detail) {
    const field = Array.isArray(err?.loc) && err.loc[0] === 'body' ? err.loc[1] : undefined
    const msg = translateValidationError(err)
    if (typeof field === 'string' && !(field in fields)) fields[field] = msg
    else other.push(msg)
  }
  return { fields, other }
}

/** Сообщение для пользователя по любой ошибке Axios. */
export function describeError(error, fallback = 'Не удалось выполнить запрос') {
  const status = error?.response?.status
  if (!error?.response) return 'Сервер недоступен. Проверьте подключение и что бэкенд запущен.'
  if (status === 403) return 'Недостаточно прав для этого действия'
  if (status === 404) return 'Запись не найдена'
  if (status === 429) return 'Слишком много запросов. Подождите немного.'
  if (status >= 500) return 'Ошибка на сервере. Попробуйте позже.'
  const detail = error.response.data?.detail
  return typeof detail === 'string' ? detail : fallback
}
