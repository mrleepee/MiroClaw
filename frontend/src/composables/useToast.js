import { ref } from 'vue'

const toasts = ref([])
let nextId = 0

export function useToast() {
  function addToast({ message, type = 'info', duration = 4000 }) {
    const id = nextId++
    toasts.value.push({ id, message, type, duration })
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
    return id
  }

  function removeToast(id) {
    const index = toasts.value.findIndex(t => t.id === id)
    if (index > -1) {
      toasts.value.splice(index, 1)
    }
  }

  function success(message, duration) {
    return addToast({ message, type: 'success', duration })
  }

  function error(message, duration) {
    return addToast({ message, type: 'error', duration })
  }

  function info(message, duration) {
    return addToast({ message, type: 'info', duration })
  }

  return { toasts, addToast, removeToast, success, error, info }
}
