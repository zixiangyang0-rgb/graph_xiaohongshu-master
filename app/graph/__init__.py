# LangGraph workflow module
# =============================================================================
# 职责说明：
#   本模块包含工作流的核心组件：
#   - state.py：工作流状态数据结构定义
#   - workflow.py：工作流图构建和编译
#   - utils.py：工具函数（Checkpointer 管理等）
#   - nodes/：所有工作流节点实现
#   - subgraphs/：子图定义（选题子图等）
#   - metrics.py：节点执行指标追踪
#
# 典型导入：
#   from app.graph import get_graph, AgentState, INITIAL_STATE
