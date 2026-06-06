"""
LLM 调用前后自动脱敏 PII（邮箱、手机号等），
防止敏感信息进入 LangSmith 等追踪系统。
"""
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from app.core.pii_anonymizer import default_anonymizer, PIIAnonymizer
from app.core.logger import get_logger


logger = get_logger(__name__)


class PIIAnonymizingCallback(BaseCallbackHandler):
    """LangChain 回调：在 LLM 输入/输出时自动脱敏。"""

    def __init__(
        self,
        anonymizer: Optional[PIIAnonymizer] = None,
        anonymize_input: bool = True,
        anonymize_output: bool = True,
    ):
        self.anonymizer = anonymizer or default_anonymizer
        self.anonymize_input = anonymize_input
        self.anonymize_output = anonymize_output
        super().__init__()

    def _anonymize_messages(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if not self.anonymize_input:
            return messages
        anonymized = []
        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                content = self.anonymizer.anonymize(content)
            elif isinstance(content, list):
                content = [
                    self.anonymizer.anonymize(item.get("text", "")) if isinstance(item, dict) else item
                    for item in content
                ]
            anonymized.append(msg.__class__(content=content))
        return anonymized

    def on_chat_model_start(
        self,
        handler,
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        return [self._anonymize_messages(m) for m in messages]

    def on_llm_start(
        self,
        handler,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        if self.anonymize_input:
            return [self.anonymizer.anonymize(p) for p in prompts]
        return prompts

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs) -> Any:
        if not self.anonymize_output:
            return
        for i, generations in enumerate(response.generations or []):
            for j, gen in enumerate(generations or []):
                text = getattr(gen, "text", "") or ""
                if text:
                    response.generations[i][j].text = self.anonymizer.anonymize(text)


pii_callback = PIIAnonymizingCallback()
