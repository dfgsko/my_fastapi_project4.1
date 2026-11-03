<!-- Модальное окно: Teleport в <body>, Transition, закрытие по Escape и клику
     по фону, фокус переносится внутрь окна и возвращается после закрытия. -->
<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  // Пока идёт операция (например, DELETE), окно не закрывается по Escape/фону.
  persistent: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const dialog = ref(null)
let previouslyFocused = null
const titleId = `modal-title-${Math.random().toString(36).slice(2, 8)}`

function requestClose() {
  if (!props.persistent) emit('close')
}
function onKey(e) {
  if (e.key === 'Escape' && props.open) requestClose()
}

// Слушатель Escape вешается только пока окно открыто.
watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      previouslyFocused = document.activeElement
      window.addEventListener('keydown', onKey)
      await nextTick()
      const target = dialog.value?.querySelector('[data-autofocus]') ?? dialog.value
      target?.focus()
    } else {
      window.removeEventListener('keydown', onKey)
      previouslyFocused?.focus?.()
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" @click.self="requestClose">
        <div
          ref="dialog"
          class="modal-content"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="title ? titleId : undefined"
          tabindex="-1"
        >
          <h3 v-if="title" :id="titleId" class="modal-title">{{ title }}</h3>
          <slot />
          <div v-if="$slots.actions" class="modal-actions">
            <slot name="actions" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: var(--color-surface, #fff);
  padding: 1.5rem;
  border-radius: var(--radius-lg, 10px);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.12));
  max-width: 500px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}
.modal-content:focus {
  outline: none;
}
.modal-title {
  margin: 0 0 0.75rem;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.25rem;
}
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-active .modal-content,
.modal-leave-active .modal-content {
  transition: transform 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .modal-content,
.modal-leave-to .modal-content {
  transform: translateY(12px) scale(0.98);
}
</style>
