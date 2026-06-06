"""
图片生成服务。

拿到文案或视觉描述后，这里会去调用方舟的画图接口，
把结果落到本地，再把可访问的图片路径返回出去。
"""
import warnings
import os
import uuid
import asyncio
import httpx
import base64
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

warnings.filterwarnings("ignore", message="Unverified HTTPS request")


class ImageGenerationError(RuntimeError):
    """图片生成失败"""


load_dotenv()


class ImageService:
    """
    通过火山引擎方舟 Ark 平台生成图片

    图片会保存到 static/images/generated/ 目录。
    """

    # 小红书风格 prompt 模板
    XHS_STYLE_PROMPT = """请根据以下内容生成一张小红书风格的爆款配图：

【内容主题】
{content}

【图片要求】
- 风格：小红书流行的高质感、精致感、氛围感风格
- 色调：明亮温暖、柔和治愈、或高级感色调
- 构图：简洁大气、留白得当、视觉重点突出
- 比例：3:4 竖版构图（适合手机浏览）

请生成一张高质量、有吸引力的图片。"""

    # 备用 prompt（生成失败时降级用）
    FALLBACK_PROMPTS = [
        "小红书风格，明亮温暖的生活场景，咖啡和书本，柔和自然光，3:4竖版构图",
        "小红书风格，创意工作台，文具和绿植，ins风格，3:4竖版构图",
        "小红书风格，清新简约的扁平插画，渐变色背景，3:4竖版构图",
    ]

    DEFAULT_MODEL = "doubao-seedream-4-0-250828"

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        self.model = self.DEFAULT_MODEL

        self.image_dir = Path("static/images/generated")
        self.image_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_key:
            raise ValueError(
                "LLM_API_KEY 未配置。请确保 .env 中有 LLM_API_KEY（方舟 Ark 平台的 API Key）。"
            )

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def _generate_one(self, prompt: str) -> Optional[bytes]:
        """
        调方舟 API 生成一张图片，返回图片二进制数据或 None
        """
        url = f"{self.base_url}/images/generations"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": "2K",
            "response_format": "b64_json",
            "watermark": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                data = resp.json()

            if resp.status_code != 200:
                self._log(f"[ImageService] HTTP {resp.status_code}: {data}")
                return None

            image_data = data.get("data", [])
            if not image_data:
                self._log(f"[ImageService] 返回数据为空: {data}")
                return None

            b64_img = image_data[0].get("b64_json", "")
            if b64_img:
                return base64.b64decode(b64_img)

            # 如果返回的是 URL 而不是 base64，就下载
            url_img = image_data[0].get("url", "")
            if url_img:
                async with httpx.AsyncClient(timeout=60.0, verify=False) as c2:
                    img_resp = await c2.get(url_img)
                    img_resp.raise_for_status()
                    return img_resp.content

            self._log(f"[ImageService] 两种格式都没有: {data}")
            return None

        except httpx.TimeoutException:
            self._log("[ImageService] 请求超时")
            return None
        except Exception as e:
            self._log(f"[ImageService] 生成失败: {e}")
            return None

    async def generate_single_image(
        self,
        prompt: str,
        optimize_for_xhs: bool = True,
    ) -> Optional[str]:
        """
        生成一张图片，返回保存后的访问路径或 None
        """
        if optimize_for_xhs:
            prompt = self.XHS_STYLE_PROMPT.format(content=prompt)

        print(f"[ImageService] 生成图片: {prompt[:50]}...")

        image_data = await self._generate_one(prompt)

        # 主 prompt 失败，用备用 prompt 降级
        if not image_data:
            print("[ImageService] 主 prompt 失败，尝试备用 prompt...")
            image_data = await self._generate_one(
                FALLBACK_PROMPTS[uuid.uuid4().int % len(self.FALLBACK_PROMPTS)]
            )

        if not image_data:
            return None

        # 保存到本地
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"xhs_{timestamp}_{unique_id}.png"
        file_path = self.image_dir / filename

        with open(file_path, "wb") as f:
            f.write(image_data)

        path = f"/static/images/generated/{filename}"
        print(f"[ImageService] 保存成功: {path} ({len(image_data) / 1024:.1f} KB)")
        return path

    async def generate_images(
        self,
        visual_points: List[str],
        optimize_for_xhs: bool = True,
    ) -> List[str]:
        """并行生成多张配图"""
        if not visual_points:
            return []

        tasks = [
            self.generate_single_image(point, optimize_for_xhs)
            for point in visual_points
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        image_paths = []
        for r in results:
            if isinstance(r, str) and r:
                image_paths.append(r)
            elif isinstance(r, Exception):
                print(f"[ImageService] 异常: {type(r).__name__}: {r}")

        print(f"[ImageService] 生成结果: {len(image_paths)}/{len(visual_points)} 张成功")
        return image_paths

    def _log(self, msg: str):
        """写入日志文件"""
        try:
            p = Path("logs/image_service.log")
            p.parent.mkdir(exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] {msg}\n")
        except Exception:
            pass


image_service = ImageService()
