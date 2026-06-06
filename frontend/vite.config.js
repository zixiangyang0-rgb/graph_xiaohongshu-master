/**
 * Vite 的开发配置。
 *
 * 这里主要是把前端本地开发时发出去的 `/api` 和 `/static` 请求
 * 转到后端，省得前后端联调时被跨域问题打断。
 */

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],

  // 开发服务器配置
  server: {
    // 代理规则
    proxy: {
      // 将所有 /api 开头的请求代理到后端服务器
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 将静态资源请求代理到后端
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
