"""
PII（个人身份信息）脱敏模块
=============================================================================
职责说明：
  自动检测并脱敏日志中的敏感个人信息，防止敏感数据泄露到日志文件。

核心概念：
  - PII（Personally Identifiable Information）：能识别个人身份的信息
  - 脱敏：对敏感数据进行变形处理，打码或替换

支持检测的敏感数据类型：
  1. 邮箱地址：user@example.com -> us***@example.com
  2. 信用卡号：1234-5678-9012-3456 -> ****-****-****-3456
  3. API Key：sk-xxx...xxx -> sk-xxx***xxxx
  4. 手机号（中国）：13812345678 -> 138****5678
  5. IP 地址：192.168.1.1 -> 192.168.***.***
  6. 身份证号（中国）：110101199001011234 -> 110101********1234

脱敏策略说明：
  - mask（打码）：保留部分字符，中间用 * 替换（默认策略）
  - redact（全替换）：完全替换成 [REDACTED_EMAIL] 等标记
  - hash（哈希）：替换成哈希值，便于日志统计但不暴露原文
  - block（阻断）：发现 PII 直接抛出异常（适合严格合规场景）

典型场景：
  用户在输入框填写了手机号，AI 生成的回复被记录日志
  未脱敏：{"user_input": "我的手机号是 13812345678，请帮我..."}
  脱敏后：{"user_input": "我的手机号是 138****5678，请帮我..."}
=============================================================================
"""
import re
import hashlib
from typing import Callable, Literal, Optional
from dataclasses import dataclass, field


# =============================================================================
# 第 1 步：定义 PII 类型的数据结构
# =============================================================================

@dataclass
class PIIPattern:
    """
    PII 检测模式定义
    ==========================================================================
    每个 PII 类型（邮箱、手机号等）对应一个 PIIPattern 实例，
    包含检测用的正则表达式和脱敏函数。

    字段说明：
      - name：PII 类型名称，用于日志标记，如 "email"、"phone_cn"
      - pattern：正则表达式，用于在文本中匹配这种 PII
      - mask_func：自定义脱敏函数（可选），不提供就用默认策略

    为什么要用 dataclass？
      比普通类更简洁，自动生成 __init__、__repr__ 等方法
    """
    name: str  # PII 类型名称
    pattern: re.Pattern  # 编译后的正则表达式
    # 自定义脱敏函数，接收原始文本返回脱敏后文本
    # 例如：lambda x: x[:3] + '****' + x[-4:] 把手机号中间四位打码
    mask_func: Optional[Callable[[str], str]] = None


# =============================================================================
# 第 2 步：内置 PII 检测模式
# =============================================================================

# 内置的 PII 检测模式表
# 格式：{类型名: PIIPattern实例}
# 所有内置模式都可以通过 PIIAnonymizer.add_pattern() 直接使用

