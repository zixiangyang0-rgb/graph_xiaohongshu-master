/**
 * =============================================================================
 * Vite 构建工具配置文件
 * =============================================================================
 *
 * 职责说明：
 *   Vite 是下一代前端构建工具，本文件定义其构建和开发服务器配置。
 *
 * 核心配置项：
 *   1. proxy: 代理配置
 *      - 将 /api/* 请求转发到后端服务器 (http://localhost:8000)
 *      - 解决前后端跨域问题
 *      - changeOrigin: true 使代理请求携带原始 Host 头
 *      - rewrite: 去掉 /api 前缀
 *
 *   典型场景：
 *     - 开发时，前端发起的 /api/auth/login 请求会被代理到
 *       http://localhost:8000/auth/login
 *     - 生产构建时，proxy 配置不生效，需要后端和前端分别部署
 *
 * 字段具体含义：
 *   - proxy['/api']: 匹配以 /api 开头的 URL
 *   - target: 目标服务器地址（后端 API 根地址）
 *   - changeOrigin: 代理请求时修改 Origin 为 target 的值，防止后端 CORS 拦截
 *   - rewrite: 函数，接收路径，返回重写后的路径（去掉 /api 前缀）
 */

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],

  // 开发服务器代理配置
  server: {
    // 代理规则
    proxy: {
      // 将所有 /api 开头的请求代理到后端服务器
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // rewrite 函数：接收请求路径 (path)，返回新的路径
        // 例如 /api/auth/login -> /auth/login
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
