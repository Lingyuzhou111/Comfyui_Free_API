import os
import json
import time
from io import BytesIO
from typing import Tuple, Optional, Any

import requests
from PIL import Image
import numpy as np
import torch


class HAIYIVideoNode:
    """
    海艺视频生成节点：支持文生视频与图生视频，两种模型：海艺影像 专业版、VIDU Q2
    - 读取 `haiyi_config.json` 的 `video_models` 映射
    - 提交任务到 haiyi.art 平台，并轮询 `/api/v1/task/batch-progress` 获取结果
    - 返回 ComfyUI VIDEO 与 generation_info 文本
    """

    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), "haiyi_config.json")
        if not os.path.exists(self.config_path):
            raise RuntimeError("缺少配置文件 haiyi_config.json")
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 基本设置
        self.cookie = (self.config.get("cookie") or "").strip()
        if not self.cookie:
            raise RuntimeError("haiyi_config.json 未配置 cookie")
        self.timeout = int(self.config.get("timeout", 30))
        self.max_wait_time = int(self.config.get("max_wait_time", 300))
        self.check_interval = int(self.config.get("check_interval", 3))
        self.base_url = "https://www.haiyi.art"

        headers_cfg = self.config.get("headers", {}) or {}
        self.base_headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": headers_cfg.get("origin", "https://www.haiyi.art"),
            "referer": headers_cfg.get("referer", "https://www.haiyi.art/"),
            "user-agent": headers_cfg.get("user-agent", "Mozilla/5.0"),
            "x-app-id": headers_cfg.get("x-app-id", "web_global_seaart"),
            "x-platform": headers_cfg.get("x-platform", "web"),
            "Cookie": self.cookie,
        }

        self.video_models = self.config.get("video_models", {}) or {}
        if not self.video_models:
            raise RuntimeError("haiyi_config.json 未配置 video_models")

    @classmethod
    def INPUT_TYPES(cls):
        # 读取视频模型列表，并对 V2.0 使用更友好的显示名
        try:
            cfg_path = os.path.join(os.path.dirname(__file__), "haiyi_config.json")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            model_names = list((cfg.get("video_models") or {}).keys()) or ["VIDU Q2"]
        except Exception:
            model_names = ["VIDU Q2"]
        display_names = ["多图参考V2.0" if n == "V2.0" else n for n in model_names]
        default_display = "多图参考V2.0" if "V2.0" in model_names else ("海艺影像 专业版" if "海艺影像 专业版" in model_names else display_names[0])
        return {
            "required": {
                "video_model": (display_names, {"default": default_display}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "duration": ([5, 6, 8, 10], {"default": 5}),
                "aspect_ratio": (["9:16", "3:4", "1:1", "9:16", "16:9"], {"default": "16:9"}),
#               "quality_mode": (["360p", "540p", "720p", "1080p"], {"default": "360p"}),
                "audio_effect": ("BOOLEAN", {"default": False}),
                "hd_mode": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("video", "generation_info")
    FUNCTION = "generate_video"
    CATEGORY = "🦉FreeAPI/Haiyi"

    def generate_video(self, video_model: str, prompt: str,
                       image1: Optional[torch.Tensor] = None,
                       image2: Optional[torch.Tensor] = None,
                       image3: Optional[torch.Tensor] = None,
                       image4: Optional[torch.Tensor] = None,
                       duration: int = 5,
                       aspect_ratio: str = "16:9",
                       quality_mode: str = "360p",
                       audio_effect: bool = False,
                       hd_mode: bool = False) -> Tuple[Optional[Any], str]:
        # 将显示名映射回配置名
        if video_model == "多图参考V2.0":
            config_key = "V2.0"
        else:
            config_key = video_model
        model_cfg = self.video_models.get(config_key) or {}
        model_no = str(model_cfg.get("model_no", "")).strip()
        model_ver_no = str(model_cfg.get("model_ver_no", "")).strip()
        ss = int(model_cfg.get("ss", 52))
        print(f"[HaiyiVideo] 选择模型: 显示名='{video_model}', 配置键='{config_key}', model_no={model_no}, model_ver_no={model_ver_no}, ss={ss}")
        print(f"[HaiyiVideo] 生成参数: duration={duration}, aspect_ratio={aspect_ratio}, quality={quality_mode}, audio_effect={audio_effect}, hd_mode={hd_mode}")
        if not model_no or not model_ver_no:
            return (None, f"错误：未配置模型 {video_model} 的 model_no/model_ver_no")

        # 构造提交 payload
        images = [img for img in [image1, image2, image3, image4] if img is not None]
        is_multi = (config_key == "V2.0") and len(images) >= 1
        if is_multi:
            # 多图参考：上传所有参考图得到 URL 列表
            try:
                img_urls = []
                for idx, t in enumerate(images[:4]):
                    u = self._upload_image_presign(t, template_id=model_no)
                    img_urls.append(u)
                    print(f"[HaiyiVideo] 参考图{idx+1} 上传成功: {u}")
            except Exception as e:
                print(f"[HaiyiVideo] 参考图上传失败: {e}")
                return (None, f"错误：上传参考图失败：{e}")
            payload = {
                "model_no": model_no,
                "model_ver_no": model_ver_no,
                "meta": {
                    "prompt": prompt or "",
                    "height": self._size_for_quality(aspect_ratio, quality_mode)[1],
                    "width": self._size_for_quality(aspect_ratio, quality_mode)[0],
                    "negative_prompt": "",
                    "aspect_ratio": aspect_ratio,
                    "generate": {"gen_mode": 1 if hd_mode else 0},
                    "generate_video": {
                        "generate_video_duration": int(duration),
                        "audio_effect": bool(audio_effect),
                        "movement_amplitude": "auto",
                        "image_opts": [{"url": u} for u in img_urls],
                    },
                    "original_translated_meta_prompt": "",
                },
                "task_domain_type": 25,
                "ss": ss,
            }
            print(f"[HaiyiVideo] 提交多图参考任务: model_no={model_no}, ver={model_ver_no}, 图片数={len(img_urls)}, size={payload['meta']['width']}x{payload['meta']['height']}, duration={duration}")
            submit_fn = self._submit_multi_img_to_video
        elif len(images) == 1:
            # 单图图生视频：先上传首帧
            try:
                img_url = self._upload_image_presign(images[0], template_id=model_no)
            except Exception as e:
                return (None, f"错误：上传首帧失败：{e}")
            payload = {
                "model_no": model_no,
                "model_ver_no": model_ver_no,
                "meta": {
                    "prompt": prompt or "",
                    "generate_video": {
                        "relevance": 0.5,
                        "camera_control_option": {"mode": "Camera Movement", "offset": 0},
                        "generate_video_duration": int(duration),
                        "image_opts": [{"mode": "first_frame", "url": img_url}],
                        "quality_mode": quality_mode,
                        "audio_effect": bool(audio_effect),
                        "n_iter": 1,
                    },
                    "width": self._size_for_quality(aspect_ratio, quality_mode)[0],
                    "height": self._size_for_quality(aspect_ratio, quality_mode)[1],
                    "lora_models": [],
                    "aspect_ratio": "",
                    "generate": {"anime_enhance": 2, "mode": 0, "gen_mode": 1 if hd_mode else 0},
                    "n_iter": 1,
                    "original_translated_meta_prompt": "",
                },
                "ss": ss,
            }
            print(f"[HaiyiVideo] 提交单图图生视频: model_no={model_no}, ver={model_ver_no}, size={payload['meta']['width']}x{payload['meta']['height']}, duration={duration}, quality={quality_mode}")
            submit_fn = self._submit_img_to_video
        else:
            # 文生视频：使用专业版
            payload = {
                "model_no": model_no,
                "model_ver_no": model_ver_no,
                "meta": {
                    "prompt": prompt or "",
                    "generate_video": {
                        "relevance": 0.5,
                        "camera_control_option": {"mode": "Camera Movement", "offset": 0},
                        "generate_video_duration": int(duration),
                        "quality_mode": quality_mode,
                        "audio_effect": bool(audio_effect),
                        "n_iter": 1,
                    },
                    "width": self._size_for_quality(aspect_ratio, quality_mode)[0],
                    "height": self._size_for_quality(aspect_ratio, quality_mode)[1],
                    "lora_models": [],
                    "aspect_ratio": aspect_ratio,
                    "generate": {"anime_enhance": 2, "mode": 0, "gen_mode": 1 if hd_mode else 0},
                    "n_iter": 1,
                    "original_translated_meta_prompt": "",
                },
                "ss": ss,
            }
            print(f"[HaiyiVideo] 提交文生视频: model_no={model_no}, ver={model_ver_no}, size={payload['meta']['width']}x{payload['meta']['height']}, duration={duration}, quality={quality_mode}, aspect_ratio={aspect_ratio}")
            submit_fn = self._submit_text_to_video

        # 特殊：V2.0 多图参考模式仅在 config_key=="V2.0" 时可选；其余模型忽略多图，按单图/文生逻辑

        # 提交任务
        print(f"[HaiyiVideo] POST 提交到: {submit_fn.__name__}")
        task_id, err = submit_fn(payload)
        if err:
            print(f"[HaiyiVideo] 提交失败: {err}")
            info = f"错误：提交失败：{err}"
            return (self._placeholder_video(), info)
        if not task_id:
            print("[HaiyiVideo] 提交失败：未返回 task_id")
            info = "错误：提交失败，未返回 task_id"
            return (self._placeholder_video(), info)
        print(f"[HaiyiVideo] 任务提交成功 task_id={task_id}")

        # 轮询
        print(f"[HaiyiVideo] 开始轮询 task_id={task_id}")
        urls, raw = self._wait_for_finish(task_id, ss)
        if urls is None:
            # 被系统取消（敏感内容等），raw 包含错误信息
            print("[HaiyiVideo] 轮询结束：系统取消/敏感内容")
            info = "系统取消，可能您的输入参数包含敏感内容，请修改后再试"
            return (self._placeholder_video(), info)
        if not urls:
            print(f"[HaiyiVideo] 轮询结束：失败或超时，raw={raw}")
            info = f"错误：生成失败或超时。最近一次响应：{raw}"
            return (self._placeholder_video(), info)
        video_url = None
        # 提取首个 mp4 链接
        for u in urls:
            if isinstance(u, str) and u.lower().endswith(".mp4"):
                video_url = u
                break
        if not video_url:
            # 若未找到 mp4，用第一个链接
            video_url = urls[0]

        # 下载并转换为 ComfyUI VIDEO
        print(f"[HaiyiVideo] 获取到视频URL: {video_url}")
        video_obj = self._download_and_convert_video(video_url)
        if video_obj is None:
            print("[HaiyiVideo] 视频下载/转换失败，返回占位VIDEO以避免下游报错")
            info = "错误：视频下载或转换失败，请检查网络或视频直链有效性"
            return (self._placeholder_video(), info)

        info_lines = [
            f"✨ 模型: {video_model}",
            f"⌛️ 时长: {duration}s",
            f"📺 画质: {quality_mode}",
            f"📐 纵横比: {aspect_ratio}",
            f"🔖 任务ID: {task_id}",
            "🔗 视频链接:",
            video_url,
        ]
        # 追加剩余积分信息
        try:
            coins = self._fetch_remaining_temp_coins()
            if coins is not None:
                info_lines.append(f"🪙 剩余积分: {coins}")
                print(f"[HaiyiVideo] 剩余积分: {coins}")
            else:
                print("[HaiyiVideo] 获取剩余积分失败或无返回")
        except Exception as e:
            print(f"[HaiyiVideo] 获取剩余积分异常: {e}")
        generation_info = "\n".join(info_lines)
        return (video_obj, generation_info)

    # =============== 提交方法 ===============
    def _submit_text_to_video(self, payload: dict):
        url = f"{self.base_url}/api/v1/task/v2/video/text-to-video"
        try:
            r = requests.post(url, headers=self.base_headers, data=json.dumps(payload), timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return None, str(e)
        status = (data or {}).get("status", {})
        code = status.get("code")
        msg = status.get("msg") or ""
        if code == 10000:
            return (data.get("data") or {}).get("id"), None
        if code == 70026:
            return None, "您的提示词中含有敏感词汇，请修改后再试"
        return None, f"code={code}, msg={msg}"

    def _submit_img_to_video(self, payload: dict):
        url = f"{self.base_url}/api/v1/task/v2/video/img-to-video"
        try:
            r = requests.post(url, headers=self.base_headers, data=json.dumps(payload), timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return None, str(e)
        status = (data or {}).get("status", {})
        code = status.get("code")
        msg = status.get("msg") or ""
        if code == 10000:
            return (data.get("data") or {}).get("id"), None
        if code == 70026:
            return None, "您的提示词中含有敏感词汇，请修改后再试"
        return None, f"code={code}, msg={msg}"

    def _submit_multi_img_to_video(self, payload: dict):
        url = f"{self.base_url}/api/v1/task/v2/video/multi-img-to-video"
        try:
            r = requests.post(url, headers=self.base_headers, data=json.dumps(payload), timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return None, str(e)
        status = (data or {}).get("status", {})
        code = status.get("code")
        msg = status.get("msg") or ""
        if code == 10000:
            return (data.get("data") or {}).get("id"), None
        if code == 70026:
            return None, "您的提示词中含有敏感词汇，请修改后再试"
        return None, f"code={code}, msg={msg}"

    # =============== 轮询与解析 ===============
    def _wait_for_finish(self, task_id: str, ss: int):
        url = f"{self.base_url}/api/v1/task/batch-progress"
        start = time.time()
        last = None
        while True:
            if time.time() - start > self.max_wait_time:
                return None, last
            body = {"task_ids": [task_id], "ss": ss}
            try:
                r = requests.post(url, headers=self.base_headers, data=json.dumps(body), timeout=self.timeout)
                r.raise_for_status()
                payload = r.json()
                last = payload
            except Exception as e:
                print(f"[HaiyiVideo] 轮询请求失败: {e}")
                last = {"error": str(e)}
                time.sleep(self.check_interval)
                continue
            try:
                items = payload.get("data", {}).get("items", [])
                if not items:
                    time.sleep(self.check_interval)
                    continue
                item = items[0]
                proc = item.get("process")
                if proc is not None:
                    print(f"[HaiyiVideo] 进度: {proc}%")
                status_code = item.get("status")
                if status_code == 4:
                    # 系统取消，可能包含敏感内容
                    return None, {
                        "error": "系统取消，可能您的输入参数包含敏感内容，请修改后再试",
                        "raw": payload,
                    }
                if status_code == 3:
                    img_uris = item.get("img_uris") or []
                    urls = []
                    for u in img_uris:
                        if isinstance(u, dict):
                            url_field = u.get("url") or u.get("cover_url")
                            if url_field:
                                urls.append(url_field)
                    return urls, payload
                time.sleep(self.check_interval)
            except Exception:
                time.sleep(self.check_interval)

    # =============== 上传首帧（复用图片上传逻辑） ===============
    def _upload_image_presign(self, image_tensor, template_id: str) -> str:
        pil_img = self._tensor_to_pil(image_tensor)
        buf = BytesIO()
        pil_img.save(buf, format="PNG")
        raw = buf.getvalue()
        file_size = len(raw)
        file_name = f"comfy_{int(time.time())}.png"
        content_type = "image/png"

        url_presign = f"{self.base_url}/api/v1/resource/uploadImageByPreSign"
        body = {
            "content_type": content_type,
            "file_name": file_name,
            "file_size": file_size,
            "category": 20,
            "hash_val": self._sha256_hex(raw),
            "template_id": template_id,
        }
        r = requests.post(url_presign, headers=self.base_headers, data=json.dumps(body), timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("status", {}).get("code") != 10000:
            raise RuntimeError(f"预签名失败: {data}")
        pre_sign = data.get("data", {}).get("pre_sign")
        file_id = data.get("data", {}).get("file_id")
        if not pre_sign or not file_id:
            raise RuntimeError("预签名返回缺少 pre_sign 或 file_id")

        put_headers = {
            "Accept": "*/*",
            "Content-Type": content_type,
            "Origin": "https://www.haiyi.art",
            "Referer": "https://www.haiyi.art/",
            "User-Agent": self.base_headers.get("user-agent", "Mozilla/5.0"),
        }
        put_resp = requests.put(pre_sign, data=raw, headers=put_headers, timeout=self.timeout)
        put_resp.raise_for_status()

        url_confirm = f"{self.base_url}/api/v1/resource/confirmImageUploadedByPreSign"
        confirm_body = {"category": 20, "file_id": file_id, "template_id": template_id}
        c = requests.post(url_confirm, headers=self.base_headers, data=json.dumps(confirm_body), timeout=self.timeout)
        c.raise_for_status()
        c_data = c.json()
        if c_data.get("status", {}).get("code") != 10000:
            raise RuntimeError(f"确认上传失败: {c_data}")
        url = c_data.get("data", {}).get("url")
        if not url:
            raise RuntimeError("确认上传返回缺少 url")
        print(f"[HaiyiVideo] 上传完成并确认成功，返回URL: {url}")
        return url

    # =============== 工具方法 ===============
    def _placeholder_video(self) -> Any:
        """
        返回一个可被 ComfyUI 下游节点接受的“空视频”占位对象。
        这里复用 DownloadVideoFromUrlNode 的构造能力：传入 about:blank 会产生最小化的视频对象或 None；
        若失败则尽量返回 None 但已在调用方用占位兜底，避免再抛错。
        """
        try:
            from ..OpenAI_Node.download_video_from_url import DownloadVideoFromUrlNode
        except Exception:
            try:
                from custom_nodes.Comfyui_Free_API.OpenAI_Node.download_video_from_url import DownloadVideoFromUrlNode
            except Exception:
                return None
        helper = DownloadVideoFromUrlNode()
        video_obj, _ = helper.convert_url_to_video(
            video_url="about:blank",
            timeout=10,
            max_retries=1,
            retry_delay=1,
            user_agent_type="Chrome桌面版",
            skip_url_test=True,
            custom_user_agent="",
        )
        return video_obj

    def _tensor_to_pil(self, image_tensor) -> Image.Image:
        if image_tensor is None:
            raise RuntimeError("传入空图片")
        if isinstance(image_tensor, torch.Tensor):
            arr = image_tensor.detach().cpu().numpy()
        else:
            arr = np.asarray(image_tensor)
        if arr.ndim == 4:
            arr = arr[0]
        arr = (np.clip(arr, 0, 1) * 255.0).astype(np.uint8)
        return Image.fromarray(arr)

    def _sha256_hex(self, raw: bytes) -> str:
        import hashlib
        h = hashlib.sha256()
        h.update(raw)
        return h.hexdigest()

    def _size_for_quality(self, aspect_ratio: str, quality_mode: str):
        # 简单分辨率映射，常见的视频规格
        table = {
            "360p": {"16:9": (640, 360), "9:16": (360, 640)},
            "720p": {"16:9": (1280, 720), "9:16": (720, 1280)},
            "1080p": {"16:9": (1920, 1080), "9:16": (1080, 1920)},
        }
        return table.get(quality_mode, table["360p"]).get(aspect_ratio, (640, 360))

    def _download_and_convert_video(self, video_url: str) -> Optional[Any]:
        try:
            try:
                from custom_nodes.Comfyui_Free_API.OpenAI_Node.download_video_from_url import DownloadVideoFromUrlNode
            except Exception:
                from ..OpenAI_Node.download_video_from_url import DownloadVideoFromUrlNode
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
            return video_obj
        except Exception:
            return None

    def _fetch_remaining_temp_coins(self) -> Optional[int]:
        """
        调用 haiyi 接口获取当前账号剩余积分，仅返回 temp_coins。
        成功返回 int，失败返回 None。
        """
        url = f"{self.base_url}/api/v1/payment/assets/get"
        try:
            r = requests.post(url, headers=self.base_headers, data=json.dumps({}), timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            if (data or {}).get("status", {}).get("code") == 10000:
                coins = ((data or {}).get("data") or {}).get("temp_coins")
                if isinstance(coins, int):
                    return coins
        except Exception as e:
            # 仅记录，不抛出，以免影响主流程
            print(f"[HaiyiVideo] 查询积分失败: {e}")
        return None


NODE_CLASS_MAPPINGS = {
    "HAIYIVideoNode": HAIYIVideoNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HAIYIVideoNode": "🦉Haiyi Video",
}
