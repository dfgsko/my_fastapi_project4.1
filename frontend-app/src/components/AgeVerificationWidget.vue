<!-- Проверка возраста по фото (BetterAgeVerify на бэкенде): выбор файла, превью,
     отправка multipart/form-data. Вместо QR-кода self.xyz — весь поток на одной странице. -->
<script setup>
import { onUnmounted, ref } from 'vue'
import apiClient from '@/api/client'
import { IMAGE_TYPES, validateImageFile } from '@/api/account'
import BaseButton from '@/components/ui/BaseButton.vue'

const emit = defineEmits(['success'])
const file = ref(null)
const previewUrl = ref(null)
const isUploading = ref(false)
const error = ref('')

function revokePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = null
}

function onFileChange(event) {
  const selected = event.target.files?.[0]
  if (!selected) return
  error.value = validateImageFile(selected, 10 * 1024 * 1024)
  revokePreview()
  if (error.value) {
    file.value = null
    return
  }
  file.value = selected
  previewUrl.value = URL.createObjectURL(selected) // превью только в браузере
}

async function submit() {
  if (!file.value) {
    error.value = 'Выберите фотографию'
    return
  }
  isUploading.value = true
  error.value = ''
  try {
    const formData = new FormData()
    formData.append('photo', file.value)
    const { data } = await apiClient.post('/auth/verify-age', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    revokePreview()
    file.value = null
    emit('success', data)
  } catch (e) {
    const status = e.response?.status
    error.value =
      status === 429
        ? 'Слишком много попыток. Попробуйте через 10 минут.'
        : status === 503
          ? 'Проверка возраста временно недоступна.'
          : e.response?.data?.detail || 'Не удалось подтвердить возраст. Попробуйте другое фото.'
  } finally {
    isUploading.value = false
  }
}

onUnmounted(revokePreview)
</script>

<template>
  <div class="age-widget">
    <p class="privacy">
      Загрузите фотографию лица анфас при хорошем освещении. Фото обрабатывается на сервере только в
      памяти и не сохраняется — мы храним лишь результат «18+: да/нет».
    </p>

    <label class="picker">
      <input
        type="file"
        :accept="IMAGE_TYPES.join(',')"
        data-testid="age-photo"
        @change="onFileChange"
      />
      <span>{{ file ? file.name : 'Выбрать фото (JPEG, PNG, WebP до 10 МБ)' }}</span>
    </label>

    <div v-if="previewUrl" class="preview">
      <img :src="previewUrl" alt="Превью фотографии" />
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <BaseButton :loading="isUploading" :disabled="!file" @click="submit">
      Подтвердить возраст
    </BaseButton>
  </div>
</template>

<style scoped>
.age-widget {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.privacy {
  margin: 0;
  color: var(--color-muted, #4a5568);
  line-height: 1.5;
}
.picker {
  position: relative;
  display: block;
  padding: 1rem;
  border: 2px dashed var(--color-border, #cbd5e0);
  border-radius: var(--radius-md, 6px);
  text-align: center;
  cursor: pointer;
}
.picker:hover {
  border-color: var(--color-primary, #2b6cb0);
}
.picker input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.preview img {
  display: block;
  max-width: 200px;
  max-height: 200px;
  margin: 0 auto;
  border-radius: 8px;
  object-fit: cover;
}
.error {
  margin: 0;
  color: var(--color-danger, #c53030);
}
</style>
