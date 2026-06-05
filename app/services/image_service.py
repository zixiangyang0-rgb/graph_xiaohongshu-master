"""
Image Generation Service - Volcengine Seedream v3.0 (Synchronous CVProcess API)
=============================================================================
Uses CVProcess (synchronous) instead of async submit/poll.
  - POST ?Action=CVProcess&Version=2022-08-31
  - Returns result immediately (no polling needed)
  - Auth: HMAC-SHA256 V4 via volcengine-python-sdk SignerV4
=============================================================================
"""
import os
import json
import uuid
import random
import httpx
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from volcenginesdkcore.signv4 import SignerV4
except ImportError:
    raise ImportError("volcengine-python-sdk not installed. Run: pip install volcengine-python-sdk")


class ImageService:
    """Image generation via Volcengine Seedream v3.0 (synchronous CVProcess)."""

    XHS_STYLE_PROMPT = """请根据以下内容生成一张小红书风格的爆款配图：

【内容主题】
{content}

【图片要求】
- 风格：小红书流行的高质感、精致感、氛围感风格
- 色调：明亮温暖、柔和治愈、或高级感色调
- 构图：简洁大气、留白得当、视觉重点突出
- 比例：3:4 竖版构图（适合手机浏览）

请生成一张高质量、有吸引力的图片。"""

    FALLBACK_PROMPTS = [
        "小红书风格，明亮温暖的生活场景，咖啡和书本，柔和自然光，3:4竖版构图",
        "小红书风格，创意工作台，文具和绿植，ins风格，3:4竖版构图",
        "小红书风格，清新简约的扁平插画，渐变色背景，3:4竖版构图",
    ]

    REQ_KEY = "high_aes_general_v20"  # Works with CVProcess

    def __init__(self):
        self.access_key = os.getenv("VOLC_ACCESS_KEY_ID", "")
        self.secret_key = os.getenv("VOLC_SECRET_ACCESS_KEY", "")
        self.base_url = os.getenv("IMAGE_API_BASE", "https://visual.volcengineapi.com")
        self.host = self.base_url.replace("https://", "").replace("http://", "")

        self.image_dir = Path("static/images/generated")
        self.image_dir.mkdir(parents=True, exist_ok=True)

        if not self.access_key or not self.secret_key:
            raise ValueError(
                "VOLC_ACCESS_KEY_ID and VOLC_SECRET_ACCESS_KEY must be configured. "
                "Get them from: https://console.volcengine.com/iam/keyman"
            )

    def _sign(self, body: str) -> dict:
        """Build HMAC-signed headers."""
        headers = {"Content-Type": "application/json", "Host": self.host}
        SignerV4.sign(
            path="/",
            method="POST",
            headers=headers,
            body=body,
            post_params=None,
            query={"Action": "CVProcess", "Version": "2022-08-31"},
            ak=self.access_key,
            sk=self.secret_key,
            region="cn-north-1",
            service="cv",
        )
        return headers

    async def _generate_sync(self, prompt: str) -> Optional[bytes]:
        """Call CVProcess synchronously. Returns image bytes or None."""
        body = json.dumps({
            "req_key": self.REQ_KEY,
            "prompt": prompt,
            "width": 1024,
            "height": 1360,
            "return_url": True,
        }, ensure_ascii=False)

        headers = self._sign(body)
        url = f"{self.base_url}/?Action=CVProcess&Version=2022-08-31"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, content=body.encode("utf-8"), headers=headers)
                data = resp.json()

                if data.get("code") == 10000:
                    image_urls = data.get("data", {}).get("image_urls", [])
                    if image_urls:
                        print(f"[ImageService] CVProcess success, URL: {image_urls[0][:60]}...")
                        # Download image
                        async with httpx.AsyncClient(timeout=60.0) as c2:
                            img_resp = await c2.get(image_urls[0])
                            img_resp.raise_for_status()
                            return img_resp.content
                    else:
                        binary_data = data.get("data", {}).get("binary_data_base64", [])
                        if binary_data:
                            import base64
                            return base64.b64decode(binary_data[0])

                err = data.get("message", str(data))
                self._log(f"[ImageService] CVProcess failed: {err[:200]}")
                return None

        except Exception as e:
            self._log(f"[ImageService] Exception: {type(e).__name__}: {e}")
            return None

    async def generate_single_image(
        self,
        prompt: str,
        optimize_for_xhs: bool = True,
    ) -> Optional[str]:
        """Generate one image. Returns access path or None."""
        if optimize_for_xhs:
            prompt = self.XHS_STYLE_PROMPT.format(content=prompt)
        print(f"[ImageService] Generating: {prompt[:50]}...")

        image_data = await self._generate_sync(prompt)
        if not image_data:
            print("[ImageService] Trying fallback prompt...")
            image_data = await self._generate_sync(random.choice(self.FALLBACK_PROMPTS))

        if not image_data:
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"xhs_{timestamp}_{unique_id}.png"
        file_path = self.image_dir / filename

        with open(file_path, "wb") as f:
            f.write(image_data)

        path = f"/static/images/generated/{filename}"
        print(f"[ImageService] Saved: {path} ({len(image_data)/1024:.1f} KB)")
        return path

    async def generate_images(
        self,
        visual_points: List[str],
        optimize_for_xhs: bool = True,
    ) -> List[str]:
        """Batch generate images in parallel."""
        if not visual_points:
            return []

        import asyncio
        tasks = [
            self.generate_single_image(point, optimize_for_xhs)
            for point in visual_points
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        image_paths = []
        for r in results:
            if isinstance(r, str):
                image_paths.append(r)
            elif isinstance(r, Exception):
                print(f"[ImageService] Exception: {type(r).__name__}")

        print(f"[ImageService] Generated {len(image_paths)}/{len(visual_points)} images")
        return image_paths

    def _log(self, msg: str):
        """Log to file (avoid GBK encoding issues on Windows)."""
        try:
            p = Path("logs/image_service.log")
            p.parent.mkdir(exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] {msg}\n")
        except Exception:
            pass


# =============================================================================
# Singleton
# =============================================================================

image_service = ImageService()
