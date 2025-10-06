import json
import requests
import os
from typing import Optional, Any


CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),
    "sora_api.json"
)


def _load_provider_conf(api_provider: str) -> dict:
    """
    从 sora_api.json 加载指定平台的配置：
    {
      "302": {"base_url":"...", "async_suffix":"/sora/v2/video", "model":"sora-2", "api_key":"..."},
      "T8star": {"base_url":"...", "async_suffix":"/v2/videos/generations", "model":"sora_video2", "api_key":"..."}
    }
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        conf = data.get(api_provider or "")
        if not isinstance(conf, dict):
            raise ValueError(f"配置中未找到提供者: {api_provider}")
        base_url = (conf.get("base_url") or "").strip().rstrip("/")
        async_suffix = (conf.get("async_suffix") or "").strip()
        model = (conf.get("model") or "").strip()
        api_key = (conf.get("api_key") or "").strip()
        if not base_url:
            raise ValueError(f"{api_provider} 的 base_url 未配置")
        if not api_key:
            raise ValueError(f"{api_provider} 的 api_key 未配置")
        # 默认模型兜底
        if not model:
            model = "sora-2" if api_provider == "302" else "sora_video2"
        # async_suffix 默认兜底，兼容未配置场景
        if not async_suffix:
            async_suffix = "/sora/v2/video" if api_provider == "302" else "/v2/videos/generations"
        return {"base_url": base_url, "async_suffix": async_suffix, "model": model, "api_key": api_key}
    except FileNotFoundError:
        raise RuntimeError(f"缺少配置文件: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"配置文件 JSON 解析失败: {e}")
    except Exception as e:
        raise RuntimeError(f"加载配置失败: {e}")


class OpenAISoraAPIAsyncSubmit:
    """
    ComfyUI 自定义节点：提交 Sora 异步视频生成任务（支持 302 与 t8star 平台）
    - 从 sora_api.json 读取 base_url、model、api_key
    - 302:
        - POST {base_url}/sora/v2/video
        - 请求体: {"model": "sora-2", "orientation": "portrait|landscape", "prompt": "...", "images": ["data:image/png;base64,..."]?}
        - 响应: {"code":200,"data":{"id":"sora-2:task_xxx", ...}}
    - t8star:
        - POST {base_url}/v2/videos/generations
        - 请求体: {"prompt":"...", "model":"sora_video2", "images":["..."]?, "aspect_ratio":"9:16|16:9", "hd":true|false, "duration":"10|15"}
        - 响应: {"task_id": "uuid"}
    - 输出: task_id (字符串)
    """

    _last_task_id: Optional[str] = None

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (["302", "T8star"],),
                "prompt": ("STRING", {"default": "请描述要生成的视频内容", "multiline": True}),
                "aspect_ratio": (["9:16", "16:9"],),

            },
            "optional": {
                "image": ("IMAGE",),
                "duration": (["10", "15"],),
                "hd": ("BOOLEAN", {"default": False}),
                "is_locked": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("task_id",)
    FUNCTION = "submit"
    CATEGORY = "🦉FreeAPI/OpenAI"

    def submit(self, api_provider: str, prompt: str,
               aspect_ratio: str, is_locked: bool = False, hd: Optional[bool] = False,
               duration: Optional[str] = None, image=None):
        """
        提交异步视频生成任务，返回 task_id。
        - is_locked == "true" 时：返回缓存的 task_id
        - 读取 sora_api.json 获取 base_url、model、api_key
        """
        if bool(is_locked):
            if self.__class__._last_task_id:
                print(f"[OpenAISoraAPIAsyncSubmit] is_locked=true，返回缓存 task_id: {self.__class__._last_task_id}")
                return (self.__class__._last_task_id,)
            else:
                return ("错误：is_locked 为 true 但没有可用缓存 task_id，请先在 is_locked=false 下提交一次任务",)

        if not prompt or not prompt.strip():
            return ("错误：prompt 为空",)
        if aspect_ratio not in ("9:16", "16:9"):
            return ("错误：aspect_ratio 必须为 9:16 或 16:9",)

        # 加载平台配置
        try:
            conf = _load_provider_conf(api_provider or "302")
        except Exception as e:
            return (f"配置错误：{e}",)

        base_url = conf["base_url"]
        async_suffix = conf.get("async_suffix") or ("/sora/v2/video" if api_provider == "302" else "/v2/videos/generations")
        model = conf["model"]
        api_key = conf["api_key"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # 根据纵横比在提示词末尾追加中文说明
        try:
            if aspect_ratio == "9:16":
                _ratio_suffix = "，竖屏portrait比例"
            else:
                _ratio_suffix = "，横屏landscape比例"
        except Exception:
            _ratio_suffix = ""
        prompt_final = (prompt or "").strip() + _ratio_suffix

        # 构造 URL 与载荷
        if api_provider == "302":
            url = f"{base_url}{async_suffix}"
            orientation = "portrait" if aspect_ratio == "9:16" else "landscape"
            payload = {
                "model": model,
                "orientation": orientation,
                "prompt": prompt_final,
            }
        elif api_provider == "T8star":
            url = f"{base_url}{async_suffix}"
            hd_bool = bool(hd)
            duration_str = str(duration or "10")
            if duration_str not in ("10", "15"):
                duration_str = "10"
            payload = {
                "prompt": prompt_final,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "hd": hd_bool,
                "duration": duration_str,
            }
        else:
            return (f"错误：不支持的 api_provider: {api_provider}",)

        # 图像输入处理
        if image is not None:
            try:
                data_url = self._image_to_data_url(image)
                if data_url:
                    payload["images"] = [data_url]
                    print("[OpenAISoraAPIAsyncSubmit] 已附带输入图像(image-to-video)，使用 data URL (已截断日志)")
            except Exception as e:
                return (f"输入图像处理失败: {e}",)

        try:
            print(f"[OpenAISoraAPIAsyncSubmit] 请求: POST {url}")
            print(f"[OpenAISoraAPIAsyncSubmit] 模型: {model} | 提供者: {api_provider}")
            _preview = (prompt[:120] + "...") if len(prompt) > 120 else prompt
            print(f"[OpenAISoraAPIAsyncSubmit] 提交Sora任务 | 提示词: {_preview}")
            print(f"[OpenAISoraAPIAsyncSubmit] 请求载荷(精简): {self._safe_json_dumps(payload)}")
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            print(f"[OpenAISoraAPIAsyncSubmit] 状态码: {resp.status_code}")

            if resp.status_code != 200:
                return (f"API错误(状态码 {resp.status_code}): {resp.text}",)

            data = resp.json()
            if not isinstance(data, dict):
                return ("API响应格式异常：非JSON对象",)

            if api_provider == "302":
                code = data.get("code")
                if code != 200:
                    return (f"API返回非200: {data}",)
                d = data.get("data") or {}
                task_id = d.get("id") or ""
            else:
                task_id = data.get("task_id") or ""

            if not task_id:
                return ("未获取到 task_id",)

            print(f"[OpenAISoraAPIAsyncSubmit] 成功提交任务: task_id={task_id}")
            self.__class__._last_task_id = task_id
            return (task_id,)
        except requests.exceptions.Timeout:
            return ("请求超时，请稍后重试",)
        except requests.exceptions.RequestException as e:
            return (f"网络错误: {e}",)
        except Exception as e:
            return (f"提交失败: {e}",)

    def _safe_json_dumps(self, obj, ensure_ascii=False, indent=2):
        import json as _json

        def _truncate_cand(v: str) -> str:
            if not isinstance(v, str):
                return v
            try:
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
                return {k: _walk(_truncate_cand(val)) for k, val in x.items()}
            if isinstance(x, list):
                return [_walk(_truncate_cand(i)) for i in x]
            return _truncate_cand(x)

        try:
            return _json.dumps(_walk(obj), ensure_ascii=ensure_ascii, indent=indent)
        except Exception:
            try:
                return _json.dumps(obj, ensure_ascii=ensure_ascii)
            except Exception:
                return str(obj)

    def _image_to_data_url(self, image) -> Optional[str]:
        try:
            from io import BytesIO
            import base64
            try:
                from PIL import Image as PILImage
            except Exception as e:
                raise RuntimeError(f"未安装 Pillow: {e}")

            pil_img = None

            if hasattr(image, "cpu"):
                import numpy as np
                t = image
                if getattr(t, "dim", None):
                    if t.dim() == 4:
                        t = t[0]
                    if t.dim() == 3:
                        if t.shape[-1] == 3:
                            arr = t.detach().cpu().numpy()
                        elif t.shape[0] == 3:
                            arr = t.detach().cpu().numpy().transpose(1, 2, 0)
                        else:
                            raise ValueError(f"不支持的Tensor形状: {tuple(t.shape)}")
                    else:
                        raise ValueError(f"不支持的Tensor维度: {t.dim()}")
                else:
                    raise ValueError("未知的Tensor类型")
                if arr.max() <= 1.0:
                    arr = (arr * 255.0).clip(0, 255).astype("uint8")
                else:
                    arr = arr.clip(0, 255).astype("uint8")
                pil_img = PILImage.fromarray(arr)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
            elif hasattr(image, "save"):
                pil_img = image
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
            else:
                import numpy as np
                if isinstance(image, np.ndarray):
                    arr = image
                    if arr.ndim == 3 and arr.shape[0] == 3:
                        arr = arr.transpose(1, 2, 0)
                    if arr.max() <= 1.0:
                        arr = (arr * 255.0).clip(0, 255).astype("uint8")
                    else:
                        arr = arr.clip(0, 255).astype("uint8")
                    pil_img = PILImage.fromarray(arr)
                    if pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")
                else:
                    raise ValueError(f"不支持的图像类型: {type(image)}")

            buf = BytesIO()
            pil_img.save(buf, format="PNG")
            buf.seek(0)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            raise


class OpenAISoraAPIAsyncCheck:
    """
    ComfyUI 自定义节点：查询 Sora 异步视频生成任务结果（支持 302 与 t8star 平台）
    - 从 sora_api.json 读取 base_url、api_key
    - 302:
        - GET {base_url}/sora/v2/video/{task_id}
        - 在 data.status == "completed" 且 data.outputs 为数组时，返回第一个视频URL
    - t8star:
        - GET {base_url}/v2/videos/generations/{task_id}
        - 在根级 status == "SUCCESS" 时，data.output 为视频URL
    - 输出:
        - video_url: 字符串；已完成时返回直链，未完成或无结果为空串
        - status_info: 可读的状态信息
    """
    _completed_tasks = set()

    @classmethod
    def IS_CHANGED(cls, task_id, api_provider="302"):
        """
        缓存判定键：纳入 api_provider，避免跨平台串扰。
        """
        try:
            import hashlib, time
            tid = (task_id or "").strip()
            stable_key_src = f"{api_provider}|{tid}"
            stable_hash = hashlib.sha256(stable_key_src.encode("utf-8")).hexdigest()
            if tid and tid in cls._completed_tasks:
                return stable_hash
            nonce_src = f"{stable_key_src}|{time.time_ns()}"
            return hashlib.sha256(nonce_src.encode("utf-8")).hexdigest()
        except Exception:
            return str(__import__("time").time_ns())

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (["302", "T8star"],),
                "task_id": ("STRING", {"default": "sora-2:task_xxx", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("status_info", "video_url")
    FUNCTION = "check"
    CATEGORY = "🦉FreeAPI/OpenAI"

    def check(self, api_provider: str, task_id: str):
        """
        查询任务结果：
        - 已完成：返回 (status_info, video_url)
        - 进行中/无输出：返回 (status_info, "")
        - 发生错误：返回 ("错误：...", "")
        """
        if not task_id or not task_id.strip():
            return ("错误：task_id 为空", "")

        # 加载平台配置
        try:
            conf = _load_provider_conf(api_provider or "302")
        except Exception as e:
            return (f"配置错误：{e}", "")

        base_url = conf["base_url"]
        api_key = conf["api_key"]
        suffix = conf.get("async_suffix") or ("/sora/v2/video" if api_provider == "302" else "/v2/videos/generations")
        url = f"{base_url}{suffix}/{task_id.strip()}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        try:
            print(f"[OpenAISoraAPIAsyncCheck] 请求: GET {url}")
            resp = requests.get(url, headers=headers, timeout=60)
            print(f"[OpenAISoraAPIAsyncCheck] 状态码: {resp.status_code}")

            if resp.status_code != 200:
                _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
                status_pretty = f"♻️ 任务状态：查询失败\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：HTTP {resp.status_code}"
                return (status_pretty, "")

            data = resp.json()
            if not isinstance(data, dict):
                _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
                status_pretty = f"♻️ 任务状态：查询失败\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：API响应格式异常：非JSON对象"
                return (status_pretty, "")

            # 响应解析分支
            if api_provider == "302":
                code = data.get("code")
                if code != 200:
                    _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
                    msg = data.get("message", "接口返回非200")
                    status_pretty = f"♻️ 任务状态：查询失败\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：{msg}"
                    return (status_pretty, "")
                d = data.get("data") or {}
                status_raw = (d.get("status") or d.get("Status") or "").strip().lower()
                outputs = d.get("outputs") or []
            else:
                status_raw = str(data.get("status") or "").strip().lower()
                d = data.get("data") or {}
                outputs = []
                out_url = d.get("output") or ""
                if out_url:
                    outputs = [out_url]

            if status_raw in ("completed", "succeeded", "success"):
                status_cn = "已完成"
            elif status_raw in ("failed", "error", "canceled", "cancelled"):
                status_cn = "生成失败"
            elif status_raw in ("created", "processing", "queued", "running", "in_progress"):
                status_cn = "进行中"
            elif status_raw in ("success", "SUCCESS"):
                status_cn = "已完成"
            else:
                status_cn = "未知"

            try:
                if status_raw in ("completed", "succeeded", "success", "SUCCESS"):
                    self.__class__._completed_tasks.add(task_id.strip())
            except Exception:
                pass

            task_type = "文生视频"
            try:
                inputs_like = d.get("inputs") or d.get("input") or {}
                if isinstance(inputs_like, dict):
                    if any(k in inputs_like for k in ("image", "image_url", "imageUrl", "images")):
                        task_type = "图生视频"
                req_like = d.get("request") or {}
                if isinstance(req_like, dict) and any(k in req_like for k in ("image", "image_url", "imageUrl", "images")):
                    task_type = "图生视频"
            except Exception:
                pass

            created_at = d.get("created_at") or d.get("createdAt") or "-"
            full_id = d.get("id") or task_id or "-"
            task_id_short = str(full_id).split(":")[-1] if isinstance(full_id, str) else str(full_id)

            video_url = ""
            if isinstance(outputs, list) and outputs:
                video_url = str(outputs[0])

            vlink_disp = video_url if video_url else "等待返回"
            status_pretty = (
                f"♻️ 任务状态：{status_cn}\n"
                f"⌚️ 创建时间：{created_at}\n"
                f"🔖 任务ID：{task_id_short}\n"
                f"🔗 视频链接: {vlink_disp}"
            )

            print(f"[OpenAISoraAPIAsyncCheck] 任务状态: {status_raw} → {status_cn}")
            if video_url:
                print(f"[OpenAISoraAPIAsyncCheck] 返回视频URL: {video_url}")

            return (status_pretty, video_url)
        except requests.exceptions.Timeout:
            _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
            status_pretty = f"♻️ 任务状态：查询失败\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：请求超时，请稍后重试"
            return (status_pretty, "")
        except requests.exceptions.RequestException as e:
            _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
            status_pretty = f"♻️ 任务状态：查询失败\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：网络错误: {e}"
            return (status_pretty, "")
        except Exception as e:
            _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
            status_pretty = f"♻️ 任务状态：查询失败\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：查询失败: {e}"
            return (status_pretty, "")

# 节点注册
NODE_CLASS_MAPPINGS = {
    "OpenAI_Sora_API_ASYNC": OpenAISoraAPIAsyncSubmit,
    "OpenAI_Sora_Check_Result": OpenAISoraAPIAsyncCheck,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenAI_Sora_API_ASYNC": "🦉OpenAI Sora API Async（提交任务）",
    "OpenAI_Sora_Check_Result": "🦉OpenAI Sora Check Result（查询结果）",
}
