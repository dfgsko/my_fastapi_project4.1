<!-- Переход по ссылке из письма: «Проверяем… N сек» → успех + отсчёт 5 сек → «/». -->
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import apiClient from '@/api/client'
import BaseButton from '@/components/ui/BaseButton.vue'

const route = useRoute()
const router = useRouter()

// 'pending' | 'success' | 'error'
const state = ref('pending')
const elapsed = ref(0)
const redirectIn = ref(5)
const errorMessage = ref('')
let tickInterval = null
let redirectInterval = null

onMounted(async () => {
  // Счётчик ожидания — только индикатор для пользователя, на запрос не влияет.
  tickInterval = setInterval(() => {
    elapsed.value += 1
  }, 1000)

  try {
    const token = route.query.token
    if (!token) throw new Error('Токен отсутствует в ссылке')

    await apiClient.get('/auth/verify-email', { params: { token } })

    clearInterval(tickInterval)
    state.value = 'success'
    startRedirectCountdown()
  } catch (e) {
    clearInterval(tickInterval)
    state.value = 'error'
    errorMessage.value =
      e?.response?.data?.detail || e?.message || 'Ссылка недействительна или истекла'
  }
})

function startRedirectCountdown() {
  redirectInterval = setInterval(() => {
    redirectIn.value -= 1
    if (redirectIn.value <= 0) {
      clearInterval(redirectInterval)
      router.push('/')
    }
  }, 1000)
}

// Без очистки таймеры продолжили бы тикать после ухода со страницы
// (утечка памяти и router.push уже из размонтированного компонента).
onUnmounted(() => {
  if (tickInterval) clearInterval(tickInterval)
  if (redirectInterval) clearInterval(redirectInterval)
})
</script>

<template>
  <div class="verify-email-screen">
    <!-- Экран 1: ожидание ответа со счётчиком -->
    <div v-if="state === 'pending'" class="state-card">
      <div class="spinner"></div>
      <h2>Проверяем ссылку…</h2>
      <p class="counter">{{ elapsed }} сек.</p>
      <p class="muted">Пожалуйста, не закрывайте страницу.</p>
    </div>

    <!-- Экран 2: успех + обратный отсчёт -->
    <div v-else-if="state === 'success'" class="state-card success">
      <div class="checkmark">✓</div>
      <h2>Email подтверждён</h2>
      <p class="muted">Аккаунт активирован, теперь можно войти.</p>
      <p class="redirect-hint">
        Перенаправление на главную через <strong>{{ redirectIn }}</strong> сек.
      </p>
    </div>

    <!-- Экран 3: ошибка -->
    <div v-else class="state-card error">
      <div class="cross">✗</div>
      <h2>Не удалось подтвердить email</h2>
      <p class="muted">{{ errorMessage }}</p>
      <BaseButton @click="router.push('/login')">Вернуться на страницу входа</BaseButton>
      <p>
        <RouterLink :to="{ name: 'check-email' }">Запросить новое письмо</RouterLink>
      </p>
    </div>
  </div>
</template>

<style scoped>
.verify-email-screen {
  min-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 0;
}
.state-card {
  text-align: center;
  max-width: 400px;
  padding: 2.5rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 16px;
  background: var(--color-surface, #fff);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05);
}
.spinner {
  width: 48px;
  height: 48px;
  margin: 0 auto 1.5rem;
  border: 4px solid var(--color-secondary, #e2e8f0);
  border-top-color: var(--color-primary, #2b6cb0);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.counter {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-primary, #2b6cb0);
  margin: 1rem 0;
}
.checkmark,
.cross {
  width: 72px;
  height: 72px;
  margin: 0 auto 1.5rem;
  border-radius: 50%;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.5rem;
  font-weight: 700;
}
.checkmark {
  background: #38a169;
  animation: pop 0.3s ease;
}
.cross {
  background: #c53030;
}
@keyframes pop {
  0% {
    transform: scale(0);
  }
  100% {
    transform: scale(1);
  }
}
.muted {
  color: var(--color-muted, #718096);
}
.redirect-hint {
  margin-top: 1rem;
  font-size: 0.875rem;
  color: var(--color-muted, #4a5568);
}
@media (prefers-reduced-motion: reduce) {
  .spinner,
  .checkmark {
    animation: none;
  }
}
</style>
