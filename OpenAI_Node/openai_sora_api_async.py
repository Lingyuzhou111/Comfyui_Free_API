import json
import requests
from typing import Optional, Any


class OpenAISoraAPIAsyncSubmit:
    """
    ComfyUI 自定义节点：提交 Sora 异步视频生成任务
    - POST {base_url}/sora/v2/video
    - 请求体: {"model": "sora-2", "orientation": "portrait|landscape", "prompt": "..."}
    - 响应: {"code":200,"data":{"id":"sora-2:task_xxx", ...}}
    - 输出: task_id (字符串)
    """

    # 会话级缓存：存放上一轮提交成功得到的 task_id
    _last_task_id: Optional[str] = None

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://api.302.ai", "multiline": False}),
                "model": ("STRING", {"default": "sora-2", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "prompt": ("STRING", {"default": "请描述要生成的视频内容", "multiline": True}),
                "orientation": (["portrait", "landscape"],),
                "use_cache": (["false", "true"],),
            },
            "optional": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("task_id",)
    FUNCTION = "submit"
    CATEGORY = "🦉FreeAPI/OpenAI"

    def submit(self, base_url: str, model: str, api_key: str, prompt: str, orientation: str, use_cache: str, image=None):
        """
        提交异步视频生成任务，返回 task_id。
        - 当 use_cache == "true" 时：不提交新任务，直接返回上一次缓存的 task_id；若无缓存则返回错误提示
        """
        # 处理缓存逻辑：当开启缓存时，禁止提交新任务
        if str(use_cache).lower() == "true":
            if self.__class__._last_task_id:
                print(f"[OpenAISoraAPIAsyncSubmit] use_cache=true，返回缓存 task_id: {self.__class__._last_task_id}")
                return (self.__class__._last_task_id,)
            else:
                return ("错误：use_cache 为 true 但没有可用缓存 task_id，请先在 use_cache=false 下提交一次任务",)

        if not api_key:
            return ("错误：未配置 API Key",)
        if not base_url:
            return ("错误：未配置 base_url",)
        if not prompt or not prompt.strip():
            return ("错误：prompt 为空",)
        if orientation not in ("portrait", "landscape"):
            return ("错误：orientation 必须为 portrait 或 landscape",)

        url = f"{base_url.rstrip('/')}/sora/v2/video"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": model or "sora-2",
            "orientation": orientation,
            "prompt": prompt.strip(),
        }

        # 若提供 IMAGE，则转为 PNG 的 data URL 注入 payload.image
        if image is not None:
            try:
                data_url = self._image_to_data_url(image)
                if data_url:
                    payload["images"] = [data_url]
                    # 打印时避免输出完整base64
                    print("[OpenAISoraAPIAsyncSubmit] 已附带输入图像(image-to-video)，使用 data URL (已截断日志)")
            except Exception as e:
                return (f"输入图像处理失败: {e}",)

        try:
            # 与同步节点一致的精简日志：打印URL/模型/提示词预览与精简后的载荷
            print(f"[OpenAISoraAPIAsyncSubmit] 请求: POST {url}")
            print(f"[OpenAISoraAPIAsyncSubmit] 模型: {model}")
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

            code = data.get("code")
            if code != 200:
                return (f"API返回非200: {data}",)

            d = data.get("data") or {}
            task_id = d.get("id") or ""
            if not task_id:
                return ("未获取到 task_id",)

            print(f"[OpenAISoraAPIAsyncSubmit] 成功提交任务: task_id={task_id}")
            # 写入缓存，供 use_cache=true 时复用
            self.__class__._last_task_id = task_id
            return (task_id,)
        except requests.exceptions.Timeout:
            return ("请求超时，请稍后重试",)
        except requests.exceptions.RequestException as e:
            return (f"网络错误: {e}",)
        except Exception as e:
            return (f"提交失败: {e}",)

    def _safe_json_dumps(self, obj, ensure_ascii=False, indent=2):
        """
        序列化JSON时截断超长/疑似base64或data URL字段，避免日志刷屏。
        规则：
        - 截断以 data:image/* 开头且长度>100 的字符串
        - 截断常见base64头(如 iVBORw0K,/9j/)且长度>100 的字符串
        - 深度遍历所有字典/列表
        """
        import json as _json

        def _truncate_cand(v: str) -> str:
            if not isinstance(v, str):
                return v
            try:
                if len(v) > 100 and (
                    v.startswith("data:image/") or
                    v[:8] in ("iVBORw0K", "/9j/")  # PNG/JPEG 常见base64头
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
        """
        将ComfyUI的 IMAGE 输入转换为 PNG 的 data URL（data:image/png;base64,xxx）。
        支持 torch.Tensor、PIL.Image、numpy.ndarray。
        """
        try:
            # 延迟导入，避免不必要依赖
            from io import BytesIO
            import base64
            try:
                from PIL import Image as PILImage
            except Exception as e:
                raise RuntimeError(f"未安装 Pillow: {e}")

            # 统一转成 PIL.Image(RGB)
            pil_img = None

            # torch.Tensor
            if hasattr(image, "cpu"):
                import torch  # noqa: F401
                import numpy as np
                t = image
                if getattr(t, "dim", None):
                    if t.dim() == 4:
                        t = t[0]
                    if t.dim() == 3:
                        # 可能是 (H,W,3) 或 (3,H,W)
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
                # 归一化
                if arr.max() <= 1.0:
                    arr = (arr * 255.0).clip(0, 255).astype("uint8")
                else:
                    arr = arr.clip(0, 255).astype("uint8")
                pil_img = PILImage.fromarray(arr)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")

            # PIL.Image
            elif hasattr(image, "save"):
                pil_img = image
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")

            # numpy.ndarray
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

            # 导出为 PNG 并编码为 data URL
            buf = BytesIO()
            pil_img.save(buf, format="PNG")
            buf.seek(0)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            raise


class OpenAISoraAPIAsyncCheck:
    """
    ComfyUI 自定义节点：查询 Sora 异步视频生成任务结果
    - GET {base_url}/sora/v2/video/{task_id}
    - 在 data.status == "completed" 且 data.outputs 为数组时，返回第一个视频URL
    - 输出:
        - video: VIDEO；若有直链则下载并转换为 ComfyUI 视频对象，否则为 None
        - video_url: 字符串；已完成时返回直链，未完成或无结果为空串
        - status: 当前任务状态（如 created, processing, completed, failed 等）
    """
    # 记录已完成的任务ID，用于使 IS_CHANGED 在完成后返回稳定键以启用缓存
    _completed_tasks = set()

    @classmethod
    def IS_CHANGED(cls, base_url, api_key, task_id):
        """
        返回用于缓存判定的变化键：
        - 未完成任务：返回带时间因子的哈希，确保每次运行都会执行
        - 已完成任务：返回稳定哈希，使缓存生效，避免重复请求
        """
        try:
            import hashlib, time
            tid = (task_id or "").strip()
            # 稳定键仅依赖稳定输入；api_key仅取后8位以避免泄露，且稳定
            stable_key_src = f"{base_url}|{api_key[-8:]}|{tid}"
            stable_hash = hashlib.sha256(stable_key_src.encode("utf-8")).hexdigest()
            # 已完成：返回稳定键，启用缓存
            if tid and tid in cls._completed_tasks:
                return stable_hash
            # 未完成：加入时间因子，确保每次不同，强制执行
            nonce_src = f"{stable_key_src}|{time.time_ns()}"
            return hashlib.sha256(nonce_src.encode("utf-8")).hexdigest()
        except Exception:
            # 任何异常下都强制执行
            return str(__import__("time").time_ns())

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://api.302.ai", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "task_id": ("STRING", {"default": "sora-2:task_xxx", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("status_info", "video_url")
    FUNCTION = "check"
    CATEGORY = "🦉FreeAPI/OpenAI"

    def check(self, base_url: str, api_key: str, task_id: str):
        """
        查询任务结果：
        - 已完成：返回 (video_url, status)
        - 进行中/无输出：返回 ("", status)
        - 发生错误：返回 ("", "错误：...") 以便在图中直观看到错误原因
        """
        if not api_key:
            return ("", "错误：未配置 API Key")
        if not base_url:
            return ("", "错误：未配置 base_url")
        if not task_id or not task_id.strip():
            return ("", "错误：task_id 为空")

        url = f"{base_url.rstrip('/')}/sora/v2/video/{task_id.strip()}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        try:
            print(f"[OpenAISoraAPIAsyncCheck] 请求: GET {url}")
            resp = requests.get(url, headers=headers, timeout=60)
            print(f"[OpenAISoraAPIAsyncCheck] 状态码: {resp.status_code}")

            if resp.status_code != 200:
                # 非200：构造可读状态
                _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
                status_pretty = f"♻️ 任务状态：查询失败\n🎨 任务类型：未知\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：HTTP {resp.status_code}"
                return (status_pretty, "")

            data = resp.json()
            if not isinstance(data, dict):
                _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
                status_pretty = f"♻️ 任务状态：查询失败\n🎨 任务类型：未知\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：API响应格式异常：非JSON对象"
                return (status_pretty, "")

            code = data.get("code")
            if code != 200:
                _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
                msg = data.get("message", "接口返回非200")
                status_pretty = f"♻️ 任务状态：查询失败\n🎨 任务类型：未知\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：{msg}"
                return (status_pretty, "")

            d = data.get("data") or {}
            status_raw = (d.get("status") or d.get("Status") or "").strip().lower()
            outputs = d.get("outputs") or []

            # 映射中文状态
            if status_raw in ("completed", "succeeded", "success"):
                status_cn = "已完成"
            elif status_raw in ("failed", "error", "canceled", "cancelled"):
                status_cn = "生成失败"
            elif status_raw in ("created", "processing", "queued", "running", "in_progress"):
                status_cn = "进行中"
            else:
                status_cn = "未知"

            # 若已完成，记录 task_id，使 IS_CHANGED 返回稳定键以启用缓存
            try:
                if status_raw in ("completed", "succeeded", "success"):
                    self.__class__._completed_tasks.add(task_id.strip())
            except Exception:
                pass

            # 任务类型推断：若响应里出现与图像相关的输入字段则判定为图生视频，否则默认文生视频
            task_type = "文生视频"
            try:
                inputs_like = d.get("inputs") or d.get("input") or {}
                if isinstance(inputs_like, dict):
                    if any(k in inputs_like for k in ("image", "image_url", "imageUrl")):
                        task_type = "图生视频"
                # 有些服务会把原始请求体透传在 data.request
                req_like = d.get("request") or {}
                if isinstance(req_like, dict) and any(k in req_like for k in ("image", "image_url", "imageUrl")):
                    task_type = "图生视频"
            except Exception:
                pass

            created_at = d.get("created_at") or d.get("createdAt") or "-"
            full_id = d.get("id") or task_id or "-"
            task_id_short = str(full_id).split(":")[-1] if isinstance(full_id, str) else str(full_id)

            video_url = ""
            if isinstance(outputs, list) and outputs:
                video_url = str(outputs[0])

            # 可读格式
            vlink_disp = video_url if video_url else "等待返回"
            status_pretty = (
                f"♻️ 任务状态：{status_cn}\n"
                f"🎨 任务类型：{task_type}\n"
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
            status_pretty = f"♻️ 任务状态：查询失败\n🎨 任务类型：未知\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：请求超时，请稍后重试"
            return (status_pretty, "")
        except requests.exceptions.RequestException as e:
            _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
            status_pretty = f"♻️ 任务状态：查询失败\n🎨 任务类型：未知\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：网络错误: {e}"
            return (status_pretty, "")
        except Exception as e:
            _tid_short = (task_id.strip().split(":")[-1]) if isinstance(task_id, str) else "-"
            status_pretty = f"♻️ 任务状态：查询失败\n🎨 任务类型：未知\n⌚️ 创建时间：-\n🔖 任务ID：{_tid_short}\n🔗 视频链接: -\n详情：查询失败: {e}"
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
