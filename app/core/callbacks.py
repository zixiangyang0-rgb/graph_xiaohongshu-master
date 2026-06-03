"""
LangChain Callback 模块
=============================================================================
职责说明：
  为 LangChain/LangGraph 提供回调处理器，在 LLM 调用的关键时机注入逻辑。

核心功能：
  1. PII 脱敏回调（PIIAnonymizingCallback）：在 LLM 输入/输出时自动脱敏敏感信息
     防止用户输入和 AI 输出中的敏感数据被记录到 LangSmith 等追踪系统

设计原理：
  LangChain 的 Callback 机制允许你在 LLM 调用的各个阶段注入自定义逻辑。
  PIIAnonymizingCallback 实现了 BaseCallbackHandler 的关键方法：
  - on_llm_start / on_chat_model_start：LLM 开始调用时脱敏输入
  - on_llm_end：LLM 返回结果时脱敏输出
  - on_llm_error：LLM 调用出错时记录日志

为什么需要这个？
  LangSmith 等追踪系统会记录 Prompt 和 Completion，这些数据可能包含用户隐私。
  通过在 Callback 层脱敏，确保发送到 LangSmith 的数据不包含敏感信息。

典型场景：
  用户输入："我的邮箱是 user@example.com，请帮我写篇文章"
  -> on_chat_model_start 脱敏 -> LangSmith 收到：邮箱已打码
  -> AI 回复："你的邮箱是 us***@example.com..."
  -> on_llm_end 脱敏 -> LangSmith 收到：邮箱已打码
=============================================================================
"""
from typing import Any, Optional, Union
from uuid import UUID

# LangChain 核心回调基类
# BaseCallbackHandler 是所有自定义回调的基类
# 实现其中的方法即可在 LLM 调用的各个时机注入逻辑
from langchain_core.callbacks import BaseCallbackHandler

# LangChain 消息类型
from langchain_core.messages import BaseMessage

# LLM 调用结果类型
from langchain_core.outputs import LLMResult

# 导入 PII 脱敏工具
from app.core.pii_anonymizer import default_anonymizer, PIIAnonymizer

# 导入日志工具
from app.core.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# PII 脱敏回调处理器
# =============================================================================

