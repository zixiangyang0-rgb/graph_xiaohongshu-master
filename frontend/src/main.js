/**
 * =============================================================================
 * Vue 应用入口
 * =============================================================================
 *
 * 职责说明：
 *   创建 Vue 应用实例并挂载到 DOM。
 *
 * 工作流程：
 *   1. 导入 Vue 3 的 createApp 函数
 *   2. 导入根组件 App.vue
 *   3. 导入全局样式
 *   4. 创建应用实例
 *   5. 挂载到 #app DOM 节点
 *
 * 典型场景：
 *   用户访问 http://localhost:5173/
 *   -> Vite 加载 /src/main.js
 *   -> 创建 Vue 应用
 *   -> 渲染 App.vue 组件
 *   -> 挂载到 <div id="app"></div>
 */

import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

// 创建 Vue 应用实例并挂载
// createApp(App)：创建以 App.vue 为根组件的应用实例
// .mount('#app')：挂载到 index.html 中的 <div id="app"></div>
createApp(App).mount('#app')
