import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'
import pkg from './package.json'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // CHANGELOG.md lives in the repository root
    fs: { allow: ['..'] },
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
  },
})
