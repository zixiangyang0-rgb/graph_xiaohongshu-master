/**
 * API 客户端模块
 * =============================================================================
 * 职责说明：
 *   封装所有与后端 API 交互的逻辑，提供统一的上层接口。
 *
 * 核心功能：
 *   1. Axios 实例配置（拦截器、自动刷新 Token）
 *   2. 认证相关 API（登录、注册、登出）
 *   3. 工作流 API（非流式 + 流式）
 *   4. SSE 事件处理（流式获取 AI 生成内容）
 *
 * 为什么用 Axios？
 *   - 自动处理 JSON 序列化/反序列化
 *   - 支持请求/响应拦截器
 *   - 自动转换请求/响应数据
 *   - 更好的错误处理
 *
 * Token 管理：
 *   - 存储在 localStorage
 *   - 请求拦截器自动添加到 Authorization 头
 *   - 响应拦截器处理 401 自动登出
 *
 * 典型场景：
 *   import { login, startWorkflow } from './api.js'
 *   await login('alice', 'pass123')
 *   const result = await startWorkflow('Python 开发')
 */

// Axios：HTTP 客户端库，比 fetch 更方便
import axios from 'axios'

// =============================================================================
// 第 1 步：创建 Axios 实例
// =============================================================================

// 创建 Axios 实例（而不是直接用 axios.post）的原因：
// 1. 可以预设 baseURL，所有请求自动加上前缀
// 2. 可以预设 timeout，所有请求自动超时控制
// 3. 可以添加拦截器，所有请求/响应自动处理
const api = axios.create({
    // API 基础路径，后端 FastAPI 的路由前缀
    baseURL: '/api/v1',

    // 请求超时时间（毫秒）
    // 设为 2 分钟，因为 AI 生成内容可能需要较长时间
    timeout: 120000
})


// =============================================================================
// 第 2 步：Token 管理
// =============================================================================

// Token = JWT 令牌，登录成功后服务器返回
// 存储在 localStorage，页面刷新后仍然保留

/**
 * 从 localStorage 获取 Token
 * @returns {string|null} Token 字符串或 null
 */
export function getToken() {
    return localStorage.getItem('token')
}

/**
 * 保存 Token 到 localStorage
 * @param {string} token - JWT 令牌
 */
export function setToken(token) {
    localStorage.setItem('token', token)
}

/**
 * 从 localStorage 删除 Token
 * 通常在登出时调用
 */
export function removeToken() {
    localStorage.removeItem('token')
}

/**
 * 检查用户是否已登录
 * @returns {boolean} 已登录返回 true
 */
export function isLoggedIn() {
    return !!getToken()  // !! 把 null/undefined 转成 false，有值转成 true
}


// =============================================================================
// 第 3 步：请求拦截器
// =============================================================================

// 请求拦截器：在每个请求发出之前执行
// 用途：自动把 Token 添加到请求头
api.interceptors.request.use(
    config => {
        // 从 localStorage 读取 Token
        const token = getToken()
        if (token) {
            // 添加到 Authorization 头，格式：Bearer <token>
            // 这是 HTTP 标准认证方案
            config.headers.Authorization = `Bearer ${token}`
        }
        return config  // 返回 config 让请求继续发出
    },
    error => Promise.reject(error)  // 错误直接 reject
)


// =============================================================================
// 第 4 步：响应拦截器
// =============================================================================

// 响应拦截器：在每个响应到达之前执行
// 用途：处理 401 错误（Token 过期/无效），自动登出
api.interceptors.response.use(
    response => response,  // 正常响应直接返回
    error => {
        // 捕获 401 Unauthorized 错误
        if (error.response?.status === 401) {
            // 删除本地 Token
            removeToken()
            // 派发自定义事件通知前端组件需要跳转登录页
            // 为什么用自定义事件而不是直接跳转？
            // 因为认证逻辑可能在任何组件中触发，用事件可以让所有组件响应
            window.dispatchEvent(new CustomEvent('auth:logout'))
        }
        return Promise.reject(error)  // 错误继续传递，让调用方处理
    }
)


// =============================================================================
// 第 5 步：认证相关 API
// =============================================================================

/**
 * 用户注册
 * @param {string} username - 用户名（3-50 字符）
 * @param {string} password - 密码（6-100 字符）
 * @returns {Promise} 返回成功消息
 *
 * 典型场景：
 *   await register('alice', 'pass123')
 *   // 成功：{ message: "注册成功" }
 */
export async function register(username, password) {
    const res = await api.post('/auth/register', { username, password })
    return res.data
}

/**
 * 用户登录
 * @param {string} username - 用户名
 * @param {string} password - 密码
 * @returns {Promise} 返回 Token
 *
 * 工作流程：
 *   1. POST /auth/login
 *   2. 服务器验证用户名+密码
 *   3. 服务器返回 JWT Token
 *   4. 客户端保存 Token 到 localStorage
 *
 * 典型场景：
 *   const data = await login('alice', 'pass123')
 *   // data.access_token = "eyJ..."
 *   // Token 已自动保存到 localStorage
 */
