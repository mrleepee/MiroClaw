import { ref, watch, onMounted } from 'vue'

const STORAGE_KEY = 'miroclaw-theme'

const theme = ref(null)

function getSystemPreference() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(newTheme) {
  document.documentElement.setAttribute('data-theme', newTheme)
  localStorage.setItem(STORAGE_KEY, newTheme)
}

export function useTheme() {
  if (theme.value === null) {
    const stored = localStorage.getItem(STORAGE_KEY)
    theme.value = stored || getSystemPreference()
  }

  onMounted(() => {
    applyTheme(theme.value)

    // Listen for OS preference changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => {
      if (!localStorage.getItem(STORAGE_KEY)) {
        theme.value = e.matches ? 'dark' : 'light'
        applyTheme(theme.value)
      }
    }
    mediaQuery.addEventListener('change', handler)
  })

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme(theme.value)
  }

  function setTheme(newTheme) {
    theme.value = newTheme
    applyTheme(newTheme)
  }

  const isDark = ref(theme.value === 'dark')
  watch(theme, (val) => {
    isDark.value = val === 'dark'
  })

  return { theme, isDark, toggleTheme, setTheme }
}
