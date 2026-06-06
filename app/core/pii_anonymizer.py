"""
自动脱敏日志里的个人信息（邮箱、手机号、身份证等）。
"""
import re
import hashlib
from typing import Callable, Literal, Optional, Union
from dataclasses import dataclass, field


@dataclass
class PIIPattern:
    """一种 PII 的检测模式和脱敏方式。"""
    name: str
    pattern: re.Pattern
    mask_func: Optional[Callable[[str], str]] = None


BUILTIN_PII_PATTERNS: dict[str, PIIPattern] = {

    "email": PIIPattern(
        name="email",
        pattern=re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        mask_func=lambda x: x.split('@')[0][:2] + '***@' + x.split('@')[1] if '@' in x else x
    ),

    "phone_cn": PIIPattern(
        name="phone_cn",
        pattern=re.compile(r'\b1[3-9]\d{9}\b'),
        mask_func=lambda x: x[:3] + '****' + x[-4:] if len(x) == 11 else x
    ),

    "id_card_cn": PIIPattern(
        name="id_card_cn",
        pattern=re.compile(r'\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'),
        mask_func=lambda x: x[:6] + '********' + x[-4:] if len(x) == 18 else x
    ),

    "credit_card": PIIPattern(
        name="credit_card",
        pattern=re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'),
        mask_func=lambda x: '****-****-****-' + x[-4:].replace('-', '').replace(' ', '')
    ),

    "ip_address": PIIPattern(
        name="ip_address",
        pattern=re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        mask_func=lambda x: '.'.join(p + '***' if i < 3 else p for i, p in enumerate(x.split('.')))
    ),

    "api_key": PIIPattern(
        name="api_key",
        pattern=re.compile(r'\b(?:sk-|api-)[a-zA-Z0-9]{20,}\b'),
        mask_func=lambda x: x[:6] + '***' + x[-4:] if len(x) > 12 else x
    ),
}


AnonymizeStrategy = Literal["mask", "redact", "hash", "block"]


@dataclass
class PIIMatchResult:
    """一次检测结果。"""
    matched_text: str
    pii_type: str
    original: str
    anonymized: str


class PIIAnonymizer:
    """按注册顺序对文本中的每种 PII 执行脱敏。"""

    def __init__(self):
        self._patterns: list[PIIPattern] = []
        self._strategy: AnonymizeStrategy = "mask"
        self._block_on_detect: bool = False

    def add_pattern(self, pii_pattern: PIIPattern) -> "PIIAnonymizer":
        self._patterns.append(pii_pattern)
        return self

    def set_strategy(self, strategy: AnonymizeStrategy) -> "PIIAnonymizer":
        self._strategy = strategy
        self._block_on_detect = (strategy == "block")
        return self

    def anonymize(self, text: str) -> str:
        result = text
        for pii_pattern in self._patterns:
            def _replace(m: re.Match) -> str:
                original = m.group()
                if pii_pattern.mask_func:
                    return pii_pattern.mask_func(original)
                if self._strategy == "redact":
                    return f"[{pii_pattern.name.upper()}]"
                if self._strategy == "hash":
                    return hashlib.sha256(original.encode()).hexdigest()[:16]
                return original[:3] + '*' * (len(original) - 6) + original[-3:] if len(original) > 6 else '***'
            result = pii_pattern.pattern.sub(_replace, result)
        return result

    def anonymize_dict(self, data: dict) -> dict:
        return {k: self.anonymize(str(v)) if isinstance(v, str) else v for k, v in data.items()}


default_anonymizer = PIIAnonymizer()
for p in BUILTIN_PII_PATTERNS.values():
    default_anonymizer.add_pattern(p)


def pii_anonymize_processor(logger, method_name, event_dict):
    """structlog processor：自动脱敏日志里的敏感字段。"""
    if isinstance(event_dict.get("event"), str):
        event_dict["event"] = default_anonymizer.anonymize(event_dict["event"])
    return event_dict
