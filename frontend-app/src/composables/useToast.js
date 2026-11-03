// Глобальные уведомления. Состояние объявлено ВНЕ функции: все вызовы
// useToast() работают с одним массивом (singleton без Pinia).
import { ref } from 'vue'

const toasts = ref([])
const timers = new Map()
let nextId = 1
const MAX_TOASTS = 5

function remove(id) {
  clearTimeout(timers.get(id))
  timers.delete(id)
  toasts.value = toasts.value.filter((t) => t.id !== id)
}

function add(type, message, duration = 3500) {
  const id = nextId++
  toasts.value = [...toasts.value, { id, type, message }]
  // Не даём уведомлениям заполнить весь экран.
  while (toasts.value.length > MAX_TOASTS) remove(toasts.value[0].id)
  if (duration > 0)
    timers.set(
      id,
      setTimeout(() => remove(id), duration),
    )
  return id
}

function clear() {
  for (const id of toasts.value.map((t) => t.id)) remove(id)
}

export function useToast() {
  return {
    toasts,
    success: (msg, duration) => add('success', msg, duration),
    // Ошибки держатся дольше: их нужно успеть прочитать.
    error: (msg, duration = 6000) => add('error', msg, duration),
    info: (msg, duration) => add('info', msg, duration),
    remove,
    clear,
  }
}
