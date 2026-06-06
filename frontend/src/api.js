/**
 * 前端和后端通信都从这里走。
 *
 * 这个文件主要做三件事：
 *   1. 配好 axios
 *   2. 统一管理 token
 *   3. 把工作流相关请求封成好调用的方法
 */

import axios from 'axios'

// 前端请求后端都从这里走
const api = axios.create({
    baseURL: '/api/v1',        // 所有请求自动加上这个前缀
    timeout: 120000            // 超时 2 分钟（AI 生成内容可能较慢）
})

// 这几个函数就是登录态在浏览器里的最小封装
export function getToken() { return localStorage.getItem('token') }
export function setToken(token) { localStorage.setItem('token', token) }
export function removeToken() { localStorage.removeItem('token') }
export function isLoggedIn() { return !!getToken() }

// 每次请求如果有 token，就自动带上
api.interceptors.request.use(config => {
    const token = getToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
}, error => Promise.reject(error))

// 如果后端回了 401，就说明登录态已经失效
api.interceptors.response.use(
    response => response,
    error => {
        if (error.response?.status === 401) {
            removeToken()
            window.dispatchEvent(new CustomEvent('auth:logout'))
        }
        return Promise.reject(error)
    }
)

// =============================================================================
// 认证相关 API
// =============================================================================

/** 用户注册 */
export async function register(username, password) {
    const res = await api.post('/auth/register', { username, password })
    return res.data
}

/** 用户登录 */
export async function login(username, password) {
    const res = await api.post('/auth/login', { username, password })
    if (res.data.access_token) setToken(res.data.access_token)
    return res.data
}

/** 获取当前用户信息 */
export async function getCurrentUser() {
    const res = await api.get('/auth/me')
    return res.data
}

/** 登出（只删本地 Token） */
export function logout() { removeToken() }

// =============================================================================
// 工作流 API（非流式）
// =============================================================================

/** 启动工作流 */
export async function startWorkflow(topicDirection) {
    const res = await api.post('/workflow/start', { topic_direction: topicDirection })
    return res.data
}

/** 获取工作流状态 */
export async function getWorkflowState(threadId) {
    const res = await api.get(`/workflow/state/${threadId}`)
    return res.data
}

/** 恢复工作流 - 选择选题 */
export async function selectTopic(threadId, selectedTopic) {
    const res = await api.post(`/workflow/resume/${threadId}`, {
        action: 'select_topic', data: { selected_topic: selectedTopic }
    })
    return res.data
}

/** 恢复工作流 - 审核通过 */
export async function approveArticle(threadId) {
    const res = await api.post(`/workflow/resume/${threadId}`, { action: 'approve' })
    return res.data
}

/** 恢复工作流 - 审核驳回 */
export async function rejectArticle(threadId, feedback) {
    const res = await api.post(`/workflow/resume/${threadId}`, {
        action: 'reject', data: { feedback }
    })
    return res.data
}

/** 获取工作流历史记录 */
export async function getWorkflowHistory(threadId) {
    const res = await api.get(`/workflow/history/${threadId}`)
    return res.data
}

/** 获取用户所有工作流列表 */
export async function getAllThreads() {
    const res = await api.get('/workflow/threads')
    return res.data
}

/** 删除工作流 */
export async function deleteThread(threadId) {
    const res = await api.delete(`/workflow/threads/${threadId}`)
    return res.data
}

// 流式 API（SSE）

/** 选题阶段不走真正的 SSE，这里用普通接口加回调包装。 */
export async function streamStartWorkflow(topicDirection, callbacks, streamMode = 'updates') {
    try {
        callbacks.onInit?.({ thread_id: 'loading...' })
        callbacks.onStart?.({ stream_mode: streamMode })

        const res = await api.post('/workflow/start', { topic_direction: topicDirection })
        const data = res.data

        callbacks.onInit?.({ thread_id: data.thread_id })
        callbacks.onNodeEnd?.({ node: 'plan_topics', metrics: data.node_metrics?.[0] || null })
        callbacks.onUpdate?.('topic_selection', {
            generated_topics: data.generated_topics,
            node_metrics: data.node_metrics
        })
        callbacks.onDone?.({
            status: data.status,
            interrupt_info: data.interrupt_info,
            values: {
                generated_topics: data.generated_topics,
                node_metrics: data.node_metrics
            }
        })
    } catch (error) {
        callbacks.onError?.(error.response?.data?.detail || error.message)
    }
}

/** 审核通过（包装成回调形式）。 */
export async function streamApproveArticle(threadId, callbacks, streamMode = 'updates') {
    try {
        callbacks.onResume?.({ thread_id: threadId, action: 'approve' })
        callbacks.onStart?.({ stream_mode: streamMode })

        const res = await api.post(`/workflow/resume/${threadId}`, { action: 'approve' })
        const data = res.data

        if (data.result?.visual_points) callbacks.onUpdate?.('extract_visuals', {
            visual_points: data.result.visual_points, node_metrics: data.node_metrics
        })
        if (data.result?.image_urls) callbacks.onUpdate?.('generate_images', {
            image_urls: data.result.image_urls, node_metrics: data.node_metrics
        })
        callbacks.onDone?.({
            status: data.status,
            is_completed: data.is_completed,
            interrupt_info: data.interrupt_info,
            values: {
                article_content: data.result?.article_content || '',
                visual_points: data.result?.visual_points || [],
                image_urls: data.result?.image_urls || [],
                node_metrics: data.node_metrics
            }
        })
    } catch (error) {
        callbacks.onError?.(error.response?.data?.detail || error.message)
    }
}

/**
 * SSE 事件处理器
 * 用 fetch + ReadableStream 读取 SSE 响应，按行解析 data: 前缀，再根据 type 分发到对应回调。
 * 用 fetch 而不是 EventSource 是因为 SSE 恢复需要 POST 请求带 action 参数。
 */
async function handleSSEStream(response, callbacks) {
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const event = JSON.parse(line.slice(6))
                    const { type, data } = event

                    switch (type) {
                        case 'start': callbacks.onStart?.(data); break
                        case 'resume': callbacks.onResume?.(data); break
                        case 'llm_start': callbacks.onLlmStart?.(data); break
                        case 'llm_token': callbacks.onLlmToken?.(data.content); break
                        case 'llm_end': callbacks.onLlmEnd?.(data); break
                        case 'done': callbacks.onDone?.(data); break
                        case 'error': callbacks.onError?.(data.message); break
                    }
                } catch (e) {
                    console.error('解析SSE数据失败:', e, line)
                }
            }
        }
    }
}

/** 流式选择选题（SSE） */
export function streamSelectTopic(threadId, selectedTopic, callbacks) {
    const token = getToken()
    return fetch(`/api/v1/workflow/stream/resume/${threadId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
            action: 'select_topic',
            data: { selected_topic: selectedTopic }
        })
    }).then(response => handleSSEStream(response, callbacks))
}

/** 流式驳回重写（SSE） */
export function streamRejectArticle(threadId, feedback, callbacks) {
    const token = getToken()
    return fetch(`/api/v1/workflow/stream/resume/${threadId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
            action: 'reject',
            data: { feedback: feedback || '' }
        })
    }).then(response => handleSSEStream(response, callbacks))
}
