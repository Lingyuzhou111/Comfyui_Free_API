# -*- coding: utf-8 -*-
"""
Gaga.art 图生视频节点（Image to Video）
- 输入:
    - image (必填): ComfyUI IMAGE 张量
    - prompt(必填): 文本提示词
- 可选:
    - aspectRatio: 下拉，仅 16:9（默认 16:9）
    - duration: 下拉，5 或 10（默认 10）
    - cropArea_x: 裁剪区域起点X（默认 0）
    - cropArea_y: 裁剪区域起点Y（默认 0）
- 输出:
    - video_url (STRING): 最终生成视频直链，对应 API 的 resultVideoURL
- 配置:
    - 同目录 gaga_config.json:
        {
          "base_url": "https://gaga.art",
          "cookie": "session=...; _ga=...; ...",  # 注意：整段 Cookie 作为一个字符串，不拆分
          "headers": {
            "user-agent": "Mozilla/5.0 ... Chrome/141 Safari/537.36"
          },
          "timeouts": {
            "connect": 10,
            "read": 20,
            "poll_interval": 3,
            "poll_timeout_secs": 300
          },
          "model": "test-performer",
          "defaults": {
            "resolution": "540p",
            "enhancementType": "i2v_performer_performer-v3-6_gemini",
            "nSampleSteps": 32,
            "enablePromptEnhancement": true,
            "enableWatermark": true
          }
        }
- 注意:
    1) 严格使用配置文件中的 base_url 与 cookie，不在代码中硬编码敏感值；
    2) 上传图片使用 multipart/form-data，不打印实际图像内容；
    3) cropArea 的 width/height 将根据 16:9 比例与图片尺寸自动计算并被边界裁剪。
"""

import os
import io
import json
import time
from typing import Tuple, Any, Dict, Optional

import torch
import requests
from PIL import Image

import logging
logger = logging.getLogger(__name__)


