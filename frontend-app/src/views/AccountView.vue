<!-- /account: шапка (аватар + ник + @username) и вкладки. Активная вкладка —
     в ?tab=…, поэтому на неё можно дать ссылку (например, из меню «Безопасность»). -->
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore, ROLE_LABELS } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import UserAvatar from '@/components/UserAvatar.vue'
import AccountProfileTab from '@/components/account/AccountProfileTab.vue'
import AccountSettingsTab from '@/components/account/AccountSettingsTab.vue'
import AccountSecurityTab from '@/components/account/AccountSecurityTab.vue'
import AccountSessionsTab from '@/components/account/AccountSessionsTab.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const toast = useToast()

const tabs = [
  { id: 'profile', label: 'Профиль', component: AccountProfileTab },
  { id: 'settings', label: 'Настройки', component: AccountSettingsTab },
  { id: 'security', label: 'Безопасность', component: AccountSecurityTab },
  { id: 'sessions', label: 'Сессии', component: AccountSessionsTab },
]

const isTab = (id) => tabs.some((t) => t.id === id)
// Локальное состояние + синхронизация с ?tab=: компонент работает и без роутера (тесты).
const activeTab = ref(isTab(route?.query?.tab) ? route.query.tab : 'profile')
watch(
  () => route?.query?.tab,
  (tab) => {
    if (isTab(tab)) activeTab.value = tab
  },
)
const current = computed(() => tabs.find((t) => t.id === activeTab.value))

function select(id) {
  activeTab.value = id
  router?.replace({ query: { ...route?.query, tab: id, age: undefined } })
}

onMounted(() => {
  // Возврат после внешней проверки возраста (?age=success|failure).
  if (route.query?.age === 'success') toast.success('Возраст подтверждён')
  if (route.query?.age === 'failure') toast.error('Не удалось подтвердить возраст')
})
</script>

<template>
  <div class="account">
    <header class="account-header">
      <UserAvatar :user="auth.user" :size="64" />
      <div>
        <h1>{{ auth.user?.display_name || auth.user?.username }}</h1>
        <p class="muted">@{{ auth.user?.username }} · {{ ROLE_LABELS[auth.user?.role] || '—' }}</p>
      </div>
    </header>

    <nav class="tabs" role="tablist">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        class="tab"
        :class="{ active: activeTab === t.id }"
        :aria-selected="activeTab === t.id"
        @click="select(t.id)"
      >
        {{ t.label }}
      </button>
    </nav>

    <section class="panel" role="tabpanel">
      <component :is="current.component" />
    </section>
  </div>
</template>

<style scoped>
.account {
  max-width: 760px;
  margin: 0 auto;
}
.account-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0.5rem 0 1.25rem;
}
.account-header h1 {
  margin: 0;
  font-size: 1.5rem;
}
.muted {
  margin: 0.2rem 0 0;
  color: var(--color-muted, #4a5568);
}
.tabs {
  display: flex;
  gap: 0.25rem;
  border-bottom: 1px solid var(--color-border, #cbd5e0);
  overflow-x: auto;
}
.tab {
  padding: 0.6rem 1rem;
  border: 0;
  border-bottom: 3px solid transparent;
  background: none;
  color: var(--color-muted, #4a5568);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.tab:hover {
  color: var(--color-text, #1a202c);
}
.tab.active {
  color: var(--color-primary, #2b6cb0);
  border-bottom-color: var(--color-primary, #2b6cb0);
}
.tab:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
.panel {
  padding: 1.5rem 0;
}
</style>