export async function login(username, password) {
    const res = await api.post('/auth/login', { username, password })
    if (res.data.access_token) {
        // 登录成功后保存 Token
        setToken(res.data.access_token)
    }
    return res.data
}

/**
 * 获取当前登录用户信息
 * @returns {Promise} 返回用户信息
 *
 * 典型场景：
 *   const user = await getCurrentUser()
 *   // user = { id: "uuid", username: "alice" }
 */
export async function getCurrentUser() {
    const res = await api.get('/auth/me')
    return res.data
}

/**
 * 登出
 * 只删除本地 Token，不调用后端（后端无登出接口）
 *
 * 典型场景：
 *   logout()  // 删除 Token
 *   // 前端组件监听 auth:logout 事件，跳转登录页
 */
export function logout() {
    removeToken()
}


// =============================================================================
// 第 6 步：工作流 API（非流式）
// =============================================================================

/**
 * 启动工作流
 * @param {string} topicDirection - 用户输入的主题方向
 * @returns {Promise} 返回生成的选题列表和 thread_id
 *
 * 典型场景：
 *   const result = await startWorkflow('Python 开发')
 *   // result = {
 *   //   thread_id: "uuid_xxx",
 *   //   generated_topics: ["Python 5步法", ...],
 *   //   status: "topics_generated"
 *   // }
 */
export async function startWorkflow(topicDirection) {
    const res = await api.post('/workflow/start', {
        topic_direction: topicDirection
    })
    return res.data
}

/**
 * 获取工作流当前状态
 * @param {string} threadId - 工作流线程 ID
 * @returns {Promise} 返回完整状态快照
 *
 * 典型场景：
 *   - 页面刷新后恢复状态
 *   - 查看当前工作流的详细数据
 */
export async function getWorkflowState(threadId) {
    const res = await api.get(`/workflow/state/${threadId}`)
    return res.data
}

/**
 * 恢复工作流 - 选择选题
 * @param {string} threadId - 工作流线程 ID
 * @param {string} selectedTopic - 选中的选题标题
 * @returns {Promise} 返回操作结果
 *
 * 典型场景：
 *   await selectTopic(threadId, "Python 5步法")
 *   // 触发文章生成，返回草稿状态
 */
export async function selectTopic(threadId, selectedTopic) {
    const res = await api.post(`/workflow/resume/${threadId}`, {
        action: 'select_topic',
        data: { selected_topic: selectedTopic }
    })
    return res.data
}

/**
 * 恢复工作流 - 审核通过
 * @param {string} threadId - 工作流线程 ID
 * @returns {Promise} 返回操作结果
 *
 * 典型场景：
 *   await approveArticle(threadId)
 *   // 触发配图生成，返回最终结果
 */
export async function approveArticle(threadId) {
    const res = await api.post(`/workflow/resume/${threadId}`, {
        action: 'approve'
    })
    return res.data
}

/**
 * 恢复工作流 - 审核驳回
 * @param {string} threadId - 工作流线程 ID
 * @param {string} feedback - 修改意见
 * @returns {Promise} 返回操作结果
 *
 * 典型场景：
 *   await rejectArticle(threadId, "文章太长了，缩短到 600 字")
 *   // 触发文章重写，返回新草稿
 */
export async function rejectArticle(threadId, feedback) {
    const res = await api.post(`/workflow/resume/${threadId}`, {
        action: 'reject',
        data: { feedback }
    })
    return res.data
}

/**
 * 获取工作流历史记录
 * @param {string} threadId - 工作流线程 ID
 * @returns {Promise} 返回历史状态列表
 *
 * 典型场景：
 *   - 调试时查看每个节点的输入输出
 *   - 审计工作流的每个决策点
 */
export async function getWorkflowHistory(threadId) {
    const res = await api.get(`/workflow/history/${threadId}`)
    return res.data
}

/**
 * 获取用户所有工作流列表
 * @returns {Promise} 返回线程列表
 *
 * 典型场景：
 *   - 侧边栏显示历史记录
 *   - 用户可以切换不同的工作流
 */
export async function getAllThreads() {
    const res = await api.get('/workflow/threads')
    return res.data
}

/**
 * 删除工作流
 * @param {string} threadId - 工作流线程 ID
 * @returns {Promise} 返回删除结果
 *
 * 典型场景：
 *   - 用户点击删除按钮
 *   - 从数据库删除工作流状态
 */
export async function deleteThread(threadId) {
    const res = await api.delete(`/workflow/threads/${threadId}`)
    return res.data
}


// =============================================================================
// 第 7 步：流式 API（基于 SSE）
// =============================================================================

// 流式 API 说明：
// - 使用 Server-Sent Events（SSE）技术
// - 服务器推送事件，客户端通过 EventSource 接收
// - 适合：AI 生成内容逐字显示（打字机效果）
// - 不适合：需要双向通信的场景（用 WebSocket）

