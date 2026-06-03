"""
服务模块 - 提供 LLM 和图片生成服务
=============================================================================
职责说明：
  提供统一的入口访问 llm_service 和 image_service 单例。

为什么用函数包装？
  - 延迟初始化：单例在首次访问时才真正创建
  - 统一入口：所有模块都从这导入，方便以后改实现

导出内容：
  - llm_service / get_llm_service()：LLM 服务实例和方法
  - image_service / get_image_service()：图片服务实例和方法
  - LLMUsageInfo / TopicsResponse / StreamResult：数据结构
=============================================================================
"""
from app.services.llm_service import llm_service, LLMUsageInfo, TopicsResponse, StreamResult
from app.services.image_service import image_service


def get_llm_service():
    """
    获取 LLM 服务实例

    ==========================================================================
    用途：
      工作流节点通过这个函数获取 LLM 服务
      而不是直接导入单例（避免循环依赖）
    """
    return llm_service


def get_image_service():
    """
    获取图片服务实例

    ==========================================================================
    用途：
      工作流节点通过这个函数获取图片服务
      而不是直接导入单例（避免循环依赖）
    """
    return image_service
