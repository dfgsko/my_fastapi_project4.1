// Тема оформления: light | dark | auto. Это удобство одного браузера, а не
// данные аккаунта, поэтому хранится в localStorage (в try/catch: в приватном
// режиме хранилище может быть недоступно).
import { ref } from 'vue'

const KEY = 'ui-theme'
const theme = ref(read())

function read() {
  try {
    return localStorage.getItem(KEY) || 'light'
  } catch {
    return 'light'
  }
}

function prefersDark() {
  return (
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
  )
}

export function applyTheme(value = theme.value) {
  const effective = value === 'auto' ? (prefersDark() ? 'dark' : 'light') : value
  document.documentElement.dataset.theme = effective
}

export function useTheme() {
  function setTheme(value) {
    theme.value = value
    try {
      localStorage.setItem(KEY, value)
    } catch {
      /* без сохранения — только на эту сессию */
    }
    applyTheme(value)
  }
  return { theme, setTheme }
}
