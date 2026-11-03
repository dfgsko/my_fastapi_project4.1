<!-- Карточка курса в списке. Ссылка растянута на всю карточку (::after),
     поэтому карточка кликабельна мышью и доступна с клавиатуры (Tab, Enter). -->
<script setup>
import { RouterLink } from 'vue-router'
import BaseCard from '@/components/ui/BaseCard.vue'

defineProps({ course: { type: Object, required: true } })
</script>

<template>
  <BaseCard as="li" interactive class="course-card">
    <h3 class="course-card__title">
      <RouterLink :to="{ name: 'course-detail', params: { id: course.id } }" class="stretched">
        {{ course.title }}
      </RouterLink>
    </h3>
    <p class="course-card__description">{{ course.description }}</p>
    <p class="course-card__meta">
      <span>{{ course.instructor }}</span>
      <span class="badge">{{ course.duration_hours }} ч</span>
    </p>
  </BaseCard>
</template>

<style scoped>
.course-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.course-card__title {
  margin: 0;
  font-size: 1.1rem;
}
.stretched {
  color: var(--color-text, #1a202c);
  text-decoration: none;
}
.stretched::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
.stretched:focus-visible {
  outline: none;
}
.course-card__description {
  margin: 0;
  color: var(--color-muted, #4a5568);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.course-card__meta {
  margin: auto 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}
.badge {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: var(--color-secondary, #e2e8f0);
  white-space: nowrap;
}
</style>
