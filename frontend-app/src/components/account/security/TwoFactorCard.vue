<!-- Карточка 2FA: статус и дата включения; «Включить» → модалка с QR-кодом,
     «Отключить» → модалка с вводом текущего кода. -->
<script setup>
import { ref, onMounted } from 'vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import apiClient from '@/api/client'
import { getMe } from '@/api/account'

const toast = useToast()
const enabled = ref(false)
const enabledAt = ref(null)
const codesLeft = ref(null)
const loading = ref(false)

const showEnableModal = ref(false)
const showDisableModal = ref(false)
const qrCode = ref(null)
const secret = ref(null)
const recoveryCodes = ref([])
const code = ref('')
const error = ref('')
const busy = ref(false)

onMounted(async () => {
  try {
    const { data } = await getMe()
    enabled.value = !!data.totp_enabled
    enabledAt.value = data.totp_enabled_at
    codesLeft.value = data.recovery_codes_left ?? null
  } catch {
    /* статус останется «Выключена» */
  }
})

async function startEnable() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await apiClient.post('/auth/2fa/enable')
    qrCode.value = data.qr_code
    secret.value = data.secret
    recoveryCodes.value = []
    showEnableModal.value = true
  } catch {
    toast.error('Не удалось начать настройку 2FA')
  } finally {
    loading.value = false
  }
}

async function confirmEnable() {
  error.value = ''
  busy.value = true
  try {
    const { data } = await apiClient.post('/auth/2fa/confirm', { code: code.value.trim() })
    enabled.value = true
    enabledAt.value = new Date().toISOString()
    code.value = ''
    qrCode.value = null
    secret.value = null
    recoveryCodes.value = data?.recovery_codes || []
    codesLeft.value = recoveryCodes.value.length
    if (!recoveryCodes.value.length) showEnableModal.value = false
    toast.success('2FA включена')
  } catch {
    error.value = 'Неверный код'
  } finally {
    busy.value = false
  }
}

async function confirmDisable() {
  error.value = ''
  busy.value = true
  try {
    await apiClient.post('/auth/2fa/disable', { code: code.value.trim() })
    enabled.value = false
    enabledAt.value = null
    showDisableModal.value = false
    code.value = ''
    toast.success('2FA отключена')
  } catch {
    error.value = 'Неверный код'
  } finally {
    busy.value = false
  }
}

function closeEnable() {
  showEnableModal.value = false
  recoveryCodes.value = []
  code.value = ''
  error.value = ''
}

function openDisable() {
  code.value = ''
  error.value = ''
  showDisableModal.value = true
}
</script>

<template>
  <div class="security-card">
    <div class="card-header">
      <div>
        <h3>Двухфакторная аутентификация</h3>
        <p class="muted">
          <span :class="enabled ? 'badge-on' : 'badge-off'">
            {{ enabled ? 'Включена' : 'Выключена' }}
          </span>
          <span v-if="enabledAt"> · с {{ new Date(enabledAt).toLocaleDateString('ru-RU') }}</span>
          <span v-if="enabled && codesLeft !== null"> · кодов восстановления: {{ codesLeft }}</span>
        </p>
      </div>
      <BaseButton
        :variant="enabled ? 'danger' : 'primary'"
        :loading="loading"
        @click="enabled ? openDisable() : startEnable()"
      >
        {{ enabled ? 'Отключить' : 'Включить' }}
      </BaseButton>
    </div>
    <p class="muted description">
      Вход потребует не только пароль, но и код из приложения на телефоне.
    </p>

    <BaseModal :open="showEnableModal" title="Настройка 2FA" @close="closeEnable">
      <template v-if="!recoveryCodes.length">
        <p>Отсканируйте QR-код в Google Authenticator, Microsoft Authenticator или Authy.</p>
        <img
          v-if="qrCode"
          :src="`data:image/png;base64,${qrCode}`"
          alt="QR-код для 2FA"
          class="qr"
        />
        <p class="muted">
          Не сканируется? Введите ключ вручную: <code class="secret">{{ secret }}</code>
        </p>
        <BaseInput
          id="totp-code"
          v-model="code"
          label="Введите 6-значный код"
          maxlength="6"
          inputmode="numeric"
          autocomplete="one-time-code"
          :error="error"
        />
      </template>
      <template v-else>
        <p>
          <strong>Сохраните коды восстановления.</strong> Каждый работает один раз и понадобится,
          если телефон потерян. Больше мы их не покажем.
        </p>
        <ul class="codes">
          <li v-for="c in recoveryCodes" :key="c">{{ c }}</li>
        </ul>
      </template>
      <template #actions>
        <template v-if="!recoveryCodes.length">
          <BaseButton variant="secondary" @click="closeEnable">Отмена</BaseButton>
          <BaseButton :loading="busy" @click="confirmEnable">Подтвердить</BaseButton>
        </template>
        <BaseButton v-else @click="closeEnable">Я сохранил коды</BaseButton>
      </template>
    </BaseModal>

    <BaseModal :open="showDisableModal" title="Отключить 2FA?" @close="showDisableModal = false">
      <p>Введите текущий код из приложения (или код восстановления), чтобы подтвердить.</p>
      <BaseInput
        id="disableCode"
        v-model="code"
        label="Код"
        maxlength="20"
        autocomplete="one-time-code"
        :error="error"
      />
      <template #actions>
        <BaseButton variant="secondary" @click="showDisableModal = false">Отмена</BaseButton>
        <BaseButton variant="danger" :loading="busy" @click="confirmDisable">Отключить</BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped src="./security-card.css"></style>
