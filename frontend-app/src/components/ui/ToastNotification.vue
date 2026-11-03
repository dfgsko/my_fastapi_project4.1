<!-- Одно уведомление: тип (success/error/info), текст и кнопка закрытия. -->
<script setup>
defineProps({
  type: {
    type: String,
    default: 'info',
    validator: (v) => ['success', 'error', 'info'].includes(v),
  },
  message: { type: String, required: true },
})
const emit = defineEmits(['close'])
const icons = { success: '✓', error: '!', info: 'i' }
</script>

<template>
  <div
    :class="['toast', `toast--${type}`]"
    :role="type === 'error' ? 'alert' : 'status'"
    @click="emit('close')"
  >
    <span class="toast__icon" aria-hidden="true">{{ icons[type] }}</span>
    <span class="toast__message">{{ message }}</span>
    <button type="button" class="toast__close" aria-label="Закрыть" @click.stop="emit('close')">
      ×
    </button>
  </div>
</template>

<style scoped>
.toast {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.75rem 0.75rem 1rem;
  border-radius: var(--radius-md, 6px);
  color: #fff;
  cursor: pointer;
  min-width: 220px;
  max-width: 360px;
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.15));
}
.toast--success {
  background: var(--color-success, #2f855a);
}
.toast--error {
  background: var(--color-danger, #c53030);
}
.toast--info {
  background: var(--color-info, #2b6cb0);
}
.toast__icon {
  display: inline-grid;
  place-items: center;
  width: 1.4em;
  height: 1.4em;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.25);
  font-weight: 700;
  flex: none;
}
.toast__message {
  flex: 1;
}
.toast__close {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  padding: 0 0.25rem;
  border-radius: var(--radius-sm, 4px);
}
.toast__close:focus-visible {
  outline: 2px solid #fff;
}
</style>
