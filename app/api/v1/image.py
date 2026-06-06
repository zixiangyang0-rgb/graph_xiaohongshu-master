"""
这个接口主要拿来测画图链路通不通。

给一个 prompt，看看后端能不能顺利调起图片服务并返回地址。
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services import get_image_service

router = APIRouter(prefix="/image", tags=["Image"])


class GenerateImageRequest(BaseModel):
    """图片生成请求——你要画什么，以及要不要套小红书风格"""


class GenerateImageResponse(BaseModel):
    """图片生成返回——成功返回图片路径，失败返回错误"""


class ImageErrorDetail(BaseModel):
    """结构化的错误信息（方便前端判断要不要提示用户重试）"""


@router.post("/generate", response_model=GenerateImageResponse)
async def generate_image(req: GenerateImageRequest) -> GenerateImageResponse:
    """
    生成单张图片（用于连通性测试）

    工作流程：
      1. 获取图片服务
      2. 调用 generate_single_image 生成图片
         - 如果 optimize_for_xhs=True，套上小红书风格模板
         - 调用火山引擎方舟 Ark 平台图片生成 API
         - 备用 prompt：主 prompt 失败时才用
         - 保存到 static/images/generated/ 目录
      3. 返回图片访问路径

    返回：
      - url：图片访问路径（/static/images/generated/xxx.png）
      - model：使用的模型名称
      - success：是否生成成功
    """
    image_service = get_image_service()
    model_name = getattr(image_service, "model", getattr(image_service, "REQ_KEY", "unknown"))

    try:
        url = await image_service.generate_single_image(
            prompt=req.prompt,
            optimize_for_xhs=req.optimize_for_xhs,
        )

        return GenerateImageResponse(
            url=url,
            model=model_name,
            success=url is not None,
        )
    except Exception as e:
        detail = ImageErrorDetail(
            message=f"图片生成失败: {str(e)}",
            error_type="unexpected_generation_error",
            retryable=False,
            model=model_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail.model_dump(),
        ) from e
