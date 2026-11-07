<!-- Детали курса: все поля, редактирование и удаление с подтверждением. -->
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useResource } from '@/composables/useResource'
import { useToast } from '@/composables/useToast'
import { describeError } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import BaseModal from '@/components/ui/BaseModal.vue'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()
const toast = useToast()
const auth = useAuthStore()
const { item, isLoading, error, notFound, errorCode, fetchOne, remove } = useResource('/courses')

const showConfirm = ref(false)
const isDeleting = ref(false)

onMounted(() => fetchOne(props.id))

async function confirmDelete() {
  isDeleting.value = true
  const title = item.value?.title
  try {
    await remove(props.id)
    showConfirm.value = false
    toast.success(`Курс «${title}» удалён`)
    router.push({ name: 'home' })
  } catch (e) {
    toast.error(describeError(e, 'Не удалось удалить курс'))
  } finally {
    isDeleting.value = false
  }
}
</script>

<template>
  <div class="detail">
    <RouterLink :to="{ name: 'home' }" class="back">← Все курсы</RouterLink>

    <div v-if="isLoading" class="state">Загрузка…</div>
    <!-- Курс 18+: бэкенд вернул 403 с X-Error-Code — показываем заглушку, а не ошибку. -->
    <BaseCard v-else-if="errorCode === 'age_verification_required'" class="age-lock">
      <div class="lock" aria-hidden="true">18+</div>
      <h1>Для доступа подтвердите возраст</h1>
      <p>Этот курс доступен только пользователям, подтвердившим, что им больше 18 лет.</p>
      <BaseButton @click="router.push('/verify-age')">Подтвердить возраст</BaseButton>
    </BaseCard>
    <div v-else-if="notFound" class="state error">
      <h1>Запись не найдена</h1>
      <p>Возможно, курс уже удалён.</p>
    </div>
    <div v-else-if="error" class="state error">
      <p>{{ error }}</p>
      <BaseButton variant="secondary" size="sm" @click="fetchOne(id)">Повторить</BaseButton>
    </div>

    <BaseCard v-else-if="item" as="article">
      <template #header>
        <h1 class="title">{{ item.title }}</h1>
      </template>
      <dl class="fields">
        <dt>Описание</dt>
        <dd class="description">{{ item.description }}</dd>
        <dt>Преподаватель</dt>
        <dd>{{ item.instructor }}</dd>
        <dt>Длительность</dt>
        <dd>{{ item.duration_hours }} ч</dd>
        <dt>Возраст</dt>
        <dd>{{ item.min_age > 0 ? `${item.min_age}+` : 'Для всех' }}</dd>
        <dt>ID</dt>
        <dd>{{ item.id }}</dd>
      </dl>
      <template v-if="auth.canManageContent" #footer>
        <div class="actions">
          <BaseButton @click="router.push({ name: 'course-edit', params: { id } })">
            Редактировать
          </BaseButton>
          <BaseButton variant="danger" @click="showConfirm = true">Удалить</BaseButton>
        </div>
      </template>
    </BaseCard>

    <BaseModal
      :open="showConfirm"
      :title="`Удалить «${item?.title}»?`"
      :persistent="isDeleting"
      @close="showConfirm = false"
    >
      <p>Это действие невозможно отменить. Записи студентов на курс тоже будут удалены.</p>
      <template #actions>
        <BaseButton
          variant="secondary"
          data-autofocus
          :disabled="isDeleting"
          @click="showConfirm = false"
        >
          Отмена
        </BaseButton>
        <BaseButton variant="danger" :loading="isDeleting" @click="confirmDelete">
          Да, удалить
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
.back {
  display: inline-block;
  margin-bottom: 1rem;
}
.title {
  margin: 0;
}
.fields {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.5rem 1.5rem;
  margin: 0;
}
dt {
  font-weight: 600;
  color: var(--color-muted, #4a5568);
}
dd {
  margin: 0;
}
.description {
  white-space: pre-line;
}
@media (max-width: 480px) {
  .fields {
    grid-template-columns: 1fr;
  }
  dd {
    margin-bottom: 0.5rem;
  }
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.age-lock {
  max-width: 480px;
  margin: 1rem auto;
  text-align: center;
}
.age-lock h1 {
  font-size: 1.4rem;
}
.lock {
  width: 72px;
  height: 72px;
  margin: 0 auto 1rem;
  border-radius: 50%;
  background: var(--color-danger, #c53030);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
  font-weight: 800;
}
.state {
  padding: 2rem 1rem;
  text-align: center;
}
.state.error {
  color: var(--color-danger, #c53030);
}
</style>
