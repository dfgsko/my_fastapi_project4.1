<!-- Регистрация: username, email, пароль ×2. Клиентская валидация — для удобства;
     обязательная проверка и уникальность (409) — на бэкенде. -->
<script setup>
import { useRouter } from 'vue-router'
import { useForm } from '@/composables/useForm'
import { useToast } from '@/composables/useToast'
import apiClient from '@/api/client'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'

const router = useRouter()
const toast = useToast()

const { values, errors, isSubmitting, submitError, submit, validateField } = useForm(
  { username: '', email: '', password: '', confirmPassword: '' },
  {
    username: (v) =>
      v.trim().length < 3
        ? 'Минимум 3 символа'
        : !/^[A-Za-z0-9_.-]+$/.test(v.trim())
          ? 'Только латиница, цифры и _ . -'
          : '',
    email: (v) => (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim()) ? 'Некорректный email' : ''),
    password: (v) =>
      v.length < 12
        ? 'Минимум 12 символов'
        : !/\d/.test(v) || !/[A-Za-zА-Яа-яЁё]/.test(v)
          ? 'Нужны и буквы, и цифры'
          : '',
    confirmPassword: (v, all) => (v !== all.password ? 'Пароли не совпадают' : ''),
  },
  async (data) => {
    try {
      const { data: res } = await apiClient.post('/auth/register', {
        username: data.username.trim(),
        email: data.email.trim(),
        password: data.password,
      })
      if (res.requires_age_verification) {
        // Письмо уйдёт после проверки возраста (или отказа от неё).
        router.push({ name: 'verify-age', query: { registration: 'true' } })
      } else {
        toast.success('Аккаунт создан. Проверьте почту.')
        router.push({ name: 'check-email', query: { email: res.email } })
      }
    } catch (e) {
      // 409 Conflict: запрос корректен, но email/логин уже заняты.
      if (e.response?.status === 409) {
        const field = e.response.data?.field === 'username' ? 'username' : 'email'
        errors.value = { ...errors.value, [field]: e.response.data?.detail }
      } else throw e
    }
  },
)
</script>

<template>
  <BaseCard class="auth-card">
    <h1>Регистрация</h1>
    <form novalidate @submit.prevent="submit">
      <BaseInput
        id="username"
        v-model="values.username"
        label="Username"
        autocomplete="username"
        hint="Латиница, цифры и _ . -"
        :error="errors.username"
        @blur="validateField('username')"
      />
      <BaseInput
        id="email"
        v-model="values.email"
        type="email"
        label="Email"
        autocomplete="email"
        :error="errors.email"
        @blur="validateField('email')"
      />
      <BaseInput
        id="password"
        v-model="values.password"
        type="password"
        label="Пароль"
        autocomplete="new-password"
        hint="Не короче 12 символов, буквы и цифры"
        :error="errors.password"
        @blur="validateField('password')"
      />
      <BaseInput
        id="confirmPassword"
        v-model="values.confirmPassword"
        type="password"
        label="Повторите пароль"
        autocomplete="new-password"
        :error="errors.confirmPassword"
        @blur="validateField('confirmPassword')"
      />
      <p v-if="submitError" class="error" role="alert">{{ submitError }}</p>
      <BaseButton type="submit" size="lg" class="submit" :loading="isSubmitting">
        Зарегистрироваться
      </BaseButton>
    </form>
    <p class="alt">Уже есть аккаунт? <RouterLink to="/login">Войти</RouterLink></p>
  </BaseCard>
</template>

<style scoped>
.auth-card {
  max-width: 420px;
  margin: 40px auto;
}
h1 {
  margin-top: 0;
  font-size: 1.6rem;
}
.error {
  color: var(--color-danger, #c53030);
  margin: 0 0 1rem;
}
.submit {
  width: 100%;
}
.alt {
  margin: 1rem 0 0;
  text-align: center;
  color: var(--color-muted, #4a5568);
}
</style>
