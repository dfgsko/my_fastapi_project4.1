<!-- Карточка «Возрастная верификация». Скрывается, если проверка в системе не
     требуется или /auth/me недоступен (не показываем «полуготовую» функцию). -->
<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import { getMe } from '@/api/account'

const router = useRouter()
const loading = ref(true)
const required = ref(false)
const verified = ref(false)
const verifiedAt = ref(null)

onMounted(async () => {
  try {
    const { data } = await getMe()
    // Если бэкенд не отдаёт поле — считаем, что верификация не требуется.
    // age_verification_available: функция включена в системе — тогда карточку
    // видит и тот, кто отказался от проверки при регистрации (required=false).
    required.value =
      data.age_verification_required !== false || data.age_verification_available === true
    verified.value = data.is_age_verified === true
    verifiedAt.value = data.age_verified_at || null
  } catch {
    required.value = false
  } finally {
    loading.value = false
  }
})

function startVerification() {
  router.push('/verify-age')
}
</script>

<template>
  <div v-if="!loading && required" class="security-card">
    <div class="card-header">
      <div>
        <h3>Возрастная верификация</h3>
        <p class="muted">
          <span :class="verified ? 'badge-on' : 'badge-off'">
            {{ verified ? '✓ Подтверждён' : '⚠ Не подтверждён' }}
          </span>
          <span v-if="verifiedAt"> · {{ new Date(verifiedAt).toLocaleDateString('ru-RU') }}</span>
        </p>
      </div>
      <BaseButton v-if="!verified" variant="primary" @click="startVerification">
        Подтвердить возраст
      </BaseButton>
    </div>
    <p v-if="!verified" class="muted description">
      Для доступа к контенту 18+ подтвердите, что вам больше 18 лет. Проверка — по фото
      (BetterAgeVerify), фото не сохраняется.
    </p>
    <p v-else class="muted description">Доступ к контенту с возрастным ограничением открыт.</p>
  </div>
</template>

<style scoped src="./security-card.css"></style>
