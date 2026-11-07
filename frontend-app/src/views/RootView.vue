<!-- Маршрут «/»: вошедший видит список курсов, гость — публичный лендинг.
     Условный рендеринг вместо двух маршрутов не ломает существующие ссылки на «/». -->
<script setup>
import { useAuthStore } from '@/stores/auth'
import HomeView from './HomeView.vue'
import LandingView from './LandingView.vue'

const auth = useAuthStore()
</script>

<template>
  <HomeView v-if="auth.isAuthenticated" />
  <LandingView v-else />
</template>