/**
 * 流式启动工作流 - 包装成回调形式
 *
 * 工作原理：
 *   1. 调用普通 API（POST /workflow/start）
 *   2. 模拟流式事件回调（实际不是真正的 SSE）
 *   3. 按顺序触发回调：onInit -> onNodeEnd -> onUpdate -> onDone
 *
 * 为什么不是真正的 SSE？
 *   选题阶段使用结构化输出（非流式），不需要实时 token
 *   所以用回调包装普通 API 更简单
 *
 * @param {string} topicDirection - 主题方向
 * @param {Object} callbacks - 回调函数对象
 */
export async function streamStartWorkflow(topicDirection, callbacks, streamMode = 'updates') {
    try {
        // 触发初始化回调
        callbacks.onInit?.({ thread_id: 'loading...' })
        callbacks.onStart?.({ stream_mode: streamMode })

        // 调用普通 API
        const res = await api.post('/workflow/start', {
            topic_direction: topicDirection
        })
        const data = res.data

        // 模拟事件回调
        callbacks.onInit?.({ thread_id: data.thread_id })
        callbacks.onNodeEnd?.({
            node: 'plan_topics',
            metrics: data.node_metrics?.[0] || null
        })
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

/**
 * 流式审核通过 - 包装成回调形式
 * @param {string} threadId - 线程 ID
 * @param {Object} callbacks - 回调函数对象
 */
export async function streamApproveArticle(threadId, callbacks, streamMode = 'updates') {
    try {
        callbacks.onResume?.({ thread_id: threadId, action: 'approve' })
        callbacks.onStart?.({ stream_mode: streamMode })

        // 调用普通 API
        const res = await api.post(`/workflow/resume/${threadId}`, {
            action: 'approve'
        })
        const data = res.data

        // 模拟事件回调
        if (data.result?.visual_points) {
            callbacks.onUpdate?.('extract_visuals', {
                visual_points: data.result.visual_points,
                node_metrics: data.node_metrics
            })
        }
        if (data.result?.image_urls) {
            callbacks.onUpdate?.('generate_images', {
                image_urls: data.result.image_urls,
                node_metrics: data.node_metrics
            })
        }
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
 * SSE 事件处理器 - 处理真正的流式响应
 *
 * 工作原理：
 *   1. 使用 fetch + ReadableStream 读取 SSE 响应
 *   2. 解析 data: 行，提取 JSON 事件
 *   3. 根据事件 type 调用对应的回调
 *
 * 为什么用 fetch 而不是 EventSource？
 *   EventSource 不支持 POST 请求，只能接收服务器推送
 *   流式恢复需要发送数据（action、selected_topic 等）
 *
 * @param {Response} response - fetch 响应对象
 * @param {Object} callbacks - 回调函数对象
 */
async function handleSSEStream(response, callbacks) {
    // 检查 HTTP 状态码
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
    }

    // 获取响应体读取器
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''  // 缓冲区，存储不完整的行

    // 循环读取直到流结束
    while (true) {
        const { done, value } = await reader.read()
        if (done) break  // 流结束，退出循环

        // 解码二进制数据为字符串
        buffer += decoder.decode(value, { stream: true })

        // 按换行分割，lines 的最后一项是不完整的行（留在缓冲区）
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''  // 弹出最后一项，重新赋值缓冲区

        // 处理每一行
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                // 解析 SSE 数据行
                try {
                    // 去掉 "data: " 前缀，解析 JSON
                    const event = JSON.parse(line.slice(6))
                    const { type, data } = event

                    // 根据事件类型调用对应回调
                    switch (type) {
                        case 'start':
                            callbacks.onStart?.(data)
                            break
                        case 'resume':
                            callbacks.onResume?.(data)
                            break
                        case 'llm_start':
                            callbacks.onLlmStart?.(data)
                            break
                        case 'llm_token':
                            // 关键事件：AI 输出的每个 token（内容逐字显示）
                            callbacks.onLlmToken?.(data.content)
                            break
                        case 'llm_end':
                            callbacks.onLlmEnd?.(data)
                            break
                        case 'done':
                            callbacks.onDone?.(data)
                            break
                        case 'error':
                            callbacks.onError?.(data.message)
                            break
                    }
                } catch (e) {
                    console.error('解析SSE数据失败:', e, line)
                }
            }
        }
    }
}

/**
 * 流式选择选题 - SSE 方式
 * @param {string} threadId - 线程 ID
 * @param {string} selectedTopic - 选中的选题
 * @param {Object} callbacks - 回调函数对象
 * @returns {Promise} Promise（完成时 resolve）
 *
 * 典型场景：
 *   streamSelectTopic(threadId, "Python 5步法", {
 *       onLlmToken: (content) => articleText += content,  // 逐字追加
 *       onDone: (data) => console.log('完成')
 *   })
 */
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

/**
 * 流式驳回重写 - SSE 方式
 * @param {string} threadId - 线程 ID
 * @param {string} feedback - 修改意见
 * @param {Object} callbacks - 回调函数对象
 * @returns {Promise} Promise（完成时 resolve）
 */
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
