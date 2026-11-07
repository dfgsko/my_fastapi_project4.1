<!-- Корневой компонент: шапка с навигацией, <router-view> и контейнер уведомлений. -->
<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ToastContainer from '@/components/ui/ToastContainer.vue'
import UserMenu from '@/components/UserMenu.vue'

const auth = useAuthStore()
</script>

<template>
  <header class="app-header">
    <RouterLink to="/" class="brand">Курсы и студенты</RouterLink>
    <nav>
      <template v-if="auth.isAuthenticated">
        <RouterLink to="/">Курсы</RouterLink>
        <!-- Пункт виден только модераторам и администраторам. -->
        <RouterLink v-if="auth.isModerator" to="/moderation">Модерация</RouterLink>
        <UserMenu />
      </template>
      <template v-else-if="auth.initialized">
        <RouterLink to="/login">Войти</RouterLink>
        <RouterLink to="/register" class="cta">Регистрация</RouterLink>
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
  padding: 0.6rem 1rem;
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
.cta {
  padding: 6px 12px;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-primary, #2b6cb0);
  color: #fff;
  text-decoration: none;
}
.cta:hover {
  background: var(--color-primary-hover, #2c5282);
}
</style>