BUILTIN_PII_PATTERNS: dict[str, PIIPattern] = {

    # ---------- 邮箱地址 ----------
    # 典型场景：用户注册时填写邮箱 "test@example.com"
    # 脱敏结果：te***@example.com（保留 @ 前前两个字符）
    "email": PIIPattern(
        name="email",
        # 匹配标准邮箱格式：用户名@域名.后缀
        pattern=re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        mask_func=lambda x: x.split('@')[0][:2] + '***@' + x.split('@')[1] if '@' in x else x
        # 脱敏逻辑：用户名保留前两位 + *** + @ + 域名不变
    ),

    # ---------- 信用卡号 ----------
    # 典型场景：用户在支付页面输入信用卡号
    # 脱敏结果：****-****-****-3456（只保留末位）
    # 场景：日志记录用户操作时，不小心包含了卡号
    "credit_card": PIIPattern(
        name="credit_card",
        # 匹配信用卡号：16 位数字，可选 - 或空格分隔
        # \b 边界确保不匹配更长数字的一部分
        pattern=re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'),
        mask_func=lambda x: re.sub(r'\d', '*', x[:-4]) + x[-4:]
        # 脱敏逻辑：前 12 位全部替换成 *，保留最后 4 位（显示银行识别用）
    ),

    # ---------- API Key ----------
    # 典型场景：LLM API 调用日志可能包含 API Key
    # 脱敏结果：sk-xxx***xxxx（保留前 8 位和末 4 位）
    "api_key": PIIPattern(
        name="api_key",
        # 匹配多种格式的 API Key：
        # sk-：OpenAI 的 Secret Key（sk- 后 20+ 字符）
        # sk-proj-：OpenAI Project Key
        # lsv2_pt_：LangSmith 的 Key
        # ak-：通用 Access Key
        # UUID 格式的 Key（如某些云服务的）
        pattern=re.compile(
            r'\b('
            r'sk-[a-zA-Z0-9]{20,}|'           # OpenAI 标准 Key
            r'sk-proj-[a-zA-Z0-9_-]{20,}|'    # OpenAI Project Key
            r'lsv2_pt_[a-zA-Z0-9_]{20,}|'     # LangSmith
            r'ak-[a-zA-Z0-9]{20,}|'           # 通用 Access Key
            r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'  # UUID v4
            r')\b'
        ),
        mask_func=lambda x: x[:8] + '***' + x[-4:] if len(x) > 12 else '***'
        # 脱敏逻辑：保留前 8 位和末 4 位，中间打码
    ),

    # ---------- 中国手机号 ----------
    # 典型场景：用户注册或填写表单时输入手机号
    # 脱敏结果：138****5678（保留前 3 位和末 4 位）
    "phone_cn": PIIPattern(
        name="phone",
        # 匹配中国手机号：1 开头，第二位 3-9，后面 9 位数字
        # 总共 11 位，如 13812345678、+8613912345678（去掉 +86 也匹配）
        pattern=re.compile(r'\b1[3-9]\d{9}\b'),
        mask_func=lambda x: x[:3] + '****' + x[-4:]
        # 脱敏逻辑：138（前 3 位） + **** + 5678（末 4 位）
    ),

    # ---------- IP 地址 ----------
    # 典型场景：日志中记录的客户端 IP 地址
    # 脱敏结果：192.168.***.***（只保留 A 类和 B 类网段）
    "ip": PIIPattern(
        name="ip",
        # 匹配 IPv4 地址：四个 1-3 位数字用 . 分隔
        # 注意：不会匹配 999.999.999.999（正则只检测格式，不验证合法性）
        pattern=re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        mask_func=lambda x: '.'.join(x.split('.')[:2]) + '.***.***'
        # 脱敏逻辑：前两段（A 类 + B 类网络）保留，后两段打码
    ),

    # ---------- 身份证号（中国） ----------
    # 典型场景：用户实名认证或需要身份验证的表单
    # 脱敏结果：110101********1234（出生日期和行政区划代码打码）
    "id_card_cn": PIIPattern(
        name="id_card",
        # 匹配中国 18 位身份证号：
        # 前 6 位：行政区划代码（省市区）
        # 8-14 位：出生日期（YYYYMMDD）
        # 15-17 位：顺序码 + 性别位
        # 末位：校验码（数字或 X）
        pattern=re.compile(
            r'\b[1-9]\d{5}'
            r'(?:19|20)\d{2}'    # 出生年份：19xx 或 20xx
            r'(?:0[1-9]|1[0-2])'  # 出生月份：01-12
            r'(?:0[1-9]|[12]\d|3[01])'  # 出生日期：01-31
            r'\d{3}[\dXx]\b'     # 顺序码 3 位 + 校验码
        ),
        mask_func=lambda x: x[:6] + '********' + x[-4:]
        # 脱敏逻辑：行政区划代码（前 6 位）和顺序码（中间 3 位）打码
    ),
}


# =============================================================================
# 第 3 步：定义脱敏策略类型
# =============================================================================

# Literal 定义枚举类型，只能是这几个字符串之一
# - redact：完全替换成 [REDACTED_<类型>]
# - mask：用 mask_func 局部打码
# - hash：替换成哈希值（可用于统计去重，但不暴露原文）
# - block：发现 PII 直接抛出异常（严格合规场景）
Strategy = Literal["redact", "mask", "hash", "block"]


# =============================================================================
# 第 4 步：定义匹配结果数据结构
# =============================================================================

@dataclass
class PIIMatch:
    """
    PII 匹配结果
    ==========================================================================
    记录一次 PII 检测的结果，用于分析报告或审计。

    字段说明：
      - text：匹配到的原始文本（如 "13812345678"）
      - start：文本中的起始位置（字符偏移）
      - end：文本中的结束位置
      - pii_type：匹配到的 PII 类型名称（如 "phone_cn"）

    用途：
      - 审计报告：统计日志中出现了哪些类型的 PII
      - 数据分析：PII 在文本中出现的位置分布
    """
    text: str      # 原始匹配文本
    start: int    # 起始位置（字符索引）
    end: int      # 结束位置
    pii_type: str  # PII 类型名


# =============================================================================
# 第 5 步：PII 脱敏器主类
# =============================================================================

