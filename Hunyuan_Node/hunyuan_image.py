import os
import json
import time
import requests
from io import BytesIO
from PIL import Image
import torch
import numpy as np

class HunyuanImageNode:
    """
    ComfyUI 自定义节点：Hunyuan Image（混元文生图）
    - 文生图：使用提示词提交任务
    - 轮询查询任务状态，成功后下载图片并转换为 ComfyUI IMAGE 张量
    - 返回 image（IMAGE）与 generation_info（STRING）

    认证：
    - 从 custom_nodes/Comfyui_Free_API/Hunyuan_Node/hy_config.json 读取 cookie（整段字符串）
      请确保在 hy_config.json 中填写正确的 cookie，否则会报错。
    """

    def __init__(self):
        # 读取配置
        self.config_path = os.path.join(os.path.dirname(__file__), "hy_config.json")
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # API/轮询配置
        self.timeout = int(self.config.get("timeout", 30))                 # 单次请求超时（秒）
        self.max_wait_time = int(self.config.get("max_wait_time", 600))    # 轮询总时长（秒）
        self.check_interval = int(self.config.get("check_interval", 6))    # 轮询间隔（秒）

        # 域名与接口路径：来源于 curl 示例
        # generation: https://api.hunyuan.tencent.com/api/vision_platform/generation
        # query_task: https://api.hunyuan.tencent.com/api/vision_platform/query_task
        api_base_default = "https://api.hunyuan.tencent.com/api/vision_platform"
        self.api_base = self.config.get("api_base", api_base_default).rstrip("/")
        self.origin_base = self.config.get("origin", "https://hunyuan.tencent.com").rstrip("/")

        # 认证 Cookie
        self.cookie = self.config.get("cookie", "").strip()

        # 默认生成尺寸（可在配置文件中调整）
        self.default_size = self.config.get("default_size", "896x1152")

        # 统一的请求头（按照 curl 示例）
        self.base_headers = {
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": self.origin_base,
            "Pragma": "no-cache",
            "Referer": f"{self.origin_base}/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
            "X-Requested-With": "XMLHttpRequest",
            "X-Source": "web",
            "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            # Cookie 通过专用头传递
            "Cookie": self.cookie,
        }

        # 模型列表：本节点只需要一个模型选项，默认 hunyuan-image-v3.0
        # 若未来需要扩展版本，可在此增加映射并同步到 INPUT_TYPES
        self.model_options = self.config.get("models", ["hunyuan-image-v3.0-v1.0.1"])

    @classmethod
    def INPUT_TYPES(cls):
        """
        定义节点输入参数：
        - 必选：
          - model: 下拉框（默认 hunyuan-image-v3.0-v1.0.1）
          - prompt: STRING 多行
        - 可选：
          - num_images: 下拉 1~4（默认 4）
        """
        # 动态读取配置以保证下拉选项一致
        config_path = os.path.join(os.path.dirname(__file__), "hy_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            model_options = cfg.get("models", ["hunyuan-image-v3.0-v1.0.1"])
            ratios_options = cfg.get("ratios", ["1:1", "3:4", "4:3", "16:9", "9:16"])
        except Exception:
            model_options = ["hunyuan-image-v3.0-v1.0.1"]
            ratios_options = ["1:1", "3:4", "4:3", "16:9", "9:16"]

        # 默认模型优先 hunyuan-image-v3.0
        default_model = "hunyuan-image-v3.0-v1.0.1" if "hunyuan-image-v3.0-v1.0.1" in model_options else model_options[0]

        # num_images 选项
        num_images_options = ["1", "2", "3", "4"]
        # ratio 选项
        default_ratio = "1:1" if "1:1" in ratios_options else ratios_options[0]

        return {
            "required": {
                "model": (model_options, {"default": default_model}),
                "prompt": ("STRING", {"multiline": True, "default": "用中文或英文描述你想要的图片"}),
            },
            "optional": {
                "ratio": (ratios_options, {"default": default_ratio}),
                "num_images": (num_images_options, {"default": "4"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "generation_info")
    FUNCTION = "generate"
    CATEGORY = "🦉FreeAPI/Hunyuan"

    def generate(self, model, prompt, num_images="4", ratio="1:1"):
        """
        核心生成方法：
        1) 校验 cookie
        2) 提交 /generation 任务，取得 taskId
        3) 轮询 /query_task，直到 status=succeeded
        4) 解析返回 result（JSON 字符串）中的 data[].url 列表
        5) 批量下载图片并堆叠为 ComfyUI IMAGE 张量
        6) 返回 (image_tensor, generation_info_str)
        """
        print(f"[HunyuanImage] 开始生成，model={model}, num_images={num_images}, prompt长度={len(prompt)}")
        # 1) 校验 cookie
        if not self.cookie:
            raise RuntimeError("未配置 Cookie。请在 hy_config.json 的 cookie 字段填写完整的认证 Cookie。")

        # 2) 准备提交参数
        try:
            num_calls = int(num_images)
            if num_calls < 1 or num_calls > 4:
                num_calls = 4
        except Exception:
            num_calls = 4

        # modelName 与 model：按照 curl 示例相同值即可
        model_name = model

        # 根据 ratio 映射生成 size
        ratio_map = self.config.get("ratio_map", {})
        size_str = self.default_size
        if isinstance(ratio, str):
            entry = ratio_map.get(ratio)
            if isinstance(entry, dict):
                w = entry.get("width")
                h = entry.get("height")
                if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
                    size_str = f"{w}x{h}"

        payload = {
            # curl 示例中常见字段，均可选；已在配置中预留
            "cid": "d3cfcus2c3mfmac8flc0",
            "modelId": 10570,
            "appId": 289,
            "modelPath": "/openapi/v1/images/ar/generations",
            # 关键字段
            "modelName": model_name,
            "model": model_name,
            "num_calls": num_calls,
            "verbose": True,
            "size": size_str,
            "prompt": prompt,
        }

        # 清理空值项，避免发送 None
        payload = {k: v for k, v in payload.items() if v is not None}

        # 3) 提交任务
        task_id = self._submit_task(payload)
        if not task_id:
            raise RuntimeError("提交任务失败，未取得 taskId")
        print(f"[HunyuanImage] 任务提交成功，task_id={task_id}")

        # 4) 轮询查询结果
        image_urls, full_query_payload = self._wait_for_result(task_id)
        if not image_urls:
            # 解析失败原因并写入 generation_info
            try:
                payload_obj = json.loads(full_query_payload) if isinstance(full_query_payload, str) else (full_query_payload or {})
            except Exception:
                payload_obj = {}
            status_val = str(payload_obj.get("status", "")).lower()
            fail_msg = payload_obj.get("message")

            if status_val == "failed":
                msg_text = fail_msg or "任务失败，原因未知"
                generation_info_text = (
                    f"❌ 任务失败\n"
                    f"🎨 模型名称: {model}\n"
                    f"📣 失败原因: {msg_text}\n"
                )
                # 返回占位的 512x512 黑色图片，保持输出类型一致
                placeholder = torch.zeros((1, 512, 512, 3), dtype=torch.float32)
                print(f"[HunyuanImage] 任务失败，已返回占位图片与失败信息：{msg_text}")
                return (placeholder, generation_info_text)

            # 非明确失败（如超时），仍按原逻辑抛错
            raise RuntimeError(f"生成失败或超时未取得图片URL。最后响应：{full_query_payload}")
        print(f"[HunyuanImage] 生成成功，图片数量={len(image_urls)}，urls={image_urls}")

        # 5) 批量下载图片并转换为 ComfyUI IMAGE batch
        image_tensor = self._download_images_to_tensor(image_urls)

        # 6) 生成信息文本
        urls_text = "\n".join(image_urls)
        generation_info_text = (
            f"✨ 任务类型: 文生图\n"
            f"🎨 模型名称: {model}\n"
            f"🖼️ 请求张数: {num_calls}\n"
            f"🔗 图片链接: \n{urls_text}"
        )

        return (image_tensor, generation_info_text)

    # ===================== 内部方法 =====================

    def _auth_headers(self):
        """
        返回带 Cookie 的请求头。
        """
        headers = dict(self.base_headers)
        headers["Cookie"] = self.cookie
        headers["Content-Type"] = "application/json"
        return headers

    def _submit_task(self, payload):
        """
        POST /generation 提交任务，返回 taskId
        请求体示例（精简版）：
        {
          "model": "hunyuan-image-v3.0-v1.0.1",
          "modelName": "hunyuan-image-v3.0-v1.0.1",
          "num_calls": 4,
          "verbose": true,
          "size": "896x1152",
          "prompt": "..."
        }
        """
        url = f"{self.api_base}/generation"
        headers = self._auth_headers()

        # 记录摘要，避免打印全部 prompt
        print(f"[HunyuanImage] 提交payload摘要：model={payload.get('model')}, num_calls={payload.get('num_calls')}, size={payload.get('size')}, prompt前50字={payload.get('prompt', '')[:50]}")

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        print(f"[HunyuanImage] 提交HTTP状态：{resp.status_code}")
        if resp.status_code != 200:
            raise RuntimeError(f"提交任务HTTP错误: {resp.status_code} {resp.text}")

        data = resp.json()
        # 根据 curl 示例，响应为 {"taskId":"..."}
        task_id = data.get("taskId")
        print(f"[HunyuanImage] 提交返回 taskId：{task_id}")
        return task_id

    def _wait_for_result(self, task_id):
        """
        轮询 /query_task，直到 status=succeeded
        返回 (image_urls:list[str], full_query_payload_json_str)
        - 响应结构参考 curl 示例：
          {
            "type":"finish",
            "status":"succeeded",
            "result":"{\"data\":[{\"url\":\"...\"},...]}"
          }
        """
        url = f"{self.api_base}/query_task"
        headers = self._auth_headers()
        start = time.time()
        last_payload = None

        print(f"[HunyuanImage] 开始轮询结果，task_id={task_id}, url={url}")

        while time.time() - start < self.max_wait_time:
            resp = requests.post(url, headers=headers, json={"taskId": str(task_id)}, timeout=self.timeout)
            if resp.status_code != 200:
                print(f"[HunyuanImage] 查询HTTP状态：{resp.status_code}，等待重试")
                time.sleep(self.check_interval)
                continue

            payload = resp.json()
            last_payload = payload

            status = str(payload.get("status", "")).lower()
            progress = payload.get("progressValue")
            print(f"[HunyuanImage] 查询状态：status={status}, progress={progress}")

            # 若任务失败，立即停止轮询并返回失败信息
            if status == "failed":
                msg = payload.get("message") or "任务失败，原因未知"
                print(f"[HunyuanImage] 任务失败，message={msg}")
                return None, json.dumps(payload, ensure_ascii=False)

            if status == "succeeded":
                # 解析 result（字符串内嵌 JSON）
                result_str = payload.get("result")
                image_urls = self._parse_urls_from_result(result_str)
                if not image_urls:
                    print("[HunyuanImage] 成功状态但未找到有效图片URL")
                    return None, json.dumps(payload, ensure_ascii=False)
                return image_urls, json.dumps(payload, ensure_ascii=False)

            # 其它状态（如 running / queued），等待下一次
            time.sleep(self.check_interval)

        return None, json.dumps(last_payload, ensure_ascii=False) if last_payload is not None else "{}"

    def _parse_urls_from_result(self, result_str):
        """
        从 result 字符串中解析 data[].url 列表。
        - result 是一个字符串形式的 JSON，需要二次解析。
        - 返回有效的 http(s) URL 列表。
        """
        try:
            if not isinstance(result_str, str) or not result_str.strip():
                return []
            # 二次解析
            inner = json.loads(result_str)
            data_list = inner.get("data") or []
            urls = []
            for item in data_list:
                url = item.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    urls.append(url)
            return urls
        except Exception as e:
            print(f"[HunyuanImage] 解析 result 失败：{e}")
            return []

    def _download_images_to_tensor(self, image_urls):
        """
        批量下载图片并堆叠为 [N,H,W,3] 的 batch 张量，若尺寸不一致则按第一张统一 resize
        忽略无效URL，若全部失败则抛错
        """
        tensors = []
        target_size = None  # (W,H)
        for idx, url in enumerate(image_urls):
            try:
                print(f"[HunyuanImage] 开始下载第{idx+1}张：{url}")
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                if target_size is None:
                    target_size = img.size
                else:
                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                        print(f"[HunyuanImage] 尺寸不一致，统一为 {target_size[0]}x{target_size[1]}")
                np_img = np.array(img, dtype=np.float32) / 255.0
                tensor_img = torch.from_numpy(np_img).unsqueeze(0)  # [1,H,W,3]
                tensors.append(tensor_img)
            except Exception as e:
                print(f"[HunyuanImage] 第{idx+1}张下载失败：{e}")
                continue
        if not tensors:
            raise RuntimeError("所有图片下载失败")
        batch = torch.cat(tensors, dim=0)  # [N,H,W,3]
        print(f"[HunyuanImage] 最终tensor batch: 形状={batch.shape}, dtype={batch.dtype}")
        return batch


# 节点注册
NODE_CLASS_MAPPINGS = {
    "Hunyuan_Image": HunyuanImageNode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Hunyuan_Image": "🦉Hunyuan Image 文生图"
}