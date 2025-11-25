import os
import json
import time
from io import BytesIO

import requests
from PIL import Image
import numpy as np
import torch


class HAIYIImageNode:
    """
    ComfyUI 自定义节点：Haiyi Image（海艺文生图）

    功能：
    1. 提交海艺「文生图」任务到 /api/v1/creativity/generate/apply
    2. 轮询 /api/v1/task/batch-progress 直到生成完成
    3. 下载首张图片，转换为 ComfyUI IMAGE 张量
    4. 返回 (image, generation_info)

    认证：
    - 在与本文件同目录的 haiyi_config.json 中配置 Cookie 与模型映射
      {"cookie": "deviceId=...; T=...", "image_models": {"Seedream 4.0": {"apply_id": "...", "ver_no": "...", "ss": 52}}}

    重要说明：
    - 海艺接口需要有效登录 Cookie。请在 haiyi_config.json 的 cookie 字段填入你的整串 Cookie。
    - 若接口字段变更，请按实际返回适配解析逻辑。
    """

    def __init__(self):
        # 读取配置文件
        self.config_path = os.path.join(os.path.dirname(__file__), "haiyi_config.json")
        if not os.path.exists(self.config_path):
            raise RuntimeError("缺少配置文件 haiyi_config.json，请先创建并填写 cookie 与模型配置。")
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 基本配置
        self.cookie = self.config.get("cookie", "").strip()
        if not self.cookie:
            raise RuntimeError("haiyi_config.json 未配置 cookie，请粘贴你的海艺账号 Cookie 到 cookie 字段。")

        self.timeout = int(self.config.get("timeout", 30))
        self.max_wait_time = int(self.config.get("max_wait_time", 300))
        self.check_interval = int(self.config.get("check_interval", 2))

        # headers
        headers_cfg = self.config.get("headers", {}) or {}
        self.base_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zhCN",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": headers_cfg.get("origin", "https://www.haiyi.art"),
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": headers_cfg.get("referer", "https://www.haiyi.art/"),
            "sec-ch-ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": headers_cfg.get("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"),
            "x-app-id": headers_cfg.get("x-app-id", "web_global_seaart"),
            "x-platform": headers_cfg.get("x-platform", "web"),
            # Cookie 通过 headers 传入（等价于 curl -b）
            "Cookie": self.cookie,
        }

        # 模型映射
        self.models = self.config.get("image_models", {})
        if not self.models:
            raise RuntimeError("haiyi_config.json 未配置 models，请至少配置 Seedream 4.0 的 apply_id/ver_no/ss。")

        # API 基础地址
        self.base_url = "https://www.haiyi.art"

    @classmethod
    def INPUT_TYPES(cls):
        """
        定义节点输入：
        - 必选：model(下拉，默认 Seedream 4.0)，prompt(多行文本)
        - 可选：ratio(默认 3:4)，resolution(新增，支持1K/2K/4K，默认1K)
        """
        # 动态读取模型选项
        config_path = os.path.join(os.path.dirname(__file__), "haiyi_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            model_names = list(cfg.get("image_models", {}).keys())
            if not model_names:
                model_names = ["Seedream 4.0"]
        except Exception:
            model_names = ["Seedream 4.0"]

        default_model = "Seedream 4.0" if "Seedream 4.0" in model_names else model_names[0]

        return {
            "required": {
                "model": (model_names, {"default": default_model}),
                "prompt": ("STRING", {"multiline": True, "default": "液态金属装甲，机动武神"}),
            },
            "optional": {
                "ratio": (["1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2", "4:5", "5:4", "21:9", "auto"], {"default": "3:4"}),
                "resolution": (["1K", "2K", "4K"], {"default": "1K"}),
                "image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "generation_info")
    FUNCTION = "generate"
    CATEGORY = "🦉FreeAPI/Haiyi"

    def generate(self, model: str, prompt: str, ratio: str = "3:4", resolution: str = "1K", image=None):
        """
        核心流程：
        - 若提供 image(IMAGE)：按图生图流程
          1) 预签名 -> PUT 上传 -> 确认上传 -> 获得 url
          2) 调用 apply(image+prompt) -> task_id
        - 否则：按文生图流程
          1) 调用 apply(prompt+ratio+resolution) -> task_id
        - 统一：轮询 batch-progress -> 下载首图 -> 返回
        """
        model_cfg = self.models.get(model, None)
        if not model_cfg:
            raise RuntimeError(f"未找到模型配置：{model}，请在 haiyi_config.json 的 models 中添加。")

        ss = int(model_cfg.get("ss", 52))

        # 分支：图生图 or 文生图
        # 海艺影像 2.0（官方常规文生图）分支：仅支持文生图，忽略 image；该模型不需要 apply_id/ver_no
        if model == "海艺影像 2.0":
            if image is not None:
                print("[Haiyi] 提示: '海艺影像 2.0'仅支持文生图，image 输入将被忽略")
            t2i_cfg = model_cfg
            model_no = str(t2i_cfg.get("model_no", "")).strip()
            model_ver_no = str(t2i_cfg.get("model_ver_no", "")).strip()
            if not model_no or not model_ver_no:
                raise RuntimeError("海艺影像 2.0 配置缺少 model_no 或 model_ver_no")
            width, height = self._size_from_ratio(ratio)
            steps = int(t2i_cfg.get("default_steps", 20))
            cfg_scale = float(t2i_cfg.get("default_cfg_scale", 2.5))
            n_iter = int(t2i_cfg.get("default_n_iter", 4))
            seed = int(time.time()) % 4294967295
            payload = {
                "model_no": model_no,
                "model_ver_no": model_ver_no,
                "channel_id": "",
                "speed_type": 2,
                "meta": {
                    "prompt": prompt,
                    "negative_prompt": "",
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                    "sampler_name": "",
                    "n_iter": n_iter,
                    "lora_models": [],
                    "vae": "None",
                    "clip_skip": 0,
                    "seed": seed,
                    "restore_faces": False,
                    "embeddings": [],
                    "generate": {"anime_enhance": 0, "mode": 0, "gen_mode": 1, "prompt_magic_mode": 2},
                    "original_translated_meta_prompt": prompt,
                    "artwork_remix_local_prompt": prompt,
                },
                "ss": ss,
            }
            print(f"[Haiyi] 提交常规文生图参数: model_no={model_no}, model_ver_no={model_ver_no}, size={width}x{height}")
            task_id, err = self._submit_text_to_img(payload)
            if err:
                info = f"模型: {model}\n比例: {ratio}\n分辨率: {resolution}\n错误: {err}"
                print(f"[Haiyi] 提交失败: {err}")
                return (self._blank_image_tensor(), info)
            print(f"[Haiyi] 任务提交返回 task_id={task_id}")
        else:
            apply_id = str(model_cfg.get("apply_id", "")).strip()
            ver_no = str(model_cfg.get("ver_no", "")).strip()
            if not apply_id:
                raise RuntimeError(f"模型 {model} 缺少 apply_id。")

            # NanoBananaPro 系列模型分支
            if model in ["NanoBananaPro_T2I", "NanoBananaPro_I2I"]:
                if model == "NanoBananaPro_T2I" and image is not None:
                    print("[Haiyi] 提示: 'NanoBananaPro_T2I'仅支持文生图，image 输入将被忽略")
                if model == "NanoBananaPro_I2I" and image is None:
                    raise RuntimeError("NanoBananaPro_I2I 需要输入图片")
                
                if image is not None and model == "NanoBananaPro_I2I":
                    # 图生图流程
                    print(f"[Haiyi] NanoBananaPro图生图流程开始，ratio={ratio}, resolution={resolution}")
                    img_url = self._upload_image_presign(image, apply_id)
                    print(f"[Haiyi] 上传完成，返回URL: {img_url}")
                    inputs = [
                        {"field": "image", "node_id": "4", "node_type": "LoadImage", "val": img_url},
                        {"field": "image", "node_id": "5", "node_type": "LoadImage", "val": img_url},
                        {"field": "image", "node_id": "6", "node_type": "LoadImage", "val": img_url},
                        {"field": "prompt", "node_id": "1", "node_type": "HaiYiNanoBananaPro", "val": prompt},
                        {"field": "resolution", "node_id": "1", "node_type": "HaiYiNanoBananaPro", "val": resolution},
                        {"field": "aspect_ratio", "node_id": "1", "node_type": "HaiYiNanoBananaPro", "val": ratio},
                    ]
                else:
                    # 文生图流程
                    print(f"[Haiyi] NanoBananaPro文生图流程开始，ratio={ratio}, resolution={resolution}")
                    inputs = [
                        {"field": "prompt", "node_id": "1", "node_type": "HaiYiNanoBananaPro", "val": prompt},
                        {"field": "resolution", "node_id": "1", "node_type": "HaiYiNanoBananaPro", "val": resolution},
                        {"field": "aspect_ratio", "node_id": "1", "node_type": "HaiYiNanoBananaPro", "val": ratio},
                    ]
                payload = {"apply_id": apply_id, "inputs": inputs, "ss": ss}
            else:
                # 原有模型分支（Seedream 4.0, NanoBanana等）
                if image is not None:
                    print(f"[Haiyi] 图生图流程开始，模型={model}，ratio={ratio}")
                    img_url = self._upload_image_presign(image, apply_id)
                    print(f"[Haiyi] 上传完成，返回URL: {img_url}")
                    if model == "NanoBanana":
                        inputs = [
                            {"field": "image", "node_id": "2", "node_type": "LoadImage", "val": img_url},
                            {"field": "prompt", "node_id": "4", "node_type": "SeaArtNanoBanana", "val": prompt},
                        ]
                        payload = {"apply_id": apply_id, "inputs": inputs, "ver_no": ver_no, "ss": ss}
                    else:
                        inputs = [
                            {"field": "image", "node_id": "3", "node_type": "LoadImage", "val": img_url},
                            {"field": "value", "node_id": "10", "node_type": "String-🔬", "val": prompt},
                        ]
                        payload = {"apply_id": apply_id, "inputs": inputs, "ss": ss}
                else:
                    print(f"[Haiyi] 文生图流程开始，模型={model}，ratio={ratio}")
                    if model == "NanoBanana":
                        inputs = [
                            {"field": "prompt", "node_id": "4", "node_type": "SeaArtNanoBanana", "val": prompt},
                        ]
                        payload = {"apply_id": apply_id, "inputs": inputs, "ver_no": ver_no, "ss": ss}
                    else:
                        inputs = [
                            {"field": "value", "node_id": "11", "node_type": "String-🔬", "val": prompt},
                            {"field": "ratio", "node_id": "10", "node_type": "HaiYiFilmEdit", "val": ratio},
                            {"field": "resolution", "node_id": "10", "node_type": "HaiYiFilmEdit", "val": "2K"},
                        ]
                        payload = {"apply_id": apply_id, "inputs": inputs, "ver_no": ver_no, "ss": ss}
            
            if 'inputs' in locals():
                print(f"[Haiyi] 提交参数摘要: apply_id={apply_id}, ver_no={ver_no if 'ver_no' in locals() else 'N/A'}, ss={ss}, inputs={inputs}")
            task_id, err = self._submit_task(payload)
            if err:
                info = f"模型: {model}\n比例: {ratio}\n分辨率: {resolution}\n错误: {err}"
                print(f"[Haiyi] 提交失败: {err}")
                return (self._blank_image_tensor(), info)
            print(f"[Haiyi] 任务提交返回 task_id={task_id}")        

        img_urls, raw_progress = self._wait_for_finish(task_id, ss)
        print(f"[Haiyi] 任务轮询完成，结果URLs={img_urls}")
        if not img_urls:
            raise RuntimeError(f"生成失败或超时，未取得图片链接。最近一次返回：{raw_progress}")

        # 将所有返回 URL 下载为批量张量；若只有1张则退化为单张
        image_tensor = self._download_images_to_tensor(img_urls[:4] if img_urls else img_urls)

        # 组织 generation_info 文本（包含关键信息与最多四张图片直链）
        info_lines = [
            f"✨ 模型: {model}",
            f"📐 比例: {ratio}",
            f"📱 分辨率: {resolution}",
            f"🔖 任务ID: {task_id}",
            "🔗 图片链接:" ,
        ]
        for i, u in enumerate(img_urls[:4]):
            info_lines.append(f"[{i}] {u}")
        # 追加剩余积分信息
        try:
            coins = self._fetch_remaining_temp_coins()
            if coins is not None:
                info_lines.append(f"🪙 剩余积分: {coins}")
                print(f"[Haiyi] 剩余积分: {coins}")
            else:
                print("[Haiyi] 获取剩余积分失败或无返回")
        except Exception as e:
            print(f"[Haiyi] 获取剩余积分异常: {e}")
        generation_info = "\n".join(info_lines)
        print(f"[Haiyi] generation_info:\n{generation_info}")

        return (image_tensor, generation_info)

    # =============== 内部方法 ===============

    def _submit_task(self, payload: dict):
        url = f"{self.base_url}/api/v1/creativity/generate/apply"
        print(f"[Haiyi] POST {url}")
        try:
            resp = requests.post(url, headers=self.base_headers, data=json.dumps(payload), timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return None, f"提交任务请求失败: {e}"
        # 统一处理状态码
        try:
            status = (data or {}).get("status", {})
            code = status.get("code")
            msg = status.get("msg") or ""
            if code == 10000:
                task_id = (data.get("data") or {}).get("id")
                return task_id, None
            if code == 70026:
                return None, "您的提示词中含有敏感词汇，请修改后再试"
            return None, f"提交失败: code={code}, msg={msg}"
        except Exception:
            return None, "提交失败: 未知响应格式"

    def _submit_text_to_img(self, payload: dict):
        url = f"{self.base_url}/api/v1/task/v2/text-to-img"
        print(f"[Haiyi] POST {url}")
        try:
            resp = requests.post(url, headers=self.base_headers, data=json.dumps(payload), timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return None, f"提交常规文生图失败: {e}"
        try:
            status = (data or {}).get("status", {})
            code = status.get("code")
            msg = status.get("msg") or ""
            if code == 10000:
                task_id = (data.get("data") or {}).get("id")
                return task_id, None
            if code == 70026:
                return None, "您的提示词中含有敏感词汇，请修改后再试"
            return None, f"提交失败: code={code}, msg={msg}"
        except Exception:
            return None, "提交失败: 未知响应格式"

    def _extract_task_id(self, data: dict) -> str:
        task_id = None
        try:
            if isinstance(data, dict) and data.get("status", {}).get("code") == 10000:
                task_id = data.get("data", {}).get("id")
        except Exception:
            task_id = None
        return task_id

    def _wait_for_finish(self, task_id: str, ss: int):
        url = f"{self.base_url}/api/v1/task/batch-progress"
        print(f"[Haiyi] 开始轮询进度 task_id={task_id}")
        start_time = time.time()
        last_payload = None

        while True:
            if time.time() - start_time > self.max_wait_time:
                print("[Haiyi] 轮询超时")
                return None, last_payload

            body = {"task_ids": [task_id], "ss": ss}
            try:
                resp = requests.post(url, headers=self.base_headers, data=json.dumps(body), timeout=self.timeout)
                resp.raise_for_status()
                payload = resp.json()
                last_payload = payload
            except Exception as e:
                last_payload = {"error": str(e)}
                time.sleep(self.check_interval)
                continue

            try:
                items = payload.get("data", {}).get("items", [])
                if not items:
                    time.sleep(self.check_interval)
                    continue
                item = items[0]
                # 仅打印关键进度值
                try:
                    proc = item.get("process")
                    if proc is not None:
                        print(f"[Haiyi] 进度: {proc}%")
                except Exception:
                    pass
                status_code = item.get("status")  # 1 waiting, 3 finished
                if status_code == 3:
                    img_uris = item.get("img_uris") or []
                    # 提取 index 0-3 的4张图，按 index 排序，优先取 url，无则取 cover_url
                    urls = []
                    try:
                        sorted_uris = sorted(
                            [u for u in img_uris if isinstance(u, dict) and isinstance(u.get("index"), int)],
                            key=lambda x: x.get("index")
                        )
                        for u in sorted_uris:
                            idx = u.get("index")
                            if idx is not None and 0 <= idx <= 3:
                                url_field = u.get("url") or u.get("cover_url")
                                if url_field:
                                    urls.append(url_field)
                    except Exception:
                        # 回退：保持旧逻辑，收集所有存在的 url/cover_url
                        for u in img_uris:
                            if isinstance(u, dict):
                                url_field = u.get("url") or u.get("cover_url")
                                if url_field:
                                    urls.append(url_field)
                    return urls, payload
                time.sleep(self.check_interval)
            except Exception:
                time.sleep(self.check_interval)

    def _download_first_image_as_tensor(self, url: str):
        print(f"[Haiyi] 下载图片: {url}")
        try:
            r = requests.get(url, headers={"User-Agent": self.base_headers.get("user-agent", "Mozilla/5.0")}, timeout=self.timeout)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB")
        except Exception as e:
            raise RuntimeError(f"下载图片失败: {e}")

        np_img = np.array(img).astype(np.float32) / 255.0  # H, W, C in [0,1]
        # 扩展 batch 维度 -> (1, H, W, C)
        if np_img.ndim == 3:
            np_img = np.expand_dims(np_img, axis=0)
        tensor = torch.from_numpy(np_img.copy())
        return tensor

    def _blank_image_tensor(self, width: int = 256, height: int = 256):
        arr = np.zeros((height, width, 3), dtype=np.float32)  # [H,W,3] zeros
        return torch.from_numpy(arr).unsqueeze(0)  # [1,H,W,3]

    def _size_from_ratio(self, ratio: str):
        # 简单尺寸映射，满足大多数需求；如需调整可扩展为参数
        table = {
            "1:1": (2048, 2048),
            "3:4": (1536, 2048),
            "4:3": (2048, 1536),
            "9:16": (1152, 2048),
            "16:9": (2048, 1152),
        }
        return table.get(ratio, (1024, 1024))

    def _download_images_to_tensor(self, image_urls):
        """
        批量下载图片并堆叠为 [N,H,W,3] 的 batch 张量；若尺寸不一致，按第一张统一 resize。
        忽略失败项；若全部失败则抛错。
        """
        tensors = []
        target_size = None  # (W,H)
        for idx, url in enumerate(image_urls or []):
            try:
                print(f"[Haiyi] 开始下载第{idx+1}张：{url}")
                r = requests.get(url, headers={"User-Agent": self.base_headers.get("user-agent", "Mozilla/5.0")}, timeout=self.timeout)
                r.raise_for_status()
                img = Image.open(BytesIO(r.content)).convert("RGB")
                if target_size is None:
                    target_size = img.size
                else:
                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                        print(f"[Haiyi] 尺寸不一致，统一为 {target_size[0]}x{target_size[1]}")
                np_img = np.array(img, dtype=np.float32) / 255.0
                tensor_img = torch.from_numpy(np_img).unsqueeze(0)  # [1,H,W,3]
                tensors.append(tensor_img)
            except Exception as e:
                print(f"[Haiyi] 第{idx+1}张下载失败：{e}")
                continue
        if not tensors:
            raise RuntimeError("所有图片下载失败")
        batch = torch.cat(tensors, dim=0)  # [N,H,W,3]
        print(f"[Haiyi] 最终tensor batch: 形状={batch.shape}, dtype={batch.dtype}")
        return batch

    # =============== 上传相关 ===============
    def _upload_image_presign(self, image_tensor, template_id: str) -> str:
        """
        三步：
        1) 预签名 uploadImageByPreSign -> 得到 pre_sign 与 file_id
        2) PUT 上传到 pre_sign
        3) confirmImageUploadedByPreSign -> 得到静态CDN url
        返回：图片 CDN URL
        """
        # 将 ComfyUI IMAGE(tensor) 转换为 PNG 二进制
        pil_img = self._tensor_to_pil(image_tensor)
        img_bytes = BytesIO()
        pil_img.save(img_bytes, format="PNG")
        raw = img_bytes.getvalue()
        file_size = len(raw)
        file_name = f"comfy_{int(time.time())}.png"
        content_type = "image/png"

        # 1) 预签名
        url_presign = f"{self.base_url}/api/v1/resource/uploadImageByPreSign"
        body = {
            "content_type": content_type,
            "file_name": file_name,
            "file_size": file_size,
            "category": 20,
            "hash_val": self._sha256_hex(raw),
            "template_id": template_id,
        }
        print(f"[Haiyi] 上传预签名 body={body}")
        r = requests.post(url_presign, headers=self.base_headers, data=json.dumps(body), timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        print(f"[Haiyi] 预签名响应: {data}")
        if data.get("status", {}).get("code") != 10000:
            raise RuntimeError(f"预签名失败: {data}")
        pre_sign = data.get("data", {}).get("pre_sign")
        file_id = data.get("data", {}).get("file_id")
        if not pre_sign or not file_id:
            raise RuntimeError("预签名返回缺少 pre_sign 或 file_id")

        # 2) PUT 上传
        put_headers = {
            "Accept": "*/*",
            "Content-Type": content_type,
            "Origin": "https://www.haiyi.art",
            "Referer": "https://www.haiyi.art/",
            "User-Agent": self.base_headers.get("user-agent", "Mozilla/5.0"),
        }
        print(f"[Haiyi] PUT 上传到 pre_sign: {pre_sign}，大小={file_size}")
        put_resp = requests.put(pre_sign, data=raw, headers=put_headers, timeout=self.timeout)
        put_resp.raise_for_status()

        # 3) 确认上传
        url_confirm = f"{self.base_url}/api/v1/resource/confirmImageUploadedByPreSign"
        confirm_body = {"category": 20, "file_id": file_id, "template_id": template_id}
        print(f"[Haiyi] 确认上传 body={confirm_body}")
        c = requests.post(url_confirm, headers=self.base_headers, data=json.dumps(confirm_body), timeout=self.timeout)
        c.raise_for_status()
        c_data = c.json()
        print(f"[Haiyi] 确认上传响应: {c_data}")
        if c_data.get("status", {}).get("code") != 10000:
            raise RuntimeError(f"确认上传失败: {c_data}")
        url = c_data.get("data", {}).get("url")
        if not url:
            raise RuntimeError("确认上传返回缺少 url")
        return url

    def _tensor_to_pil(self, image_tensor) -> Image.Image:
        # ComfyUI IMAGE: (B,H,W,C) float32 [0,1]
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

    def _fetch_remaining_temp_coins(self) -> int | None:
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
            print(f"[Haiyi] 查询积分失败: {e}")
        return None

# 节点注册
NODE_CLASS_MAPPINGS = {
    "HAIYIImageNode": HAIYIImageNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HAIYIImageNode": "🦉Haiyi Image",
}
