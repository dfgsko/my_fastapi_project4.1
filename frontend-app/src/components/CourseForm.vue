<!-- Форма курса: одна для создания и редактирования (различаются initialValues
     и mode). Отправку выполняет родитель через prop onSubmit (async-функция):
     так форма дожидается ответа сервера и показывает ошибки 422 под полями. -->
<script setup>
import { useForm } from '@/composables/useForm'
import { toCoursePayload } from '@/api/courses'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseButton from '@/components/ui/BaseButton.vue'

const props = defineProps({
  initialValues: {
    type: Object,
    default: () => ({ title: '', description: '', instructor: '', duration_hours: 36 }),
  },
  mode: { type: String, default: 'create', validator: (v) => ['create', 'edit'].includes(v) },
  // async (payload) => void. Бросает ошибку Axios — форма её разберёт.
  onSubmit: { type: Function, required: true },
})
const emit = defineEmits(['cancel', 'saved'])

const required = (label) => (v) => (!String(v ?? '').trim() ? `Введите ${label}` : '')
const maxLength = (n) => (v) =>
  String(v ?? '').trim().length > n ? `Не длиннее ${n} символов` : ''
const all =
  (...rules) =>
  (v) =>
    rules.map((r) => r(v)).find(Boolean) || ''

// Клиентские правила ловят очевидные ошибки до запроса. Верхняя граница
// длительности (1000 ч) проверяется только сервером — так видна обработка 422.
const validators = {
  title: all(required('название'), maxLength(200)),
  description: all(required('описание'), maxLength(2000)),
  instructor: all(required('преподавателя'), maxLength(200)),
  duration_hours: (v) => {
    if (v === '' || v === null || v === undefined) return 'Введите длительность'
    if (!Number.isInteger(v)) return 'Введите целое число часов'
    if (v < 1) return 'Длительность должна быть больше 0'
    return ''
  },
}

// В PUT уходят только поля курса: id из initialValues сервер отклонил бы
// как лишнее поле (extra="forbid", лаб. № 5).
const form = useForm({ ...toCoursePayload(props.initialValues) }, validators, async (data) => {
  const saved = await props.onSubmit(toCoursePayload(data))
  emit('saved', saved)
})
const { values, errors, isSubmitting, submitError, isDirty, submit, validateField } = form

defineExpose({ isDirty })
</script>

<template>
  <form class="course-form" novalidate @submit.prevent="submit">
    <BaseInput
      id="title"
      v-model="values.title"
      label="Название"
      required
      maxlength="200"
      :error="errors.title"
      @blur="validateField('title')"
    />
    <BaseInput
      id="description"
      v-model="values.description"
      label="Описание"
      multiline
      required
      maxlength="2000"
      :error="errors.description"
      @blur="validateField('description')"
    />
    <BaseInput
      id="instructor"
      v-model="values.instructor"
      label="Преподаватель"
      required
      maxlength="200"
      :error="errors.instructor"
      @blur="validateField('instructor')"
    />
    <BaseInput
      id="duration_hours"
      v-model.number="values.duration_hours"
      type="number"
      label="Длительность, ч"
      required
      min="1"
      step="1"
      inputmode="numeric"
      hint="Целое число часов"
      :error="errors.duration_hours"
      @blur="validateField('duration_hours')"
    />
    <p v-if="submitError" class="submit-error" role="alert">{{ submitError }}</p>
    <div class="course-form__actions">
      <BaseButton variant="secondary" :disabled="isSubmitting" @click="emit('cancel')">
        Отмена
      </BaseButton>
      <BaseButton type="submit" :loading="isSubmitting">
        {{ mode === 'create' ? 'Создать' : 'Сохранить' }}
      </BaseButton>
    </div>
  </form>
</template>

<style scoped>
.course-form {
  max-width: 640px;
}
.submit-error {
  color: var(--color-danger, #c53030);
  margin: 0 0 1rem;
}
.course-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}
</style>