class PIIAnonymizer:
    """
    PII 脱敏器
    ==========================================================================
    核心功能：
      1. 注册 PII 检测模式（内置或自定义）
      2. 检测文本中的 PII
      3. 对文本进行脱敏处理
      4. 对字典/列表进行递归脱敏

    使用流程：
      第 1 步：创建 PIIAnonymizer 实例
      第 2 步：注册要检测的 PII 类型和脱敏策略
      第 3 步：调用 anonymize() 进行脱敏

    典型场景：
      ```python
      # 创建脱敏器并注册模式
      anonymizer = PIIAnonymizer()
      anonymizer.add_pattern("email", strategy="mask")      # 邮箱打码
      anonymizer.add_pattern("phone_cn", strategy="redact")  # 手机号全替换

      # 对文本脱敏
      text = "联系邮箱: user@example.com, 电话: 13812345678"
      result = anonymizer.anonymize(text)
      # 结果："联系邮箱: us***@example.com, 电话: [REDACTED_PHONE]"

      # 对字典脱敏（递归处理所有字符串值）
      data = {"email": "user@example.com", "name": "张三"}
      result = anonymizer.anonymize_dict(data)
      ```
    """

    def __init__(self):
        # 内部存储：[(PII模式, 脱敏策略)] 列表
        # 一个匿名化器可以同时处理多种 PII 类型
        self._patterns: list[tuple[PIIPattern, Strategy]] = []

    def add_pattern(
        self,
        pii_type: str,
        strategy: Strategy = "redact",
        detector: Optional[str | re.Pattern | Callable] = None,
    ) -> "PIIAnonymizer":
        """
        注册一个 PII 检测模式

        参数说明：
          - pii_type：PII 类型名称
            内置类型："email"、"credit_card"、"api_key"、"phone_cn"、"ip"、"id_card_cn"
          - strategy：脱敏策略（默认 "redact"）
          - detector：自定义检测器（可选）
            - 字符串：正则表达式字符串，会被编译成 Pattern
            - Pattern：已编译的正则表达式
            - Callable：自定义检测函数（目前仅支持正则）

        返回值：
          self，支持链式调用（add_pattern().add_pattern()...）

        典型场景：
          # 使用内置模式
          anonymizer.add_pattern("email", strategy="mask")
          anonymizer.add_pattern("phone_cn", strategy="redact")

          # 使用自定义正则
          anonymizer.add_pattern("custom_id", strategy="mask", detector=r'\bID-\d{6}\b')
        """
        if detector is not None:
            # 有自定义检测器
            if isinstance(detector, str):
                # 字符串正则 -> 编译
                pattern = PIIPattern(name=pii_type, pattern=re.compile(detector))
            elif isinstance(detector, re.Pattern):
                # 已编译正则 -> 直接用
                pattern = PIIPattern(name=pii_type, pattern=detector)
            else:
                # 函数检测器暂不支持
                raise ValueError("Currently only regex detectors are supported")
        else:
            # 使用内置模式
            if pii_type not in BUILTIN_PII_PATTERNS:
                raise ValueError(
                    f"Unknown PII type: {pii_type}. "
                    f"Available: {list(BUILTIN_PII_PATTERNS.keys())}"
                )
            pattern = BUILTIN_PII_PATTERNS[pii_type]

        self._patterns.append((pattern, strategy))
        return self

    def detect(self, content: str) -> list[PIIMatch]:
        """
        检测文本中的所有 PII

        参数说明：
          - content：要检测的文本

        返回值：
          PIIMatch 列表，每个匹配到一个 PIIMatch 对象

        典型场景：
          matches = anonymizer.detect("联系 13812345678 或 user@example.com")
          for m in matches:
              print(f"{m.pii_type}: {m.text} (位置 {m.start}-{m.end})")
        """
        matches = []
        for pattern, _ in self._patterns:
            for match in pattern.pattern.finditer(content):
                matches.append(PIIMatch(
                    text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    pii_type=pattern.name
                ))
        return matches

    def anonymize(self, content: str) -> str:
        """
        对文本进行脱敏处理

        参数说明：
          - content：要脱敏的原始文本

        返回值：
          脱敏后的文本

        工作流程：
          按注册顺序，依次对每种 PII 类型执行脱敏
          脱敏后的文本会传入下一个处理器继续处理

        典型场景：
          text = "我的邮箱是 user@example.com，手机是 13812345678"
          result = anonymizer.anonymize(text)
        """
        if not content or not isinstance(content, str):
            return content

        result = content

        # 依次应用每个模式的脱敏策略
        for pattern, strategy in self._patterns:
            result = self._apply_strategy(result, pattern, strategy)

        return result

    def _apply_strategy(self, content: str, pattern: PIIPattern, strategy: Strategy) -> str:
        """
        对内容应用指定的脱敏策略

        策略行为：
          - redact：完全替换成 [REDACTED_<类型名>]
          - mask：调用 pattern.mask_func 打码，无则用默认逻辑
          - hash：替换成 SHA256 哈希的前 8 位
          - block：发现 PII 直接抛出 PIIDetectedError 异常
        """

        def replace_func(match: re.Match) -> str:
            text = match.group()

            if strategy == "redact":
                # 全替换：替换成 [REDACTED_<类型>]
                return f"[REDACTED_{pattern.name.upper()}]"

            elif strategy == "mask":
                # 局部打码：保留部分字符
                if pattern.mask_func:
                    # 有自定义打码函数就用它
                    return pattern.mask_func(text)
                # 默认打码：保留首尾，中间全 *
                if len(text) <= 4:
                    return '*' * len(text)
                return text[:2] + '*' * (len(text) - 4) + text[-2:]

            elif strategy == "hash":
                # 哈希替换：保留用于统计去重，但不暴露原文
                hash_value = hashlib.sha256(text.encode()).hexdigest()[:8]
                return f"[HASH_{pattern.name.upper()}_{hash_value}]"

            elif strategy == "block":
                # 阻断：发现 PII 直接抛异常
                raise PIIDetectedError(f"PII detected: {pattern.name}")

            return text

        return pattern.pattern.sub(replace_func, content)

    def anonymize_dict(self, data: dict, recursive: bool = True) -> dict:
        """
        对字典中的所有字符串值进行脱敏（递归）

        参数说明：
          - data：要脱敏的字典
          - recursive：是否递归处理嵌套字典和列表（默认 True）

        返回值：
          脱敏后的新字典（原始字典不会被修改）

        工作流程：
          遍历字典的每个 key-value：
          - 字符串值：直接调用 anonymize() 脱敏
          - 字典：递归调用 anonymize_dict()
          - 列表：遍历每个元素，递归处理
          - 其他类型：原样保留

        典型场景：
          # 日志字典包含用户输入
          log_data = {
              "event": "user_action",
              "user_email": "user@example.com",
              "metadata": {"ip": "192.168.1.1"}
          }
          result = anonymizer.anonymize_dict(log_data)
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                # 字符串：直接脱敏
                result[key] = self.anonymize(value)
            elif isinstance(value, dict) and recursive:
                # 嵌套字典：递归脱敏
                result[key] = self.anonymize_dict(value, recursive)
            elif isinstance(value, list):
                # 列表：遍历每个元素分别处理
                result[key] = [
                    self.anonymize(item) if isinstance(item, str)
                    else self.anonymize_dict(item, recursive) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                # 其他类型（数字、布尔等）：原样保留
                result[key] = value
        return result


class PIIDetectedError(Exception):
    """
    检测到 PII 时抛出的异常（用于 block 策略）
    ==========================================================================
    当脱敏策略设为 "block" 时，如果检测到 PII，会抛出这个异常。

    典型场景：
      - 严格合规要求：不允许日志中出现任何 PII
      - 发现 PII 时立即中断处理，记录审计日志
      - 配合异常处理器可以自动告警
    """
    pass


# =============================================================================
# 第 6 步：预配置的脱敏器实例
# =============================================================================

def create_default_anonymizer() -> PIIAnonymizer:
    """
    创建默认配置的脱敏器
    ==========================================================================
    出厂默认配置，适合大多数场景：
      - 邮箱：打码（保留域名）
      - 信用卡：打码（保留末 4 位）
      - API Key：全替换（安全风险最高）
      - 手机号：打码（保留前 3 + 后 4 位）

    典型场景：
      anonymizer = create_default_anonymizer()
      result = anonymizer.anonymize(text)
    """
    return (
        PIIAnonymizer()
        .add_pattern("email", strategy="mask")
        .add_pattern("credit_card", strategy="mask")
        .add_pattern("api_key", strategy="redact")
        .add_pattern("phone_cn", strategy="mask")
    )


# 全局默认脱敏器实例（供 structlog 处理器使用）
# 导入方式：from app.core.pii_anonymizer import default_anonymizer
default_anonymizer = create_default_anonymizer()


# =============================================================================
# 第 7 步：structlog Processor 集成
# =============================================================================

def pii_anonymize_processor(logger, method_name: str, event_dict: dict) -> dict:
    """
    structlog 处理器：对日志内容进行 PII 脱敏
    ==========================================================================
    用途：
      作为 structlog 的 Processor，在每条日志输出前调用脱敏。

    使用方式：
      在 setup_logging() 的 shared_processors 列表中加入这个处理器
      所有日志都会在写入文件/控制台之前经过脱敏

    工作原理：
      接收 structlog 传入的日志字典（包含 event、level、request_id 等字段）
      对字典中所有字符串值调用 anonymize_dict() 进行脱敏
      返回脱敏后的字典，写入日志文件/控制台

    典型场景：
      业务代码调用 logger.info("用户输入", user_input="我的邮箱是 abc@x.com")
      日志处理器捕获后，调用 pii_anonymize_processor
      输出到日志文件时变成："用户输入", user_input="我的邮箱是 ab***@x.com"
    """
    return default_anonymizer.anonymize_dict(event_dict)
