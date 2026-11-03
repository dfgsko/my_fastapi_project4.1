// Состояние формы: значения, клиентская валидация, отправка, ошибки 422.
import { computed, ref, toRaw } from 'vue'
import { describeError, parseValidationErrors } from '@/api/errors'

function clone(values) {
  return structuredClone(toRaw(values ?? {}))
}

export function useForm(initialValues, validators = {}, onSubmit) {
  // Копия: правки формы не меняют объект родителя (например, item в заголовке).
  let initial = clone(initialValues)
  const values = ref(clone(initial))
  const errors = ref({})
  const isSubmitting = ref(false)
  const submitError = ref(null)
  const touched = ref({})

  function errorFor(key) {
    const validator = validators[key]
    return validator ? validator(values.value[key], values.value) || '' : ''
  }

  const isValid = computed(() => Object.keys(validators).every((key) => !errorFor(key)))
  const isDirty = computed(() => JSON.stringify(values.value) !== JSON.stringify(initial))

  function validate() {
    const next = {}
    for (const key of Object.keys(validators)) {
      const msg = errorFor(key)
      if (msg) next[key] = msg
    }
    errors.value = next
    return Object.keys(next).length === 0
  }

  // Проверка одного поля (например, при потере фокуса).
  function validateField(key) {
    touched.value = { ...touched.value, [key]: true }
    const msg = errorFor(key)
    const next = { ...errors.value }
    if (msg) next[key] = msg
    else delete next[key]
    errors.value = next
  }

  async function submit() {
    if (isSubmitting.value) return false // защита от двойной отправки
    submitError.value = null
    if (!validate()) return false
    isSubmitting.value = true
    try {
      await onSubmit(clone(values.value))
      return true
    } catch (e) {
      if (e?.response?.status === 422) {
        const { fields, other } = parseValidationErrors(e.response.data?.detail)
        const known = {}
        const unknown = [...other]
        for (const [field, msg] of Object.entries(fields)) {
          // Ошибка по полю, которого нет в форме, не должна потеряться молча.
          if (field in values.value) known[field] = msg
          else unknown.push(`${field}: ${msg}`)
        }
        errors.value = known
        submitError.value = unknown.length ? unknown.join('; ') : null
      } else {
        submitError.value = describeError(e, 'Не удалось сохранить')
      }
      return false
    } finally {
      isSubmitting.value = false
    }
  }

  function reset(nextInitial) {
    if (nextInitial) initial = clone(nextInitial)
    values.value = clone(initial)
    errors.value = {}
    touched.value = {}
    submitError.value = null
  }

  return {
    values,
    errors,
    touched,
    isSubmitting,
    submitError,
    isValid,
    isDirty,
    submit,
    reset,
    validate,
    validateField,
  }
}
