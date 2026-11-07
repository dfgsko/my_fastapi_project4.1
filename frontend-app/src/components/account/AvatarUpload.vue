<!-- Загрузка аватара: превью до отправки, проверка типа и размера (JPEG/PNG/WebP ≤ 5 МБ).
     Сервер всё равно проверит магические байты, отклонит SVG и перекодирует в WebP. -->
<script setup>
import { onUnmounted, ref } from 'vue'
import { accountApi, IMAGE_TYPES, validateImageFile } from '@/api/account'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { describeError } from '@/api/errors'
import BaseButton from '@/components/ui/BaseButton.vue'
import UserAvatar from '@/components/UserAvatar.vue'

const auth = useAuthStore()
const toast = useToast()
const file = ref(null)
const preview = ref(null)
const error = ref('')
const busy = ref(false)
const input = ref(null)

function clearPreview() {
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = null
}

function onChange(e) {
  const f = e.target.files?.[0]
  if (!f) return
  clearPreview()
  error.value = validateImageFile(f)
  file.value = error.value ? null : f
  if (file.value) preview.value = URL.createObjectURL(f)
}

function cancel() {
  clearPreview()
  file.value = null
  error.value = ''
  if (input.value) input.value.value = ''
}

async function upload() {
  busy.value = true
  try {
    auth.setUser(await accountApi.uploadAvatar(file.value))
    toast.success('Аватар обновлён')
    cancel()
  } catch (e) {
    error.value = e.response?.status === 415 ? e.response.data.detail : describeError(e)
  } finally {
    busy.value = false
  }
}

async function remove() {
  busy.value = true
  try {
    await accountApi.deleteAvatar()
    auth.setUser({ ...auth.user, avatar_url: null })
    toast.success('Аватар удалён')
  } catch (e) {
    toast.error(describeError(e))
  } finally {
    busy.value = false
  }
}

onUnmounted(clearPreview)
</script>

<template>
  <div class="avatar-upload">
    <div class="current">
      <img v-if="preview" :src="preview" alt="Новый аватар" class="preview" />
      <UserAvatar v-else :user="auth.user" :size="88" />
    </div>
    <div class="controls">
      <label class="pick">
        <input ref="input" type="file" :accept="IMAGE_TYPES.join(',')" @change="onChange" />
        Выбрать изображение
      </label>
      <p class="hint">JPEG, PNG или WebP до 5 МБ. Будет обрезано до квадрата 256×256.</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="row">
        <template v-if="file">
          <BaseButton size="sm" :loading="busy" @click="upload">Сохранить аватар</BaseButton>
          <BaseButton size="sm" variant="secondary" @click="cancel">Отмена</BaseButton>
        </template>
        <BaseButton
          v-else-if="auth.user?.avatar_url"
          size="sm"
          variant="secondary"
          :loading="busy"
          @click="remove"
        >
          Удалить аватар
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.avatar-upload {
  display: flex;
  gap: 1.25rem;
  align-items: center;
  flex-wrap: wrap;
}
.preview {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  object-fit: cover;
}
.pick {
  position: relative;
  display: inline-block;
  padding: 6px 12px;
  border: 1px solid var(--color-border, #cbd5e0);
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
}
.pick:hover {
  background: var(--color-secondary, #e2e8f0);
}
.pick input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.hint {
  margin: 0.4rem 0;
  color: var(--color-muted, #4a5568);
  font-size: 0.85rem;
}
.error {
  margin: 0.25rem 0;
  color: var(--color-danger, #c53030);
}
.row {
  display: flex;
  gap: 0.5rem;
}
</style>