class PIIAnonymizingCallback(BaseCallbackHandler):
    """
    PII 脱敏回调处理器
    ==========================================================================
    功能说明：
      在 LangChain/LangGraph 的 LLM 调用前后自动脱敏敏感信息。

    工作原理：
      1. 实现 BaseCallbackHandler 的关键方法
      2. 在方法中调用 PIIAnonymizer 对 Prompt/Completion 进行脱敏
      3. LangChain 内部会将脱敏后的数据传给后续的回调（如 LangSmith）

    为什么要继承 BaseCallbackHandler？
      BaseCallbackHandler 提供了所有回调方法的默认实现（空实现）
      我们只需要 override 我们关心的方法，不用全部实现

    典型场景：
      # 创建带脱敏功能的 LLM
      llm = ChatOpenAI(
          callbacks=[PIIAnonymizingCallback()]
      )
      # 调用 LLM
      response = llm.invoke("我的邮箱是 user@example.com")
      # LangSmith 收到的是脱敏后的 Prompt
    """

    def __init__(
        self,
        anonymizer: Optional[PIIAnonymizer] = None,
        anonymize_input: bool = True,
        anonymize_output: bool = True,
    ):
        """
        初始化脱敏回调

        参数说明：
          - anonymizer：PII 脱敏器实例，默认使用全局的 default_anonymizer
            允许注入自定义的脱敏器（如需要额外检测某种 PII）
          - anonymize_input：是否对 LLM 输入（Prompt）进行脱敏
            典型场景：关闭以节省性能，如果确定输入不含敏感数据
          - anonymize_output：是否对 LLM 输出（Completion）进行脱敏
            典型场景：开启，因为 AI 输出可能包含从训练数据中学到的个人信息

        典型场景：
          # 使用默认配置
          callback = PIIAnonymizingCallback()

          # 只脱敏输出，关闭输入脱敏（节省性能）
          callback = PIIAnonymizingCallback(anonymize_input=False)

          # 使用自定义脱敏器
          custom_anonymizer = PIIAnonymizer().add_pattern("custom_id", strategy="mask")
          callback = PIIAnonymizingCallback(anonymizer=custom_anonymizer)
        """
        super().__init__()
        self.anonymizer = anonymizer or default_anonymizer
        self.anonymize_input = anonymize_input
        self.anonymize_output = anonymize_output

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        LLM（非 Chat 模型）调用开始时触发

        ==========================================================================
        触发时机：调用 llm.invoke() 或 llm.predict() 等方法时

        参数说明：
          - serialized：LLM 的序列化信息（如模型名、参数配置）
          - prompts：发送给 LLM 的 Prompt 列表（通常只有一个）
          - run_id：这次 LLM 调用的唯一 ID
          - parent_run_id：父调用的 run_id（如果有嵌套调用）

        工作逻辑：
          如果 anonymize_input=True，遍历所有 Prompt 并调用脱敏
          脱敏后的 Prompt 会被 LangChain 传给后续的回调和追踪系统

        典型场景：
          Prompt = "用户的邮箱是 user@example.com，请回复"
          -> 脱敏后 -> "用户的邮箱是 us***@example.com，请回复"
        """
        if self.anonymize_input:
            for i, prompt in enumerate(prompts):
                prompts[i] = self.anonymizer.anonymize(prompt)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Chat 模型（ChatGPT、Claude 等）调用开始时触发

        ==========================================================================
        触发时机：调用 chat_model.invoke() 或 chat_model.batch() 时

        参数说明：
          - serialized：模型的序列化信息
          - messages：消息列表的列表
            外层列表：不同的对话轮次（如 few-shot learning 有多个示例）
            内层列表：单轮中的消息（如 [SystemMessage, HumanMessage, AIMessage]）

        工作逻辑：
          遍历所有消息，遍历每个消息的 content
          如果 content 是字符串，调用脱敏

        为什么有 on_llm_start 和 on_chat_model_start 两个方法？
          on_llm_start：非流式 LLM（如 text-davinci-003）
          on_chat_model_start：Chat 模型（如 GPT-4、Claude）
          它们参数不同，Chat 模型用 messages 而非 prompts
        """
        if self.anonymize_input:
            for message_list in messages:
                for message in message_list:
                    if hasattr(message, 'content') and isinstance(message.content, str):
                        message.content = self.anonymizer.anonymize(message.content)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        """
        LLM 调用结束时触发

        ==========================================================================
        触发时机：LLM 返回结果后（成功或异常都会触发）

        参数说明：
          - response：LLM 返回结果，包含 generations（生成的文本列表）
          - run_id：这次调用的唯一 ID

        工作逻辑：
          如果 anonymize_output=True，遍历所有 generation 并脱敏
          - generation.text：非 Chat 模型的输出文本
          - generation.message.content：Chat 模型的输出文本

        典型场景：
          AI 输出 = "你的邮箱是 us***@example.com，已收到"
          -> 脱敏后 -> "你的邮箱是 us***@example.com，已收到"
          （输出本身可能包含敏感信息被再次打码）

        为什么要脱敏输出？
          AI 模型可能从训练数据中学到了个人信息
          当用户输入某些提示词时，AI 输出可能包含这些信息
          在输出层脱敏可以进一步保护隐私
        """
        if self.anonymize_output:
            for generations in response.generations:
                for generation in generations:
                    # 脱敏非 Chat 模型的输出
                    if hasattr(generation, 'text') and generation.text:
                        generation.text = self.anonymizer.anonymize(generation.text)
                    # 脱敏 Chat 模型的输出
                    if hasattr(generation, 'message') and hasattr(generation.message, 'content'):
                        if isinstance(generation.message.content, str):
                            generation.message.content = self.anonymizer.anonymize(
                                generation.message.content
                            )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        """
        LLM 调用出错时触发

        ==========================================================================
        触发时机：LLM 调用过程中抛出异常

        参数说明：
          - error：捕获到的异常对象
          - run_id：这次调用的唯一 ID

        工作逻辑：
          记录错误日志，方便排查 LLM 调用问题
        """
        logger.error(
            "llm_error",
            error=str(error),
            run_id=str(run_id),
        )


# =============================================================================
# 全局 PII 脱敏回调实例
# =============================================================================

# 预创建的单例实例，供 LLMService 直接使用
# 导入方式：from app.core.callbacks import pii_callback
pii_callback = PIIAnonymizingCallback()
