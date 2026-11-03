<!-- Контейнер с фоном, рамкой и тенью. as — тег корня (div, li, article, section);
     interactive — эффекты наведения для кликабельных карточек. -->
<script setup>
defineProps({
  as: { type: String, default: 'div' },
  interactive: { type: Boolean, default: false },
})
</script>

<template>
  <component :is="as" class="base-card" :class="{ 'base-card--interactive': interactive }">
    <header v-if="$slots.header" class="base-card__header"><slot name="header" /></header>
    <slot />
    <footer v-if="$slots.footer" class="base-card__footer"><slot name="footer" /></footer>
  </component>
</template>

<style scoped>
.base-card {
  display: block;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #cbd5e0);
  border-radius: var(--radius-lg, 10px);
  box-shadow: var(--shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.1));
  padding: 1rem 1.25rem;
}
.base-card--interactive {
  position: relative;
  transition:
    box-shadow 0.15s ease,
    transform 0.15s ease,
    border-color 0.15s ease;
}
.base-card--interactive:hover,
.base-card--interactive:focus-within {
  border-color: var(--color-primary, #2b6cb0);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.12));
  transform: translateY(-2px);
}
.base-card__header {
  margin-bottom: 0.75rem;
}
.base-card__footer {
  margin-top: 1rem;
}
@media (prefers-reduced-motion: reduce) {
  .base-card--interactive:hover,
  .base-card--interactive:focus-within {
    transform: none;
  }
}
</style>
