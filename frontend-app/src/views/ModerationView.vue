<!-- /moderation (moderator, admin): пользователи, санкции и роли.
     Модератор: сброс username и блокировка клиентов. Администратор: ещё и роли. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import apiClient from '@/api/client'
import { useAuthStore, ROLE_LABELS } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { describeError } from '@/api/errors'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'

const auth = useAuthStore()
const toast = useToast()
const users = ref([])
const loading = ref(true)
const error = ref('')
const confirm = ref(null) // { user, action }
const busy = ref(false)

const LEVEL = { client: 0, moderator: 1, admin: 2 }
// Та же логика, что на бэкенде (там она и проверяется): модератор действует
// только над клиентами, администратор — над всеми, кроме себя.
const canAct = (u) => u.id !== auth.user?.id && (auth.isAdmin || LEVEL[u.role] < LEVEL[auth.role])

const stats = computed(() => ({
  total: users.value.length,
  blocked: users.value.filter((u) => !u.is_active).length,
  twoFa: users.value.filter((u) => u.totp_enabled).length,
}))

async function load() {
  loading.value = true
  try {
    users.value = (await apiClient.get('/users')).data
  } catch (e) {
    error.value = describeError(e, 'Не удалось загрузить пользователей')
  } finally {
    loading.value = false
  }
}

function replace(updated) {
  users.value = users.value.map((u) => (u.id === updated.id ? updated : u))
}

const ACTIONS = {
  reset: {
    title: 'Сбросить username',
    run: (u) => apiClient.post(`/users/${u.id}/reset-username`),
  },
  block: { title: 'Заблокировать', run: (u) => apiClient.post(`/users/${u.id}/block`) },
  unblock: { title: 'Разблокировать', run: (u) => apiClient.post(`/users/${u.id}/unblock`) },
}

async function runConfirmed() {
  const { user, action } = confirm.value
  busy.value = true
  try {
    replace((await ACTIONS[action].run(user)).data)
    toast.success(`${ACTIONS[action].title}: готово`)
    confirm.value = null
  } catch (e) {
    toast.error(describeError(e))
  } finally {
    busy.value = false
  }
}

async function changeRole(user, role) {
  try {
    replace((await apiClient.patch(`/users/${user.id}`, { role })).data)
    toast.success(`Роль ${user.username}: ${ROLE_LABELS[role]}`)
  } catch (e) {
    toast.error(describeError(e))
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1>Модерация</h1>
    <p class="muted">
      Всего: {{ stats.total }} · заблокировано: {{ stats.blocked }} · с 2FA: {{ stats.twoFa }}
    </p>
    <p v-if="loading">Загрузка…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Пользователь</th>
            <th>Email</th>
            <th>Роль</th>
            <th>Статус</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id" :class="{ blocked: !u.is_active }">
            <td>{{ u.id }}</td>
            <td>
              <strong>{{ u.display_name || u.username }}</strong>
              <div class="muted small">
                @{{ u.username }}<span v-if="u.totp_enabled"> · 2FA</span>
              </div>
            </td>
            <td class="small">{{ u.email || '—' }}</td>
            <td>
              <select
                v-if="auth.isAdmin && u.id !== auth.user?.id"
                :value="u.role"
                :aria-label="`Роль ${u.username}`"
                @change="changeRole(u, $event.target.value)"
              >
                <option value="client">Клиент</option>
                <option value="moderator">Модератор</option>
                <option value="admin">Администратор</option>
              </select>
              <span v-else>{{ ROLE_LABELS[u.role] }}</span>
            </td>
            <td>
              <span :class="u.is_active ? 'ok' : 'bad'">{{
                u.is_active ? 'Активен' : 'Заблокирован'
              }}</span>
            </td>
            <td class="actions">
              <template v-if="canAct(u)">
                <BaseButton
                  size="sm"
                  variant="secondary"
                  @click="confirm = { user: u, action: 'reset' }"
                >
                  Сбросить ник
                </BaseButton>
                <BaseButton
                  size="sm"
                  :variant="u.is_active ? 'danger' : 'secondary'"
                  @click="confirm = { user: u, action: u.is_active ? 'block' : 'unblock' }"
                >
                  {{ u.is_active ? 'Блок' : 'Разблок' }}
                </BaseButton>
              </template>
              <span v-else class="muted small">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <BaseModal
      :open="!!confirm"
      :title="confirm ? `${ACTIONS[confirm.action].title}: @${confirm.user.username}?` : ''"
      :persistent="busy"
      @close="confirm = null"
    >
      <p v-if="confirm?.action === 'reset'">
        Username станет «user{{ confirm.user.id }}», никнейм очистится. Пользователь сможет сразу
        выбрать новый username — без 6-месячного ожидания.
      </p>
      <p v-else-if="confirm?.action === 'block'">
        Пользователь не сможет войти, все его сессии будут завершены.
      </p>
      <p v-else>Пользователь снова сможет войти.</p>
      <template #actions>
        <BaseButton variant="secondary" :disabled="busy" @click="confirm = null">Отмена</BaseButton>
        <BaseButton
          :variant="confirm?.action === 'block' ? 'danger' : 'primary'"
          :loading="busy"
          @click="runConfirmed"
        >
          Подтвердить
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
.muted {
  color: var(--color-muted, #4a5568);
}
.small {
  font-size: 0.85rem;
}
.error {
  color: var(--color-danger, #c53030);
}
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-surface, #fff);
}
th,
td {
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--color-border, #e2e8f0);
  text-align: left;
  vertical-align: middle;
}
th {
  font-size: 0.85rem;
  color: var(--color-muted, #4a5568);
}
tr.blocked td {
  opacity: 0.6;
}
.ok {
  color: var(--color-success, #2f855a);
}
.bad {
  color: var(--color-danger, #c53030);
  font-weight: 600;
}
.actions {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
select {
  padding: 0.3rem;
  border-radius: 4px;
  border: 1px solid var(--color-border, #cbd5e0);
  background: var(--color-surface, #fff);
  color: inherit;
  font: inherit;
}
</style>
