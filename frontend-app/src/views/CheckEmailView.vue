<!-- «Проверьте почту»: после регистрации письмо со ссылкой уже в очереди Celery. -->
<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import apiClient from '@/api/client'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

const route = useRoute()
const toast = useToast()
const email = ref(typeof route.query.email === 'string' ? route.query.email : '')
const sending = ref(false)

async function resend() {
  if (!email.value.trim()) return
  sending.value = true
  try {
    await apiClient.post('/auth/resend-verification', { email: email.value.trim() })
    toast.success('Если адрес зарегистрирован и не подтверждён, письмо отправлено.')
  } catch (e) {
    toast.error(
      e.response?.status === 429 ? 'Подождите минуту перед повтором' : 'Не удалось отправить',
    )
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <BaseCard class="check-email">
    <div class="icon" aria-hidden="true">✉</div>
    <h1>Проверьте почту</h1>
    <p v-if="route.query.email">
      Мы отправили письмо на <strong>{{ route.query.email }}</strong
      >. Перейдите по ссылке из письма, чтобы активировать аккаунт. Ссылка действует 24 часа.
    </p>
    <p v-else>Введите email, указанный при регистрации, и мы отправим ссылку ещё раз.</p>
    <form class="resend" @submit.prevent="resend">
      <BaseInput id="resend-email" v-model="email" type="email" label="Email" />
      <BaseButton type="submit" variant="secondary" :loading="sending">
        Отправить письмо ещё раз
      </BaseButton>
    </form>
    <p class="muted">Письмо не пришло? Проверьте папку «Спам».</p>
    <RouterLink to="/login">Перейти ко входу</RouterLink>
  </BaseCard>
</template>

<style scoped>
.check-email {
  max-width: 460px;
  margin: 50px auto;
  text-align: center;
}
.icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 1rem;
  border-radius: 50%;
  background: var(--color-secondary, #e2e8f0);
  color: var(--color-primary, #2b6cb0);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
}
.resend {
  text-align: left;
  margin: 1.5rem 0 0.5rem;
}
.muted {
  color: var(--color-muted, #4a5568);
  font-size: 0.9rem;
}
</style>
