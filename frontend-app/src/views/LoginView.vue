<!-- Страница входа: проверка ввода, индикатор загрузки, понятные ошибки. -->
<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

const auth = useAuthStore()
const username = ref('')
const password = ref('')
const error = ref('')
const isLoading = ref(false)

function messageFor(e) {
  const status = e?.response?.status
  if (status === 401) return 'Invalid username or password'
  if (status === 429) return 'Слишком много попыток входа. Подождите минуту и повторите.'
  // Нет ответа: бэкенд не запущен ИЛИ браузер заблокировал ответ по CORS.
  if (!e?.response) return 'Сервер недоступен или запрос заблокирован (CORS). Проверьте бэкенд.'
  return 'Не удалось выполнить вход. Попробуйте позже.'
}

async function handleSubmit() {
  error.value = ''
  isLoading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
  } catch (e) {
    error.value = messageFor(e)
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <BaseCard class="login-container">
    <h2>Login</h2>
    <form @submit.prevent="handleSubmit">
      <BaseInput
        id="username"
        v-model="username"
        label="Username"
        autocomplete="username"
        required
      />
      <BaseInput
        id="password"
        v-model="password"
        type="password"
        label="Password"
        autocomplete="current-password"
        required
      />
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <BaseButton type="submit" size="lg" class="submit" :loading="isLoading">
        {{ isLoading ? 'Logging in…' : 'Login' }}
      </BaseButton>
    </form>
  </BaseCard>
</template>

<style scoped>
.login-container {
  max-width: 400px;
  margin: 50px auto;
}
h2 {
  margin-top: 0;
}
.error {
  color: var(--color-danger, #c53030);
  margin: 0 0 1rem;
}
.submit {
  width: 100%;
}
</style>
