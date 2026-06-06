<template>
  <!-- 登录页 -->
  <div v-if="!isLoggedIn" class="auth-page">
    <div class="auth-container">
      <div class="auth-card">
        <h2>{{ isLoginMode ? '登录' : '注册' }}</h2>
        <form @submit.prevent="handleAuth">
          <div class="form-group">
            <label>用户名</label>
            <input v-model="authForm.username" type="text" class="input"
              placeholder="请输入用户名（至少3个字符）" required minlength="3" />
          </div>
          <div class="form-group">
            <label>密码</label>
            <input v-model="authForm.password" type="password" class="input"
              placeholder="请输入密码（至少6个字符）" required minlength="6" />
          </div>
          <div v-if="authError" class="auth-error">{{ authError }}</div>
          <button type="submit" class="btn btn-primary auth-btn" :disabled="authLoading">
            {{ authLoading ? '处理中...' : (isLoginMode ? '登录' : '注册') }}
          </button>
        </form>
        <div class="auth-switch">
          <span v-if="isLoginMode">
            还没有账号？<a href="#" @click.prevent="isLoginMode = false">立即注册</a>
          </span>
          <span v-else>
            已有账号？<a href="#" @click.prevent="isLoginMode = true">立即登录</a>
          </span>
        </div>
      </div>
    </div>
  </div>

  <!-- 主应用页面 -->
  <div v-else class="app-layout">
    <!-- 侧边栏 -->
    <div class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <div class="sidebar-header">
        <h3 v-if="sidebarOpen">历史记录</h3>
        <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen">
          {{ sidebarOpen ? '◀' : '▶' }}
        </button>
      </div>
      <div v-if="sidebarOpen" class="sidebar-content">
        <button class="btn btn-primary sidebar-btn" @click="handleNewWorkflow">+ 新建工作流</button>
        <div class="thread-list">
          <div v-if="loadingThreads" class="loading-small"><div class="loading-spinner-small"></div></div>
          <div v-else-if="threadList.length === 0" class="empty-state">暂无历史记录</div>
          <div v-else v-for="thread in threadList" :key="thread.thread_id" class="thread-item"
            :class="{ active: threadId === thread.thread_id }"
            @click="handleSwitchThread(thread.thread_id)">
            <div class="thread-item-header">
              <span class="thread-status" :class="thread.is_completed ? 'completed' : 'in-progress'">
                {{ thread.is_completed ? '✓' : '●' }}
              </span>
              <span class="thread-title">{{ thread.topic_direction || '未命名' }}</span>
            </div>
            <div class="thread-item-meta">
              <span class="thread-topic">{{ thread.selected_topic || thread.status }}</span>
            </div>
            <button class="thread-delete-btn" @click.stop="handleDeleteThread(thread.thread_id)" title="删除">×</button>
          </div>
        </div>
        <button v-if="threadList.length > 0" class="btn sidebar-btn refresh-btn" @click="fetchThreadList" :disabled="loadingThreads">刷新列表</button>
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="main-content">
      <div class="container">
        <!-- 头部 -->
        <div class="header">
          <div class="header-top">
            <div>
              <h1>AI 内容运营助手</h1>
              <p>基于 LangGraph 的智能内容生成工作流</p>
            </div>
            <div class="user-info">
              <span class="username">{{ currentUsername }}</span>
              <button class="btn btn-logout" @click="handleLogout">退出登录</button>
            </div>
          </div>
        </div>

        <!-- 进度条 -->
        <div class="card">
          <div class="workflow-steps">
            <div class="step" :class="{ active: currentStep === 0, completed: currentStep > 0 }">
              <div class="step-icon">1</div><div class="step-title">输入主题</div>
            </div>
            <div class="step" :class="{ active: currentStep === 1, completed: currentStep > 1 }">
              <div class="step-icon">2</div><div class="step-title">选择选题</div>
            </div>
            <div class="step" :class="{ active: currentStep === 2, completed: currentStep > 2 }">
              <div class="step-icon">3</div><div class="step-title">审核文章</div>
            </div>
            <div class="step" :class="{ active: currentStep === 3, completed: currentStep > 3 }">
              <div class="step-icon">4</div><div class="step-title">生成配图</div>
            </div>
            <div class="step" :class="{ active: currentStep === 4, completed: currentStep > 4 }">
              <div class="step-icon">✓</div><div class="step-title">完成</div>
            </div>
          </div>
        </div>

        <!-- 消息提示 -->
        <div v-if="message" :class="['message', `message-${messageType}`]">{{ message }}</div>

        <!-- 当前工作流信息 -->
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

        <!-- Step 0: 输入主题方向 -->
        <div v-if="currentStep === 0" class="card">
          <div class="card-title">输入主题方向</div>
          <div style="display: flex; gap: 12px;">
            <input v-model="topicDirection" class="input"
              placeholder="请输入内容主题方向，例如：AI技术、Python开发、职场技能"
              @keyup.enter="handleStart" />
            <button class="btn btn-primary" :disabled="!topicDirection.trim() || loading" @click="handleStart">
              {{ loading ? '生成中...' : '开始' }}
            </button>
          </div>
        </div>

        <!-- Step 1: 选择选题 -->
        <div v-if="currentStep === 1" class="card">
          <div class="card-title">请选择一个选题</div>
          <div v-if="loading && streamingTopicsText" class="streaming-content">
            <div class="streaming-label">AI 正在生成选题...</div>
            <div class="streaming-text">{{ streamingTopicsText }}<span class="typing-cursor">▊</span></div>
          </div>
          <div v-else-if="loading && generatedTopics.length === 0 && !streamingTopicsText" class="loading">
            <div class="loading-spinner"></div>
            <p style="margin-top: 12px;">AI 正在生成选题...</p>
          </div>
          <div v-else class="topic-list">
            <div v-for="(topic, index) in generatedTopics" :key="index" class="topic-item"
              :class="{ selected: selectedTopic === topic }" @click="selectedTopic = topic">
              {{ topic }}
            </div>
            <div v-if="loading && generatedTopics.length > 0" class="loading-small" style="margin-top: 12px;">
              <div class="loading-spinner-small"></div>
              <span style="margin-left: 8px; color: #666;">正在生成更多选题...</span>
            </div>
          </div>
          <div class="btn-group">
            <button class="btn btn-primary" :disabled="!selectedTopic || loading" @click="handleSelectTopic">确认选题</button>
            <button class="btn" style="background: #f0f0f0;" @click="handleReset">重新开始</button>
          </div>
        </div>

        <!-- Step 2: 审核文章 -->
        <div v-if="currentStep === 2" class="card">
          <div class="card-title">审核文章草稿</div>
          <div v-if="loading && !articleContent" class="loading">
            <div class="loading-spinner"></div>
            <p style="margin-top: 12px;">AI 正在撰写文章...</p>
          </div>
          <template v-else>
            <div class="article-content">{{ articleContent }}<span v-if="loading" class="typing-cursor">▊</span></div>
            <div class="feedback-section">
              <label>驳回反馈（可选）:</label>
              <textarea v-model="feedback" class="textarea"
                placeholder="如果需要驳回，请输入修改意见..." :disabled="loading"></textarea>
            </div>
            <div class="btn-group">
              <button class="btn btn-success" :disabled="loading" @click="handleApprove">通过</button>
              <button class="btn btn-danger" :disabled="loading" @click="handleReject">驳回重写</button>
            </div>
          </template>
        </div>

        <!-- Step 3: 生成配图中 -->
        <div v-if="currentStep === 3" class="card">
          <div class="card-title">正在生成配图</div>
          <div v-if="visualPoints.length > 0" class="visual-summary">
            <div class="visual-summary-title">配图摘要（AI 提取的视觉要点）</div>
            <ul class="visual-summary-list">
              <li v-for="(point, index) in visualPoints" :key="index">
                <span class="visual-point-index">{{ index + 1 }}</span>
                <span class="visual-point-text">{{ point }}</span>
              </li>
            </ul>
          </div>
          <div class="loading">
            <div class="loading-spinner"></div>
            <p style="margin-top: 12px;">AI 正在根据配图摘要生成图片...</p>
          </div>
        </div>

        <!-- Step 4: 完成 -->
        <div v-if="currentStep === 4">
          <div class="card">
            <div class="card-title">最终文章</div>
            <div class="article-content">{{ articleContent }}</div>
          </div>
          <div v-if="imageUrls.length > 0" class="card">
            <div class="card-title">生成的配图</div>
            <div class="image-grid">
              <div v-for="(url, index) in imageUrls" :key="index" class="image-item">
                <img :src="url" :alt="'配图 ' + (index + 1)" />
              </div>
            </div>
          </div>
          <div v-if="visualPoints.length > 0" class="card">
            <div class="card-title">视觉要点</div>
            <ul style="padding-left: 20px;">
              <li v-for="(point, index) in visualPoints" :key="index" style="margin-bottom: 8px;">{{ point }}</li>
            </ul>
          </div>
          <div class="btn-group">
            <button class="btn btn-primary" @click="handleReset">开始新的创作</button>
          </div>
        </div>

        <!-- 节点执行指标面板 -->
        <div v-if="nodeMetrics.length > 0" class="card">
          <div class="metrics-panel">
            <div class="metrics-panel-title">节点执行指标</div>
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

        <!-- 调试信息 -->
        <div v-if="threadId" class="card" style="margin-top: 20px; background: #fafafa;">
          <div class="card-title" style="font-size: 14px; color: #666;">工作流信息</div>
          <div style="font-size: 12px; color: #999;">
            <p>Thread ID: {{ threadId }}</p>
            <p>当前状态: {{ workflowStatus }}</p>
            <p v-if="interruptInfo">中断信息: {{ JSON.stringify(interruptInfo) }}</p>
          </div>
        </div>

        <!-- 流式日志面板 -->
        <div class="card stream-log-card">
          <div class="stream-log-header" @click="streamLogOpen = !streamLogOpen">
            <div class="stream-log-title">
              <span class="stream-log-icon">📡</span>
              Graph 流式输出日志
              <span class="stream-log-badge" v-if="streamLogs.length > 0">{{ streamLogs.length }}</span>
            </div>
            <div class="stream-log-actions">
              <button class="stream-log-clear-btn" @click.stop="clearStreamLogs" v-if="streamLogs.length > 0">清空</button>
              <span class="stream-log-toggle">{{ streamLogOpen ? '▼' : '▶' }}</span>
            </div>
          </div>
          <div v-if="streamLogOpen" class="stream-log-content">
            <div v-if="streamLogs.length === 0" class="stream-log-empty">暂无日志，启动工作流后将显示流式输出数据</div>
            <div v-else class="stream-log-list" ref="streamLogList">
              <div v-for="(log, index) in streamLogs" :key="index" class="stream-log-item" :class="['log-type-' + log.type]">
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
            <div class="stream-log-stats" v-if="streamLogs.length > 0">
              <div class="stat-item"><span class="stat-label">总事件:</span><span class="stat-value">{{ streamLogs.length }}</span></div>
              <div class="stat-item"><span class="stat-label">Token数:</span><span class="stat-value">{{ tokenCount }}</span></div>
              <div class="stat-item"><span class="stat-label">节点更新:</span><span class="stat-value">{{ updateCount }}</span></div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
