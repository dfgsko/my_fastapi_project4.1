// Отложенное значение: обновляется, только когда source не меняется delay мс.
// Нужен для поиска: запрос уходит после паузы в наборе, а не на каждую букву.
import { onScopeDispose, ref, watch } from 'vue'

export function useDebouncedRef(source, delay = 300) {
  const debounced = ref(source.value)
  let timer
  watch(source, (value) => {
    clearTimeout(timer)
    timer = setTimeout(() => (debounced.value = value), delay)
  })
  onScopeDispose(() => clearTimeout(timer))
  return debounced
}
