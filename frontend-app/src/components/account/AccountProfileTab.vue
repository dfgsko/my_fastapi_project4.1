<!-- Вкладка «Профиль»: карточка (аватар, ник, @username, роль) и редактирование. -->
<script setup>
import { computed, ref, watch } from 'vue'
import { useAuthStore, ROLE_LABELS } from '@/stores/auth'
import { accountApi } from '@/api/account'
import { useToast } from '@/composables/useToast'
import { describeError } from '@/api/errors'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import AvatarUpload from './AvatarUpload.vue'

const auth = useAuthStore()
const toast = useToast()

const displayName = ref(auth.user?.display_name || '')
const newUsername = ref('')
const nameError = ref('')
const usernameError = ref('')
const savingName = ref(false)
const savingUsername = ref(false)

watch(
  () => auth.user?.display_name,
  (v) => (displayName.value = v || ''),
)

// Редактирование открывается после подтверждения email; до этого — только
// аватар и ник (в нашей схеме неподтверждённый пользователь войти не может,
// но при EMAIL_VERIFICATION_REQUIRED=false это защищает профиль).
const canEdit = computed(() => !!auth.user?.is_email_verified)
const nextChange = computed(() => {
  const at = auth.user?.next_username_change_at
  return at && new Date(at) > new Date() ? new Date(at).toLocaleDateString('ru-RU') : null
})

async function saveName() {
  nameError.value = displayName.value.length > 60 ? 'Не длиннее 60 символов' : ''
  if (nameError.value) return
  savingName.value = true
  try {
    auth.setUser(await accountApi.updateProfile({ display_name: displayName.value || null }))
    toast.success('Никнейм сохранён')
  } catch (e) {
    nameError.value = describeError(e, 'Не удалось сохранить')
  } finally {
    savingName.value = false
  }
}

async function saveUsername() {
  usernameError.value = /^[A-Za-z0-9_.-]{3,50}$/.test(newUsername.value.trim())
    ? ''
    : '3–50 символов: латиница, цифры, _ . -'
  if (usernameError.value) return
  savingUsername.value = true
  try {
    auth.setUser(await accountApi.changeUsername(newUsername.value.trim()))
    newUsername.value = ''
    toast.success('Username изменён. Следующая смена — через 6 месяцев.')
  } catch (e) {
    const s = e.response?.status
    usernameError.value =
      s === 409 ? 'Этот username уже занят' : s === 429 ? e.response.data.detail : describeError(e)
  } finally {
    savingUsername.value = false
  }
}
</script>

<template>
  <div class="profile-tab">
    <div class="profile-card">
      <UserAvatar :user="auth.user" :size="96" class="avatar-large" />
      <h2>{{ auth.user?.display_name || auth.user?.username }}</h2>
      <p class="username">@{{ auth.user?.username }}</p>
      <p class="role-badge">{{ ROLE_LABELS[auth.user?.role] || '—' }}</p>
    </div>

    <div v-if="!auth.user?.is_email_verified" class="info-banner">
      Аккаунт не активирован. Подтвердите email во вкладке «Безопасность».
    </div>

    <template v-if="canEdit">
      <section class="block">
        <h3>Аватар</h3>
        <AvatarUpload />
      </section>

      <section class="block">
        <h3>Отображаемое имя</h3>
        <form class="inline" @submit.prevent="saveName">
          <BaseInput
            id="display_name"
            v-model="displayName"
            label="Никнейм"
            maxlength="60"
            hint="Видно в шапке и в профиле. Можно менять когда угодно."
            :error="nameError"
          />
          <BaseButton type="submit" :loading="savingName">Сохранить</BaseButton>
        </form>
      </section>

      <section class="block">
        <h3>Username</h3>
        <p class="muted">
          Используется для входа. Менять можно не чаще раза в 6 месяцев.
          <template v-if="nextChange"><br />Следующая смена доступна {{ nextChange }}.</template>
        </p>
        <form class="inline" @submit.prevent="saveUsername">
          <BaseInput
            id="new_username"
            v-model="newUsername"
            label="Новый username"
            autocomplete="off"
            :error="usernameError"
          />
          <BaseButton type="submit" :loading="savingUsername" :disabled="!!nextChange">
            Сменить
          </BaseButton>
        </form>
      </section>

      <section class="block">
        <h3>Email</h3>
        <p class="mono">{{ auth.user?.email || '—' }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.profile-card {
  text-align: center;
  padding: 2rem;
  background: var(--color-background, #f7fafc);
  border-radius: 12px;
}
.avatar-large {
  margin: 0 auto 1rem;
}
.profile-card h2 {
  margin: 0;
}
.username {
  color: var(--color-muted, #718096);
  margin: 0.25rem 0 0;
}
.role-badge {
  display: inline-block;
  margin: 0.75rem 0 0;
  padding: 0.25rem 0.75rem;
  background: var(--color-secondary, #e2e8f0);
  border-radius: 999px;
  font-size: 0.875rem;
}
.info-banner {
  margin-top: 1.5rem;
  padding: 1rem;
  background: #fffbea;
  color: #744210;
  border-left: 4px solid #d69e2e;
  border-radius: 6px;
}
.block {
  margin-top: 1.75rem;
}
.block h3 {
  margin: 0 0 0.5rem;
}
.inline {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  flex-wrap: wrap;
}
.inline :deep(.base-input) {
  flex: 1 1 260px;
}
.inline > button {
  margin-top: 1.6rem;
}
.muted {
  color: var(--color-muted, #4a5568);
  margin: 0 0 0.5rem;
}
.mono {
  font-family: ui-monospace, monospace;
  margin: 0;
}
</style>
