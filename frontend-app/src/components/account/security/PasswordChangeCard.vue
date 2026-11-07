<!-- Карточка «Пароль»: смена с проверкой текущего; остальные сессии завершаются. -->
<script setup>
import { onMounted, ref } from 'vue'
import { useForm } from '@/composables/useForm'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import apiClient from '@/api/client'
import { getMe } from '@/api/account'

const toast = useToast()
const lastChanged = ref('—')

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString('ru-RU') : '—'
}

onMounted(async () => {
  try {
    const { data } = await getMe()
    lastChanged.value = formatDate(data.password_changed_at || data.created_at)
  } catch {
    /* дата необязательна */
  }
})

const { values, errors, isSubmitting, submitError, submit, reset } = useForm(
  { oldPassword: '', newPassword: '', confirmPassword: '' },
  {
    oldPassword: (v) => (!v ? 'Введите текущий пароль' : ''),
    newPassword: (v) => (v.length < 12 ? 'Минимум 12 символов' : ''),
    confirmPassword: (v, all) => (v !== all.newPassword ? 'Пароли не совпадают' : ''),
  },
  async (data) => {
    try {
      await apiClient.post('/auth/change-password', {
        current_password: data.oldPassword,
        new_password: data.newPassword,
      })
      toast.success('Пароль изменён. Остальные сессии завершены.')
      lastChanged.value = formatDate(new Date().toISOString())
      reset()
    } catch (e) {
      // 400 (не 401): 401 перехватчик Axios принял бы за истёкшую сессию.
      if (e.response?.status === 400) {
        const detail = e.response.data?.detail || ''
        errors.value = detail.includes('совпадает')
          ? { newPassword: detail }
          : { oldPassword: 'Неверный текущий пароль' }
      } else throw e
    }
  },
)
</script>

<template>
  <div class="security-card">
    <div class="card-header">
      <h3>Пароль</h3>
      <p class="muted">Последнее изменение: {{ lastChanged }}</p>
    </div>
    <form novalidate @submit.prevent="submit">
      <BaseInput
        id="oldPassword"
        v-model="values.oldPassword"
        type="password"
        label="Текущий пароль"
        autocomplete="current-password"
        :error="errors.oldPassword"
      />
      <BaseInput
        id="newPassword"
        v-model="values.newPassword"
        type="password"
        label="Новый пароль"
        autocomplete="new-password"
        :error="errors.newPassword"
      />
      <BaseInput
        id="confirmNewPassword"
        v-model="values.confirmPassword"
        type="password"
        label="Повторите новый пароль"
        autocomplete="new-password"
        :error="errors.confirmPassword"
      />
      <p v-if="submitError" class="error">{{ submitError }}</p>
      <BaseButton type="submit" :loading="isSubmitting">Сменить пароль</BaseButton>
    </form>
  </div>
</template>

<style scoped src="./security-card.css"></style>
<style scoped>
.card-header {
  align-items: baseline;
  margin-bottom: 1rem;
}
form {
  max-width: 420px;
}
</style>
