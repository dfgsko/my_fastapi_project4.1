<!-- Список курсов: useResource, поиск по преподавателю с debounce, адаптивная сетка. -->
<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useResource } from '@/composables/useResource'
import { useDebouncedRef } from '@/composables/useDebounce'
import { useAuthStore } from '@/stores/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import CourseCard from '@/components/CourseCard.vue'

const router = useRouter()
const auth = useAuthStore()
const { items, isLoading, error, fetchList } = useResource('/courses')

const search = ref('')
const debouncedSearch = useDebouncedRef(search, 300)

// Фильтр выполняет бэкенд (GET /courses?instructor=…, частичное совпадение).
function load() {
  const instructor = debouncedSearch.value.trim()
  return fetchList(instructor ? { instructor } : {})
}

onMounted(load)
watch(debouncedSearch, load)
</script>

<template>
  <div>
    <header class="page-header">
      <h1>Курсы</h1>
      <BaseButton v-if="auth.isAdmin" @click="router.push({ name: 'course-create' })">
        + Добавить
      </BaseButton>
    </header>

    <BaseInput
      id="search"
      v-model="search"
      type="search"
      label="Поиск по преподавателю"
      placeholder="Например, Иванов"
      autocomplete="off"
      class="search"
    />

    <div v-if="isLoading && items.length === 0" class="state loading">Загрузка…</div>
    <div v-else-if="error" class="state error">
      <p>{{ error }}</p>
      <BaseButton variant="secondary" size="sm" @click="load">Повторить</BaseButton>
    </div>
    <div v-else-if="items.length === 0" class="state empty">
      {{ search.trim() ? 'Ничего не найдено' : 'Пока нет ни одной записи' }}
    </div>
    <ul v-else class="items-list" :class="{ 'items-list--stale': isLoading }">
      <CourseCard v-for="item in items" :key="item.id" :course="item" />
    </ul>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.search {
  max-width: 360px;
}
/* Адаптивная сетка без медиа-запросов: столько колонок по 240px, сколько влезет. */
.items-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1rem;
  list-style: none;
  padding: 0;
  margin: 0;
  transition: opacity 0.15s ease;
}
.items-list--stale {
  opacity: 0.6;
}
.state {
  padding: 2rem 1rem;
  text-align: center;
}
.state.error {
  color: var(--color-danger, #c53030);
}
</style>
