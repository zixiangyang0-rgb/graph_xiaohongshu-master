"""
LLM 服务都收在这里。

选题、写作、视觉提取都会走这个服务；
区别主要在于 prompt 和用哪一个模型。
"""
import os
import re
from typing import List, Tuple, Optional, Callable, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk
from pydantic import BaseModel, Field, ValidationError

load_dotenv()


def _get_pii_callback():
    """
    延迟获取 PII 脱敏回调（避免循环依赖）

    为什么延迟导入？
      如果在文件顶部直接 import app.core.callbacks，可能会形成循环依赖。
      这里在运行时获取，完美解决。
    """
    try:
        from app.core.callbacks import pii_callback
        return pii_callback
    except ImportError:
        return None


# =============================================================================
# 数据结构定义
# =============================================================================

class TopicItem(BaseModel):
    """单个选题项"""
    title: str = Field(..., description="选题标题")


class TopicsResponse(BaseModel):
    """选题响应结构（结构化输出）"""
    topics: List[TopicItem] = Field(..., description="生成的选题列表")


@dataclass
class LLMUsageInfo:
    """记录一次 LLM 调用用了多少 token"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


@dataclass
class StreamResult:
    """流式输出结果"""
    content: str = ""
    usage: LLMUsageInfo = field(default_factory=LLMUsageInfo)


# =============================================================================
# LLM 服务主类
# =============================================================================

class LLMService:
    """
    LLM 服务类 - 和火山引擎 Doubao 模型对话

    Prompt 设计理念：
      - 选题：用小红书爆款标题公式（数字+痛点、悬念反转等）
      - 文章：开头抓人、干货满满、语言活泼、结构清晰
      - 配图：纯视觉描述，禁止文字内容
    """

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

    def __init__(self, enable_pii_anonymize: bool = True):
        """
        初始化 LLM 服务

        参数：
          - enable_pii_anonymize：是否开启 PII 脱敏
            True：LLM 的输入输出都会经过脱敏，防止敏感信息泄露
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

    def _get_callbacks(self) -> List:
        """获取 LangChain 回调列表（如果有 PII 脱敏回调就加上）"""
        if self.enable_pii_anonymize:
            pii_callback = _get_pii_callback()
            if pii_callback:
                return [pii_callback]
        return []

    def _create_llm(self, model: str, temperature: float) -> ChatOpenAI:
        """
        创建 LLM 客户端实例

        temperature 参数说明：
          0 = 完全确定，每次输出相同
          0.7 = 有创意但稳定，适合大多数任务
          1.0 = 完全随机，可能产生奇怪输出
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
        """标准 LLM（用于文章写作）"""
        if self._llm is None:
            self._llm = self._create_llm(self.model, self.temperature)
        return self._llm

    @property
    def llm_fast(self) -> ChatOpenAI:
        """快速 LLM（用于选题、简单任务）"""
        if self._llm_fast is None:
            self._llm_fast = self._create_llm(self.model_fast, self.temperature_fast)
        return self._llm_fast

    @property
    def llm_extract(self) -> ChatOpenAI:
        """提取专用 LLM（低温度，更确定性）"""
        if self._llm_extract is None:
            self._llm_extract = self._create_llm(self.model_fast, self.temperature_extract)
        return self._llm_extract

    def _get_topic_llm_candidates(self) -> List[tuple[ChatOpenAI, str]]:
        """获取选题生成可用的模型候选列表"""
        return [(self.llm, self.model)]

    def _get_extract_llm_candidates(self) -> List[tuple[ChatOpenAI, str]]:
        """获取提取任务可用的模型候选列表"""
        candidates: List[tuple[ChatOpenAI, str]] = [(self.llm_extract, self.model_fast)]
        if self.model != self.model_fast:
            candidates.append((self._create_llm(self.model, self.temperature_extract), self.model))
        return candidates

    def _extract_usage_info(self, response, model: str = "") -> LLMUsageInfo:
        """
        从 LLM 响应中提取 token 使用信息

        为什么需要这个？
          不同版本的 API 返回 usage 信息的方式不同，
          这个方法尝试多种常见格式来兼容。
        """
        usage = LLMUsageInfo(model=model or self.model)

        if hasattr(response, 'response_metadata'):
            token_usage = response.response_metadata.get('token_usage', {})
            usage.input_tokens = token_usage.get('prompt_tokens', 0)
            usage.output_tokens = token_usage.get('completion_tokens', 0)
            usage.total_tokens = token_usage.get('total_tokens', 0)

        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage.input_tokens = response.usage_metadata.get('input_tokens', usage.input_tokens)
            usage.output_tokens = response.usage_metadata.get('output_tokens', usage.output_tokens)
            usage.total_tokens = response.usage_metadata.get('total_tokens', usage.total_tokens)

        return usage

    def _update_usage_from_chunk(self, chunk: AIMessageChunk, usage: LLMUsageInfo) -> None:
        """
        从流式 chunk 更新 token 统计

        为什么需要这个？
          流式响应中，只有最后一个 chunk 包含完整的 usage 信息。
          这个方法在每个 chunk 到达时更新统计，最后一个 chunk 覆盖前面的值。
        """
        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
            usage.input_tokens = chunk.usage_metadata.get('input_tokens', usage.input_tokens)
            usage.output_tokens = chunk.usage_metadata.get('output_tokens', usage.output_tokens)
            usage.total_tokens = chunk.usage_metadata.get('total_tokens', usage.total_tokens)

        if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
            token_usage = chunk.response_metadata.get('token_usage', {})
            if token_usage:
                usage.input_tokens = token_usage.get('prompt_tokens', usage.input_tokens)
                usage.output_tokens = token_usage.get('completion_tokens', usage.output_tokens)
                usage.total_tokens = token_usage.get('total_tokens', usage.total_tokens)

    # ---------- 核心方法 ----------

    def _parse_topics_from_text(self, content: str) -> TopicsResponse:
        """
