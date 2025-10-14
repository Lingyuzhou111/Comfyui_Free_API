# -*- coding: utf-8 -*-
"""
Grok 图生视频节点（Image to Video）
- 需在grok_config.json 中配置好账号信息，详见插件目录下的README.md。
"""

import os
import io
import json
import time
import base64
import logging
from typing import Tuple, Any, Dict, Optional

import torch
import requests
from PIL import Image

# 优先使用 curl_cffi 模拟浏览器指纹（impersonate Chrome），不可用则回退到 requests
try:
    from curl_cffi import requests as cffi_requests
    _HAS_CFFI = True
except Exception:
    cffi_requests = None
    _HAS_CFFI = False

logger = logging.getLogger(__name__)

# 复用 grok2api 的动态请求头
try:
    import sys as _sys, os as _os
    _sys.path.append(_os.path.join(_os.path.dirname(__file__), "grok2api"))
    from app.services.grok.statsig import get_dynamic_headers as _grok_dynamic_headers
except Exception:
    _grok_dynamic_headers = None

class GrokImagineI2VNode:
    """
    Grok 图生视频：上传图像 -> 触发生成 -> 轮询进度 -> 返回最终视频URL
    """
    def __init__(self):
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.plugin_dir, "grok_config.json")
        self.config = self._load_config()
        # 当前激活账号的头与cookie
        self._active_headers: Dict[str, Any] = {}
        self._active_cookie: str = ""
        try:
            logger.info(f"[GrokI2V] 通道可用性 | curl_cffi={_HAS_CFFI}")
        except Exception:
            pass

    def _load_config(self) -> Dict[str, Any]:
        try:
            if not os.path.exists(self.config_path):
                logger.warning("[GrokI2V] 未找到 grok_config.json，请在同目录创建配置文件。")
                return {}
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 合理默认值
            cfg.setdefault("base_url", "https://grok.com")
            cfg.setdefault("assets_base_url", "https://assets.grok.com")
            cfg.setdefault("timeouts", {})
            cfg["timeouts"].setdefault("connect", 10)
            cfg["timeouts"].setdefault("read", 20)
            cfg["timeouts"].setdefault("poll_interval", 2)
            cfg["timeouts"].setdefault("poll_timeout_secs", 180)
            return cfg
        except Exception as e:
            logger.error(f"[GrokI2V] 读取配置失败: {e}")
            return {}

    def _is_config_ready(self) -> bool:
        if not self.config:
            return False
        if not self.config.get("base_url") or not self.config.get("assets_base_url"):
            return False
        # 支持多账号：若存在 _active_cookie 则以其为准
        cookie_str = self._active_cookie or ""
        return isinstance(cookie_str, str) and len(cookie_str.strip()) > 0

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "account": (["account_1", "account_2"], {"default": "account_1", "tooltip": "选择使用的Grok账号"}),
                "image": ("IMAGE", {"tooltip": "作为图生视频的输入图片"}),
            },
            "optional": {
                "mode": (["custom", "fun", "normal"], {"default": "normal", "tooltip": "生成模式"}),
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "仅在custom模式下生效，使用英文效果更佳"}),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("video", "generation_info")
    FUNCTION = "imagine_i2v"
    CATEGORY = "🦉FreeAPI/Grok"

    # 将 ComfyUI IMAGE 张量保存为 PNG 并返回 base64 字符串（不落盘）
    def _image_tensor_to_png_base64(self, image_tensor: torch.Tensor) -> str:
        try:
            if image_tensor is None:
                raise ValueError("image is None")
            if len(image_tensor.shape) == 4:
                image_tensor = image_tensor[0]  # 取第一张
            image_tensor = torch.clamp(image_tensor, 0, 1)
            img_np = (image_tensor.cpu().numpy() * 255).astype("uint8")
            img_pil = Image.fromarray(img_np)
            buf = io.BytesIO()
            img_pil.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            # 不在日志中打印完整base64，避免污染日志与泄露隐私
            return b64
        except Exception as e:
            raise RuntimeError(f"图像编码失败: {e}")

    def _build_cookies_header(self) -> str:
        """
        返回当前选择账号的整串 Cookie；若未选择则回退到全局配置
        """
        if isinstance(self._active_cookie, str) and self._active_cookie.strip():
            return self._active_cookie.strip()
        return str(self.config.get("cookie", "") or "").strip()

    def _base_headers(self, pathname: str = "/") -> Dict[str, str]:
        """
        统一使用 grok2api 的 get_dynamic_headers 指纹，并结合本地 grok_config.json：
        - 覆盖 Cookie 为整段 cookie
        - 若配置了 UA，则覆盖 User-Agent
        - 根据路径设置 Content-Type（upload-file 使用 text/plain，其余为 application/json）
        """
        base = self.config.get("base_url", "https://grok.com")
        # 优先使用当前选择账号的 headers；未设置则回退到全局
        cfg_headers = (self._active_headers or (self.config.get("headers") or {}))
        ua_cfg = cfg_headers.get("user-agent") or cfg_headers.get("User-Agent")

        # 先取 grok2api 的动态头；若不可用则退回空字典
        headers: Dict[str, str] = {}
        try:
            if _grok_dynamic_headers:
                headers = _grok_dynamic_headers(pathname=pathname) or {}
        except Exception:
            headers = {}

        # 覆盖/补充必要字段
        headers["Origin"] = base
        # 简化并回归稳定行为：upload-file 与 conversations/new 均使用 /imagine
        if "upload-file" in (pathname or ""):
            headers["Referer"] = f'{base.rstrip("/")}/imagine'
        elif "conversations/new" in (pathname or ""):
            headers["Referer"] = f'{base.rstrip("/")}/imagine'
        else:
            headers["Referer"] = f'{base.rstrip("/")}/'

        # 覆盖 UA（如果用户配置了）
        if ua_cfg:
            headers["User-Agent"] = ua_cfg
            headers["user-agent"] = ua_cfg
        # 每次请求生成新的 x-xai-request-id；并优先覆盖 x-statsig-id 为配置值（若提供）
        try:
            from uuid import uuid4 as _uuid4
            headers["x-xai-request-id"] = str(_uuid4())
        except Exception:
            pass
        # 使用固定的 x-statsig-id（来自配置），以兼容所有请求
        _cfg_statsig = cfg_headers.get("x-statsig-id")
        if _cfg_statsig:
            headers["x-statsig-id"] = _cfg_statsig

        # 补充语言与可选跟踪头（如配置提供）
        headers["Accept-Language"] = cfg_headers.get("accept-language", "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6")
        if "sentry-trace" in cfg_headers:
            headers["sentry-trace"] = cfg_headers["sentry-trace"]
        if "baggage" in cfg_headers:
            headers["baggage"] = cfg_headers["baggage"]

        # 设置 Content-Type（网页端 upload-file 使用 application/json）
        is_upload = "upload-file" in (pathname or "")
        headers["Content-Type"] = "application/json"
        headers["content-type"] = headers["Content-Type"]

        # 注入整段 Cookie
        cookie_str = self._build_cookies_header()
        if cookie_str:
            headers["Cookie"] = cookie_str
            headers["cookie"] = cookie_str

        return headers

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

    def _format_http_error(self, resp, hint_prefix: str) -> str:
        """
        生成简短的HTTP错误信息，避免把整页HTML打到日志/UI。
        """
        try:
            status = getattr(resp, "status_code", None)
            text = getattr(resp, "text", "")
            short = (text or "")[:200].replace("\n", " ")
            # 识别Cloudflare挑战页关键词
            if "Just a moment" in text or "/cdn-cgi/challenge-platform" in text:
                return f"{hint_prefix}: HTTP {status} - 可能被 Cloudflare 拦截，请更新 cookie(cf_clearance) 且保持相同出口IP/UA"
            return f"{hint_prefix}: HTTP {status} - {short}..."
        except Exception:
            return f"{hint_prefix}: HTTP 错误"

    def _post(self, url: str, headers: Dict[str, str], json_payload: Dict[str, Any], timeout):
        """
        统一 POST 入口（顺序：curl_cffi -> requests）：
        - 优先用 curl_cffi 模拟 Chrome；否则回退到 requests。
        - timeout: 元组 (connect, read) 将折算为单值总超时（秒）。
        """
        # 规范化超时
        total_timeout = None
        try:
            if isinstance(timeout, (tuple, list)) and len(timeout) >= 2:
                total_timeout = max(float(timeout[0]) + float(timeout[1]), float(timeout[1]))
            elif isinstance(timeout, (int, float)):
                total_timeout = float(timeout)
        except Exception:
            pass

        # 1) curl_cffi
        if '_HAS_CFFI' in globals() and _HAS_CFFI:
            try:
                logger.info(f"[GrokI2V] 使用 curl_cffi 发送: {url}")
                # 固定使用 chrome120 指纹（与你环境兼容），避免多版本尝试的复杂性
                s = cffi_requests.Session(impersonate="chrome120")
                _ct = headers.get("content-type", "")
                if isinstance(_ct, str) and _ct.lower().startswith("text/plain"):
                    resp = s.post(url, headers=headers, data=json.dumps(json_payload), timeout=total_timeout or timeout)
                else:
                    resp = s.post(url, headers=headers, json=json_payload, timeout=total_timeout or timeout)
                logger.info(f"[GrokI2V] curl_cffi 返回状态码: {getattr(resp, 'status_code', 'N/A')}")
                if getattr(resp, "status_code", 0) != 403:
                    return resp
                logger.warning("[GrokI2V] curl_cffi 返回 403")
            except Exception as e:
                logger.warning(f"[GrokI2V] curl_cffi 异常: {e}")


        # 3) requests 兜底
        logger.info(f"[GrokI2V] 回退 requests 发送: {url}")
        _ct = headers.get("content-type", "")
        if isinstance(_ct, str) and _ct.lower().startswith("text/plain"):
            return requests.post(url, headers=headers, data=json.dumps(json_payload), timeout=timeout)
        else:
            return requests.post(url, headers=headers, json=json_payload, timeout=timeout)

    def _upload_image(self, file_name: str, file_mime: str, b64_content: str) -> Dict[str, Any]:
        """
        上传图片到 Grok，返回包含 fileMetadataId, fileUri 等信息的 JSON
        POST: {base_url}/rest/app-chat/upload-file
        """
        url = f'{self.config["base_url"].rstrip("/")}/rest/app-chat/upload-file'
        payload = {
            "fileName": file_name,
            "fileMimeType": file_mime,
            "content": b64_content
        }
        headers = self._base_headers("/rest/app-chat/upload-file")
        t = self.config.get("timeouts", {})
        logger.info(f"[GrokI2V] 请求: POST {url}")
        # 完全不打印 base64 内容，仅打印长度，避免日志刷屏
        try:
            _content_len = len(b64_content) if isinstance(b64_content, str) else 0
        except Exception:
            _content_len = 0
        logger.info(f'[GrokI2V] 上传载荷: {{"fileName": "{file_name}", "fileMimeType": "{file_mime}", "content_len": {_content_len}}}')
        # 超时策略：先用配置超时；若超时则重试并放宽超时（connect≥30s, read≥90s）
        conn_to = int(self.config.get("timeouts", {}).get("connect", 10))
        read_to = int(self.config.get("timeouts", {}).get("read", 20))
        try:
            resp = self._post(url, headers, payload, (max(10, conn_to), max(20, read_to)))
        except requests.exceptions.Timeout:
            logger.warning("[GrokI2V] 上传超时，准备重试并放宽超时（connect>=30s, read>=90s）")
            resp = self._post(url, headers, payload, (max(30, conn_to), max(90, read_to)))
        logger.info(f"[GrokI2V] 响应状态码: {resp.status_code}")
        if resp.status_code == 403:
            logger.error("[GrokI2V] 收到 403，可能被 Cloudflare 拦截。请确认 cookie 中 cf_clearance 有效，且与当前出口 IP/UA 一致。")
        if resp.status_code != 200:
            raise RuntimeError(self._format_http_error(resp, "上传图片失败"))
        return resp.json()

    def _create_media_post(self, file_uri_full: str, mime_type: str = "image/png") -> Dict[str, Any]:
        """
        可选：创建媒体 Post（与 curl 第3步一致）。有助于兼容站内资产流。
        POST: {base_url}/rest/media/post/create
        """
        url = f'{self.config["base_url"].rstrip("/")}/rest/media/post/create'
        payload = {
            "mediaType": "MEDIA_POST_TYPE_IMAGE",
            "mediaUrl": file_uri_full
        }
        headers = self._base_headers("/rest/media/post/create")
        t = self.config.get("timeouts", {})
        logger.info(f"[GrokI2V] 请求: POST {url}")
        logger.info(f"[GrokI2V] 创建媒体载荷(精简): {self._safe_json_dumps(payload, indent=0)}")
        resp = self._post(url, headers, payload, (t["connect"], t["read"]))
        logger.info(f"[GrokI2V] 响应状态码: {resp.status_code}")
        if resp.status_code != 200:
            logger.warning(self._format_http_error(resp, "[GrokI2V] 创建媒体Post失败"))
            return {}
        return resp.json()

    def _poll_until_done(self, image_url_full: str, asset_id: str, mode: str = "normal", prompt: str = "") -> Optional[str]:
        """
        使用单次长请求等待服务端在同一响应中持续输出多段 JSON（与网页端一致）：
        - 保留 fileAttachments=[asset_id]，确保服务端将此请求识别为同一生成任务的延续
        - 覆盖 Referer 为 /imagine/post/{asset_id}
        - 单次请求总超时设置为 poll_timeout_secs（默认180s），避免 30s 被切断
        - 解析响应文本的每一行 JSON，直到提取到 streamingVideoGenerationResponse.videoUrl
        """
        base_url = self.config.get("base_url", "https://grok.com").rstrip("/")
        url = f'{base_url}/rest/app-chat/conversations/new'
        headers = self._base_headers("/rest/app-chat/conversations/new")
        # 覆盖 Referer 以贴近网页端行为
        try:
            headers["Referer"] = f'{base_url}/imagine/post/{asset_id}'
            headers["referer"] = headers["Referer"]
        except Exception:
            pass

        t = self.config.get("timeouts", {})
        poll_timeout_secs = int(t.get("poll_timeout_secs", 180))

        # 根据不同模式构造 message
        if mode == "custom" and prompt:
            # custom 模式：图片URL + 用户提示词 + --mode=custom
            message = f"{image_url_full}  {prompt} --mode=custom"
        elif mode == "fun":
            # fun 模式：图片URL + --mode=extremely-crazy
            message = f"{image_url_full}  --mode=extremely-crazy"
        else:
            # normal 模式（默认）：图片URL + --mode=normal
            message = f"{image_url_full}  --mode=normal"

        payload = {
            "temporary": True,
            "modelName": "grok-3",
            "message": message,
            "fileAttachments": [asset_id],
            "toolOverrides": {"videoGen": True}
        }
        logger.info(f"[GrokI2V] 开始长连接等待生成结果 | 单次超时: {poll_timeout_secs}s")
        try:
            # 单值超时用于 curl_cffi 的 total_timeout
            resp = self._post(url, headers, payload, poll_timeout_secs)
            if getattr(resp, "status_code", 0) != 200:
                logger.debug(f"[GrokI2V] 长请求HTTP{resp.status_code}: {getattr(resp, 'text', '')[:200]}")
                return None

            text = (getattr(resp, "text", "") or "").strip()
            if not text:
                logger.debug("[GrokI2V] 长请求返回空响应文本")
                return None

            # 从响应中逐行提取视频 URL
            import re as _re
            m = _re.search(r"/users/([^/]+)/", image_url_full)
            user_id = m.group(1) if m else None

            rel_or_full = self._extract_video_url(text, user_id)
            if rel_or_full:
                if rel_or_full.startswith("http"):
                    full_url = rel_or_full
                else:
                    full_url = f'{self.config["assets_base_url"].rstrip("/")}/{rel_or_full.lstrip("/")}'
                logger.info(f"[GrokI2V] ✅ 生成完成，视频URL: {full_url}")
                # 返回响应文本和视频URL，以便提取更多信息
                return text
            logger.debug("[GrokI2V] 未在长请求响应中提取到视频URL")
            return None
        except Exception as e:
            logger.debug(f"[GrokI2V] 长请求异常: {e}")
            return None

    def imagine_i2v(self, image: torch.Tensor, account: str = "account_1", mode: str = "normal", prompt: str = "") -> Tuple[str]:
        """
        主执行：
        1) 将 ComfyUI 的 IMAGE 张量转为 PNG base64
        2) 上传图片到 Grok -> 得到 fileMetadataId 与 fileUri
        3) 构造 assets 完整 URL
        4) 可选创建媒体 Post（非必须）
        5) 发起对话触发视频生成
        6) 轮询同一接口直到获取 videoUrl 相对路径，拼接为完整直链并返回
        """
        try:
            # 0) 选择账号：支持 grok_config.json.accounts 或单账号回退（必须先选择再校验）
            accs = self.config.get("accounts") or {}
            chosen = (accs.get(account) or {})
            # 当不存在 accounts 或缺少指定账号时，回退到全局 cookie/headers
            self._active_cookie = (chosen.get("cookie") or self.config.get("cookie") or "")
            self._active_headers = (chosen.get("headers") or self.config.get("headers") or {})
            if not self._active_cookie:
                return (None, f"错误: 未找到所选账号的 cookie，请在 grok_config.json 中配置 accounts.{account}.cookie")

            # 配置完整性校验（基于当前激活账号）
            if not self._is_config_ready():
                return (None, f"错误: grok_config.json 配置不完整，请填入 base_url / assets_base_url / cookie 等")
            # 检查 cf_clearance 是否存在（基于当前激活账号）
            cookie_str = (self._active_cookie or "").lower()
            if "cf_clearance=" not in cookie_str:
                logger.warning("[GrokI2V] cookie 中未检测到 cf_clearance，可能被 Cloudflare 拦截导致 403。请从浏览器复制最新整段 Cookie。")

            logger.info(f"[GrokI2V] 开始图生视频 | 模式: {mode}")
            if mode == "custom" and prompt:
                logger.info(f"[GrokI2V] 自定义提示词: {prompt}")
            elif prompt:
                logger.info(f"[GrokI2V] 当前模式({mode})不使用提示词，但提示词内容为: {prompt}")

            # 1) 编码图像
            b64 = self._image_tensor_to_png_base64(image)
            file_name = "ComfyUI_Image.png"
            file_mime = "image/png"

            # 2) 上传图片
            upload_info = self._upload_image(file_name, file_mime, b64)
            file_meta_id = upload_info.get("fileMetadataId")
            file_uri = upload_info.get("fileUri")  # 形如 users/{uid}/{assetId}/content
            if not file_meta_id or not file_uri:
                return (None, f"错误: 上传图片返回异常: {json.dumps(upload_info, ensure_ascii=False)}")

            image_url_full = f'{self.config["assets_base_url"].rstrip("/")}/{file_uri.lstrip("/")}'
            logger.info(f"[GrokI2V] 图片已上传: {image_url_full}")

            # 3) 可选创建媒体 Post（失败不影响主流程）
            try:
                self._create_media_post(image_url_full, file_mime)
            except Exception as e:
                logger.warning(f"[GrokI2V] 创建媒体Post失败(忽略): {e}")

            # 4) 直接使用单次长请求触发并等待生成完成（与网页端一致）
            logger.info(f"[GrokI2V] 请求模式: {mode} | 请求提示词: {prompt if prompt else '无'}")
            response_text = self._poll_until_done(image_url_full, file_meta_id, mode, prompt)
            if not response_text:
                return (None, "错误: 未能在超时时间内获取视频链接")

            # 5) 从响应中提取视频URL
            import re as _re
            m = _re.search(r"/users/([^/]+)/", image_url_full)
            user_id = m.group(1) if m else None
            video_url = self._extract_video_url(response_text, user_id)
            
            if not video_url:
                return (None, "错误: 无法从响应中提取视频链接")
            
            # 构造完整视频URL
            if not video_url.startswith("http"):
                video_url = f'{self.config["assets_base_url"].rstrip("/")}/{video_url.lstrip("/")}'
            
            # 6) 提取生成信息
            generation_info = self._extract_generation_info(response_text, image_url_full)
            if not generation_info:
                # 如果无法提取详细信息，则使用基本格式
                generation_info = f"🔗 视频链接：{video_url}"

            # 7) 将视频URL转换为 ComfyUI VIDEO 对象（可选）
            video_obj = None
            try:
                safe_url = str(video_url).replace("\\u0026", "&")
                if safe_url:
                    video_obj = self._download_and_convert_video(safe_url)
                    # 确保返回的对象不是 None
                    if video_obj is None:
                        logger.warning("[GrokI2V] VIDEO转换返回 None，将返回空字符串而不是 None")
                        video_obj = ""
            except Exception as e:
                logger.warning(f"[GrokI2V] VIDEO转换失败（已忽略，仅返回URL）: {e}")
                video_obj = ""  # 确保不会返回 None
            
            logger.info("[GrokI2V] 流程结束，返回视频对象与生成信息")
            return (video_obj, generation_info)

        except Exception as e:
            logger.error(f"[GrokI2V] 执行异常: {e}", exc_info=True)
            return (None, f"错误: 执行异常: {e}")

    def _extract_video_url(self, response_text: str, user_id: Optional[str]) -> Optional[str]:
        """
        逐行解析响应文本以提取生成的视频地址：
        - 优先读取 result.response.streamingVideoGenerationResponse.videoUrl
        - 其次尝试从 result.response.modelResponse.fileAttachments[0] 构造推断路径
        返回相对路径（users/...）或完整URL（http...），未找到则返回 None
        """
        try:
            lines = (response_text or "").strip().split("\n")
            for line in lines:
                line = line.strip()
                if not (line.startswith("{") and line.endswith("}")):
                    # 仅解析完整的 JSON 行
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                result = obj.get("result") or {}
                response = result.get("response") or {}

                # 1) 直接视频地址 + 进度
                stream = response.get("streamingVideoGenerationResponse") or {}
                if isinstance(stream, dict):
                    try:
                        prog = int(stream.get("progress", -1))
                        if prog >= 0:
                            # 移除重复的日志显示，只在想象节点中显示进度
                            pass
                    except Exception:
                        pass
                    rel_or_full = stream.get("videoUrl")
                    if isinstance(rel_or_full, str) and rel_or_full.strip():
                        return rel_or_full.strip()

                # 2) 从附件推断生成视频路径
                model_resp = response.get("modelResponse") or {}
                if isinstance(model_resp, dict):
                    files = model_resp.get("fileAttachments") or []
                    if isinstance(files, list) and len(files) > 0:
                        vid = str(files[0]).strip()
                        if vid and user_id:
                            return f"users/{user_id}/generated/{vid}/generated_video.mp4"

            return None
        except Exception as e:
            logger.debug(f"[GrokI2V] 提取视频URL时出现错误: {e}")
            return None

    def _download_and_convert_video(self, video_url: str) -> Optional[Any]:
        """
        使用 curl_cffi 直接下载视频并转换为 ComfyUI VIDEO 对象。
        - 仅保留这一条路径，删除其他下载方式，减少无效重试与资源占用
        - 失败返回 None，不影响第一个输出 video_url 的稳定性
        """
        try:
            # 必须具备 curl_cffi 能力
            if not ('_HAS_CFFI' in globals() and _HAS_CFFI and cffi_requests is not None):
                logger.info("[GrokI2V] curl_cffi 不可用，跳过视频下载")
                return None

            from comfy_api.input_impl import VideoFromFile as _VideoFromFile
            import tempfile as _tempfile

            base_url = self.config.get("base_url", "https://grok.com").rstrip("/")
            # 优先使用当前激活账号的 UA，其次使用配置 UA，最后给一个稳定默认值
            ua = (
                self._active_headers.get("user-agent")
                or self._active_headers.get("User-Agent")
                or (self.config.get("headers", {}) or {}).get("user-agent")
                or (self.config.get("headers", {}) or {}).get("User-Agent")
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
            )
            cookie_str = self._build_cookies_header()

            # 使用浏览器指纹模拟
            s = cffi_requests.Session(impersonate="chrome120")
            s.headers.update({
                "User-Agent": ua,
                "Cookie": cookie_str or "",
                "Origin": base_url,
                "Referer": f"{base_url}/imagine",
                "Accept": "*/*",
                "Accept-Language": self._active_headers.get("accept-language", "zh-CN,zh;q=0.9,en;q=0.8"),
                "Connection": "keep-alive",
            })

            # 下载超时：读取 + 轮询窗口（保证足够的单次超时）
            dl_timeout = int(self.config.get("timeouts", {}).get("read", 20)) + int(self.config.get("timeouts", {}).get("poll_timeout_secs", 180))
            resp = s.get(video_url, timeout=dl_timeout, stream=True, allow_redirects=True)
            status = getattr(resp, "status_code", 0)
            if status != 200:
                logger.info(f"[GrokI2V] curl_cffi 下载失败，HTTP {status}")
                try:
                    resp.close()
                except Exception:
                    pass
                return None

            # 保存为临时文件（不自动删除，交由 ComfyUI VIDEO 对象管理）
            tmp = _tempfile.NamedTemporaryFile(prefix="grok_video_", suffix=".mp4", delete=False)
            tmp_path = tmp.name
            with tmp as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            try:
                resp.close()
            except Exception:
                pass

            logger.info(f"[GrokI2V] ✅ curl_cffi 下载成功 -> {tmp_path}")
            return _VideoFromFile(tmp_path)

        except Exception as e:
            logger.info(f"[GrokI2V] curl_cffi 下载异常: {e}")
            return None
    def _extract_generation_info(self, response_text: str, image_url_full: str) -> Optional[str]:
        """
        从响应文本中提取生成信息，包括创建时间、图片链接、视频链接和视频提示（仅motion部分）
        """
        try:
            import re
            import json
            from datetime import datetime
            
            lines = (response_text or "").strip().split("\n")
            streaming_response = None
            model_response = None
            user_response = None
            
            # 提取 streamingVideoGenerationResponse、modelResponse 和 userResponse
            for line in lines:
                line = line.strip()
                if not (line.startswith("{") and line.endswith("}")):
                    continue
                try:
                    obj = json.loads(line)
                    result = obj.get("result") or {}
                    response = result.get("response") or {}
                    
                    # 获取 streamingVideoGenerationResponse (包含完整信息的最后一个)
                    stream = response.get("streamingVideoGenerationResponse")
                    if isinstance(stream, dict) and stream.get("videoUrl"):
                        # 只保存包含完整信息的响应（包含videoUrl和videoPrompt）
                        if stream.get("videoPrompt") and stream.get("progress") == 100:
                            streaming_response = stream
                        elif not streaming_response:
                            # 如果还没有找到完整的响应，先保存一个不完整的
                            streaming_response = stream
                    
                    # 获取 modelResponse
                    model = response.get("modelResponse")
                    if isinstance(model, dict):
                        model_response = model
                        
                    # 获取 userResponse (用于获取创建时间)
                    user = response.get("userResponse")
                    if isinstance(user, dict):
                        user_response = user
                except Exception:
                    continue
            
            if not streaming_response:
                return None
            
            # 提取创建时间
            create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 优先使用 userResponse 中的创建时间
            if user_response and user_response.get("createTime"):
                try:
                    # 解析 API 返回的创建时间
                    api_create_time = user_response.get("createTime")
                    # 处理时间格式
                    if "T" in api_create_time:
                        # 处理纳秒格式的时间
                        if "." in api_create_time and len(api_create_time.split(".")[-1]) > 6:
                            parts = api_create_time.split(".")
                            microsecond_part = parts[-1]
                            if "Z" in microsecond_part:
                                microsecond_part = microsecond_part[:-1]
                            # 只保留前6位微秒
                            microsecond_part = microsecond_part[:6].ljust(6, '0')
                            api_create_time = ".".join(parts[:-1]) + "." + microsecond_part + "Z"
                        dt = datetime.fromisoformat(api_create_time.replace("Z", "+00:00"))
                        create_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.debug(f"[GrokI2V] 解析创建时间时出现错误: {e}")
                    pass
            # 如果 userResponse 中没有创建时间，尝试使用 modelResponse 中的
            elif model_response and model_response.get("createTime"):
                try:
                    api_create_time = model_response.get("createTime")
                    if "T" in api_create_time:
                        # 处理纳秒格式的时间
                        if "." in api_create_time and len(api_create_time.split(".")[-1]) > 6:
                            parts = api_create_time.split(".")
                            microsecond_part = parts[-1]
                            if "Z" in microsecond_part:
                                microsecond_part = microsecond_part[:-1]
                            microsecond_part = microsecond_part[:6].ljust(6, '0')
                            api_create_time = ".".join(parts[:-1]) + "." + microsecond_part + "Z"
                        dt = datetime.fromisoformat(api_create_time.replace("Z", "+00:00"))
                        create_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.debug(f"[GrokI2V] 解析创建时间时出现错误: {e}")
                    pass
            
            # 提取图片链接
            image_link = streaming_response.get("imageReference", image_url_full)
            
            # 提取视频链接并确保完整
            video_url = streaming_response.get("videoUrl", "")
            # 如果视频链接不是完整的URL，补全前缀
            if video_url and not video_url.startswith("http"):
                video_url = f'{self.config.get("assets_base_url", "https://assets.grok.com").rstrip("/")}/{video_url.lstrip("/")}'
            
            # 提取视频提示中的 motion 信息
            video_prompt = streaming_response.get("videoPrompt", {})
            motion_info = ""
            if isinstance(video_prompt, str):
                try:
                    # 如果是字符串，尝试解析为 JSON
                    video_prompt_json = json.loads(video_prompt)
                    motion_info = video_prompt_json.get("motion", "")
                    # 如果 motion 是字典，将其转换为字符串
                    if isinstance(motion_info, dict):
                        motion_info = json.dumps(motion_info, ensure_ascii=False, indent=2)
                except Exception:
                    # 如果不是 JSON 格式，则直接使用部分内容
                    motion_info = video_prompt
            elif isinstance(video_prompt, dict):
                motion_info = video_prompt.get("motion", "")
                # 如果 motion 是字典，将其转换为字符串
                if isinstance(motion_info, dict):
                    motion_info = json.dumps(motion_info, ensure_ascii=False, indent=2)
            
            # 如果 motion_info 仍然为空，尝试从其他字段获取相关信息
            if not motion_info:
                # 尝试从 shot 字段获取 camera_movement 信息
                if isinstance(video_prompt, dict):
                    shot = video_prompt.get("shot", {})
                    if isinstance(shot, dict):
                        camera_movement = shot.get("camera_movement", "")
                        motion_info = camera_movement
            
            # 如果仍然没有 motion 信息，使用简化的描述
            if not motion_info:
                motion_info = "视频生成完成"
            
            # 构造格式化的生成信息
            generation_info = f"⏰ 创建时间：{create_time}\n"
            generation_info += f"🌄 图片链接：{image_link}\n"
            generation_info += f"🔗 视频链接：{video_url}\n"
            generation_info += f"📺 视频提示：\n{motion_info}"
            
            return generation_info
        except Exception as e:
            logger.debug(f"[GrokI2V] 提取生成信息时出现错误: {e}")
            return None

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Grok_Imagine_I2V": GrokImagineI2VNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Grok_Imagine_I2V": "🦉Grok 图生视频"
}