// AI 内容运营助手 - Vue.js 前端应用，管理所有页面状态和用户交互。

import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'

import {
    startWorkflow, getWorkflowState, selectTopic as apiSelectTopic,
    approveArticle, rejectArticle, getAllThreads, deleteThread,
    streamStartWorkflow, streamSelectTopic, streamApproveArticle, streamRejectArticle,
    login, register, logout, isLoggedIn as checkLoggedIn, getCurrentUser
} from './api.js'


// 第 1 部分：认证状态

const isLoggedIn = ref(false)
/** 登录/注册模式切换 */
const isLoginMode = ref(true)
/** 认证操作加载状态 */
const authLoading = ref(false)
/** 认证错误信息 */
const authError = ref('')
/** 当前用户名 */
const currentUsername = ref('')
/** 认证表单数据 */
const authForm = ref({ username: '', password: '' })

/** 检查登录状态 */
async function checkAuth() {
    if (checkLoggedIn()) {
        try {
            const user = await getCurrentUser()
            currentUsername.value = user.username
            isLoggedIn.value = true
        } catch (e) {
            isLoggedIn.value = false
        }
    }
}

/** 处理登录/注册 */
async function handleAuth() {
    authError.value = ''
    authLoading.value = true
    try {
        if (isLoginMode.value) {
            await login(authForm.value.username, authForm.value.password)
            const user = await getCurrentUser()
            currentUsername.value = user.username
            isLoggedIn.value = true
            authForm.value = { username: '', password: '' }
        } else {
            await register(authForm.value.username, authForm.value.password)
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

/** 登出 */
function handleLogout() {
    logout()
    isLoggedIn.value = false
    currentUsername.value = ''
    handleReset()
    threadList.value = []
}

/** Token 失效时自动登出 */
function onAuthLogout() {
    isLoggedIn.value = false
    currentUsername.value = ''
}

onMounted(() => {
    checkAuth()
    window.addEventListener('auth:logout', onAuthLogout)
})
onUnmounted(() => {
    window.removeEventListener('auth:logout', onAuthLogout)
})
watch(isLoggedIn, (newVal) => {
    if (newVal) fetchThreadList()
})


// 第 2 部分：侧边栏状态

const sidebarOpen = ref(true)
const loadingThreads = ref(false)
const threadList = ref([])


// 第 3 部分：流式日志状态

const streamLogOpen = ref(true)
const streamLogs = ref([])
const streamLogList = ref(null)

const tokenCount = computed(() => streamLogs.value.filter(log => log.type === 'llm_token').length)
const updateCount = computed(() => streamLogs.value.filter(log => log.type === 'update').length)

function addStreamLog(type, data, source = '') {
    const now = new Date()
    const time = now.toLocaleTimeString('zh-CN', {
        hour12: false, hour: '2-digit', minute: '2-digit',
        second: '2-digit', fractionalSecondDigits: 3
    })
    const log = {
        type, time, source,
        ...(type === 'llm_token' ? { content: data } : { data, message: getLogMessage(type, data) })
    }
    streamLogs.value.push(log)
    if (streamLogs.value.length > 500) streamLogs.value = streamLogs.value.slice(-400)
    nextTick(() => {
        if (streamLogList.value) streamLogList.value.scrollTop = streamLogList.value.scrollHeight
    })
}

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

function formatLogData(data) {
    if (!data) return ''
    try {
        const str = JSON.stringify(data, null, 2)
        return str.length > 1000 ? str.substring(0, 1000) + '\n... (数据已截断)' : str
    } catch (e) { return String(data) }
}

function clearStreamLogs() { streamLogs.value = [] }


// 第 4 部分：工作流状态

/** 当前步骤：0=输入主题, 1=选择选题, 2=审核文章, 3=生成配图, 4=完成 */
const currentStep = ref(0)
const loading = ref(false)
const message = ref('')
const messageType = ref('info')
const threadId = ref('')
const workflowStatus = ref('')
const interruptInfo = ref(null)


// 第 5 部分：工作流数据

const topicDirection = ref('')
const generatedTopics = ref([])
const selectedTopic = ref('')
const streamingTopicsText = ref('')
const articleContent = ref('')
const feedback = ref('')
const imageUrls = ref([])
const visualPoints = ref([])
const nodeMetrics = ref([])


// 第 6 部分：计算属性

const totalDuration = computed(() => {
    const total = nodeMetrics.value.reduce((sum, m) => sum + (m.duration_ms || 0), 0)
    return formatDuration(total)
})
const totalTokens = computed(() => nodeMetrics.value.reduce((sum, m) => sum + (m.total_tokens || 0), 0))

function formatDuration(ms) {
    if (!ms) return '0ms'
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(2)}s`
}

const nodeNameMap = {
    'plan_topics': '选题规划', 'write_draft': '文章写作',
    'extract_visuals': '提取配图要点', 'generate_images': '生成配图'
}
function getNodeDisplayName(nodeName) { return nodeNameMap[nodeName] || nodeName }

function showMessage(msg, type = 'info') {
    message.value = msg
    messageType.value = type
    setTimeout(() => { message.value = '' }, 5000)
}


// 第 7 部分：工作流操作

async function handleStart() {
    if (!topicDirection.value.trim()) return
    loading.value = true
    message.value = ''
    generatedTopics.value = []
    streamingTopicsText.value = ''
    currentStep.value = 1

    try {
        await streamStartWorkflow(topicDirection.value, {
            onInit: (data) => { threadId.value = data.thread_id; addStreamLog('init', data, 'start') },
            onStart: (data) => addStreamLog('start', data, 'start'),
            onNodeStart: (data) => addStreamLog('node_start', data, 'start'),
            onNodeEnd: (data) => {
                addStreamLog('node_end', data, 'start')
                if (data.metrics) nodeMetrics.value = [...nodeMetrics.value, data.metrics]
            },
            onLlmStart: (data) => addStreamLog('llm_start', data, 'start'),
            onLlmToken: (content) => addStreamLog('llm_token', content, 'start'),
            onLlmEnd: (data) => addStreamLog('llm_end', data, 'start'),
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'start')
                if ((node === 'topic_selection' || node === 'plan_topics' || node.includes('plan_topics')) && output.generated_topics?.length > 0) generatedTopics.value = output.generated_topics
                if (output.node_metrics) nodeMetrics.value = output.node_metrics
            },
            onState: (data) => addStreamLog('state', data, 'start'),
            onDone: (data) => {
                addStreamLog('done', data, 'start')
                workflowStatus.value = data.status
                interruptInfo.value = data.interrupt_info
                if (data.interrupt_info?.options?.length > 0 && generatedTopics.value.length === 0) generatedTopics.value = data.interrupt_info.options
                if (data.values?.generated_topics?.length > 0) generatedTopics.value = data.values.generated_topics
                if (data.values?.node_metrics) nodeMetrics.value = data.values.node_metrics
                streamingTopicsText.value = ''
                loading.value = false
                showMessage('选题已生成，请选择一个继续', 'success')
                fetchThreadList()
            },
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

async function handleSelectTopic() {
    if (!selectedTopic.value) return
    loading.value = true
    currentStep.value = 2
    articleContent.value = ''

    try {
        await streamSelectTopic(threadId.value, selectedTopic.value, {
            onResume: (data) => addStreamLog('resume', data, 'select_topic'),
            onStart: (data) => addStreamLog('start', data, 'select_topic'),
            onNodeStart: (data) => addStreamLog('node_start', data, 'select_topic'),
            onNodeEnd: (data) => addStreamLog('node_end', data, 'select_topic'),
            onLlmStart: (data) => addStreamLog('llm_start', data, 'select_topic'),
            onLlmToken: (content) => { articleContent.value += content; addStreamLog('llm_token', content, 'select_topic') },
            onLlmEnd: (data) => addStreamLog('llm_end', data, 'select_topic'),
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'select_topic')
                if (node === 'write_draft' && output.article_content) articleContent.value = output.article_content
                if (output.node_metrics) nodeMetrics.value = output.node_metrics
            },
            onDone: (data) => {
                addStreamLog('done', data, 'select_topic')
                workflowStatus.value = data.status
                interruptInfo.value = data.interrupt_info
                if (data.values?.article_content) articleContent.value = data.values.article_content
                if (data.values?.node_metrics) nodeMetrics.value = data.values.node_metrics
                loading.value = false
                showMessage('文章草稿已生成，请审核', 'success')
            },
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

async function handleApprove() {
    loading.value = true
    currentStep.value = 3

    try {
        await streamApproveArticle(threadId.value, {
            onResume: (data) => addStreamLog('resume', data, 'approve'),
            onStart: (data) => addStreamLog('start', data, 'approve'),
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'approve')
                if (output.visual_points) visualPoints.value = output.visual_points
                if (output.image_urls) imageUrls.value = output.image_urls
                if (output.node_metrics) nodeMetrics.value = output.node_metrics
            },
            onDone: (data) => {
                addStreamLog('done', data, 'approve')
                workflowStatus.value = data.status
                if (data.is_completed) {
                    articleContent.value = data.values?.article_content || articleContent.value
                    imageUrls.value = data.values?.image_urls || []
                    visualPoints.value = data.values?.visual_points || []
                    if (data.values?.node_metrics) nodeMetrics.value = data.values.node_metrics
                    currentStep.value = 4
                    showMessage('工作流已完成！', 'success')
                }
                loading.value = false
            },
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

async function handleReject() {
    loading.value = true
    articleContent.value = ''
    const currentFeedback = feedback.value
    feedback.value = ''

    try {
        await streamRejectArticle(threadId.value, currentFeedback, {
            onResume: (data) => addStreamLog('resume', data, 'reject'),
            onStart: (data) => addStreamLog('start', data, 'reject'),
            onNodeStart: (data) => addStreamLog('node_start', data, 'reject'),
            onNodeEnd: (data) => addStreamLog('node_end', data, 'reject'),
            onLlmStart: (data) => addStreamLog('llm_start', data, 'reject'),
            onLlmToken: (content) => { articleContent.value += content; addStreamLog('llm_token', content, 'reject') },
            onLlmEnd: (data) => addStreamLog('llm_end', data, 'reject'),
            onUpdate: (node, output) => {
                addStreamLog('update', { node, output }, 'reject')
                if (node === 'write_draft' && output.article_content) articleContent.value = output.article_content
                if (output.node_metrics) nodeMetrics.value = output.node_metrics
            },
            onDone: (data) => {
                addStreamLog('done', data, 'reject')
                workflowStatus.value = data.status
                interruptInfo.value = data.interrupt_info
                if (data.values?.article_content) articleContent.value = data.values.article_content
                if (data.values?.node_metrics) nodeMetrics.value = data.values.node_metrics
                loading.value = false
                showMessage('文章已重写，请重新审核', 'info')
            },
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


// 第 8 部分：重置和列表管理

function handleReset() {
    currentStep.value = 0; threadId.value = ''; workflowStatus.value = ''
    interruptInfo.value = null; topicDirection.value = ''; generatedTopics.value = []
    selectedTopic.value = ''; streamingTopicsText.value = ''; articleContent.value = ''
    feedback.value = ''; imageUrls.value = []; visualPoints.value = []
    nodeMetrics.value = []; message.value = ''; streamLogs.value = []
}

function handleNewWorkflow() { handleReset(); fetchThreadList() }

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

async function handleSwitchThread(targetThreadId) {
    if (targetThreadId === threadId.value) return
    loading.value = true
    message.value = ''

    try {
        const state = await getWorkflowState(targetThreadId)
        threadId.value = targetThreadId
        workflowStatus.value = state.status
        interruptInfo.value = state.interrupt_info

        const values = state.values || {}
        topicDirection.value = values.topic_direction || ''
        generatedTopics.value = values.generated_topics || []
        selectedTopic.value = values.selected_topic || ''
        articleContent.value = values.article_content || ''
        imageUrls.value = values.image_urls || []
        visualPoints.value = values.visual_points || []
        feedback.value = ''
        streamingTopicsText.value = ''
        streamLogs.value = []

        const rawMetrics = state.node_metrics || values.node_metrics || []
        nodeMetrics.value = rawMetrics.map(m => ({
            node_name: m.node_name || '', duration_ms: m.duration_ms || 0,
            input_tokens: m.input_tokens || 0, output_tokens: m.output_tokens || 0,
            total_tokens: m.total_tokens || 0, start_time: m.start_time || '',
            end_time: m.end_time || '', model: m.model || ''
        }))

        currentStep.value = determineCurrentStep(state)
        showMessage('已切换到历史工作流', 'success')
    } catch (error) {
        showMessage(`切换失败: ${error.response?.data?.detail || error.message}`, 'error')
    } finally {
        loading.value = false
    }
}

function determineCurrentStep(state) {
    const values = state.values || {}
    const interruptInfoVal = state.interrupt_info
    const isCompleted = state.is_completed
    if (isCompleted) return 4
    if (interruptInfoVal) {
        const actionRequired = interruptInfoVal.action_required
        if (actionRequired === 'select_topic') return 1
        if (actionRequired === 'review') return 2
    }
    if (values.image_urls && values.image_urls.length > 0) return 4
    if (values.article_content) return 2
    if (values.generated_topics && values.generated_topics.length > 0) return 1
    return 0
}

async function handleDeleteThread(targetThreadId) {
    if (!confirm('确定要删除这条历史记录吗？')) return
    try {
        await deleteThread(targetThreadId)
        if (targetThreadId === threadId.value) handleReset()
        await fetchThreadList()
        showMessage('删除成功', 'success')
    } catch (error) {
        showMessage(`删除失败: ${error.response?.data?.detail || error.message}`, 'error')
    }
}
</script>
