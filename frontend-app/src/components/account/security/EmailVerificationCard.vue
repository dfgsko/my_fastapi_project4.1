<!-- Карточка «Email»: статус подтверждения, дата, повторная отправка письма. -->
<script setup>
import { ref, onMounted } from 'vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import apiClient from '@/api/client'
import { getMe } from '@/api/account'

const toast = useToast()
const email = ref('')
const verified = ref(false)
const verifiedAt = ref(null)
const resending = ref(false)

onMounted(async () => {
  try {
    const { data } = await getMe()
    email.value = data.email
    verified.value = data.is_email_verified
    verifiedAt.value = data.email_verified_at
  } catch {
    /* карточка покажет пустое состояние */
  }
})

async function resend() {
  resending.value = true
  try {
    await apiClient.post('/auth/resend-verification')
    toast.success('Письмо отправлено повторно. Проверьте почту.')
  } catch (e) {
    toast.error(e.response?.status === 429 ? 'Подождите минуту перед повтором' : 'Не удалось')
  } finally {
    resending.value = false
  }
}
</script>

<template>
  <div class="security-card">
    <div class="card-header">
      <div>
        <h3>Email</h3>
        <p class="muted">
          <span :class="verified ? 'badge-on' : 'badge-off'">
            {{ verified ? '✓ Подтверждён' : '⚠ Не подтверждён' }}
          </span>
          <span v-if="verifiedAt"> · {{ new Date(verifiedAt).toLocaleDateString('ru-RU') }}</span>
        </p>
        <p class="email">{{ email || '—' }}</p>
      </div>
      <BaseButton v-if="!verified && email" :loading="resending" @click="resend">
        Отправить письмо ещё раз
      </BaseButton>
    </div>
    <p v-if="!verified" class="muted description">
      Аккаунт не активирован. Проверьте почту и перейдите по ссылке из письма.
    </p>
  </div>
</template>

<style scoped src="./security-card.css"></style>
