<!-- Аватар пользователя: картинка или заглушка с первой буквой имени. -->
<script setup>
import { computed, ref, watch } from 'vue'
import { avatarSrc } from '@/api/account'

const props = defineProps({
  user: { type: Object, default: null },
  size: { type: Number, default: 36 },
})

const failed = ref(false)
watch(
  () => props.user?.avatar_url,
  () => (failed.value = false),
)

const src = computed(() => (failed.value ? '' : avatarSrc(props.user?.avatar_url)))
const initial = computed(() =>
  (props.user?.display_name || props.user?.username || '?').trim().charAt(0).toUpperCase(),
)
const style = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.round(props.size * 0.42)}px`,
}))
</script>

<template>
  <span class="avatar" :style="style">
    <img v-if="src" :src="src" alt="" @error="failed = true" />
    <span v-else class="avatar-placeholder" aria-hidden="true">{{ initial }}</span>
  </span>
</template>

<style scoped>
.avatar {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 50%;
  background: var(--color-primary, #2b6cb0);
  color: #fff;
  font-weight: 700;
  line-height: 1;
}
.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
