"""
节点执行指标追踪模块
=============================================================================
职责说明：
  记录工作流中每个节点的执行性能数据，用于监控和计费。

核心指标：
  1. duration_ms：节点执行耗时
  2. input_tokens / output_tokens / total_tokens：LLM API 调用的 token 消耗

典型场景：
  工作流执行完成后，前端显示"总耗时 5.2s，总消耗 3200 tokens"
  每个节点的耗时和 token 消耗都可以单独查看

为什么需要这个？
  - 监控：哪个节点最慢？是否有异常？
  - 计费：LLM API 按 token 计费，精确统计每个调用
  - 优化：token 消耗高可以调整 prompt 或用更便宜的模型
=============================================================================
"""
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class LLMUsage:
    """
    LLM 调用的 token 使用信息
    ==========================================================================
    字段详解：
      - input_tokens：发送给 LLM 的 token 数（Prompt 长度）
      - output_tokens：LLM 返回的 token 数（Completion 长度）
      - total_tokens：总 token 数 = input + output
      - model：实际使用的模型名称

    典型场景：
      调用 doubao-seed-1-6-flash-250828 模型
      input_tokens = 450, output_tokens = 150, total_tokens = 600
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


class NodeMetricsTracker:
    """
    节点指标追踪器

    ==========================================================================
    用途：
      记录一个节点从开始到结束的所有性能数据。

    使用流程：
      第 1 步：创建 Tracker，传入节点名称
      第 2 步：start() 记录开始时间
      第 3 步：set_llm_usage() 记录 LLM 消耗
      第 4 步：stop() 记录结束时间并计算耗时
      第 5 步：to_dict() 导出为字典

    典型场景：
      tracker = NodeMetricsTracker("plan_topics")
      tracker.start()
      result, usage = llm_service.plan_topics(...)
      tracker.set_llm_usage(usage)
      tracker.stop()
      print(tracker.to_dict())
    """

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.duration_ms: float = 0.0
        self.llm_usage: Optional[LLMUsage] = None

    def start(self):
        """记录开始时间"""
        self.start_time = datetime.now()

    def stop(self):
        """记录结束时间并计算耗时（毫秒）"""
        self.end_time = datetime.now()
        if self.start_time:
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000

    def set_llm_usage(self, usage: LLMUsage):
        """设置 LLM 使用信息"""
        self.llm_usage = usage

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于存入 AgentState）"""
        result = {
            "node_name": self.node_name,
            "duration_ms": round(self.duration_ms, 2),
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "end_time": self.end_time.isoformat() if self.end_time else "",
        }

        if self.llm_usage:
            result.update({
                "input_tokens": self.llm_usage.input_tokens,
                "output_tokens": self.llm_usage.output_tokens,
                "total_tokens": self.llm_usage.total_tokens,
                "model": self.llm_usage.model,
            })
        else:
            result.update({
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "model": "",
            })

        return result


class MetricsContext:
    """
    指标追踪上下文管理器

    ==========================================================================
    用途：
      用 with 语句自动管理 tracker 的 start/stop
      确保无论代码正常执行还是抛异常，tracker.stop() 都会被调用

    使用方式：
      with MetricsContext("plan_topics") as tracker:
          result = await llm_service.plan_topics(...)
          tracker.set_llm_usage(usage)
      # with 块结束后 tracker.stop() 自动被调用

    工作原理：
      __enter__：调用 tracker.start()，返回 tracker
      __exit__：调用 tracker.stop()，返回 False（不抑制异常）
    """

    def __init__(self, node_name: str):
        self.tracker = NodeMetricsTracker(node_name)

    def __enter__(self) -> NodeMetricsTracker:
        self.tracker.start()
        return self.tracker

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tracker.stop()
        return False


def merge_metrics(existing_metrics: list, new_metric: Dict[str, Any]) -> list:
    """
    合并现有指标和新指标

    ==========================================================================
    用途：
      工作流中每个节点执行后，需要把指标追加到 state.node_metrics
      因为 AgentState.node_metrics 是列表，不是单个对象

    参数说明：
      - existing_metrics：之前节点的指标列表
      - new_metric：新节点的指标字典

    返回值：
      合并后的完整列表

    典型场景：
      existing_metrics = [{"node_name": "plan_topics", ...}]
      new_metric = {"node_name": "write_draft", ...}
      merge_metrics(existing, new) -> [plan_topics, write_draft]
    """
    metrics = list(existing_metrics) if existing_metrics else []
    metrics.append(new_metric)
    return metrics
