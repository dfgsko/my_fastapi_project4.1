<!-- Главный экран: список курсов из БД (GET /courses) с тремя состояниями. -->
<script setup>
import { ref, onMounted } from 'vue'
import apiClient from '@/api/client'

const items = ref([])
const isLoading = ref(true)
const error = ref(null)

async function loadItems() {
  isLoading.value = true
  error.value = null
  try {
    const response = await apiClient.get('/courses')
    items.value = response.data
  } catch (e) {
    error.value = 'Не удалось загрузить данные. Попробуйте позже.'
    console.error(e)
  } finally {
    isLoading.value = false
  }
}

// Загрузка в onMounted: компонент уже в DOM, поэтому переход «Загрузка… →
// список/ошибка» рендерится предсказуемо, а запрос не уходит, пока компонент
// не смонтирован (например, при серверном рендеринге).
onMounted(loadItems)
</script>

<template>
  <div class="home">
    <h1>Курсы</h1>
    <div v-if="isLoading" class="state loading">Загрузка…</div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="items.length === 0" class="state empty">Пока нет ни одной записи</div>
    <ul v-else class="items-list">
      <li v-for="item in items" :key="item.id" class="item-card">
        <h3>{{ item.title }}</h3>
        <p class="description">{{ item.description }}</p>
        <p class="meta">
          <span>Преподаватель: {{ item.instructor }}</span>
          <span>{{ item.duration_hours }} ч</span>
        </p>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.state {
  padding: 1rem;
  text-align: center;
}
.state.error {
  color: #c00;
}
.items-list {
  list-style: none;
  padding: 0;
}
.item-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 0.5rem;
  background: #fff;
}
.item-card h3 {
  margin: 0 0 0.25rem;
}
.description {
  margin: 0 0 0.5rem;
}
.meta {
  display: flex;
  justify-content: space-between;
  margin: 0;
  color: #666;
  font-size: 0.9rem;
}
</style>
