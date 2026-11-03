<!-- Страница входа: проверка ввода, индикатор загрузки, понятные ошибки. -->
<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

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
  <div class="login-container">
    <h2>Login</h2>
    <form @submit.prevent="handleSubmit">
      <label for="username">Username</label>
      <input id="username" v-model="username" autocomplete="username" required />
      <label for="password">Password</label>
      <input
        id="password"
        v-model="password"
        type="password"
        autocomplete="current-password"
        required
      />
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="isLoading">
        {{ isLoading ? 'Logging in…' : 'Login' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-container {
  max-width: 400px;
  margin: 50px auto;
  padding: 24px;
  border: 1px solid #ccc;
  border-radius: 8px;
  background: #fff;
}
form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
input {
  padding: 8px;
  border: 1px solid #bbb;
  border-radius: 4px;
  font-size: 1rem;
}
.error {
  color: #c00;
  margin: 4px 0;
}
button {
  margin-top: 10px;
  padding: 10px;
  border: 0;
  border-radius: 4px;
  background: #2a6df4;
  color: #fff;
  font-size: 1rem;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
