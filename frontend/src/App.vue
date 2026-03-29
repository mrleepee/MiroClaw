<template>
  <ToastContainer />
  <router-view />
</template>

<script setup>
import ToastContainer from './components/ToastContainer.vue'
</script>

<style>
@import './styles/tokens.css';

/* Global styles reset */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

/* Focus-visible styles for accessibility */
:focus-visible {
  outline: 2px solid var(--color-accent, #FF4500);
  outline-offset: 2px;
}

#app {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--color-text-primary, #000000);
  background-color: var(--color-bg-primary, #FFFFFF);
}

/* Scrollbar styles */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--color-bg-elevated, #F5F5F5);
}

::-webkit-scrollbar-thumb {
  background: var(--color-text-secondary, #666666);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-primary, #000000);
}

/* Global button styles */
button {
  font-family: inherit;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
</style>
