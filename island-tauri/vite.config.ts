import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Tauri serves the built files; the dev server is only for `tauri dev`.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: './',            // relative paths: the same build opens in Tauri and in the off-screen tests
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  build: { target: 'es2022', outDir: 'dist', emptyOutDir: true },
});
