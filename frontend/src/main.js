/**
 * Vue 应用从这里启动。
 *
 * 事情很简单：把根组件挂到页面上的 `#app`。
 */

import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

// 创建 Vue 应用实例并挂载
// createApp(App)：创建以 App.vue 为根组件的应用
// .mount('#app')：挂载到 index.html 中的 <div id="app"></div>
createApp(App).mount('#app')
