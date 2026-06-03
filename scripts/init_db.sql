-- =============================================================================
-- 数据库初始化脚本 - PostgreSQL
-- =============================================================================
--
-- 职责说明：
--   创建 LangGraph Checkpointer 所必需的数据库表结构。
--   LangGraph 通过 PostgresSaver 将工作流状态（AgentState）持久化到数据库，
--   支持断点续传、多轮对话和故障恢复。
--
-- 使用方法：
--   1. 连接到 PostgreSQL：psql -U postgres -d graph_xiaohongshu
--   2. 执行脚本：\i scripts/init_db.sql
--   3. 或通过命令执行：psql -U postgres -d graph_xiaohongshu -f scripts/init_db.sql
--
-- 表结构说明：
--   LangGraph 将数据存储在两张表：
--   - checkpoints: 存储工作流在各个时间点的完整状态快照
--   - checkpoint_writes: 存储状态快照之间的增量写入（用于支持复杂的版本控制）
--
-- 典型场景：
--   - 用户发起工作流后断网，重连时通过 thread_id 恢复之前的状态
--   - AI 在 human_review_node 暂停，用户审批后继续执行
--   - 查看历史线程列表，加载已完成的工作流状态
-- =============================================================================

-- 创建 PostgresSaver 所需的两张表
-- 表名和结构由 LangGraph 内部硬编码，必须严格遵循以下格式

-- checkpoints 表：存储每个状态快照的主记录
CREATE TABLE IF NOT EXISTS checkpoints (
    -- thread_id: 线程/会话的唯一标识符
    -- 典型值示例：'user_123_workflow_20260101' 或 UUID 字符串
    -- 典型场景：一个用户可以同时运行多个独立的工作流，每个有独立的 thread_id
    thread_id TEXT NOT NULL,

    -- checkpoint_ns: 命名空间，用于支持子图（subgraph）隔离
    -- 典型值示例：''（空字符串表示根图），'topic_selection'（子图命名空间）
    -- 典型场景：当工作流包含子图时，主图和子图可以分别有自己的检查点
    checkpoint_ns TEXT NOT NULL DEFAULT '',

    -- type: 检查点的类型标识符
    -- 典型值：'checkpoint'
    -- 典型场景：LangGraph 内部使用，用于区分不同版本的检查点格式
    type TEXT NOT NULL DEFAULT 'checkpoint',

    -- checkpoint_id: 此次检查点的唯一时间戳 ID（通常是基于壁钟时间的字符串）
    -- 典型值示例：'1ef0c-0b3e6-4d89a'
    -- 典型场景：每个工作流状态变化都会产生新的 checkpoint_id，用于追踪历史
    checkpoint_id TEXT NOT NULL,

    -- serialized_checkpoint: 序列化后的状态快照（JSON 格式）
    -- 典型值示例：AgentState 的 JSON 表示，包含所有字段
    -- 典型场景：包含完整的 topics, selected_topic, article_content, image_urls 等
    serialized_checkpoint TEXT NOT NULL,

    -- created_at: 检查点创建时间
    -- 典型场景：用于排序、清理过期数据、显示历史记录时间
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 复合主键：确保每个 thread_id + checkpoint_ns + checkpoint_id 组合唯一
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- checkpoint_writes 表：存储检查点之间的增量写入
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    -- thread_id: 所属线程 ID
    -- 典型场景：关联到 checkpoints 表的 thread_id
    thread_id TEXT NOT NULL,

    -- checkpoint_ns: 所属命名空间
    -- 典型场景：与 checkpoints 表配合，支持子图隔离
    checkpoint_ns TEXT NOT NULL DEFAULT '',

    -- checkpoint_id: 关联的检查点 ID
    -- 典型值示例：与 checkpoints 表中的 checkpoint_id 对应
    -- 典型场景：标识这次写入属于哪个状态快照
    checkpoint_id TEXT NOT NULL,

    -- type: 写入操作的类型
    -- 典型值：'write'
    -- 典型场景：LangGraph 内部用于区分不同类型的写入操作
    type TEXT NOT NULL DEFAULT 'write',

    -- idx: 写入操作的序号（用于支持同一检查点的多次写入）
    -- 典型值：0, 1, 2... 整数
    -- 典型场景：当一个节点需要写入多个值时，按 idx 顺序处理
    idx BIGINT NOT NULL,

    -- channel: 要写入的 channel/变量名
    -- 典型值示例：'topic_selection'（选题节点），'article_content'（文章内容）
    -- 典型场景：标识写入的是 AgentState 中的哪个字段
    channel TEXT NOT NULL,

    -- val: 写入的值（序列化后的 JSON）
    -- 典型值示例：用户选中的选题文本，或 LLM 生成的段落
    -- 典型场景：每次状态更新都会生成一条新的写入记录
    val TEXT NOT NULL,

    -- created_at: 写入操作发生的时间
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 复合主键：确保写入记录不重复
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, type, idx, channel)
);

-- 为高频查询字段创建索引，显著提升查询性能

-- 查询特定线程的所有检查点（按时间排序）
-- 典型场景：列出某用户所有工作流历史，按创建时间倒序排列
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON checkpoints(thread_id);

-- 查询特定线程按时间排序的检查点（用于恢复最新状态）
-- 典型场景：加载某 thread_id 的最新检查点，恢复工作流状态
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON checkpoints(created_at DESC);

-- 查询某检查点的所有写入记录（用于恢复完整状态）
-- 典型场景：通过 checkpoint_id 找到所有相关的增量写入，重建状态快照
CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_checkpoint ON checkpoint_writes(thread_id, checkpoint_ns, checkpoint_id);
