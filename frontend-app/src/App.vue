<!-- Корневой компонент: шапка с навигацией + <router-view> для страниц. -->
<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>

<template>
  <header class="app-header">
    <h1>Курсы и студенты</h1>
    <nav>
      <template v-if="auth.isAuthenticated">
        <RouterLink to="/">Главная</RouterLink>
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
</template>

<style scoped>
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #f5f5f5;
  border-bottom: 1px solid #e3e3e3;
}
.app-header h1 {
  margin: 0;
  font-size: 1.3rem;
}
nav {
  display: flex;
  gap: 1rem;
  align-items: center;
}
nav button {
  padding: 6px 12px;
  border: 1px solid #bbb;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
</style>
