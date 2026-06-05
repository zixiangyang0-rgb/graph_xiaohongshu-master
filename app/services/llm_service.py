"""
LLM 服务模块
=============================================================================
职责说明：
  封装所有大语言模型（LLM）调用，提供选题生成、文章写作、视觉提取等功能。

核心设计：
  1. 使用 LangChain 的 ChatOpenAI 封装火山引擎 Doubao API
  2. 支持结构化输出（Pydantic）和流式输出两种模式
  3. 集成 PII 脱敏回调，防止敏感信息泄露到 LangSmith
  4. 多模型策略：快速模型用于简单任务（选题），标准模型用于复杂任务（写作）

支持的模型：
  - doubao-seed-1-6-flash-250828：快速模型，适合选题、提取等轻量任务
  - doubao-seed-1-8-251228：标准模型，适合文章写作

Prompt 设计：
  - TOPIC_SYSTEM_PROMPT：生成小红书爆款标题的提示词
  - ARTICLE_SYSTEM_PROMPT：生成完整文章的提示词
  - VISUAL_SYSTEM_PROMPT：从文章中提取配图描述的提示词

典型场景：
  llm_service.plan_topics("Python 开发")
  -> 返回 TopicsResponse(topics=[TopicItem(title="..."), ...])

  llm_service.stream_write_draft_with_usage("Python 5步法")
  -> 返回 StreamResult(content="...", usage=LLMUsageInfo(...))
=============================================================================
"""
import os
import re
from typing import List, Tuple, Optional, Callable, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

# LangChain OpenAI 封装（火山引擎 Doubao 兼容 OpenAI API 格式）
from langchain_openai import ChatOpenAI

# LangChain 消息类型
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk

# Pydantic 数据验证
from pydantic import BaseModel, Field

load_dotenv()


# =============================================================================
# 第 0 步：获取 PII 脱敏回调（延迟导入避免循环依赖）
# =============================================================================

def _get_pii_callback():
    """
    延迟获取 PII 脱敏回调

    ==========================================================================
    为什么延迟导入？
      app.core.callbacks 依赖 app.services（如果形成循环依赖会报错）
      这里在运行时获取，避免启动时的循环依赖

    返回值：
      PIIAnonymizingCallback 实例（如果导入失败则返回 None）
    """
    try:
        from app.core.callbacks import pii_callback
        return pii_callback
    except ImportError:
        return None


# =============================================================================
# 第 1 步：定义数据结构
# =============================================================================

class TopicItem(BaseModel):
    """
    单个选题项（结构化输出）

    ==========================================================================
    字段详解：
      - title：选题标题，15 字以内，爆款风格
        典型值："Python 入门 5 步法🔥"

    用途：
      TopicsResponse.topics 是 TopicItem 列表
      对应 AI 生成的 5 个候选选题
    """
    title: str = Field(..., description="选题标题")


class TopicsResponse(BaseModel):
    """
    选题响应结构（结构化输出）

    ==========================================================================
    字段详解：
      - topics：选题列表，通常包含 5 个 TopicItem

    用途：
      plan_topics() 方法返回这个类型
      保证 AI 输出格式正确，方便后续解析
    """
    topics: List[TopicItem] = Field(..., description="生成的选题列表")


@dataclass
class LLMUsageInfo:
    """
    LLM 调用的 token 使用信息

    ==========================================================================
    字段详解：
      - input_tokens：发送给 AI 的 token 数（Prompt 长度）
      - output_tokens：AI 返回的 token 数（Completion 长度）
      - total_tokens：总 token 数
      - model：使用的模型名称

    用途：
      用于计费和性能监控
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


@dataclass
class StreamResult:
    """
    流式输出结果

    ==========================================================================
    字段详解：
      - content：完整的文本内容（所有 chunk 拼接）
      - usage：token 使用统计

    用途：
      stream_write_draft_with_usage() 返回这个类型
      同时包含完整文本和 token 统计
    """
    content: str = ""
    usage: LLMUsageInfo = field(default_factory=LLMUsageInfo)


# =============================================================================
# 第 2 步：LLM 服务主类
# =============================================================================

class LLMService:
    """
    LLM 服务类 - 使用火山引擎 Doubao API

    ==========================================================================
    核心方法：
      1. plan_topics(topic_direction)：生成选题（结构化输出）
      2. stream_write_draft_with_usage(topic, feedback, revision_count)：生成文章（流式）
      3. extract_visual_points(article_content)：提取配图要点

    模型策略：
      - llm_fast：快速模型（doubao-seed-1-6-flash），用于选题、提取
      - llm：标准模型（doubao-seed-1-8），用于写作
      - llm_extract：低温度（0.4），用于确定性提取任务

    Prompt 设计理念：
      - 选题：用小红书爆款标题公式（数字+痛点、悬念反转等）
      - 文章：开头抓人、干货满满、语言活泼、结构清晰
      - 配图：纯视觉描述，禁止文字内容
    """

    # ---------- Prompt 模板 ----------

    TOPIC_SYSTEM_PROMPT = """你是小红书10w+爆款标题专家，精通平台流量密码。

