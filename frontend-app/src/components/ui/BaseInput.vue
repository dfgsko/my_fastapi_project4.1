<!-- Поле ввода с v-model (defineModel), подписью, подсказкой и ошибкой.
     multiline → <textarea>. Атрибуты (min, max, placeholder…) идут на сам input. -->
<script setup>
import { computed } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  id: { type: String, required: true },
  label: { type: String, default: '' },
  error: { type: String, default: '' },
  hint: { type: String, default: '' },
  type: { type: String, default: 'text' },
  multiline: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
})

// defineModel принимает и модификаторы родителя: v-model.number / v-model.trim.
const model = defineModel({ type: [String, Number], default: '' })

const describedBy = computed(
  () =>
    [props.error && `${props.id}-error`, props.hint && `${props.id}-hint`]
      .filter(Boolean)
      .join(' ') || undefined,
)
</script>

<template>
  <div class="base-input" :class="{ 'base-input--error': !!error }">
    <label v-if="label" :for="id">
      {{ label }}<span v-if="required" class="required" aria-hidden="true"> *</span>
    </label>
    <textarea
      v-if="multiline"
      :id="id"
      v-model="model"
      v-bind="$attrs"
      :required="required"
      :aria-invalid="!!error"
      :aria-describedby="describedBy"
      rows="4"
    ></textarea>
    <input
      v-else
      :id="id"
      v-model="model"
      v-bind="$attrs"
      :type="type"
      :required="required"
      :aria-invalid="!!error"
      :aria-describedby="describedBy"
    />
    <p v-if="hint && !error" :id="`${id}-hint`" class="hint">{{ hint }}</p>
    <p v-if="error" :id="`${id}-error`" class="error-message" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.base-input {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 1rem;
}
label {
  font-weight: 500;
}
.required {
  color: var(--color-danger, #c53030);
}
input,
textarea {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #cbd5e0);
  border-radius: var(--radius-md, 6px);
  font: inherit;
  background: var(--color-surface, #fff);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
textarea {
  resize: vertical;
}
input:hover:not(:disabled),
textarea:hover:not(:disabled) {
  border-color: var(--color-muted, #4a5568);
}
input:focus,
textarea:focus {
  outline: none;
  border-color: var(--color-primary, #2b6cb0);
  box-shadow: var(--focus-ring, 0 0 0 3px rgba(43, 108, 176, 0.35));
}
input:disabled,
textarea:disabled {
  background: var(--color-secondary, #e2e8f0);
  cursor: not-allowed;
}
.base-input--error input,
.base-input--error textarea {
  border-color: var(--color-danger, #c53030);
}
.hint {
  margin: 0;
  color: var(--color-muted, #4a5568);
  font-size: 0.875rem;
}
.error-message {
  margin: 0;
  color: var(--color-danger, #c53030);
  font-size: 0.875rem;
}
</style>
