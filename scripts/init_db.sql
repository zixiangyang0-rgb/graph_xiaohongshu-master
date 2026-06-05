-- =============================================================================
-- 数据库初始化脚本 - PostgreSQL
-- =============================================================================
--
-- 这是干什么的？
--   简单说：LangGraph 需要用数据库来保存工作流的"进度条"。
--   比如你正在写文章，突然断网了，下次连上时还能从断掉的地方继续，不会从头开始。
--
-- 怎么用？
--   方法1：在终端里运行 psql，连接数据库后执行：\i scripts/init_db.sql
--   方法2：直接一行命令搞定：psql -U postgres -d graph_xiaohongshu -f scripts/init_db.sql
--
-- 会创建什么？
--   两张表：
--   - checkpoints（检查点表）：保存工作流在每个时间点的完整状态
--   - checkpoint_writes（写入记录表）：保存状态之间的变化记录
--
-- 常见问题场景：
--   Q: 断网了怎么办？
--   A: 不怕！根据 thread_id（会话ID）就能找到上次保存的状态，接着干。
--
--   Q: AI 停下来等我审核是怎么回事？
--   A: 工作流里有个 human_review_node 会暂停，等你点"同意"才会继续。
--
--   Q: 怎么查看历史工作流？
--   A: 通过 thread_id 就能查到所有历史记录。
--
-- =============================================================================

-- 这个脚本会创建两张表，表名和字段都是 LangGraph 规定好的，别乱改

-- checkpoints 表：存放每个"存档点"的主数据
CREATE TABLE IF NOT EXISTS checkpoints (
    -- thread_id: 这是你的"会话ID"，用来区分不同的对话/工作流
    -- 比如：'user_123_workflow_20260101' 或一串 UUID
    -- 注意：同一个用户可以同时开多个工作流，每个都有独立的 thread_id
    thread_id TEXT NOT NULL,

    -- checkpoint_ns: 命名空间，简单理解就是"分组"
    -- 一般用空字符串 ''，表示主工作流
    -- 如果有子工作流（比如选题子图），子图会有自己的命名空间
    checkpoint_ns TEXT NOT NULL DEFAULT '',

    -- type: 类型标识符，固定写 'checkpoint'
    type TEXT NOT NULL DEFAULT 'checkpoint',

    -- checkpoint_id: 这个存档点的"身份证号"，本质是个时间戳字符串
    -- 每次状态变化都会生成一个新的 ID，类似 '1ef0c-0b3e6-4d89a'
    checkpoint_id TEXT NOT NULL,

    -- serialized_checkpoint: 存档点的完整数据，存成 JSON 文本
    -- 里面包含：用户选了哪些选题、文章内容、图片链接等所有信息
    serialized_checkpoint TEXT NOT NULL,

    -- created_at: 存档时间，帮你排序和清理过期数据
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 主键：thread_id + checkpoint_ns + checkpoint_id 三者组合唯一
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- checkpoint_writes 表：记录每次状态更新的"增量变化"
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    -- thread_id: 属于哪个会话
    thread_id TEXT NOT NULL,

    -- checkpoint_ns: 属于哪个命名空间
    checkpoint_ns TEXT NOT NULL DEFAULT '',

    -- checkpoint_id: 这次写入属于哪个存档点
    checkpoint_id TEXT NOT NULL,

    -- type: 操作类型，固定写 'write'
    type TEXT NOT NULL DEFAULT 'write',

    -- idx: 序号，因为一次可能有多条写入，按顺序排
    -- 从 0 开始：0, 1, 2, 3...
    idx BIGINT NOT NULL,

    -- channel: 要写入的"变量名"，比如 'topic_selection' 表示选题
    channel TEXT NOT NULL,

    -- val: 具体写入的值，JSON 格式
    -- 比如用户选中的选题内容，或者 AI 生成的文章段落
    val TEXT NOT NULL,

    -- created_at: 写入时间
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 主键：防止重复写入
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, type, idx, channel)
);

-- 索引：加速查询，就像书的目录一样

-- 场景：查某个会话的所有存档点（按时间排序）
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON checkpoints(thread_id);

-- 场景：找到某个会话的最新存档点（恢复状态用）
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON checkpoints(created_at DESC);

-- 场景：查某个存档点的所有写入记录（完整恢复状态）
CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_checkpoint ON checkpoint_writes(thread_id, checkpoint_ns, checkpoint_id);