根据主题方向生成5个超有吸引力的爆款选题标题。

【爆款标题公式】
1. 数字+痛点："3个方法让我..." "5分钟搞定..."
2. 悬念反转："原来xx这么简单" "后悔没早知道"
3. 情绪共鸣："救命！" "绝了！" "真的会谢"
4. 身份代入："打工人必看" "新手小白"
5. 对比冲击："花了3000学的vs我自己琢磨的"

【标题要求】
- 15字以内，一眼抓住注意力
- 口语化、接地气，像朋友聊天
- 用感叹号、问号增加情绪张力
- 可用 emoji 点缀（如🔥💡✨）"""

    ARTICLE_SYSTEM_PROMPT = """你是小红书爆款文章创作者。

文章要求：
- 开头抓人：用故事/问题/数据引入
- 干货满满：提供可操作的价值
- 语言活泼：口语化，适当用emoji
- 结构清晰：分段合理，善用小标题
- 800-1200字
- 结尾互动：提问引导评论

直接输出Markdown格式文章。"""

    VISUAL_SYSTEM_PROMPT = """为AI图片生成工具提取3个配图描述。

格式要求：
- 纯视觉描述，含场景、色彩、风格
- 第一个为封面图，需吸引眼球
- 每行一个，不编号

风格：插画/扁平化/简约现代/温馨治愈
禁止：文字内容、敏感政治暴力内容"""

    # ---------- 初始化 ----------

    def __init__(self, enable_pii_anonymize: bool = True):
        """
        初始化 LLM 服务

        参数详解：
          - enable_pii_anonymize：是否开启 PII 脱敏
            True：LLM 的输入输出都会经过脱敏
            防止敏感信息泄露到 LangSmith 等追踪系统

        环境变量配置：
          LLM_API_KEY：火山引擎 API Key
          LLM_BASE_URL：API 端点，默认火山引擎北京区域
          LLM_MODEL：标准模型
          LLM_MODEL_FAST：快速模型
          LLM_TEMPERATURE：标准模型温度（0.7 = 有创意但不随机）
          LLM_TEMPERATURE_EXTRACT：提取任务温度（0.4 = 更确定性）
        """
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

        # 模型配置
        self.model = os.getenv("LLM_MODEL", "doubao-seed-1-8-251228")
        self.model_fast = os.getenv("LLM_MODEL_FAST", "doubao-seed-1-6-flash-250828")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.temperature_fast = float(os.getenv("LLM_TEMPERATURE_FAST", "0.7"))
        self.temperature_extract = float(os.getenv("LLM_TEMPERATURE_EXTRACT", "0.4"))

        self.enable_pii_anonymize = enable_pii_anonymize

        # LLM 实例延迟初始化（用属性时才创建）
        self._llm = None
        self._llm_fast = None
        self._llm_extract = None

        print(f"[LLM] 模型配置: 标准={self.model}, 快速={self.model_fast}")

    # ---------- 内部工具方法 ----------

    def _get_callbacks(self) -> List:
        """
        获取 LangChain 回调列表

        工作原理：
          如果开启了 PII 脱敏，返回 PII 脱敏回调
          这个回调会在 LLM 输入/输出时自动脱敏
        """
        if self.enable_pii_anonymize:
            pii_callback = _get_pii_callback()
            if pii_callback:
                return [pii_callback]
        return []

    def _create_llm(self, model: str, temperature: float) -> ChatOpenAI:
        """
        创建 LLM 客户端实例

        参数详解：
          - model：模型名称，如 "doubao-seed-1-6-flash-250828"
          - temperature：温度参数
            0 = 完全确定，每次输出相同
            0.7 = 有创意但稳定，适合大多数任务
            1.0 = 完全随机，可能产生奇怪输出

        为什么用工厂方法？
          模型配置（API Key、URL、温度）可能在运行时变化
          工厂方法确保每次都创建正确配置的实例
        """
        callbacks = self._get_callbacks()
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=self.api_key,
            base_url=self.base_url,
            callbacks=callbacks if callbacks else None,
        )

    # ---------- LLM 实例（延迟初始化）----------

    @property
    def llm(self) -> ChatOpenAI:
        """
        标准 LLM（用于文章写作）
        """
        if self._llm is None:
            self._llm = self._create_llm(self.model, self.temperature)
        return self._llm

    @property
    def llm_fast(self) -> ChatOpenAI:
        """
        快速 LLM（用于选题、简单任务）
        """
        if self._llm_fast is None:
            self._llm_fast = self._create_llm(self.model_fast, self.temperature_fast)
        return self._llm_fast

    @property
    def llm_extract(self) -> ChatOpenAI:
        """
        提取专用 LLM（低温度，更确定性）
        """
        if self._llm_extract is None:
            self._llm_extract = self._create_llm(self.model_fast, self.temperature_extract)
        return self._llm_extract

    # ---------- 内部方法 ----------

    def _extract_usage_info(self, response, model: str = "") -> LLMUsageInfo:
        """
        从 LLM 响应中提取 token 使用信息

        工作原理：
          不同 API 返回 usage 信息的方式不同
          这个方法尝试多种常见格式，兼容不同版本

        参数详解：
          - response：LLM 响应对象
          - model：模型名称（从响应中可能拿不到，需要传入）

        token 统计用途：
          - 计费：LLM API 按 token 计费
          - 监控：追踪 token 消耗趋势
          - 优化：识别高消耗场景
        """
        usage = LLMUsageInfo(model=model or self.model)

        # 尝试从 response_metadata 获取（某些版本）
        if hasattr(response, 'response_metadata'):
            token_usage = response.response_metadata.get('token_usage', {})
            usage.input_tokens = token_usage.get('prompt_tokens', 0)
            usage.output_tokens = token_usage.get('completion_tokens', 0)
            usage.total_tokens = token_usage.get('total_tokens', 0)

        # 尝试从 usage_metadata 获取（推荐格式）
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage.input_tokens = response.usage_metadata.get('input_tokens', usage.input_tokens)
            usage.output_tokens = response.usage_metadata.get('output_tokens', usage.output_tokens)
            usage.total_tokens = response.usage_metadata.get('total_tokens', usage.total_tokens)

        return usage

    def _update_usage_from_chunk(self, chunk: AIMessageChunk, usage: LLMUsageInfo) -> None:
        """
        从流式 chunk 更新 token 统计

        为什么需要这个？
          流式响应中，只有最后一个 chunk 包含完整的 usage 信息
          这个方法在每个 chunk 到达时更新统计，最后一个 chunk 覆盖前面的值
        """
        # 尝试从 usage_metadata 获取
        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
            usage.input_tokens = chunk.usage_metadata.get('input_tokens', usage.input_tokens)
            usage.output_tokens = chunk.usage_metadata.get('output_tokens', usage.output_tokens)
            usage.total_tokens = chunk.usage_metadata.get('total_tokens', usage.total_tokens)

        # 尝试从 response_metadata 获取
        if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
            token_usage = chunk.response_metadata.get('token_usage', {})
            if token_usage:
                usage.input_tokens = token_usage.get('prompt_tokens', usage.input_tokens)
                usage.output_tokens = token_usage.get('completion_tokens', usage.output_tokens)
                usage.total_tokens = token_usage.get('total_tokens', usage.total_tokens)

    # ---------- 核心方法 ----------

    async def plan_topics(self, topic_direction: str) -> Tuple[TopicsResponse, LLMUsageInfo]:
        """
        根据主题方向生成候选选题（结构化输出）

        ==========================================================================
        工作流程：
          1. 构建消息列表（SystemMessage + HumanMessage）
          2. 使用 with_structured_output() 启用结构化输出
          3. 调用 LLM，返回 Pydantic 模型
          4. 提取 token 使用信息
          5. 如果结构化输出失败，fallback 到手动解析 JSON

        为什么用结构化输出？
          传统方式：LLM 输出纯文本 -> 手动正则解析 JSON
          结构化输出：LLM 直接输出正确格式的 JSON -> 自动映射到 Pydantic 模型
          更稳定，不需要解析容错

        参数详解：
          - topic_direction：用户输入的主题方向
            典型值："Python 开发"、"AI 技术趋势"

        返回值：
          - TopicsResponse：选题列表（包含 5 个 TopicItem）
          - LLMUsageInfo：token 使用统计

        典型场景：
          topics_response, usage = await llm_service.plan_topics("Python 开发")
          topics = [item.title for item in topics_response.topics]
          # ["Python 入门 5 步法🔥", "10 个 Python 技巧...", ...]
        """
        messages = [
            SystemMessage(content=self.TOPIC_SYSTEM_PROMPT),
            HumanMessage(content=f"主题：{topic_direction or '技术分享'}")
        ]

        usage = LLMUsageInfo(model=self.model_fast)

        try:
            # 使用结构化输出方法
            # with_structured_output() 让 LLM 直接输出正确格式的 JSON
            structured_llm = self.llm_fast.with_structured_output(TopicsResponse, include_raw=True)
            result = await structured_llm.ainvoke(messages)

            raw_response = result.get('raw')
            parsed_response = result.get('parsed')

            # 从原始响应中提取 usage 信息
            if raw_response:
                usage = self._extract_usage_info(raw_response, self.model_fast)

        except Exception as e:
            # 结构化输出失败，fallback 到手动解析
            print(f"[LLM] 结构化输出失败，使用备用方案: {e}")
            return await self._plan_topics_fallback(topic_direction)

        return parsed_response or TopicsResponse(topics=[]), usage

    async def _plan_topics_fallback(self, topic_direction: str) -> Tuple[TopicsResponse, LLMUsageInfo]:
        """
        备用方案：手动解析 JSON

        工作流程：
          1. 提示词末尾加上 JSON 格式要求
          2. 普通调用 LLM
          3. 从响应中提取 JSON（去掉 markdown 代码块）
          4. json.loads() 解析
          5. 返回 TopicsResponse
        """
        import json

        # 修改提示词，要求 JSON 格式输出
        system_prompt = self.TOPIC_SYSTEM_PROMPT + '\n\nJSON格式输出：{"topics":[{"title":"标题1"},...,{"title":"标题5"}]}'

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"主题：{topic_direction or '技术分享'}")
        ]

        response = await self.llm_fast.ainvoke(messages)
        usage = self._extract_usage_info(response, self.model_fast)

        try:
            content = response.content.strip()

            # 去掉 markdown 代码块
            if "```" in content:
                content = re.sub(r'^.*?```(?:json)?\s*', '', content, flags=re.DOTALL)
                content = re.sub(r'\s*```.*$', '', content, flags=re.DOTALL)

            # 提取 JSON 对象
            json_start = content.find('{')
            json_end = content.rfind('}')
            if json_start != -1 and json_end != -1:
                content = content[json_start:json_end + 1]

            data = json.loads(content)
            return TopicsResponse(**data), usage
        except Exception as e:
            print(f"[LLM] JSON 解析失败: {e}")
            return TopicsResponse(topics=[]), usage

    async def write_draft(
        self,
        topic: str,
        feedback: str = "",
        revision_count: int = 0
    ) -> Tuple[str, LLMUsageInfo]:
        """
        生成文章草稿（非流式）

        工作原理：
          和 plan_topics 类似，但不是结构化输出
          直接返回完整文本
        """
        user_prompt = self._build_article_prompt(topic, feedback, revision_count)

        messages = [
            SystemMessage(content=self.ARTICLE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]

        response = await self.llm.ainvoke(messages)
        usage = self._extract_usage_info(response)

        return response.content, usage

    async def stream_write_draft_with_usage(
        self,
        topic: str,
        feedback: str = "",
        revision_count: int = 0,
        on_chunk: Optional[Callable[[str], Any]] = None
    ) -> StreamResult:
        """
        流式生成文章草稿（带 token 统计）

        ==========================================================================
        工作流程：
          1. 构建提示词
          2. 使用 astream() 流式调用 LLM
          3. 每个 chunk 累积到 full_content
          4. 如果提供了 on_chunk 回调，实时通知（用于前端显示）
          5. 从最后一个 chunk 提取 token 使用信息
          6. 返回完整文本和统计

        为什么需要流式？
          非流式：等 AI 生成完整个文章，再返回（约 10-30 秒）
          流式：AI 生成一部分就返回一部分（逐字显示给用户）
          用户体验好：看到"正在打字"而不是"加载中"

        参数详解：
          - topic：选题标题
          - feedback：修改意见（驳回重写时传入）
          - revision_count：修订次数
          - on_chunk：每个 chunk 到达时的回调函数

        返回值：
          StreamResult：包含完整文本 content 和 token 统计 usage

        典型场景：
          result = await llm_service.stream_write_draft_with_usage(
              topic="Python 5步法",
              feedback="太长了",
              revision_count=1
          )
          print(result.content)  # 完整文章
          print(result.usage.total_tokens)  # 1650
        """
        user_prompt = self._build_article_prompt(topic, feedback, revision_count)

        messages = [
            SystemMessage(content=self.ARTICLE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]

        full_content = ""
        usage = LLMUsageInfo(model=self.model)

        # ---------- 流式调用 ----------
        async for chunk in self.llm.astream(messages):
            if isinstance(chunk, AIMessageChunk):
                # 累积文本
                if chunk.content:
                    full_content += chunk.content
                    # 如果有回调，实时通知
                    if on_chunk:
                        on_chunk(chunk.content)
                # 更新 token 统计（最后一个 chunk 有完整信息）
                self._update_usage_from_chunk(chunk, usage)

        # 估算 token（如果 API 没返回）
        if usage.total_tokens == 0:
            usage.input_tokens = len(self.ARTICLE_SYSTEM_PROMPT + user_prompt) // 2
            usage.output_tokens = len(full_content) // 2
            usage.total_tokens = usage.input_tokens + usage.output_tokens

        return StreamResult(content=full_content, usage=usage)

    async def extract_visual_points(self, article_content: str) -> Tuple[List[str], LLMUsageInfo]:
        """
        从文章中提取配图要点

        ==========================================================================
        工作流程：
          1. 截断文章（只取前 1500 字，避免 token 过多）
          2. 构建提示词（VISUAL_SYSTEM_PROMPT）
          3. 调用 LLM（低温度，更确定性）
          4. 解析响应（去掉编号）
          5. 返回最多 3 个要点

        解析逻辑：
          AI 输出可能带编号（1. xxx / 2. xxx）
          用正则去掉编号，只保留纯文字描述

        参数详解：
          - article_content：文章内容（Markdown 格式）
            会被截断到前 1500 字符

        返回值：
          - visual_points：配图描述列表（最多 3 条）
          - usage：token 使用统计

        典型场景：
          points, usage = await llm_service.extract_visual_points(article_text)
          # ["温暖的学习场景，程序员深夜编程", "简洁的代码编辑器界面", ...]
        """
        # 截断文章（避免 token 过多）
        truncated = article_content[:1500] if len(article_content) > 1500 else article_content

        messages = [
            SystemMessage(content=self.VISUAL_SYSTEM_PROMPT),
            HumanMessage(content=f"文章内容：\n{truncated}")
        ]

        response = await self.llm_extract.ainvoke(messages)
        usage = self._extract_usage_info(response, self.model_fast)

        # ---------- 解析响应 ----------
        points = []
        for line in response.content.strip().split('\n'):
            line = line.strip()
            # 去掉编号（1. / 2. / - / 等）
            if line and not line.startswith('-'):
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', line)
                if cleaned:
                    points.append(cleaned)

        # 只返回前 3 个
        return points[:3], usage

    def _build_article_prompt(self, topic: str, feedback: str, revision_count: int) -> str:
        """
        构建文章生成的用户提示

        工作原理：
          如果有修改意见，在提示词中加上修订次数和反馈
          帮助 AI 理解上下文，调整输出策略
        """
        if feedback and revision_count > 0:
            return f"选题：{topic}\n\n第{revision_count}次修订，修改意见：{feedback}\n\n请针对性修改。"
        return f"选题：{topic}"


# =============================================================================
# 单例实例
# =============================================================================

# 全局单例，整个项目复用同一个 LLM 实例
llm_service = LLMService()
