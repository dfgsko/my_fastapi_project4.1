<!-- Вкладка «Сессии»: активные входы (устройство, IP, даты), отзыв каждой
     и «Выйти со всех устройств». Сессия = цепочка refresh-токенов (family_id). -->
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { accountApi } from '@/api/account'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { describeError } from '@/api/errors'
import BaseButton from '@/components/ui/BaseButton.vue'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const sessions = ref([])
const loading = ref(true)
const error = ref('')

/** Упрощённый разбор User-Agent: браузер и ОС для подписи. */
function describeDevice(ua) {
  if (!ua) return 'Неизвестное устройство'
  const browser = /Edg\//.test(ua)
    ? 'Edge'
    : /Chrome\//.test(ua)
      ? 'Chrome'
      : /Firefox\//.test(ua)
        ? 'Firefox'
        : /Safari\//.test(ua)
          ? 'Safari'
          : /python|httpx|curl/i.test(ua)
            ? 'API-клиент'
            : 'Браузер'
  const os = /Windows/.test(ua)
    ? 'Windows'
    : /Android/.test(ua)
      ? 'Android'
      : /iPhone|iPad/.test(ua)
        ? 'iOS'
        : /Mac OS X/.test(ua)
          ? 'macOS'
          : /Linux/.test(ua)
            ? 'Linux'
            : ''
  return os ? `${browser} · ${os}` : browser
}

function fmt(value) {
  return value
    ? new Date(value).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
    : '—'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    sessions.value = await accountApi.sessions()
  } catch (e) {
    error.value = describeError(e, 'Не удалось загрузить сессии')
  } finally {
    loading.value = false
  }
}

async function leave() {
  auth.clearSession()
  await router.push('/login')
}

async function revoke(s) {
  try {
    await accountApi.revokeSession(s.id)
    if (s.current) {
      toast.info('Текущая сессия завершена')
      return leave()
    }
    toast.success('Сессия отозвана')
    sessions.value = sessions.value.filter((x) => x.id !== s.id)
  } catch (e) {
    toast.error(describeError(e))
  }
}

async function logoutAll() {
  try {
    await accountApi.logoutAll()
    toast.info('Вы вышли на всех устройствах')
    await leave()
  } catch (e) {
    toast.error(describeError(e))
  }
}

onMounted(load)
</script>

<template>
  <div class="sessions-tab">
    <div class="head">
      <h2>Активные сессии</h2>
      <BaseButton variant="danger" size="sm" @click="logoutAll">Выйти со всех устройств</BaseButton>
    </div>
    <p v-if="loading" class="muted">Загрузка…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <ul v-else class="list">
      <li v-for="s in sessions" :key="s.id" class="session" :class="{ current: s.current }">
        <div>
          <strong>{{ describeDevice(s.user_agent) }}</strong>
          <span v-if="s.current" class="badge">Это устройство</span>
          <p class="muted">
            IP {{ s.ip_address || '—' }} · вход {{ fmt(s.started_at) }} · активность
            {{ fmt(s.last_active_at) }}
          </p>
        </div>
        <BaseButton size="sm" variant="secondary" @click="revoke(s)">
          {{ s.current ? 'Выйти' : 'Отозвать' }}
        </BaseButton>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}
h2 {
  margin: 0;
}
.list {
  list-style: none;
  padding: 0;
  margin: 1rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.session {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 12px;
  background: var(--color-surface, #fff);
}
.session.current {
  border-color: var(--color-primary, #2b6cb0);
}
.badge {
  margin-left: 0.5rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: var(--color-primary, #2b6cb0);
  color: #fff;
  font-size: 0.75rem;
}
.muted {
  margin: 0.25rem 0 0;
  color: var(--color-muted, #4a5568);
  font-size: 0.875rem;
}
.error {
  color: var(--color-danger, #c53030);
}
</style>
