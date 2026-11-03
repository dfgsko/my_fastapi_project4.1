<!-- Создание курса: тонкая обёртка над CourseForm. -->
<script setup>
import { useRouter } from 'vue-router'
import { useResource } from '@/composables/useResource'
import { useToast } from '@/composables/useToast'
import BaseCard from '@/components/ui/BaseCard.vue'
import CourseForm from '@/components/CourseForm.vue'

const router = useRouter()
const toast = useToast()
const { create } = useResource('/courses')

async function save(payload) {
  const created = await create(payload) // ошибку (422 и др.) покажет форма
  toast.success(`Курс «${created.title}» создан`)
  router.push({ name: 'course-detail', params: { id: created.id } })
  return created
}
</script>

<template>
  <div>
    <h1>Новый курс</h1>
    <BaseCard>
      <CourseForm mode="create" :on-submit="save" @cancel="router.push({ name: 'home' })" />
    </BaseCard>
  </div>
</template>
