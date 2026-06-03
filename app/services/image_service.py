"""
图片生成服务模块
=============================================================================
职责说明：
  封装图片生成相关的功能，调用 Gemini Image API 生成小红书风格的配图。

核心功能：
  1. generate_single_image()：生成单张图片（带备用提示词重试）
  2. generate_images()：批量生成配图（并行执行）

典型场景：
  工作流审核通过 -> extract_visuals_node（提取视觉要点）
  -> generate_images_node -> image_service.generate_images(visual_points)
  -> 返回图片 URL 列表 -> 保存到 static/images/generated/

为什么用 Gemini？
  Gemini 的 image generation 功能支持直接通过文本生成高质量图片
  火山引擎 Doubao 提供了兼容 Gemini API 的端点

图片规格：
  - 比例：3:4 竖版（适合小红书手机浏览）
  - 风格：小红书爆款风格（高质感、精致感、氛围感）
  - 格式：PNG
=============================================================================
"""
import os
import asyncio
import base64
import uuid
import random
import httpx
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class ImageService:
    """
    图片生成服务类

    ==========================================================================
    核心方法：
      - generate_single_image()：生成单张图片（带备用提示词重试）
      - generate_images()：批量生成配图（并行执行）

    Prompt 设计：
      XHS_STYLE_PROMPT：包装后的完整提示词，加上小红书风格要求
      FALLBACK_PROMPTS：备用提示词列表，首次失败时随机选择一个重试

    错误处理：
      - API 错误：打印日志，返回 None
      - 网络超时：120 秒超时，返回 None
      - 响应无图片：打印日志，返回 None
    """

    # 小红书风格提示词模板
    # 会把用户提供的配图描述填入 {content} 占位符
    XHS_STYLE_PROMPT = """请根据以下内容生成一张小红书风格的爆款配图：

【内容主题】
{content}

【图片要求】
- 风格：小红书流行的高质感、精致感、氛围感风格
- 色调：明亮温暖、柔和治愈、或高级感色调
- 构图：简洁大气、留白得当、视觉重点突出
- 比例：3:4 竖版构图（适合手机浏览）

【风格参考】
- 美食：诱人的食物特写，暖色调打光
- 穿搭：时尚感穿搭展示，简约背景
- 家居：温馨舒适的生活场景，ins风或日系风
- 知识/干货：清新简约的图文排版，扁平插画
- 其他：根据内容匹配最适合的小红书流行风格

请生成一张高质量、有吸引力的图片。"""

    # 备用提示词列表（首次生成失败时使用）
    # 这些是通用的小红书风格提示词，不依赖具体内容
    FALLBACK_PROMPTS = [
        "小红书风格，明亮温暖的生活场景，咖啡和书本，柔和自然光，3:4竖版构图",
        "小红书风格，创意工作台，文具和绿植，ins风格，3:4竖版构图",
        "小红书风格，清新简约的扁平插画，渐变色背景，3:4竖版构图",
    ]

    def __init__(self):
        """
        初始化图片服务

        环境变量配置：
          IMAGE_API_KEY：Gemini API 密钥
          IMAGE_BASE_URL：API 端点，默认为火山引擎的 Doubao 端点
          IMAGE_MODEL：图片生成模型，默认为 gemini-3-pro-image-preview
        """
        self.api_key = os.getenv("IMAGE_API_KEY", "")
        self.base_url = os.getenv("IMAGE_BASE_URL", "https://cn-beijing.yuannengai.com")
        self.model = os.getenv("IMAGE_MODEL", "gemini-3-pro-image-preview")

        # 创建图片存储目录
        self.image_dir = Path("static/images/generated")
        self.image_dir.mkdir(parents=True, exist_ok=True)

        # 验证 API Key
        if not self.api_key:
            raise ValueError("IMAGE_API_KEY 未配置")

    def _build_api_url(self) -> str:
        """
        构建 Gemini API URL

        返回值：
          完整的 API 端点 URL
        """
        return f"{self.base_url}/v1beta/models/{self.model}:generateContent"

    def _save_image(self, image_base64: str, prefix: str = "xhs") -> str:
        """
        将 base64 图片数据解码并保存到本地文件

        ==========================================================================
        工作流程：
          1. 生成文件名（时间戳 + UUID）
          2. base64 解码为二进制数据
          3. 写入 static/images/generated/ 目录
          4. 返回访问路径

        文件命名格式：
          xhs_20240101_120000_abc123.png
          前缀_年月日_时分秒_唯一ID.png

        返回值：
          HTTP 访问路径，如 /static/images/generated/xhs_xxx.png
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{prefix}_{timestamp}_{unique_id}.png"

        file_path = self.image_dir / filename

        # base64 解码并写入文件
        with open(file_path, "wb") as f:
            f.write(base64.b64decode(image_base64))

        # 返回 HTTP 访问路径（供前端 <img src="..."> 使用）
        return f"/static/images/generated/{filename}"

    async def _call_gemini_api(self, prompt: str) -> Optional[str]:
        """
        调用 Gemini 图片生成 API

        ==========================================================================
        工作流程：
          1. 构造 HTTP 请求（POST JSON）
          2. 发送请求（120 秒超时）
          3. 解析响应，提取 base64 图片数据
          4. 返回 base64 字符串

        请求格式：
          {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
          }

        响应格式：
          {
            "candidates": [{
              "content": {
                "parts": [{
                  "inlineData": {"data": "...base64...", "mimeType": "image/png"}
                }]
              }
            }]
          }

        返回值：
          base64 编码的图片数据（如失败返回 None）

        错误处理：
          - HTTP 状态码错误：打印日志，返回 None
          - 响应无图片数据：打印日志，返回 None
          - 网络异常：打印日志，返回 None
        """
        url = self._build_api_url()

        # 请求体
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            # 要求返回 IMAGE 和 TEXT 两种模态
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
        }

        # 请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            # httpx：现代异步 HTTP 客户端（比 requests 更适合异步代码）
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()  # HTTP 错误码抛异常
                result = response.json()

                # 从响应中提取 base64 图片数据
                if "candidates" in result and result["candidates"]:
                    for part in result["candidates"][0]["content"]["parts"]:
                        if "inlineData" in part:
                            return part["inlineData"]["data"]

                # 响应中没有图片数据
                print(f"[ImageService] API 响应中未找到图片数据")
                return None

        except httpx.HTTPStatusError as e:
            # HTTP 状态码错误（如 401 未授权、429 请求过多）
            print(f"[ImageService] HTTP 错误: {e.response.status_code}")
            return None
        except Exception as e:
            # 其他异常（网络超时、JSON 解析错误等）
            print(f"[ImageService] 请求异常: {e}")
            return None

    async def generate_single_image(
        self,
        prompt: str,
        optimize_for_xhs: bool = True,
    ) -> Optional[str]:
        """
        生成单张图片（失败时使用备用提示词重试一次）

        ==========================================================================
        工作流程：
          1. 如果开启了小红书风格优化，包装提示词
          2. 首次调用 Gemini API
          3. 如果失败，用备用提示词重试
          4. 返回访问路径

        为什么需要备用提示词？
          Gemini API 可能因为网络、限流等原因失败
          备用提示词是通用风格，不依赖具体内容
          可以确保至少有图片返回

        参数详解：
          - prompt：配图描述（如 "温暖的学习场景，程序员深夜编程"）
          - optimize_for_xhs：是否包装成小红书风格模板
            True：套用 XHS_STYLE_PROMPT 模板
            False：直接用 prompt 作为生成提示词

        返回值：
          图片访问路径（如 "/static/images/generated/xhs_xxx.png"）
          失败返回 None
        """
        # ---------- 第 1 步：包装提示词 ----------
        if optimize_for_xhs:
            current_prompt = self.XHS_STYLE_PROMPT.format(content=prompt)
        else:
            current_prompt = prompt

        print(f"[ImageService] 生成图片: {prompt[:50]}...")

        # ---------- 第 2 步：首次尝试 ----------
        image_base64 = await self._call_gemini_api(current_prompt)
        if image_base64:
            image_path = self._save_image(image_base64)
            print(f"[ImageService] 图片生成成功: {image_path}")
            return image_path

        # ---------- 第 3 步：备用提示词重试 ----------
        print(f"[ImageService] 首次失败，使用备用提示词重试...")
        await asyncio.sleep(1)  # 等待 1 秒，避免频繁请求

        fallback_prompt = random.choice(self.FALLBACK_PROMPTS)
        image_base64 = await self._call_gemini_api(fallback_prompt)
        if image_base64:
            image_path = self._save_image(image_base64)
            print(f"[ImageService] 备用提示词成功: {image_path}")
            return image_path

        # ---------- 第 4 步：全部失败 ----------
        print(f"[ImageService] 图片生成失败，跳过")
        return None

    async def generate_images(
        self,
        visual_points: List[str],
        optimize_for_xhs: bool = True,
    ) -> List[str]:
        """
        批量生成配图（并行执行）

        ==========================================================================
        工作流程：
          1. 为每个配图要点创建 generate_single_image 任务
          2. asyncio.gather() 并行执行所有任务
          3. 过滤掉 None（失败的图片）
          4. 返回成功的图片路径列表

        为什么并行？
          每个配图生成是独立的 API 调用
          串行：3 张图片需要 3 x 10s = 30s
          并行：3 张图片只需要 ~10s（取决于最慢的那个）

        参数详解：
          - visual_points：配图描述列表（如 ["场景1", "场景2", "场景3"]）
          - optimize_for_xhs：是否开启小红书风格优化

        返回值：
          成功的图片 URL 列表（如 ["/static/...", "/static/..."]）
          失败的不包含在内
        """
        if not visual_points:
            return []

        # ---------- 第 1 步：创建所有任务 ----------
        tasks = [
            self.generate_single_image(prompt=point, optimize_for_xhs=optimize_for_xhs)
            for point in visual_points
        ]

        # ---------- 第 2 步：并行执行 ----------
        results = await asyncio.gather(*tasks)

        # ---------- 第 3 步：过滤成功的结果 ----------
        # gather 返回的结果包含 None（失败的），过滤掉
        image_paths = [path for path in results if path is not None]

        print(f"[ImageService] 成功生成 {len(image_paths)}/{len(visual_points)} 张图片")
        return image_paths


# =============================================================================
# 单例实例
# =============================================================================

# 全局单例，整个项目复用同一个 ImageService 实例
image_service = ImageService()
