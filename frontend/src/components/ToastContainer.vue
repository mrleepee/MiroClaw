<template>
  <div class="toast-container" aria-live="polite" role="status">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="toast"
        :class="`toast--${toast.type}`"
        role="alert"
      >
        <span class="toast__icon">
          <svg v-if="toast.type === 'success'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
          <svg v-else-if="toast.type === 'error'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
        </span>
        <span class="toast__message">{{ toast.message }}</span>
        <button class="toast__close" @click="removeToast(toast.id)" aria-label="Dismiss notification">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { useToast } from '../composables/useToast'
const { toasts, removeToast } = useToast()
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: var(--z-toast, 1000);
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--color-bg-elevated, #F5F5F5);
  border: 1px solid var(--color-border, #EAEAEA);
  border-radius: var(--radius-md, 6px);
  box-shadow: var(--shadow-md, 0 4px 16px rgba(0,0,0,0.08));
  font-family: var(--font-sans, 'Space Grotesk', sans-serif);
  font-size: 0.875rem;
  color: var(--color-text-primary, #000);
  pointer-events: auto;
  min-width: 280px;
  max-width: 420px;
}

.toast--success {
  border-left: 3px solid var(--color-success, #1A936F);
}

.toast--error {
  border-left: 3px solid var(--color-error, #EF4444);
}

.toast--info {
  border-left: 3px solid var(--color-accent, #FF4500);
}

.toast__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.toast--success .toast__icon { color: var(--color-success, #1A936F); }
.toast--error .toast__icon { color: var(--color-error, #EF4444); }
.toast--info .toast__icon { color: var(--color-accent, #FF4500); }

.toast__message {
  flex: 1;
  line-height: 1.4;
}

.toast__close {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-tertiary, #999);
  padding: 2px;
  display: flex;
  align-items: center;
  transition: color 0.15s;
}

.toast__close:hover {
  color: var(--color-text-primary, #000);
}

.toast__close:focus-visible {
  outline: 2px solid var(--color-accent, #FF4500);
  outline-offset: 2px;
  border-radius: 2px;
}

/* Transition */
.toast-enter-active {
  transition: all var(--transition-normal, 250ms ease);
}
.toast-leave-active {
  transition: all var(--transition-fast, 150ms ease);
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(50%);
}

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active {
    transition: none;
  }
}
</style>
