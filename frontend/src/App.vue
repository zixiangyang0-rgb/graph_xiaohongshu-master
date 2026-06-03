/**
 * =============================================================================
 * AI 内容运营助手 - Vue.js 前端应用
 * =============================================================================
 *
 * 职责说明：
 *   整个单页应用（SPA）的前端入口，提供用户交互界面。
 *
 * 核心功能：
 *   1. 用户认证（登录/注册）
 *   2. 工作流交互（启动、选题、审核、生成配图）
 *   3. 实时流式输出（打字机效果）
 *   4. 历史记录管理（侧边栏列表）
 *   5. 节点执行指标展示
 *
 * 状态管理：
 *   使用 Vue 3 Composition API（setup script）
 *   所有状态都是响应式的 ref/reactive
 *
 * 工作流步骤：
 *   Step 0：输入主题方向
 *   Step 1：选择选题
 *   Step 2：审核文章
 *   Step 3：生成配图（自动）
 *   Step 4：完成
 *
 * 技术栈：
 *   - Vue 3 Composition API
 *   - Axios（HTTP 客户端）
 *   - CSS（样式）
 *   - SSE（流式 API）
 */

<template>
  <!-- ============================================================
       第 1 部分：登录/注册页面
       显示条件：用户未登录（isLoggedIn = false）
       ============================================================ -->
  <div v-if="!isLoggedIn" class="auth-page">
    <div class="auth-container">
      <div class="auth-card">
        <!-- 标题：登录/注册模式切换 -->
        <h2>{{ isLoginMode ? '登录' : '注册' }}</h2>

        <!-- 表单 -->
        <form @submit.prevent="handleAuth">
          <!-- 用户名输入框 -->
          <div class="form-group">
            <label>用户名</label>
            <input
              v-model="authForm.username"
              type="text"
              class="input"
              placeholder="请输入用户名（至少3个字符）"
              required
              minlength="3"
            />
          </div>

          <!-- 密码输入框 -->
          <div class="form-group">
            <label>密码</label>
            <input
              v-model="authForm.password"
              type="password"
              class="input"
              placeholder="请输入密码（至少6个字符）"
              required
              minlength="6"
            />
          </div>

          <!-- 错误提示 -->
          <div v-if="authError" class="auth-error">
            {{ authError }}
          </div>

          <!-- 提交按钮 -->
          <button
            type="submit"
            class="btn btn-primary auth-btn"
            :disabled="authLoading"
          >
            {{ authLoading ? '处理中...' : (isLoginMode ? '登录' : '注册') }}
          </button>
        </form>

        <!-- 登录/注册切换链接 -->
        <div class="auth-switch">
          <span v-if="isLoginMode">
            还没有账号？
            <a href="#" @click.prevent="isLoginMode = false">立即注册</a>
          </span>
          <span v-else>
            已有账号？
            <a href="#" @click.prevent="isLoginMode = true">立即登录</a>
          </span>
        </div>
      </div>
    </div>
  </div>

  <!-- ============================================================
       第 2 部分：主应用页面
       显示条件：用户已登录
       ============================================================ -->
  <div v-else class="app-layout">

    <!-- ========================================================
         2.1 侧边栏 - 历史记录列表
         ======================================================== -->
    <div class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <!-- 侧边栏头部 -->
      <div class="sidebar-header">
        <h3 v-if="sidebarOpen">历史记录</h3>
        <!-- 折叠/展开按钮 -->
        <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen">
          {{ sidebarOpen ? '◀' : '▶' }}
        </button>
      </div>

      <!-- 侧边栏内容 -->
      <div v-if="sidebarOpen" class="sidebar-content">
        <!-- 新建工作流按钮 -->
        <button class="btn btn-primary sidebar-btn" @click="handleNewWorkflow">
          + 新建工作流
        </button>

        <!-- 历史记录列表 -->
        <div class="thread-list">
          <!-- 加载状态 -->
          <div v-if="loadingThreads" class="loading-small">
            <div class="loading-spinner-small"></div>
          </div>

          <!-- 空状态 -->
          <div v-else-if="threadList.length === 0" class="empty-state">
            暂无历史记录
          </div>

          <!-- 线程列表项 -->
          <div
            v-else
            v-for="thread in threadList"
            :key="thread.thread_id"
            class="thread-item"
            :class="{ active: threadId === thread.thread_id }"
            @click="handleSwitchThread(thread.thread_id)"
          >
            <!-- 线程头部：状态图标 + 主题方向 -->
            <div class="thread-item-header">
              <span class="thread-status" :class="thread.is_completed ? 'completed' : 'in-progress'">
                {{ thread.is_completed ? '✓' : '●' }}
              </span>
              <span class="thread-title">{{ thread.topic_direction || '未命名' }}</span>
            </div>
            <!-- 线程元信息：选题或状态 -->
            <div class="thread-item-meta">
              <span class="thread-topic">{{ thread.selected_topic || thread.status }}</span>
            </div>
            <!-- 删除按钮（悬停时显示） -->
            <button
              class="thread-delete-btn"
              @click.stop="handleDeleteThread(thread.thread_id)"
              title="删除"
            >
              ×
            </button>
          </div>
        </div>

        <!-- 刷新列表按钮 -->
        <button
          v-if="threadList.length > 0"
          class="btn sidebar-btn refresh-btn"
          @click="fetchThreadList"
          :disabled="loadingThreads"
        >
          刷新列表
        </button>
      </div>
    </div>

    <!-- ========================================================
         2.2 主内容区域
         ======================================================== -->
    <div class="main-content">
      <div class="container">

        <!-- ---------- 头部 ---------- -->
        <div class="header">
          <div class="header-top">
            <div>
              <h1>AI 内容运营助手</h1>
              <p>基于 LangGraph 的智能内容生成工作流</p>
            </div>
            <!-- 用户信息 + 登出 -->
            <div class="user-info">
              <span class="username">{{ currentUsername }}</span>
              <button class="btn btn-logout" @click="handleLogout">退出登录</button>
            </div>
          </div>
        </div>

        <!-- ---------- 工作流进度条 ---------- -->
        <div class="card">
          <div class="workflow-steps">
            <!-- Step 0：输入主题 -->
            <div class="step" :class="{ active: currentStep === 0, completed: currentStep > 0 }">
              <div class="step-icon">1</div>
              <div class="step-title">输入主题</div>
            </div>
            <!-- Step 1：选择选题 -->
            <div class="step" :class="{ active: currentStep === 1, completed: currentStep > 1 }">
              <div class="step-icon">2</div>
              <div class="step-title">选择选题</div>
            </div>
            <!-- Step 2：审核文章 -->
            <div class="step" :class="{ active: currentStep === 2, completed: currentStep > 2 }">
              <div class="step-icon">3</div>
              <div class="step-title">审核文章</div>
            </div>
            <!-- Step 3：生成配图 -->
            <div class="step" :class="{ active: currentStep === 3, completed: currentStep > 3 }">
              <div class="step-icon">4</div>
              <div class="step-title">生成配图</div>
            </div>
            <!-- Step 4：完成 -->
            <div class="step" :class="{ active: currentStep === 4, completed: currentStep > 4 }">
              <div class="step-icon">✓</div>
              <div class="step-title">完成</div>
            </div>
          </div>
        </div>

        <!-- ---------- 消息提示 ---------- -->
        <div v-if="message" :class="['message', `message-${messageType}`]">
          {{ message }}
        </div>

        <!-- ---------- 当前工作流信息 ---------- -->
        <div v-if="currentStep > 0 && topicDirection" class="current-workflow-info">
          <div class="workflow-info-item">
            <span class="workflow-info-label">主题方向：</span>
            <span class="workflow-info-value">{{ topicDirection }}</span>
          </div>
          <div v-if="selectedTopic" class="workflow-info-item">
            <span class="workflow-info-label">已选选题：</span>
            <span class="workflow-info-value">{{ selectedTopic }}</span>
          </div>
        </div>

        <!-- ---------- Step 0: 输入主题方向 ---------- -->
        <div v-if="currentStep === 0" class="card">
          <div class="card-title">输入主题方向</div>
          <div style="display: flex; gap: 12px;">
            <input
              v-model="topicDirection"
              class="input"
              placeholder="请输入内容主题方向，例如：AI技术、Python开发、职场技能"
              @keyup.enter="handleStart"
            />
            <button
              class="btn btn-primary"
              :disabled="!topicDirection.trim() || loading"
              @click="handleStart"
            >
              {{ loading ? '生成中...' : '开始' }}
            </button>
          </div>
        </div>

        <!-- ---------- Step 1: 选择选题 ---------- -->
        <div v-if="currentStep === 1" class="card">
          <div class="card-title">请选择一个选题</div>

          <!-- AI 正在生成选题时：显示流式文本 -->
          <div v-if="loading && streamingTopicsText" class="streaming-content">
            <div class="streaming-label">AI 正在生成选题...</div>
            <div class="streaming-text">
              {{ streamingTopicsText }}
              <span class="typing-cursor">▊</span>
            </div>
          </div>

          <!-- 加载中但还没有内容 -->
          <div v-else-if="loading && generatedTopics.length === 0 && !streamingTopicsText" class="loading">
            <div class="loading-spinner"></div>
            <p style="margin-top: 12px;">AI 正在生成选题...</p>
          </div>

          <!-- 选题列表 -->
          <div v-else class="topic-list">
            <div
              v-for="(topic, index) in generatedTopics"
              :key="index"
              class="topic-item"
              :class="{ selected: selectedTopic === topic }"
              @click="selectedTopic = topic"
            >
              {{ topic }}
            </div>
            <!-- 加载更多时显示 -->
            <div v-if="loading && generatedTopics.length > 0" class="loading-small" style="margin-top: 12px;">
              <div class="loading-spinner-small"></div>
              <span style="margin-left: 8px; color: #666;">正在生成更多选题...</span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="btn-group">
            <button
              class="btn btn-primary"
              :disabled="!selectedTopic || loading"
              @click="handleSelectTopic"
            >
              确认选题
            </button>
            <button class="btn" style="background: #f0f0f0;" @click="handleReset">
              重新开始
            </button>
          </div>
        </div>

        <!-- ---------- Step 2: 审核文章 ---------- -->
        <div v-if="currentStep === 2" class="card">
          <div class="card-title">审核文章草稿</div>

          <!-- 加载中：显示打字机效果 -->
          <div v-if="loading && !articleContent" class="loading">
            <div class="loading-spinner"></div>
            <p style="margin-top: 12px;">AI 正在撰写文章...</p>
          </div>

          <!-- 文章内容 + 操作按钮 -->
          <template v-else>
            <div class="article-content">
              {{ articleContent }}
              <!-- 加载中时显示打字光标 -->
              <span v-if="loading" class="typing-cursor">▊</span>
            </div>

            <!-- 驳回反馈 -->
            <div class="feedback-section">
              <label>驳回反馈（可选）:</label>
              <textarea
                v-model="feedback"
                class="textarea"
                placeholder="如果需要驳回，请输入修改意见..."
                :disabled="loading"
              ></textarea>
            </div>

            <!-- 审核按钮 -->
            <div class="btn-group">
              <button class="btn btn-success" :disabled="loading" @click="handleApprove">
                通过
              </button>
              <button class="btn btn-danger" :disabled="loading" @click="handleReject">
                驳回重写
              </button>
            </div>
          </template>
        </div>

        <!-- ---------- Step 3: 生成配图中 ---------- -->
        <div v-if="currentStep === 3" class="card">
          <div class="card-title">正在生成配图</div>

          <!-- 配图摘要（AI 提取的视觉要点） -->
          <div v-if="visualPoints.length > 0" class="visual-summary">
            <div class="visual-summary-title">配图摘要（AI 提取的视觉要点）</div>
            <ul class="visual-summary-list">
              <li v-for="(point, index) in visualPoints" :key="index">
                <span class="visual-point-index">{{ index + 1 }}</span>
                <span class="visual-point-text">{{ point }}</span>
              </li>
            </ul>
          </div>

          <!-- 加载状态 -->
          <div class="loading">
            <div class="loading-spinner"></div>
            <p style="margin-top: 12px;">AI 正在根据配图摘要生成图片...</p>
          </div>
        </div>

        <!-- ---------- Step 4: 完成 ---------- -->
        <div v-if="currentStep === 4">
          <!-- 最终文章 -->
          <div class="card">
            <div class="card-title">最终文章</div>
            <div class="article-content">{{ articleContent }}</div>
          </div>

          <!-- 生成的配图 -->
          <div v-if="imageUrls.length > 0" class="card">
            <div class="card-title">生成的配图</div>
            <div class="image-grid">
              <div v-for="(url, index) in imageUrls" :key="index" class="image-item">
                <img :src="url" :alt="'配图 ' + (index + 1)" />
              </div>
            </div>
          </div>

          <!-- 视觉要点 -->
          <div v-if="visualPoints.length > 0" class="card">
            <div class="card-title">视觉要点</div>
            <ul style="padding-left: 20px;">
              <li v-for="(point, index) in visualPoints" :key="index" style="margin-bottom: 8px;">
                {{ point }}
              </li>
            </ul>
          </div>

          <!-- 开始新创作按钮 -->
          <div class="btn-group">
            <button class="btn btn-primary" @click="handleReset">
              开始新的创作
            </button>
          </div>
        </div>

        <!-- ---------- 节点执行指标面板 ---------- -->
        <div v-if="nodeMetrics.length > 0" class="card">
          <div class="metrics-panel">
            <div class="metrics-panel-title">节点执行指标</div>

            <!-- 汇总统计 -->
            <div class="metrics-summary">
              <div class="metrics-summary-item">
                <div class="metrics-summary-value">{{ totalDuration }}</div>
                <div class="metrics-summary-label">总耗时</div>
              </div>
              <div class="metrics-summary-item">
                <div class="metrics-summary-value">{{ totalTokens.toLocaleString() }}</div>
                <div class="metrics-summary-label">总Token</div>
              </div>
              <div class="metrics-summary-item">
                <div class="metrics-summary-value">{{ nodeMetrics.length }}</div>
                <div class="metrics-summary-label">已执行节点</div>
              </div>
            </div>

            <!-- 各节点详情 -->
            <div class="metrics-list">
              <div v-for="(metric, index) in nodeMetrics" :key="index" class="metrics-item">
                <div class="metrics-node-name">{{ getNodeDisplayName(metric.node_name) }}</div>
                <div class="metrics-node-details">
                  <div class="metrics-detail">
                    <span class="metrics-detail-label">耗时:</span>
                    <span class="metrics-detail-value highlight">{{ formatDuration(metric.duration_ms) }}</span>
                  </div>
                  <div class="metrics-detail">
                    <span class="metrics-detail-label">输入:</span>
                    <span class="metrics-detail-value">{{ metric.input_tokens || 0 }} tokens</span>
                  </div>
                  <div class="metrics-detail">
                    <span class="metrics-detail-label">输出:</span>
                    <span class="metrics-detail-value">{{ metric.output_tokens || 0 }} tokens</span>
                  </div>
                  <div class="metrics-detail">
                    <span class="metrics-detail-label">总计:</span>
                    <span class="metrics-detail-value highlight">{{ metric.total_tokens || 0 }} tokens</span>
                  </div>
                  <div v-if="metric.model" class="metrics-detail">
                    <span class="metrics-detail-label">模型:</span>
                    <span class="metrics-detail-value">{{ metric.model }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ---------- 调试信息 ---------- -->
        <div v-if="threadId" class="card" style="margin-top: 20px; background: #fafafa;">
          <div class="card-title" style="font-size: 14px; color: #666;">工作流信息</div>
          <div style="font-size: 12px; color: #999;">
            <p>Thread ID: {{ threadId }}</p>
            <p>当前状态: {{ workflowStatus }}</p>
            <p v-if="interruptInfo">中断信息: {{ JSON.stringify(interruptInfo) }}</p>
          </div>
        </div>

        <!-- ---------- 流式日志面板 ---------- -->
        <div class="card stream-log-card">
          <div class="stream-log-header" @click="streamLogOpen = !streamLogOpen">
            <div class="stream-log-title">
              <span class="stream-log-icon">📡</span>
              Graph 流式输出日志
              <span class="stream-log-badge" v-if="streamLogs.length > 0">{{ streamLogs.length }}</span>
            </div>
            <div class="stream-log-actions">
              <button
                class="stream-log-clear-btn"
                @click.stop="clearStreamLogs"
                v-if="streamLogs.length > 0"
              >
                清空
              </button>
              <span class="stream-log-toggle">{{ streamLogOpen ? '▼' : '▶' }}</span>
            </div>
          </div>

          <!-- 日志内容 -->
          <div v-if="streamLogOpen" class="stream-log-content">
            <!-- 空状态 -->
            <div v-if="streamLogs.length === 0" class="stream-log-empty">
              暂无日志，启动工作流后将显示流式输出数据
            </div>

            <!-- 日志列表 -->
            <div v-else class="stream-log-list" ref="streamLogList">
              <div
                v-for="(log, index) in streamLogs"
                :key="index"
                class="stream-log-item"
                :class="['log-type-' + log.type]"
              >
                <div class="log-header">
                  <span class="log-time">{{ log.time }}</span>
                  <span class="log-type-badge" :class="'badge-' + log.type">{{ log.type }}</span>
                  <span class="log-source" v-if="log.source">{{ log.source }}</span>
                </div>
                <div class="log-content">
                  <template v-if="log.type === 'llm_token'">
                    <span class="log-token">{{ log.content }}</span>
                  </template>
                  <template v-else-if="log.data">
                    <pre class="log-data">{{ formatLogData(log.data) }}</pre>
                  </template>
                  <template v-else>
                    <span>{{ log.message }}</span>
                  </template>
                </div>
              </div>
            </div>

            <!-- 日志统计 -->
            <div class="stream-log-stats" v-if="streamLogs.length > 0">
              <div class="stat-item">
                <span class="stat-label">总事件:</span>
                <span class="stat-value">{{ streamLogs.length }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">Token数:</span>
                <span class="stat-value">{{ tokenCount }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">节点更新:</span>
                <span class="stat-value">{{ updateCount }}</span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * =============================================================================
 * Vue 3 Composition API 脚本
 * =============================================================================
 *
 * 状态管理说明：
 *   所有响应式状态用 ref() 或 reactive() 定义
 *   计算属性用 computed()
 *   生命周期用 onMounted() / onUnmounted()
 *
 * 状态分组：
 *   1. 认证状态（isLoggedIn、currentUsername 等）
 *   2. 侧边栏状态（sidebarOpen、threadList 等）
 *   3. 工作流状态（currentStep、threadId 等）
 *   4. 工作流数据（topicDirection、generatedTopics 等）
 *   5. UI 状态（message、loading 等）
 */

// =============================================================================
// 导入 Vue 3 响应式 API
// =============================================================================
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'

// =============================================================================
// 导入 API 函数
// =============================================================================
import {
    startWorkflow,
    getWorkflowState,
    selectTopic as apiSelectTopic,
    approveArticle,
    rejectArticle,
    getAllThreads,
    deleteThread,
    // 流式 API
    streamStartWorkflow,
    streamSelectTopic,
    streamApproveArticle,
    streamRejectArticle,
    // 认证相关
    login,
    register,
    logout,
    isLoggedIn as checkLoggedIn,
    getCurrentUser
} from './api.js'


// =============================================================================
// 第 1 部分：认证状态
// =============================================================================

/** 当前登录状态：true = 已登录，false = 未登录 */
const isLoggedIn = ref(false)

/** 登录/注册模式切换：true = 登录，false = 注册 */
const isLoginMode = ref(true)

/** 认证操作加载状态 */
const authLoading = ref(false)

/** 认证错误信息 */
const authError = ref('')

/** 当前用户名 */
const currentUsername = ref('')

/** 认证表单数据 */
const authForm = ref({
    username: '',
    password: ''
})


/**
 * 检查登录状态
 * 应用启动时调用，验证 localStorage 中的 Token 是否有效
 */
async function checkAuth() {
    if (checkLoggedIn()) {
        try {
            const user = await getCurrentUser()
            currentUsername.value = user.username
            isLoggedIn.value = true
        } catch (e) {
            // Token 无效，清除状态
            isLoggedIn.value = false
        }
    }
}

/**
 * 处理登录/注册
 * 根据 isLoginMode 决定调用 login 还是 register
 */
async function handleAuth() {
    authError.value = ''
    authLoading.value = true

    try {
        if (isLoginMode.value) {
            // ---------- 登录 ----------
            await login(authForm.value.username, authForm.value.password)
            const user = await getCurrentUser()
            currentUsername.value = user.username
            isLoggedIn.value = true
            authForm.value = { username: '', password: '' }
        } else {
            // ---------- 注册 ----------
            await register(authForm.value.username, authForm.value.password)
            // 注册成功后自动登录
            await login(authForm.value.username, authForm.value.password)
            const user = await getCurrentUser()
            currentUsername.value = user.username
            isLoggedIn.value = true
            authForm.value = { username: '', password: '' }
        }
    } catch (e) {
        authError.value = e.response?.data?.detail || e.message || '操作失败'
    } finally {
        authLoading.value = false
    }
}

/**
 * 登出
 * 删除 Token，清除状态，跳转登录页
 */
function handleLogout() {
    logout()
    isLoggedIn.value = false
    currentUsername.value = ''
    handleReset()
    threadList.value = []
}

/**
 * 监听 401 事件（Token 失效时自动登出）
 */
function onAuthLogout() {
    isLoggedIn.value = false
    currentUsername.value = ''
}

// 页面加载时：检查登录状态，监听 401 事件
onMounted(() => {
    checkAuth()
    window.addEventListener('auth:logout', onAuthLogout)
})

// 页面卸载时：移除事件监听器
onUnmounted(() => {
    window.removeEventListener('auth:logout', onAuthLogout)
})

// 登录后自动获取历史记录
watch(isLoggedIn, (newVal) => {
    if (newVal) {
        fetchThreadList()
    }
})


// =============================================================================
// 第 2 部分：侧边栏状态
// =============================================================================

/** 侧边栏展开/折叠状态 */
const sidebarOpen = ref(true)

/** 历史记录加载状态 */
const loadingThreads = ref(false)

/** 工作流线程列表 */
const threadList = ref([])


// =============================================================================
// 第 3 部分：流式日志状态
// =============================================================================

/** 流式日志面板展开/折叠 */
const streamLogOpen = ref(true)

/** 流式日志列表 */
const streamLogs = ref([])

/** 日志列表 DOM 引用（用于自动滚动） */
const streamLogList = ref(null)

/** Token 数量（llm_token 事件数） */
const tokenCount = computed(() => {
    return streamLogs.value.filter(log => log.type === 'llm_token').length
})

/** 更新次数（update 事件数） */
const updateCount = computed(() => {
    return streamLogs.value.filter(log => log.type === 'update').length
})

/**
 * 添加日志条目
 * @param {string} type - 日志类型
 * @param {any} data - 日志数据
 * @param {string} source - 来源
 */
function addStreamLog(type, data, source = '') {
    const now = new Date()
    // 时间格式：HH:mm:ss.SSS
    const time = now.toLocaleTimeString('zh-CN', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    })

    const log = {
        type,
        time,
        source,
        // llm_token 类型特殊处理，data 就是 content
        // 其他类型 data 是对象
        ...(type === 'llm_token' ? { content: data } : { data, message: getLogMessage(type, data) })
    }

    streamLogs.value.push(log)

    // 限制日志数量，避免内存溢出
    if (streamLogs.value.length > 500) {
        streamLogs.value = streamLogs.value.slice(-400)
    }

    // 自动滚动到最新日志
    nextTick(() => {
        if (streamLogList.value) {
            streamLogList.value.scrollTop = streamLogList.value.scrollHeight
        }
    })
}

/** 日志类型 -> 描述文本的映射 */
function getLogMessage(type, data) {
    const messages = {
        'init': `工作流初始化 - Thread ID: ${data?.thread_id || ''}`,
        'start': `开始执行 - 模式: ${data?.stream_mode || ''}`,
        'resume': `恢复工作流 - 操作: ${data?.action || ''}`,
        'update': `节点更新 - ${data?.node || ''}`,
        'state': '状态快照更新',
        'node_start': `节点开始 - ${data?.node || ''}`,
        'node_end': `节点结束 - ${data?.node || ''}`,
        'llm_start': `LLM 开始调用 - ${data?.model || ''}`,
        'llm_end': `LLM 调用结束`,
        'done': `执行完成 - 状态: ${data?.status || ''}`,
        'error': `错误: ${data?.message || data || ''}`
    }
    return messages[type] || type
}

/** 格式化日志数据（用于显示） */
function formatLogData(data) {
    if (!data) return ''
    try {
        const str = JSON.stringify(data, null, 2)
        // 大数据截断
        if (str.length > 1000) {
            return str.substring(0, 1000) + '\n... (数据已截断)'
        }
        return str
    } catch (e) {
        return String(data)
    }
}

/** 清空日志 */
function clearStreamLogs() {
    streamLogs.value = []
}


// =============================================================================
// 第 4 部分：工作流状态
// =============================================================================

/** 当前步骤：0=输入主题, 1=选择选题, 2=审核文章, 3=生成配图, 4=完成 */
const currentStep = ref(0)

/** 加载状态（用于禁用按钮等） */
const loading = ref(false)

/** 消息提示（成功/错误/警告） */
const message = ref('')

/** 消息类型 */
const messageType = ref('info')

/** 工作流线程 ID */
const threadId = ref('')

/** 工作流状态描述 */
const workflowStatus = ref('')

/** 中断信息（AI 等待用户操作的提示） */
const interruptInfo = ref(null)


// =============================================================================
// 第 5 部分：工作流数据
// =============================================================================

/** 用户输入的主题方向 */
const topicDirection = ref('')

/** AI 生成的选题列表 */
const generatedTopics = ref([])

/** 用户选中的选题 */
const selectedTopic = ref('')

/** 流式生成选题时的实时文本 */
const streamingTopicsText = ref('')

/** AI 生成的文章内容 */
const articleContent = ref('')

/** 驳回反馈/修改意见 */
const feedback = ref('')

/** 生成的配图 URL 列表 */
const imageUrls = ref([])

/** 视觉要点列表 */
const visualPoints = ref([])

/** 节点执行指标列表 */
const nodeMetrics = ref([])


// =============================================================================
// 第 6 部分：计算属性
// =============================================================================

/** 总耗时（所有节点耗时之和） */
const totalDuration = computed(() => {
    const total = nodeMetrics.value.reduce((sum, m) => sum + (m.duration_ms || 0), 0)
    return formatDuration(total)
})

/** 总 Token 数（所有节点 token 之和） */
const totalTokens = computed(() => {
    return nodeMetrics.value.reduce((sum, m) => sum + (m.total_tokens || 0), 0)
})

/**
 * 格式化耗时
 * @param {number} ms - 毫秒
 */
function formatDuration(ms) {
    if (!ms) return '0ms'
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(2)}s`
}

/** 节点名称 -> 中文显示名映射 */
const nodeNameMap = {
    'plan_topics': '选题规划',
    'write_draft': '文章写作',
    'extract_visuals': '提取配图要点',
    'generate_images': '生成配图'
}

/**
 * 获取节点中文显示名
 * @param {string} nodeName - 节点英文名称
 */
function getNodeDisplayName(nodeName) {
    return nodeNameMap[nodeName] || nodeName
}


// =============================================================================
// 第 7 部分：消息提示
// =============================================================================

/**
 * 显示消息提示
 * @param {string} msg - 消息文本
 * @param {string} type - 消息类型（info/success/error）
 */
function showMessage(msg, type = 'info') {
    message.value = msg
    messageType.value = type
    setTimeout(() => {
        message.value = ''
    }, 5000)
}


// =============================================================================
// 第 8 部分：工作流操作
// =============================================================================

/**
 * 启动工作流（Step 0 -> Step 1）
 * 调用 streamStartWorkflow，AI 生成选题
 */
async function handleStart() {
    if (!topicDirection.value.trim()) return

    loading.value = true
    message.value = ''
    generatedTopics.value = []
    streamingTopicsText.value = ''

    // 立即切换到 Step 1，让用户看到加载状态
    currentStep.value = 1

    try {
        await streamStartWorkflow(topicDirection.value, {
            // 初始化回调
            onInit: (data) => {
                threadId.value = data.thread_id
                addStreamLog('init', data, 'start')
            },
            // 开始事件
            onStart: (data) => {
                addStreamLog('start', data, 'start')
            },
            // 节点开始
            onNodeStart: (data) => {
                addStreamLog('node_start', data, 'start')
            },
            // 节点结束
            onNodeEnd: (data) => {
                addStreamLog('node_end', data, 'start')
                if (data.metrics) {
                    nodeMetrics.value = [...nodeMetrics.value, data.metrics]
                }
            },
            // LLM 开始
            onLlmStart: (data) => {
                addStreamLog('llm_start', data, 'start')
            },
            // LLM Token（选题阶段通常不会触发）
            onLlmToken: (content) => {
                addStreamLog('llm_token', content, 'start')
            },
            // LLM 结束
            onLlmEnd: (data) => {
                addStreamLog('llm_end', data, 'start')
            },
            // 节点更新（核心回调）
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'start')
                if (node === 'topic_selection' || node === 'plan_topics' || node.includes('plan_topics')) {
                    if (output.generated_topics?.length > 0) {
                        generatedTopics.value = output.generated_topics
                    }
                }
                if (output.node_metrics) {
                    nodeMetrics.value = output.node_metrics
                }
            },
            // 状态更新
            onState: (data) => {
                addStreamLog('state', data, 'start')
            },
            // 完成回调（核心）
            onDone: (data) => {
                addStreamLog('done', data, 'start')
                workflowStatus.value = data.status
                interruptInfo.value = data.interrupt_info

                // 从中断信息中获取选题
                if (data.interrupt_info?.options?.length > 0 && generatedTopics.value.length === 0) {
                    generatedTopics.value = data.interrupt_info.options
                }
                // 从最终状态获取选题
                if (data.values?.generated_topics?.length > 0) {
                    generatedTopics.value = data.values.generated_topics
                }
                if (data.values?.node_metrics) {
                    nodeMetrics.value = data.values.node_metrics
                }
                streamingTopicsText.value = ''
                loading.value = false
                showMessage('选题已生成，请选择一个继续', 'success')
                fetchThreadList()
            },
            // 错误回调
            onError: (errorMsg) => {
                console.error('流式启动失败:', errorMsg)
                addStreamLog('error', { message: errorMsg }, 'start')
                loading.value = false
                streamingTopicsText.value = ''
                currentStep.value = 0
                showMessage(`启动失败: ${errorMsg}`, 'error')
            }
        }, 'updates')

    } catch (error) {
        loading.value = false
        streamingTopicsText.value = ''
        currentStep.value = 0
        showMessage(`启动失败: ${error.message}`, 'error')
    }
}

/**
 * 选择选题（Step 1 -> Step 2）
 * 调用 streamSelectTopic，AI 流式生成文章
 */
async function handleSelectTopic() {
    if (!selectedTopic.value) return

    loading.value = true
    currentStep.value = 2
    articleContent.value = ''

    try {
        await streamSelectTopic(threadId.value, selectedTopic.value, {
            // 恢复事件
            onResume: (data) => {
                addStreamLog('resume', data, 'select_topic')
            },
            // 开始事件
            onStart: (data) => {
                addStreamLog('start', data, 'select_topic')
            },
            // 节点开始
            onNodeStart: (data) => {
                addStreamLog('node_start', data, 'select_topic')
            },
            // 节点结束
            onNodeEnd: (data) => {
                addStreamLog('node_end', data, 'select_topic')
            },
            // LLM 开始
            onLlmStart: (data) => {
                addStreamLog('llm_start', data, 'select_topic')
            },
            // LLM Token（核心：逐字追加文章内容）
            onLlmToken: (content) => {
                articleContent.value += content
                addStreamLog('llm_token', content, 'select_topic')
            },
            // LLM 结束
            onLlmEnd: (data) => {
                addStreamLog('llm_end', data, 'select_topic')
            },
            // 节点更新
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'select_topic')
                if (node === 'write_draft' && output.article_content) {
                    articleContent.value = output.article_content
                }
                if (output.node_metrics) {
                    nodeMetrics.value = output.node_metrics
                }
            },
            // 完成
            onDone: (data) => {
                addStreamLog('done', data, 'select_topic')
                workflowStatus.value = data.status
                interruptInfo.value = data.interrupt_info
                if (data.values?.article_content) {
                    articleContent.value = data.values.article_content
                }
                if (data.values?.node_metrics) {
                    nodeMetrics.value = data.values.node_metrics
                }
                loading.value = false
                showMessage('文章草稿已生成，请审核', 'success')
            },
            // 错误
            onError: (errorMsg) => {
                console.error('选题失败:', errorMsg)
                addStreamLog('error', { message: errorMsg }, 'select_topic')
                loading.value = false
                currentStep.value = 1
                showMessage(`操作失败: ${errorMsg}`, 'error')
            }
        }, 'events')

    } catch (error) {
        loading.value = false
        showMessage(`操作失败: ${error.message}`, 'error')
        currentStep.value = 1
    }
}

/**
 * 审核通过（Step 2 -> Step 3 -> Step 4）
 * 调用 streamApproveArticle，AI 生成配图
 */
async function handleApprove() {
    loading.value = true
    currentStep.value = 3

    try {
        await streamApproveArticle(threadId.value, {
            // 恢复事件
            onResume: (data) => {
                addStreamLog('resume', data, 'approve')
            },
            // 开始事件
            onStart: (data) => {
                addStreamLog('start', data, 'approve')
            },
            // 节点更新
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'approve')
                if (output.visual_points) {
                    visualPoints.value = output.visual_points
                }
                if (output.image_urls) {
                    imageUrls.value = output.image_urls
                }
                if (output.node_metrics) {
                    nodeMetrics.value = output.node_metrics
                }
            },
            // 完成
            onDone: (data) => {
                addStreamLog('done', data, 'approve')
                workflowStatus.value = data.status
                if (data.is_completed) {
                    articleContent.value = data.values?.article_content || articleContent.value
                    imageUrls.value = data.values?.image_urls || []
                    visualPoints.value = data.values?.visual_points || []
                    if (data.values?.node_metrics) {
                        nodeMetrics.value = data.values.node_metrics
                    }
                    currentStep.value = 4
                    showMessage('工作流已完成！', 'success')
                }
                loading.value = false
            },
            // 错误
            onError: (errorMsg) => {
                console.error('审核通过失败:', errorMsg)
                addStreamLog('error', { message: errorMsg }, 'approve')
                loading.value = false
                currentStep.value = 2
                showMessage(`操作失败: ${errorMsg}`, 'error')
            }
        }, 'updates')

    } catch (error) {
        loading.value = false
        currentStep.value = 2
        showMessage(`操作失败: ${error.message}`, 'error')
    }
}

/**
 * 驳回重写（Step 2 -> 重新执行 Step 2）
 * 调用 streamRejectArticle，AI 根据反馈重新生成文章
 */
async function handleReject() {
    loading.value = true
    articleContent.value = ''
    const currentFeedback = feedback.value
    feedback.value = ''

    try {
        await streamRejectArticle(threadId.value, currentFeedback, {
            // 恢复事件
            onResume: (data) => {
                addStreamLog('resume', data, 'reject')
            },
            // 开始事件
            onStart: (data) => {
                addStreamLog('start', data, 'reject')
            },
            // 节点开始
            onNodeStart: (data) => {
                addStreamLog('node_start', data, 'reject')
            },
            // 节点结束
            onNodeEnd: (data) => {
                addStreamLog('node_end', data, 'reject')
            },
            // LLM 开始
            onLlmStart: (data) => {
                addStreamLog('llm_start', data, 'reject')
            },
            // LLM Token（逐字追加）
            onLlmToken: (content) => {
                articleContent.value += content
                addStreamLog('llm_token', content, 'reject')
            },
            // LLM 结束
            onLlmEnd: (data) => {
                addStreamLog('llm_end', data, 'reject')
            },
            // 节点更新
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'reject')
                if (node === 'write_draft' && output.article_content) {
                    articleContent.value = output.article_content
                }
                if (output.node_metrics) {
                    nodeMetrics.value = output.node_metrics
                }
            },
            // 完成
            onDone: (data) => {
                addStreamLog('done', data, 'reject')
                workflowStatus.value = data.status
                interruptInfo.value = data.interrupt_info
                if (data.values?.article_content) {
                    articleContent.value = data.values.article_content
                }
                if (data.values?.node_metrics) {
                    nodeMetrics.value = data.values.node_metrics
                }
                loading.value = false
                showMessage('文章已重写，请重新审核', 'info')
            },
            // 错误
            onError: (errorMsg) => {
                console.error('驳回重写失败:', errorMsg)
                addStreamLog('error', { message: errorMsg }, 'reject')
                loading.value = false
                showMessage(`操作失败: ${errorMsg}`, 'error')
            }
        }, 'events')

    } catch (error) {
        loading.value = false
        showMessage(`操作失败: ${error.message}`, 'error')
    }
}


// =============================================================================
// 第 9 部分：重置和列表管理
// =============================================================================

/** 重置所有状态 */
function handleReset() {
    currentStep.value = 0
    threadId.value = ''
    workflowStatus.value = ''
    interruptInfo.value = null
    topicDirection.value = ''
    generatedTopics.value = []
    selectedTopic.value = ''
    streamingTopicsText.value = ''
    articleContent.value = ''
    feedback.value = ''
    imageUrls.value = []
    visualPoints.value = []
    nodeMetrics.value = []
    message.value = ''
    streamLogs.value = []
}

/** 新建工作流 */
function handleNewWorkflow() {
    handleReset()
    fetchThreadList()
}

/**
 * 获取历史记录列表
 */
async function fetchThreadList() {
    loadingThreads.value = true
    try {
        const result = await getAllThreads()
        threadList.value = result.threads || []
    } catch (error) {
        console.error('获取历史记录失败:', error)
    } finally {
        loadingThreads.value = false
    }
}

/**
 * 切换到指定的工作流
 * @param {string} targetThreadId - 目标线程 ID
 */
async function handleSwitchThread(targetThreadId) {
    if (targetThreadId === threadId.value) return

    loading.value = true
    message.value = ''

    try {
        const state = await getWorkflowState(targetThreadId)

        // 更新状态
        threadId.value = targetThreadId
        workflowStatus.value = state.status
        interruptInfo.value = state.interrupt_info

        // 更新数据
        const values = state.values || {}
        topicDirection.value = values.topic_direction || ''
        generatedTopics.value = values.generated_topics || []
        selectedTopic.value = values.selected_topic || ''
        articleContent.value = values.article_content || ''
        imageUrls.value = values.image_urls || []
        visualPoints.value = values.visual_points || []
        feedback.value = ''

        // 清空临时状态
        streamingTopicsText.value = ''
        streamLogs.value = []

        // 获取指标
        const rawMetrics = state.node_metrics || values.node_metrics || []
        nodeMetrics.value = rawMetrics.map(m => ({
            node_name: m.node_name || '',
            duration_ms: m.duration_ms || 0,
            input_tokens: m.input_tokens || 0,
            output_tokens: m.output_tokens || 0,
            total_tokens: m.total_tokens || 0,
            start_time: m.start_time || '',
            end_time: m.end_time || '',
            model: m.model || ''
        }))

        // 根据状态判断当前步骤
        currentStep.value = determineCurrentStep(state)

        showMessage('已切换到历史工作流', 'success')
    } catch (error) {
        showMessage(`切换失败: ${error.response?.data?.detail || error.message}`, 'error')
    } finally {
        loading.value = false
    }
}

/**
 * 根据状态判断当前步骤
 * @param {object} state - 工作流状态对象
 */
function determineCurrentStep(state) {
    const values = state.values || {}
    const interruptInfo = state.interrupt_info
    const isCompleted = state.is_completed

    if (isCompleted) return 4

    if (interruptInfo) {
        const actionRequired = interruptInfo.action_required
        if (actionRequired === 'select_topic') return 1
        if (actionRequired === 'review') return 2
    }

    if (values.image_urls && values.image_urls.length > 0) return 4
    if (values.article_content) return 2
    if (values.generated_topics && values.generated_topics.length > 0) return 1

    return 0
}

/**
 * 删除工作流
 * @param {string} targetThreadId - 目标线程 ID
 */
async function handleDeleteThread(targetThreadId) {
    if (!confirm('确定要删除这条历史记录吗？')) return

    try {
        await deleteThread(targetThreadId)

        // 如果删除的是当前工作流，重置状态
        if (targetThreadId === threadId.value) {
            handleReset()
        }

        // 刷新列表
        await fetchThreadList()
        showMessage('删除成功', 'success')
    } catch (error) {
        showMessage(`删除失败: ${error.response?.data?.detail || error.message}`, 'error')
    }
}
</script>
