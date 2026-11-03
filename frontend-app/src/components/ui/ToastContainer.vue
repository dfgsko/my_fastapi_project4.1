<!-- Контейнер уведомлений: телепортируется в <body>, TransitionGroup анимирует
     появление, исчезновение и сдвиг соседних уведомлений. -->
<script setup>
import { useToast } from '@/composables/useToast'
import ToastNotification from '@/components/ui/ToastNotification.vue'

const { toasts, remove } = useToast()
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite">
      <TransitionGroup name="toast">
        <ToastNotification
          v-for="t in toasts"
          :key="t.id"
          :type="t.type"
          :message="t.message"
          @close="remove(t.id)"
        />
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 4rem; /* под шапкой: не закрывает Logout */
  right: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  z-index: 2000;
}
@media (max-width: 480px) {
  .toast-container {
    left: 1rem;
  }
}
.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
/* Уходящий элемент выводим из потока, чтобы соседи плавно сдвинулись (move). */
.toast-leave-active {
  position: absolute;
  right: 0;
}
.toast-move {
  transition: transform 0.2s ease;
}
</style>