尽量把模型返回的原始文本整理成选题列表。

优先按 JSON 解析；如果格式不规整，再退回到按行提取标题。
"""
        import json

        text = (content or "").strip()
        if not text:
            return TopicsResponse(topics=[])

        if "```" in text:
            text = re.sub(r'^.*?```(?:json)?\s*', '', text, flags=re.DOTALL)
            text = re.sub(r'\s*```.*$', '', text, flags=re.DOTALL)

        json_start = text.find('{')
        json_end = text.rfind('}')
        if json_start != -1 and json_end != -1 and json_end > json_start:
            try:
                data = json.loads(text[json_start:json_end + 1])
                return TopicsResponse(**data)
            except (json.JSONDecodeError, ValidationError, TypeError):
                pass

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        topics: List[TopicItem] = []

        for line in lines:
            cleaned = re.sub(r'^[-*•]\s*', '', line)
            cleaned = re.sub(r'^\d+[\.)、]\s*', '', cleaned)
            cleaned = cleaned.strip('"""\' ')

            if not cleaned:
                continue
            if cleaned.startswith('{') or cleaned.startswith('['):
                continue
            if 'title' in cleaned.lower() and len(cleaned) < 12:
                continue

            topics.append(TopicItem(title=cleaned))
            if len(topics) >= 5:
                break

        return TopicsResponse(topics=topics)

    async def plan_topics(self, topic_direction: str) -> Tuple[TopicsResponse, LLMUsageInfo]:
        """
根据主题方向生成一组选题。

先走结构化输出；如果模型没按预期返回，再用兜底解析补救。
"""
        messages = [
            SystemMessage(content=self.TOPIC_SYSTEM_PROMPT),
            HumanMessage(content=f"主题：{topic_direction or '技术分享'}")
        ]

        last_error: Exception | None = None

        for llm_client, model_name in self._get_topic_llm_candidates():
            usage = LLMUsageInfo(model=model_name)
            try:
                structured_llm = llm_client.with_structured_output(TopicsResponse, include_raw=True)
                result = await structured_llm.ainvoke(messages)

                raw_response = result.get('raw')
                parsed_response = result.get('parsed')

                if raw_response:
                    usage = self._extract_usage_info(raw_response, model_name)

                if parsed_response:
                    return parsed_response, usage

                raw_content = getattr(raw_response, "content", "") if raw_response else ""
                recovered_response = self._parse_topics_from_text(raw_content)
                if recovered_response.topics:
                    print(f"[LLM] 结构化结果为空，已从原始文本恢复 {len(recovered_response.topics)} 个选题")
                    return recovered_response, usage

                fallback_response, fallback_usage = await self._plan_topics_fallback(topic_direction)
                if fallback_response.topics:
                    return fallback_response, fallback_usage

                return TopicsResponse(topics=[]), fallback_usage

            except Exception as e:
                last_error = e
                print(f"[LLM] 结构化输出失败，尝试降级: {e}")

        print(f"[LLM] 所有结构化模型都失败: {last_error}")
        return await self._plan_topics_fallback(topic_direction)

    async def _plan_topics_fallback(self, topic_direction: str) -> Tuple[TopicsResponse, LLMUsageInfo]:
        """
兜底方案：直接让模型吐 JSON，再自己解析。
"""
        import json

        system_prompt = self.TOPIC_SYSTEM_PROMPT + '\n\nJSON格式输出：{"topics":[{"title":"标题1"},...,{"title":"标题5"}]}'

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"主题：{topic_direction or '技术分享'}")
        ]

        last_error: Exception | None = None

        for llm_client, model_name in self._get_topic_llm_candidates():
            try:
                response = await llm_client.ainvoke(messages)
                usage = self._extract_usage_info(response, model_name)
                parsed = self._parse_topics_from_text(response.content)
                if parsed.topics:
                    return parsed, usage
                print(f"[LLM] 返回成功，但未解析出有效选题")
            except Exception as e:
                last_error = e
                print(f"[LLM] JSON 解析方案失败: {e}")

        print(f"[LLM] 所有选题模型都失败: {last_error}")
        return TopicsResponse(topics=[]), LLMUsageInfo(model=self.model)

    async def write_draft(
        self,
        topic: str,
        feedback: str = "",
        revision_count: int = 0
    ) -> Tuple[str, LLMUsageInfo]:
        """生成文章草稿（非流式）"""
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

        为什么需要流式？
          非流式：等 AI 生成完整个文章，再返回（约 10-30 秒）
          流式：AI 生成一部分就返回一部分（用户看到"正在打字"而不是"加载中"）
        """
        user_prompt = self._build_article_prompt(topic, feedback, revision_count)

        messages = [
            SystemMessage(content=self.ARTICLE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]

        full_content = ""
        usage = LLMUsageInfo(model=self.model)

        # 流式调用
        async for chunk in self.llm.astream(messages):
            if isinstance(chunk, AIMessageChunk):
                if chunk.content:
                    full_content += chunk.content
                    if on_chunk:
                        on_chunk(chunk.content)
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

        工作流程：
          1. 截断文章（只取前 1500 字，避免 token 过多）
          2. 调用 LLM 提取 3 个配图描述
          3. 解析响应（去掉编号）
          4. 返回最多 3 个要点
        """
        truncated = article_content[:1500] if len(article_content) > 1500 else article_content

        messages = [
            SystemMessage(content=self.VISUAL_SYSTEM_PROMPT),
            HumanMessage(content=f"文章内容：\n{truncated}")
        ]

        response = await self.llm_extract.ainvoke(messages)
        usage = self._extract_usage_info(response, self.model_fast)

        # 解析响应
        points = []
        for line in response.content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('-'):
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', line)
                if cleaned:
                    points.append(cleaned)

        return points[:3], usage

    def _build_article_prompt(self, topic: str, feedback: str, revision_count: int) -> str:
        """
        构建文章生成的用户提示

        如果有修改意见，在提示词中加上修订次数和反馈，帮助 AI 理解上下文。
        """
        if feedback and revision_count > 0:
            return f"选题：{topic}\n\n第{revision_count}次修订，修改意见：{feedback}\n\n请针对性修改。"
        return f"选题：{topic}"


# =============================================================================
# 单例实例
# =============================================================================

llm_service = LLMService()
