<!-- Меню пользователя в шапке: аватар + никнейм → выпадающее меню. -->
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore, ROLE_LABELS } from '@/stores/auth'
import UserAvatar from '@/components/UserAvatar.vue'

const auth = useAuthStore()
const open = ref(false)
const root = ref(null)

function close() {
  open.value = false
}
function onDocClick(e) {
  if (root.value && !root.value.contains(e.target)) close()
}
function onKey(e) {
  if (e.key === 'Escape') close()
}
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})

async function logout() {
  close()
  await auth.logout()
}
</script>

<template>
  <div ref="root" class="user-menu">
    <button
      type="button"
      class="trigger"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <UserAvatar :user="auth.user" :size="32" />
      <span class="name">{{ auth.displayName }}</span>
      <span class="caret" aria-hidden="true">▾</span>
    </button>
    <div v-if="open" class="dropdown" role="menu">
      <div class="who">
        <strong>{{ auth.displayName }}</strong>
        <span class="muted">@{{ auth.user?.username }} · {{ ROLE_LABELS[auth.role] }}</span>
      </div>
      <RouterLink to="/account" role="menuitem" @click="close">Аккаунт</RouterLink>
      <RouterLink
        :to="{ name: 'account', query: { tab: 'security' } }"
        role="menuitem"
        @click="close"
      >
        Безопасность
      </RouterLink>
      <RouterLink v-if="auth.isModerator" to="/moderation" role="menuitem" @click="close">
        Модерация
      </RouterLink>
      <button type="button" role="menuitem" class="logout" @click="logout">Выйти</button>
    </div>
  </div>
</template>

<style scoped>
.user-menu {
  position: relative;
}
.trigger {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 4px 10px 4px 4px;
  border: 1px solid var(--color-border, #cbd5e0);
  border-radius: 999px;
  background: var(--color-surface, #fff);
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.trigger:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
.name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.caret {
  color: var(--color-muted, #4a5568);
  font-size: 0.75rem;
}
.dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: 50;
  display: flex;
  flex-direction: column;
  min-width: 220px;
  padding: 0.35rem 0;
  border: 1px solid var(--color-border, #cbd5e0);
  border-radius: var(--radius-md, 6px);
  background: var(--color-surface, #fff);
  box-shadow: var(--shadow-md);
}
.who {
  display: flex;
  flex-direction: column;
  padding: 0.5rem 0.9rem 0.6rem;
  border-bottom: 1px solid var(--color-border, #cbd5e0);
  margin-bottom: 0.25rem;
}
.muted {
  color: var(--color-muted, #4a5568);
  font-size: 0.85rem;
}
.dropdown a,
.dropdown button {
  padding: 0.5rem 0.9rem;
  border: 0;
  background: none;
  color: var(--color-text, #1a202c);
  font: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.dropdown a:hover,
.dropdown button:hover {
  background: var(--color-secondary, #e2e8f0);
}
.logout {
  color: var(--color-danger, #c53030) !important;
}
@media (max-width: 480px) {
  .name {
    display: none;
  }
}
</style>
