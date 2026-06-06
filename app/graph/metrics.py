"""
节点执行指标追踪模块 - 记录工作流里每个 AI 节点跑了多久、花了多少 token

通俗理解：
  就像游戏里的"战绩面板"——每个节点跑完后都会记一笔：
  "用了哪个模型"、"花了多少时间"、"用了多少 token"

为什么需要这个？
  - 算钱：LLM API 是按 token 收费的，精确统计每个调用花了多少
  - 排查慢：哪个节点最慢？是否有异常？
  - 优化：token 消耗高可以调整 prompt 或用更便宜的模型
"""
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class LLMUsage:
    """
    记录一次 LLM 调用用了多少 token

    - input_tokens：发给 AI 的 token 数（Prompt 长度）
    - output_tokens：AI 返回的 token 数（Completion 长度）
    - total_tokens：总 token 数 = input + output
    - model：用的什么模型
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


class NodeMetricsTracker:
    """
    节点指标追踪器 - 记录一个节点从开始到结束的所有性能数据

    使用方法：
      tracker = NodeMetricsTracker("plan_topics")  # 创建
      tracker.start()                               # 开始计时
      result, usage = llm_service.plan_topics(...)  # 跑 AI
      tracker.set_llm_usage(usage)                 # 记录 token 消耗
      tracker.stop()                                # 停止计时
      print(tracker.to_dict())                     # 导出数据
    """

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.duration_ms: float = 0.0
        self.llm_usage: Optional[LLMUsage] = None

    def start(self):
        """开始计时"""
        self.start_time = datetime.now()

    def stop(self):
        """停止计时"""
        self.end_time = datetime.now()
        if self.start_time:
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000

    def set_llm_usage(self, usage: LLMUsage):
        """记录 LLM token 消耗"""
        self.llm_usage = usage

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典，方便存入状态"""
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
    指标追踪上下文管理器 - 用 with 语句自动管理 start/stop

    为什么用 with？
      这样就算代码抛异常了，stop() 也一定会被调用，
      不会漏掉计时。

    用法：
      with MetricsContext("plan_topics") as tracker:
          result = await llm_service.plan_topics(...)
          tracker.set_llm_usage(usage)
      # 出了 with 块，tracker.stop() 自动被调用
    """

    def __init__(self, node_name: str):
        self.tracker = NodeMetricsTracker(node_name)

    def __enter__(self) -> NodeMetricsTracker:
        self.tracker.start()
        return self.tracker

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tracker.stop()
        return False  # 不吞掉异常


def merge_metrics(existing_metrics: list, new_metric: Dict[str, Any]) -> list:
    """
    把新节点的指标追加到列表里

    为什么需要这个？
      state.node_metrics 是一个列表，每个节点跑完就往里加一条
      这个函数负责把新指标 append 进去
    """
    metrics = list(existing_metrics) if existing_metrics else []
    metrics.append(new_metric)
    return metrics
