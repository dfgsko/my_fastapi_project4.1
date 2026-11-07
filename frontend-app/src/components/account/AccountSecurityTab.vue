<!-- Вкладка «Безопасность» — список карточек: каждая функция безопасности
     отдельным компонентом (как у Google / GitHub). -->
<script setup>
import PasswordChangeCard from '@/components/account/security/PasswordChangeCard.vue'
import TwoFactorCard from '@/components/account/security/TwoFactorCard.vue'
import EmailVerificationCard from '@/components/account/security/EmailVerificationCard.vue'
import AgeVerificationCard from '@/components/account/security/AgeVerificationCard.vue'
</script>

<template>
  <div class="security-tab">
    <h2>Безопасность</h2>
    <EmailVerificationCard />
    <PasswordChangeCard />
    <TwoFactorCard />
    <AgeVerificationCard />
  </div>
</template>

<style scoped>
.security-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
h2 {
  margin: 0;
}
</style>
