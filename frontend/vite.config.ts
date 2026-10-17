import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  base: './',
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:21521' } },
  build: {
    outDir: '../viewer',
    emptyOutDir: true,
  },
})