class GagaAvartI2VNode:
    """
    Gaga.art 图生视频：上传图像 -> 提交生成任务 -> 轮询结果 -> 返回视频URL
    """
    def __init__(self):
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.plugin_dir, "gaga_config.json")
        self.config = self._load_config()

    def _preview_text(self, text: str, limit: int = 120) -> str:
        try:
            if not isinstance(text, str):
                return str(text)
            return text if len(text) <= limit else text[:limit] + "..."
        except Exception:
            return str(text)

    def _safe_json_dumps(self, obj, ensure_ascii=False, indent=2):
        """
        精简打印：截断可能很长的字符串（特别是base64、data URL等）
        """
        import json as _json

        def _truncate(v):
            if not isinstance(v, str):
                return v
            try:
                # 截断典型的base64或data URL
                if len(v) > 100 and (
                    v.startswith("data:image/") or
                    v[:8] in ("iVBORw0K", "/9j/")
                ):
                    return v[:50] + f"... (len={len(v)})"
                return v
            except Exception:
                return v

        def _walk(x):
            if isinstance(x, dict):
                return {k: _walk(_truncate(val)) for k, val in x.items()}
            if isinstance(x, list):
                return [_walk(_truncate(i)) for i in x]
            return _truncate(x)

        try:
            return _json.dumps(_walk(obj), ensure_ascii=ensure_ascii, indent=indent)
        except Exception:
            try:
                return _json.dumps(obj, ensure_ascii=ensure_ascii)
            except Exception:
                return str(obj)

    def _load_config(self) -> Dict[str, Any]:
        try:
            if not os.path.exists(self.config_path):
                return {}
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 默认值填充
            cfg.setdefault("base_url", "https://gaga.art")
            cfg.setdefault("headers", {})
            cfg.setdefault("timeouts", {})
            t = cfg["timeouts"]
            t.setdefault("connect", 10)
            t.setdefault("read", 20)
            t.setdefault("poll_interval", 3)
            t.setdefault("poll_timeout_secs", 300)
            cfg.setdefault("model", "test-performer")
            cfg.setdefault("defaults", {})
            d = cfg["defaults"]
            d.setdefault("resolution", "540p")
            d.setdefault("enhancementType", "i2v_performer_performer-v3-6_gemini")
            d.setdefault("nSampleSteps", 32)
            d.setdefault("enablePromptEnhancement", True)
            d.setdefault("enableWatermark", True)
            return cfg
        except Exception:
            return {}

    def _is_config_ready(self) -> bool:
        if not self.config:
            return False
        if not isinstance(self.config.get("base_url"), str):
            return False
        cookie = self.config.get("cookie", "")
        return isinstance(cookie, str) and len(cookie.strip()) > 0

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "作为图生视频的输入图片"}),
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "视频的文本提示词"}),
            },
            "optional": {
                "aspectRatio": (["16:9", "9:16"], {"default": "16:9", "tooltip": "当前仅支持16:9"}),
                "duration": ([5, 10], {"default": 10, "tooltip": "视频时长(秒)"}),
                "enableWatermark": ("BOOLEAN", {"default": False, "tooltip": "是否添加水印"}),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING",)
    RETURN_NAMES = ("video", "generation_info",)
    FUNCTION = "imagine_i2v"
    CATEGORY = "🦉FreeAPI/Gaga"

    # 将 ComfyUI IMAGE 张量保存为 PNG 并返回 字节数据（不落盘）
    def _image_tensor_to_png_bytes(self, image_tensor: torch.Tensor) -> bytes:
        if image_tensor is None:
            raise ValueError("image is None")
        if len(image_tensor.shape) == 4:
            image_tensor = image_tensor[0]
        image_tensor = torch.clamp(image_tensor, 0, 1)
        img_np = (image_tensor.cpu().numpy() * 255).astype("uint8")
        img_pil = Image.fromarray(img_np)
        buf = io.BytesIO()
        img_pil.save(buf, format="PNG")
        return buf.getvalue()

    def _headers(self) -> Dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "origin": self.config.get("base_url", "https://gaga.art"),
            "referer": f'{self.config.get("base_url", "https://gaga.art").rstrip("/")}/app',
        }
        # 可选 UA
        ua = (self.config.get("headers") or {}).get("user-agent")
        if ua:
            headers["user-agent"] = ua
        cookie_str = (self.config.get("cookie") or "").strip()
        if cookie_str:
            headers["cookie"] = cookie_str
        return headers

    def _upload_image(self, png_bytes: bytes) -> Dict[str, Any]:
        """
        POST {base_url}/api/v1/assets
        返回包含 id, width, height, url 等字段
        """
        url = f'{self.config["base_url"].rstrip("/")}/api/v1/assets'
        headers = self._headers()
        # 重要：requests 自动设置 multipart boundary，不要手动设置 content-type
        files = {
            "file": ("comfy_image.png", png_bytes, "image/png")
        }
        t = self.config["timeouts"]
        # 日志：请求摘要（不打印图像内容）
        try:
            logger.info(f"[GagaI2V] 请求: POST {url}")
            logger.info(f'[GagaI2V] 上传载荷摘要: {{"file": "comfy_image.png", "mime": "image/png", "bytes_len": {len(png_bytes)}}}')
        except Exception:
            pass
        resp = requests.post(url, headers=headers, files=files, timeout=(t["connect"], t["read"]))
        if resp.status_code != 200:
            # 截断错误文本，避免刷屏
            text = (resp.text or "")[:200].replace("\n", " ")
            raise RuntimeError(f"上传图片失败: HTTP {resp.status_code} - {text}...")
        return resp.json()

    def _compute_crop(self, img_w: int, img_h: int, x: int, y: int) -> Dict[str, int]:
        """
        仅支持 16:9。基于图片尺寸优先用宽度计算高度，如果超出图像高度，则改为以高度反推宽度。
        并将 x,y 和 width,height 进行边界裁剪，保证落在图像内。
        """
        # 先按宽度计算 height
        target_h = round(img_w * 9 / 16)
        target_w = img_w
        if target_h > img_h:
            # 改为以高度推宽度
            target_h = img_h
            target_w = round(img_h * 16 / 9)
        # 边界裁剪 x,y
        x = max(0, min(x, max(0, img_w - target_w)))
        y = max(0, min(y, max(0, img_h - target_h)))
        return {"x": int(x), "y": int(y), "width": int(target_w), "height": int(target_h)}

    def _start_generation(self, asset_id: int, prompt: str, aspect_ratio: str, duration: int, crop_area: Dict[str, int], enable_watermark: bool) -> int:
        """
        POST {base_url}/api/v1/generations/performer
        返回任务 id
        """
        url = f'{self.config["base_url"].rstrip("/")}/api/v1/generations/performer'
        headers = self._headers()
        headers["content-type"] = "application/json"
        defaults = self.config.get("defaults", {})
        payload = {
            "model": self.config.get("model", "test-performer"),
            "aspectRatio": aspect_ratio,
            "taskType": "I2FV",
            "taskSource": "HUMAN",
            "source": {"type": "image", "content": str(asset_id)},
            "chunks": [{
                "duration": int(duration),
                "conditions": [{"type": "text", "content": prompt or ""}]
            }],
            "extraArgs": {
                "enablePromptEnhancement": bool(defaults.get("enablePromptEnhancement", True)),
                "cropArea": {
                    "x": crop_area["x"],
                    "y": crop_area["y"],
                    "width": crop_area["width"],
                    "height": crop_area["height"]
                },
                "extraInferArgs": {
                    "enhancementType": defaults.get("enhancementType", "i2v_performer_performer-v3-6_gemini"),
                    "nSampleSteps": int(defaults.get("nSampleSteps", 32)),
                    "resolution": defaults.get("resolution", "540p"),
                    "enableWatermark": bool(enable_watermark),
                    # 与示例保持字段存在性，采用安全默认
                    "specialTokens": [],
                    "vaeModel": "",
                    "extra": "",
                    "modelVersion": "",
                    "dryRun": False,
                    "enableInputVideoToTs": False
                },
                "tSchedulerFunc": "",
                "tSchedulerArgs": ""
            }
        }
        t = self.config["timeouts"]
        # 日志：提交生成任务的主要参数与安全JSON
        try:
            logger.info(f"[GagaI2V] 请求: POST {url}")
            logger.info(f"[GagaI2V] 任务主要参数 | model={payload.get('model')} | aspectRatio={payload.get('aspectRatio')} | duration={payload.get('chunks')[0].get('duration')} | cropArea={payload.get('extraArgs', {}).get('cropArea')}")
            logger.info(f"[GagaI2V] 任务载荷(精简): {self._safe_json_dumps(payload, indent=0)}")
        except Exception:
            pass
        resp = requests.post(url, headers=headers, json=payload, timeout=(t["connect"], t["read"]))
        if resp.status_code != 200:
            text = (resp.text or "")[:200].replace("\n", " ")
            raise RuntimeError(f"提交任务失败: HTTP {resp.status_code} - {text}...")
        data = resp.json()
        if "id" not in data:
            raise RuntimeError(f"提交任务异常：响应中缺少id字段: {data}")
        return int(data["id"])

    def _download_and_convert_video(self, video_url: str) -> Optional[Any]:
        """
        复用 DownloadVideoFromUrlNode 的同步实现，下载并转换为 ComfyUI VIDEO 对象。
        出错返回 None，保证节点稳定。
        """
        try:
            # 延迟导入，避免模块加载顺序问题
            try:
                from custom_nodes.Comfyui_Free_API.OpenAI_Node.download_video_from_url import DownloadVideoFromUrlNode
            except Exception:
                from ..OpenAI_Node.download_video_from_url import DownloadVideoFromUrlNode  # 相对导入兜底

            helper = DownloadVideoFromUrlNode()
            video_obj, status_info = helper.convert_url_to_video(
                video_url=video_url,
                timeout=120,
                max_retries=3,
                retry_delay=2,
                user_agent_type="Chrome桌面版",
                skip_url_test=False,
                custom_user_agent=""
            )
            if not hasattr(video_obj, "get_dimensions"):
                logger.info(f"[GagaI2V] ❌ 视频对象类型异常：{type(video_obj)}，缺少 get_dimensions()")
                return None
            try:
                logger.info(f"[GagaI2V] ✅ DownloadVideoFromUrl 状态:\n{status_info}")
            except Exception:
                pass
            return video_obj
        except Exception as e:
            logger.info(f"[GagaI2V] 视频下载转换过程出错: {e}")
            return None

    def _poll_generation(self, gen_id: int) -> Dict[str, Any]:
        """
        轮询 GET {base_url}/api/v1/generations/{id}?chunks=true
        获取 resultVideoURL
        """
        base = self.config["base_url"].rstrip("/")
        url = f"{base}/api/v1/generations/{gen_id}?chunks=true"
        headers = self._headers()
        t = self.config["timeouts"]
        interval = max(1, int(t.get("poll_interval", 3)))
        deadline = time.time() + int(t.get("poll_timeout_secs", 300))

        last_status = None
        while time.time() < deadline:
            resp = requests.get(url, headers=headers, timeout=(t["connect"], t["read"]))
            if resp.status_code != 200:
                # 网络/风控波动时继续
                time.sleep(interval)
                continue
            data = {}
            try:
                data = resp.json()
            except Exception:
                time.sleep(interval)
                continue

            status = str(data.get("status") or "")
            if status != last_status:
                last_status = status
                logger.info(f"[GagaI2V] 任务状态: {status}")

            # 完成则读取 URL
            if status == "Success":
                url_res = data.get("resultVideoURL") or (data.get("result") or {}).get("videoURL")
                try:
                    if url_res:
                        logger.info(f"[GagaI2V] ✅ 生成完成，视频URL: {url_res}")
                except Exception:
                    pass
                return data

            # 失败场景
            if status in {"Failed", "Error", "Canceled"}:
                raise RuntimeError(f"生成失败，状态: {status}")

            time.sleep(interval)

        raise TimeoutError("轮询超时，未获取到视频链接")

    def imagine_i2v(self, image: torch.Tensor, prompt: str,
                    aspectRatio: str = "16:9", duration: int = 10,
                    enableWatermark: bool = False) -> Tuple[Optional[Any], str]:
        """
        主流程：
        1) 将 IMAGE 编码为 PNG 字节
        2) 上传获得 asset id 与图像宽高
        3) 计算 16:9 裁剪区域（结合用户x/y与边界）
        4) 提交生成任务
        5) 轮询直到拿到 resultVideoURL 并返回
        """
        try:
            if not self._is_config_ready():
                return ("错误: gaga_config.json 配置不完整，请填写 base_url 与 cookie",)

            logger.info("[GagaI2V] 开始图生视频流程")
            if prompt:
                logger.info(f"[GagaI2V] 提示词(预览): {self._preview_text(prompt)}")
            # 1) 编码图像
            png_bytes = self._image_tensor_to_png_bytes(image)

            # 2) 上传图片
            asset_info = self._upload_image(png_bytes)
            asset_id = asset_info.get("id")
            img_w = int(asset_info.get("width") or 0)
            img_h = int(asset_info.get("height") or 0)
            if not asset_id or img_w <= 0 or img_h <= 0:
                return (f"错误: 上传图片响应异常: {json.dumps(asset_info, ensure_ascii=False)}",)

            # 3) 计算裁剪区域（仅 16:9）
            crop = self._compute_crop(img_w, img_h, 0, 0)

            # 4) 提交任务
            gen_id = self._start_generation(int(asset_id), prompt or "", aspectRatio, int(duration), crop, bool(enableWatermark))

            # 5) 轮询结果
            gen_data = self._poll_generation(gen_id)

            # 解析最终结果字段
            video_url = (gen_data.get("resultVideoURL")
                         or (gen_data.get("result") or {}).get("videoURL"))
            poster_url = (gen_data.get("resultPosterURL")
                          or (gen_data.get("result") or {}).get("posterURL"))
            width = (gen_data.get("width")
                     or (gen_data.get("result") or {}).get("width") or 0)
            height = (gen_data.get("height")
                      or (gen_data.get("result") or {}).get("height") or 0)
            status = str(gen_data.get("status") or "")
            status_cn = "已完成" if status == "Success" else ("进行中" if status == "Running" else status or "未知")
            task_id = gen_data.get("id")

            def _fmt_time(s: str) -> str:
                s = str(s or "")
                s = s.replace("T", " ")
                if "." in s:
                    s = s.split(".", 1)[0]
                if s.endswith("Z"):
                    s = s[:-1]
                return s

            create_time = _fmt_time(gen_data.get("createTime"))
            complete_time = _fmt_time(gen_data.get("estimateCompleteTime"))

            # 构造可读信息
            generation_info = (
                f"🔖 任务ID：{task_id}\n"
                f"♻️ 任务状态：{status_cn}\n"
                f"📐 视频宽高：{width}x{height}\n"
                f"⌚️ 创建时间：{create_time}\n"
                f"⏰ 完成时间：{complete_time}\n"
                f"🔗 图片链接：{poster_url or ''}\n"
                f"🔗 视频链接：{video_url or ''}"
            )

            # 下载并转换为 ComfyUI VIDEO 对象
            video_obj = self._download_and_convert_video(video_url) if video_url else None
            return (video_obj, generation_info)

        except Exception as e:
            return (None, f"错误: 执行异常: {e}")


# 节点注册
NODE_CLASS_MAPPINGS = {
    "Gaga_Avart_I2V": GagaAvartI2VNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Gaga_Avart_I2V": "🦉Gaga Actor 图生视频"
}