<!-- Корневой компонент: шапка с навигацией, <router-view> и контейнер уведомлений. -->
<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ToastContainer from '@/components/ui/ToastContainer.vue'

const auth = useAuthStore()
</script>

<template>
  <header class="app-header">
    <RouterLink to="/" class="brand">Курсы и студенты</RouterLink>
    <nav>
      <template v-if="auth.isAuthenticated">
        <RouterLink to="/">Главная</RouterLink>
        <span v-if="auth.user" class="user">
          {{ auth.user.username }}<span v-if="auth.isAdmin" class="role">admin</span>
        </span>
        <button type="button" @click="auth.logout()">Logout</button>
      </template>
      <template v-else>
        <RouterLink to="/login">Login</RouterLink>
      </template>
    </nav>
  </header>
  <main>
    <RouterView />
  </main>
  <ToastContainer />
</template>

<style scoped>
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  padding: 0.75rem 1rem;
  background: var(--color-surface, #fff);
  border-bottom: 1px solid var(--color-border, #cbd5e0);
}
.brand {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--color-text, #1a202c);
  text-decoration: none;
}
nav {
  display: flex;
  gap: 1rem;
  align-items: center;
}
.user {
  color: var(--color-muted, #4a5568);
}
.role {
  margin-left: 0.35rem;
  padding: 0.05rem 0.4rem;
  border-radius: 999px;
  background: var(--color-primary, #2b6cb0);
  color: #fff;
  font-size: 0.75rem;
}
nav button {
  padding: 6px 12px;
  border: 1px solid var(--color-border, #cbd5e0);
  border-radius: var(--radius-sm, 4px);
  background: var(--color-surface, #fff);
  font: inherit;
  cursor: pointer;
}
nav button:hover {
  background: var(--color-secondary, #e2e8f0);
}
nav button:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring, 0 0 0 3px rgba(43, 108, 176, 0.35));
}
</style>
