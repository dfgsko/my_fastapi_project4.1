<!-- Публичная витрина для неавторизованных: что это за сервис и что делать дальше.
     Доступна без JWT; все данные курсов остаются за входом. -->
<script setup>
import { useRouter } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'

const router = useRouter()

const features = [
  {
    title: 'Каталог курсов',
    text: 'Поиск по преподавателю, длительность и описание каждого курса — в одном списке.',
  },
  {
    title: 'Безопасность',
    text: 'Двухфакторная аутентификация через приложение и сессии в защищённых cookie.',
  },
  {
    title: 'Роли',
    text: 'Студенты просматривают курсы, модераторы ведут каталог, администратор управляет ролями.',
  },
]
const steps = [
  'Создайте аккаунт и подтвердите email',
  'Найдите курс и запишитесь на него',
  'Получите сертификат после завершения',
]
</script>

<template>
  <section class="landing">
    <div class="hero">
      <p class="eyebrow">Образовательная платформа</p>
      <h1>Курсы и студенты в одном месте</h1>
      <p class="lead">
        Выбирайте курсы, записывайтесь на них и отслеживайте обучение. Преподаватели и модераторы
        ведут каталог, а ваш аккаунт защищён вторым фактором.
      </p>
      <div class="cta">
        <BaseButton size="lg" @click="router.push('/register')">Создать аккаунт</BaseButton>
        <BaseButton size="lg" variant="secondary" @click="router.push('/login')">Войти</BaseButton>
      </div>
    </div>

    <div class="features">
      <article v-for="f in features" :key="f.title" class="feature">
        <h3>{{ f.title }}</h3>
        <p>{{ f.text }}</p>
      </article>
    </div>

    <section class="how">
      <h2>Как начать</h2>
      <ol>
        <li v-for="(s, i) in steps" :key="s">
          <span class="num">{{ i + 1 }}</span
          >{{ s }}
        </li>
      </ol>
    </section>
  </section>
</template>

<style scoped>
.landing {
  max-width: 960px;
  margin: 0 auto;
  padding: 3rem 0 2rem;
}
.hero {
  text-align: center;
  margin-bottom: 3rem;
}
.eyebrow {
  margin: 0 0 0.5rem;
  color: var(--color-primary, #2b6cb0);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 0.85rem;
}
.hero h1 {
  font-size: clamp(1.9rem, 4.5vw, 2.6rem);
  line-height: 1.15;
  margin: 0 0 1rem;
}
.lead {
  max-width: 620px;
  margin: 0 auto;
  color: var(--color-muted, #4a5568);
  font-size: 1.1rem;
  line-height: 1.55;
}
.cta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  justify-content: center;
  margin-top: 2rem;
}
.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
}
.feature {
  padding: 1.25rem 1.4rem;
  border: 1px solid var(--color-border, #cbd5e0);
  border-radius: var(--radius-lg, 10px);
  background: var(--color-surface, #fff);
}
.feature h3 {
  margin: 0 0 0.5rem;
}
.feature p {
  margin: 0;
  color: var(--color-muted, #4a5568);
  line-height: 1.5;
}
.how {
  margin-top: 3rem;
}
.how h2 {
  text-align: center;
}
.how ol {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 1rem 2rem;
  padding: 0;
  list-style: none;
}
.how li {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-primary, #2b6cb0);
  color: #fff;
  font-weight: 700;
}
</style>
