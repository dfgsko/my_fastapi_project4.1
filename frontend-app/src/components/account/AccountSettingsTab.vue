<!-- Вкладка «Настройки»: тема (работает), язык и уведомления — заготовки на будущее. -->
<script setup>
import { ref } from 'vue'
import { useTheme } from '@/composables/useTheme'

const { theme, setTheme } = useTheme()
const language = ref('ru')
const emailNotifications = ref(true)
</script>

<template>
  <div class="settings-tab">
    <h2>Настройки</h2>

    <div class="setting-row">
      <label for="theme">Тема оформления</label>
      <select id="theme" :value="theme" @change="setTheme($event.target.value)">
        <option value="light">Светлая</option>
        <option value="dark">Тёмная</option>
        <option value="auto">Системная</option>
      </select>
    </div>

    <div class="setting-row">
      <label for="language">Язык интерфейса <span class="soon">скоро</span></label>
      <select id="language" v-model="language" disabled>
        <option value="ru">Русский</option>
        <option value="en">English</option>
      </select>
    </div>

    <div class="setting-row">
      <label for="notify">Получать email-уведомления <span class="soon">скоро</span></label>
      <input id="notify" v-model="emailNotifications" type="checkbox" disabled />
    </div>
    <p class="muted">Тема сохраняется в этом браузере. Остальные настройки появятся позже.</p>
  </div>
</template>

<style scoped>
h2 {
  margin-top: 0;
}
.setting-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 1rem 0;
  border-bottom: 1px solid var(--color-border, #edf2f7);
}
select {
  padding: 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--color-border, #cbd5e0);
  background: var(--color-surface, #fff);
  color: inherit;
  font: inherit;
}
.soon {
  margin-left: 0.4rem;
  padding: 0.05rem 0.45rem;
  border-radius: 999px;
  background: var(--color-secondary, #e2e8f0);
  color: var(--color-muted, #4a5568);
  font-size: 0.75rem;
}
.muted {
  color: var(--color-muted, #4a5568);
  font-size: 0.875rem;
}
</style>
