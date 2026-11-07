<!-- /verify-age: после регистрации (registration=true) или из настроек аккаунта. -->
<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import AgeVerificationWidget from '@/components/AgeVerificationWidget.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const auth = useAuthStore()
const isRegistrationFlow = route.query.registration === 'true'
const isSkipping = ref(false)
const error = ref('')

async function completeRegistration(skip = false) {
  const { data } = await apiClient.post('/auth/complete-registration', {
    skip_age_verification: skip,
  })
  router.push({ name: 'check-email', query: data.email ? { email: data.email } : {} })
}

async function onVerificationSuccess(result) {
  const demo = result?.estimator === 'mock' ? ' (демо-режим оценщика)' : ''
  try {
    if (isRegistrationFlow) {
      // Завершаем регистрацию — бэкенд отправит письмо для активации.
      toast.success(`Возраст подтверждён${demo}. Проверьте почту для активации аккаунта.`)
      await completeRegistration(false)
    } else {
      toast.success(`Возраст подтверждён${demo}`)
      await auth.fetchMe()
      router.push({ name: 'account', query: { tab: 'security' } })
    }
  } catch (e) {
    error.value = sessionError(e)
  }
}

function sessionError(e) {
  return e.response?.status === 401
    ? 'Сессия регистрации истекла (30 минут). Войдите с логином и паролем, чтобы продолжить.'
    : 'Не удалось завершить регистрацию. Попробуйте ещё раз.'
}

async function skip() {
  isSkipping.value = true
  try {
    toast.info('Курсы 18+ будут скрыты. Подтвердить возраст можно позже в настройках.')
    await completeRegistration(true)
  } catch (e) {
    error.value = sessionError(e)
  } finally {
    isSkipping.value = false
  }
}
</script>

<template>
  <BaseCard class="age-page">
    <h1>Подтверждение возраста</h1>
    <p v-if="isRegistrationFlow">
      Часть курсов доступна только с 18 лет. Подтвердите возраст — после этого мы отправим письмо
      для активации аккаунта. Можно и пропустить: аккаунт заработает, но курсы 18+ будут скрыты.
    </p>
    <p v-else>Для доступа к курсам 18+ подтвердите, что вам больше 18 лет.</p>

    <AgeVerificationWidget @success="onVerificationSuccess" />

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div class="footer">
      <BaseButton v-if="isRegistrationFlow" variant="secondary" :loading="isSkipping" @click="skip">
        Пропустить
      </BaseButton>
      <RouterLink v-else :to="{ name: 'account', query: { tab: 'security' } }">
        ← Назад в настройки
      </RouterLink>
    </div>
    <p class="note">
      Оценка по фото — ориентировочная (погрешность около ±2 лет) и не защищает от чужих фотографий.
      Спорные случаи проверяет модератор.
    </p>
  </BaseCard>
</template>

<style scoped>
.age-page {
  max-width: 520px;
  margin: 40px auto;
}
h1 {
  margin-top: 0;
  font-size: 1.6rem;
}
.footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}
.error {
  color: var(--color-danger, #c53030);
}
.note {
  margin: 1.25rem 0 0;
  color: var(--color-muted, #4a5568);
  font-size: 0.85rem;
}
</style>
