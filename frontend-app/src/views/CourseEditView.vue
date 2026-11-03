<!-- Редактирование курса: загрузка текущих данных, PUT, обработка 404. -->
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useResource } from '@/composables/useResource'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import CourseForm from '@/components/CourseForm.vue'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()
const toast = useToast()
const { item, isLoading, error, notFound, fetchOne, update } = useResource('/courses')
const deletedWhileEditing = ref(false)

onMounted(() => fetchOne(props.id))

async function save(payload) {
  try {
    const saved = await update(props.id, payload)
    toast.success('Изменения сохранены')
    router.push({ name: 'course-detail', params: { id: props.id } })
    return saved
  } catch (e) {
    // Курс удалили, пока форма была открыта: PUT вернул 404.
    if (e.response?.status === 404) {
      deletedWhileEditing.value = true
      toast.error('Курс уже удалён другим пользователем')
      return null
    }
    throw e // 422 и остальное обработает форма
  }
}
</script>

<template>
  <div>
    <RouterLink :to="{ name: 'course-detail', params: { id } }" class="back">← К курсу</RouterLink>

    <!-- Форму не показываем, пока нет данных: иначе поля были бы пустыми. -->
    <div v-if="isLoading" class="state">Загрузка…</div>
    <div v-else-if="notFound || deletedWhileEditing" class="state error">
      <h1>Запись не найдена</h1>
      <p>Курс удалён, изменения сохранить нельзя.</p>
      <BaseButton variant="secondary" @click="router.push({ name: 'home' })">
        К списку курсов
      </BaseButton>
    </div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="item">
      <h1>Редактировать: {{ item.title }}</h1>
      <BaseCard>
        <CourseForm
          :initial-values="item"
          mode="edit"
          :on-submit="save"
          @cancel="router.push({ name: 'course-detail', params: { id } })"
        />
      </BaseCard>
    </div>
  </div>
</template>

<style scoped>
.back {
  display: inline-block;
  margin-bottom: 1rem;
}
.state {
  padding: 2rem 1rem;
  text-align: center;
}
.state.error {
  color: var(--color-danger, #c53030);
}
</style>
