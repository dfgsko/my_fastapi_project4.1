<!-- Вход в два шага: пароль → (если включена 2FA) 6-значный код из приложения.
     temp_token второго шага хранится только в памяти компонента (ref). -->
<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

const auth = useAuthStore()
const router = useRouter()

const step = ref('password') // 'password' | '2fa'
const username = ref('')
const password = ref('')
const code = ref('')
const tempToken = ref('')
const useRecovery = ref(false)
const error = ref('')
const errorCode = ref('')
const isLoading = ref(false)

function messageFor(e) {
  const status = e?.response?.status
  if (status === 401) return 'Неверный логин или пароль'
  if (status === 403) return e.response.data?.detail || 'Вход запрещён'
  if (status === 429) return 'Слишком много попыток входа. Подождите минуту и повторите.'
  // Нет ответа: бэкенд не запущен ИЛИ браузер заблокировал ответ по CORS.
  if (!e?.response) return 'Сервер недоступен или запрос заблокирован (CORS). Проверьте бэкенд.'
  return 'Не удалось выполнить вход. Попробуйте позже.'
}

async function handlePassword() {
  error.value = ''
  errorCode.value = ''
  isLoading.value = true
  try {
    const result = await auth.login(username.value.trim(), password.value)
    if (result?.twoFactor) {
      tempToken.value = result.tempToken
      password.value = '' // пароль больше не нужен — не держим его в памяти
      step.value = '2fa'
    }
  } catch (e) {
    error.value = messageFor(e)
    errorCode.value = e?.response?.data?.code || ''
  } finally {
    isLoading.value = false
  }
}

async function handle2FA() {
  error.value = ''
  isLoading.value = true
  try {
    await auth.verifyTwoFactor(tempToken.value, code.value.trim())
  } catch (e) {
    const status = e?.response?.status
    if (status === 401) {
      // temp_token живёт 5 минут и одноразовый — начинаем вход заново.
      backToPassword('Время на ввод кода истекло. Войдите ещё раз.')
    } else if (status === 429) {
      error.value = 'Слишком много попыток. Подождите несколько минут.'
    } else {
      error.value = 'Неверный код. Попробуйте ещё раз.'
    }
  } finally {
    isLoading.value = false
  }
}

function backToPassword(message = '') {
  step.value = 'password'
  tempToken.value = ''
  code.value = ''
  useRecovery.value = false
  error.value = message
}
</script>

<template>
  <BaseCard class="login-container">
    <template v-if="step === 'password'">
      <h2>Вход</h2>
      <form @submit.prevent="handlePassword">
        <BaseInput
          id="username"
          v-model="username"
          label="Username или email"
          autocomplete="username"
          required
        />
        <BaseInput
          id="password"
          v-model="password"
          type="password"
          label="Пароль"
          autocomplete="current-password"
          required
        />
        <div v-if="error" class="error" role="alert">
          <p>{{ error }}</p>
          <BaseButton
            v-if="errorCode === 'age_verification_required'"
            size="sm"
            variant="secondary"
            @click="router.push({ name: 'verify-age', query: { registration: 'true' } })"
          >
            Пройти проверку возраста
          </BaseButton>
          <RouterLink v-if="errorCode === 'email_not_verified'" :to="{ name: 'check-email' }">
            Отправить письмо ещё раз
          </RouterLink>
        </div>
        <BaseButton type="submit" size="lg" class="submit" :loading="isLoading">
          {{ isLoading ? 'Входим…' : 'Войти' }}
        </BaseButton>
      </form>
      <p class="alt">Нет аккаунта? <RouterLink to="/register">Зарегистрироваться</RouterLink></p>
    </template>

    <template v-else>
      <h2>Двухфакторная аутентификация</h2>
      <form @submit.prevent="handle2FA">
        <p class="hint">
          {{
            useRecovery
              ? 'Введите один из кодов восстановления, сохранённых при включении 2FA.'
              : 'Введите 6-значный код из Google Authenticator, Microsoft Authenticator или Authy.'
          }}
        </p>
        <BaseInput
          id="code"
          v-model="code"
          :label="useRecovery ? 'Код восстановления' : 'Код'"
          :maxlength="useRecovery ? 20 : 6"
          :inputmode="useRecovery ? 'text' : 'numeric'"
          autocomplete="one-time-code"
          required
        />
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <BaseButton type="submit" size="lg" class="submit" :loading="isLoading">
          Подтвердить
        </BaseButton>
      </form>
      <div class="links">
        <button type="button" class="link" @click="useRecovery = !useRecovery">
          {{ useRecovery ? 'Ввести код из приложения' : 'Нет доступа к телефону?' }}
        </button>
        <button type="button" class="link" @click="backToPassword()">← Назад</button>
      </div>
    </template>
  </BaseCard>
</template>

<style scoped>
.login-container {
  max-width: 420px;
  margin: 50px auto;
}
h2 {
  margin-top: 0;
}
.hint {
  margin-top: 0;
  color: var(--color-muted, #4a5568);
}
.error {
  color: var(--color-danger, #c53030);
  margin: 0 0 1rem;
}
.error p {
  margin: 0 0 0.5rem;
}
.submit {
  width: 100%;
}
.alt {
  margin: 1rem 0 0;
  text-align: center;
  color: var(--color-muted, #4a5568);
}
.links {
  display: flex;
  justify-content: space-between;
  margin-top: 1rem;
}
.link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-primary, #2b6cb0);
  font: inherit;
  cursor: pointer;
}
.link:hover {
  text-decoration: underline;
}
</style>
