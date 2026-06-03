"""
图片生成 API 模块
=============================================================================
职责说明：
  提供图片生成相关的 HTTP 接口，用于测试 AI 图片生成功能。

典型接口：
  POST /image/generate：生成单张图片（用于连通性测试）

典型场景：
  1. 开发者测试：调用此接口确认图片生成服务正常工作
  2. 调试配图：手动生成一张图片看看效果
  3. 验证 API Key：确认 IMAGE_API_KEY 配置正确

技术细节：
  - 调用 Gemini Image API 生成图片
  - 默认生成小红书爆款风格（3:4 竖版）
  - 图片以 base64 格式返回，自动保存到 static 目录
=============================================================================
"""
from typing import Optional

# FastAPI 核心
from fastapi import APIRouter, HTTPException, status

# Pydantic 数据验证
from pydantic import BaseModel, Field

# 导入图片服务（单例）
from app.services import get_image_service

# 创建路由实例
router = APIRouter(prefix="/image", tags=["Image"])


# =============================================================================
# 第 1 步：定义请求/响应模型
# =============================================================================

class GenerateImageRequest(BaseModel):
    """
    图片生成请求
    ==========================================================================
    字段说明：
      - prompt：图片描述文案，AI 根据这个生成图片
      - optimize_for_xhs：是否优化为小红书爆款风格（默认开启）
        开启后：自动加上风格描述（明亮温暖、高质感等）
        关闭后：直接用 prompt 作为生成提示词

    典型场景：
      # 生成小红书风格配图
      {"prompt": "一个程序员在深夜写代码", "optimize_for_xhs": true}
      # 直接生成（不套风格模板）
      {"prompt": "a programmer coding at night", "optimize_for_xhs": false}
    """
    # prompt：图片描述文案，LLM 根据文案生成图片内容
    # 典型值："程序员深夜编程的场景，温暖台灯光线"
    prompt: str = Field(..., description="图片描述文案")

    # optimize_for_xhs：是否套用小红书爆款风格模板
    # 典型值：
    #   - True：加上"小红书流行的高质感、精致感"等描述
    #   - False：直接使用用户提供的 prompt
    optimize_for_xhs: bool = Field(True, description="是否优化为小红书爆款风格")


class GenerateImageResponse(BaseModel):
    """
    图片生成响应
    ==========================================================================
    字段说明：
      - url：生成的图片访问路径，格式 /static/images/generated/xxx.png
      - model：使用的图片模型名称
      - success：是否生成成功

    典型场景：
      成功：{"url": "/static/images/generated/xhs_20240101_120000_abc123.png", "model": "gemini-3-pro-image-preview", "success": true}
      失败：{"url": null, "model": "gemini-3-pro-image-preview", "success": false}
    """
    # url：图片的 HTTP 访问路径（不是本地路径）
    # 前端可以用 <img src="url"> 直接显示
    url: Optional[str] = Field(None, description="生成的图片访问路径")

    # model：实际调用的模型名称（如 "gemini-3-pro-image-preview"）
    model: str = Field(..., description="使用的图片模型")

    # success：生成是否成功
    # 即使部分成功也算 True（url 有值），完全失败才是 False
    success: bool = Field(..., description="是否生成成功")


# =============================================================================
# 第 2 步：图片生成接口
# =============================================================================

@router.post("/generate", response_model=GenerateImageResponse)
async def generate_image(req: GenerateImageRequest) -> GenerateImageResponse:
    """
    生成单张图片（用于连通性测试）

    ==========================================================================
    请求：POST /image/generate
    参数：GenerateImageRequest（prompt + optimize_for_xhs）

    工作流程（每一步都有明确目的）：

    ---------- 第 1 步：获取图片服务 ----------
    get_image_service() 返回全局单例（延迟初始化）
    内部会用 IMAGE_API_KEY、IMAGE_BASE_URL 等配置创建 API 客户端

    ---------- 第 2 步：调用图片生成 ----------
    image_service.generate_single_image(
        prompt=req.prompt,
        optimize_for_xhs=req.optimize_for_xhs
    )
    内部逻辑：
      1. 如果 optimize_for_xhs=True，把 prompt 包装成 XHS_STYLE_PROMPT 模板
         加上风格要求："小红书流行的高质感、精致感、氛围感风格"
      2. 调用 Gemini API 生成图片
      3. 如果失败，用备用提示词（FALLBACK_PROMPTS）重试一次
      4. 把返回的 base64 图片数据解码，保存到 static/images/generated/ 目录
      5. 返回文件路径

    ---------- 第 3 步：构造响应 ----------
    - url：图片访问路径（/static/images/generated/xxx.png）
    - model：使用的模型名称
    - success：是否生成成功

    ---------- 第 4 步：异常处理 ----------
    如果发生任何异常（如 API Key 错误、网络超时），返回 500 错误

    典型场景：
      POST {"prompt": "深夜程序员编程的温馨场景", "optimize_for_xhs": true}
      -> 调用 Gemini API -> 保存图片 -> 返回 URL
      -> 前端用 <img :src="response.url"> 显示图片
    ==========================================================================
    """
    try:
        # ---------- 第 1 步：获取图片服务实例 ----------
        image_service = get_image_service()

        # ---------- 第 2 步：生成图片 ----------
        # generate_single_image 内部会：
        # 1. 包装 prompt（如果开启小红书风格）
        # 2. 调用 Gemini API
        # 3. 失败时用备用提示词重试
        # 4. 保存图片到 static 目录
        # 5. 返回访问路径
        url = await image_service.generate_single_image(
            prompt=req.prompt,
            optimize_for_xhs=req.optimize_for_xhs,
        )

        # ---------- 第 3 步：获取模型名称 ----------
        model_name = getattr(image_service, "model", "unknown")

        # ---------- 第 4 步：返回响应 ----------
        return GenerateImageResponse(
            url=url,
            model=model_name,
            success=url is not None
        )

    except Exception as e:
        # ---------- 第 5 步：异常处理 ----------
        # 捕获所有异常（API 错误、网络超时、文件写入失败等）
        # 返回 500 错误，并附带错误信息
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"图片生成失败: {str(e)}",
        ) from e
