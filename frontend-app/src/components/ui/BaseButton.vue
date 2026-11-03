<!-- Кнопка-«прозрачная обёртка»: варианты, размеры, disabled и loading.
     Нативные атрибуты и слушатели (type, @click, aria-*) переходят на <button>. -->
<script setup>
defineOptions({ inheritAttrs: false })

defineProps({
  variant: {
    type: String,
    default: 'primary',
    validator: (v) => ['primary', 'secondary', 'danger'].includes(v),
  },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md', 'lg'].includes(v) },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
})
</script>

<template>
  <button
    v-bind="$attrs"
    :type="type"
    :class="['base-button', `base-button--${variant}`, `base-button--${size}`]"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span v-if="loading" class="spinner" aria-hidden="true"></span>
    <slot />
  </button>
</template>

<style scoped>
.base-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: 1px solid transparent;
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
  line-height: 1.2;
  transition:
    background-color 0.15s ease,
    box-shadow 0.15s ease,
    opacity 0.15s ease;
}
.base-button:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring, 0 0 0 3px rgba(43, 108, 176, 0.35));
}
.base-button--primary {
  background: var(--color-primary, #2b6cb0);
  color: #fff;
}
.base-button--primary:hover:not(:disabled) {
  background: var(--color-primary-hover, #2c5282);
}
.base-button--secondary {
  background: var(--color-secondary, #e2e8f0);
  color: var(--color-text, #1a202c);
}
.base-button--secondary:hover:not(:disabled) {
  background: var(--color-secondary-hover, #cbd5e0);
}
.base-button--danger {
  background: var(--color-danger, #c53030);
  color: #fff;
}
.base-button--danger:hover:not(:disabled) {
  background: var(--color-danger-hover, #9b2c2c);
}
.base-button--sm {
  padding: 0.25rem 0.75rem;
  font-size: 0.875rem;
}
.base-button--md {
  padding: 0.5rem 1rem;
  font-size: 1rem;
}
.base-button--lg {
  padding: 0.75rem 1.5rem;
  font-size: 1.125rem;
}
.base-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.spinner {
  width: 1em;
  height: 1em;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 1.5s;
  }
}
</style>
