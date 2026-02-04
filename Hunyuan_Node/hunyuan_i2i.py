import os
import json
import time
import uuid
import hmac
import hashlib
import requests
from io import BytesIO
from PIL import Image
import torch
import numpy as np
from urllib.parse import quote


class HunyuanImg2ImgNode:
    """
    ComfyUI 自定义节点：Hunyuan Image-to-Image（混元图生图）
    - 图生图：基于参考图片和提示词生成新图片
    - 支持风格转换、图像编辑等功能
    - 使用 SSE 流式接口实时获取生成进度和结果
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
        self.max_wait_time = int(self.config.get("max_wait_time", 600))    # 最大等待时间（秒）

        # 域名与接口路径
        self.api_base = "https://api.hunyuan.tencent.com"
        self.origin_base = self.config.get("origin", "https://hunyuan.tencent.com").rstrip("/")

        # 认证 Cookie
        self.cookie = self.config.get("cookie", "").strip()

        # 图生图专用模型（从配置读取，默认使用 Instruct 模型）
        self.model_options = self.config.get("i2i_models", ["Hunyuan-Image-3.0-Instruct"])

        # 生成唯一的 cid（会话ID）
        self.cid = self._generate_cid()
        
        # 备用图片URL（当无水印版本下载失败时使用）
        self._fallback_image_url = None

        # 统一的请求头
        self.base_headers = {
            "Accept": "*/*",
            "Accept-Language": "zh",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": self.origin_base,
            "Pragma": "no-cache",
            "Referer": f"{self.origin_base}/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
            "X-AgentID": "HunyuanDefault",
            "X-Requested-With": "XMLHttpRequest",
            "X-Source": "web",
            "chat_version": "v1",
            "credentials": "include",
            "mode": "cors",
            "sec-ch-ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Cookie": self.cookie,
        }

    def _generate_cid(self):
        """
        生成唯一的会话ID（cid），格式参考：d5vmmlc2c3m52oskui9g
        """
        # 生成22位随机字符串（小写字母+数字）
        return uuid.uuid4().hex[:22]

    @classmethod
    def INPUT_TYPES(cls):
        """
        定义节点输入参数：
        - 必选：
          - image: 参考图片（ComfyUI IMAGE 类型）
          - model: 下拉框选择模型
          - prompt: STRING 多行，描述想要的变换效果
        - 可选：
          - image2: 第二张参考图片（可选）
          - image3: 第三张参考图片（可选）
          - ratio: 图片比例（1:1, 3:4, 4:3, 9:16, 16:9）
        """
        # 动态读取配置以保证下拉选项一致
        config_path = os.path.join(os.path.dirname(__file__), "hy_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            model_options = cfg.get("i2i_models", ["Hunyuan-Image-3.0-Instruct"])
            ratios_options = cfg.get("ratios", ["1:1", "3:4", "4:3", "9:16", "16:9"])
        except Exception:
            model_options = ["Hunyuan-Image-3.0-Instruct"]
            ratios_options = ["1:1", "3:4", "4:3", "9:16", "16:9"]

        # 默认模型
        default_model = "Hunyuan-Image-3.0-Instruct" if "Hunyuan-Image-3.0-Instruct" in model_options else model_options[0]
        # 默认比例
        default_ratio = "9:16" if "9:16" in ratios_options else ratios_options[0]

        return {
            "required": {
                "image": ("IMAGE",),
                "model": (model_options, {"default": default_model}),
                "prompt": ("STRING", {"multiline": True, "default": "描述你想要的图片变换效果，例如：变成写实风格"}),
            },
            "optional": {
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "ratio": (ratios_options, {"default": default_ratio}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "generation_info", "text_response")
    FUNCTION = "generate"
    CATEGORY = "🦉FreeAPI/Hunyuan"

    def generate(self, image, model, prompt, image2=None, image3=None, ratio="9:16"):
        """
        核心生成方法：
        1) 校验 cookie
        2) 将 ComfyUI 张量转换为图片并上传，获取 resourceUrl（支持最多3张图片）
        3) 提交图生图任务（SSE 流式请求）
        4) 解析 SSE 流，获取生成的图片 URL
        5) 批量下载图片并堆叠为 ComfyUI IMAGE 张量
        6) 返回 (image_tensor, generation_info_str)
        """
        # 1) 校验 cookie
        if not self.cookie:
            raise RuntimeError("未配置 Cookie。请在 hy_config.json 的 cookie 字段填写完整的认证 Cookie。")

        # 2) 上传参考图片（支持多张）
        print(f"[HunyuanImg2Img] 开始图生图，上传参考图片...")
        resource_urls = []
        
        # 上传第一张图片（必选）
        resource_url = self._upload_reference_image(image)
        if not resource_url:
            raise RuntimeError("上传第一张参考图片失败")
        resource_urls.append(resource_url)
        
        # 上传第二张图片（可选）
        if image2 is not None:
            resource_url2 = self._upload_reference_image(image2)
            if resource_url2:
                resource_urls.append(resource_url2)
        
        # 上传第三张图片（可选）
        if image3 is not None:
            resource_url3 = self._upload_reference_image(image3)
            if resource_url3:
                resource_urls.append(resource_url3)
        
        print(f"[HunyuanImg2Img] 已上传 {len(resource_urls)} 张参考图片，正在生成...")
        image_url, generation_text, text_response = self._submit_img2img_task(model, prompt, resource_urls, ratio)

        if not image_url:
            # 生成失败，返回占位图和错误信息
            placeholder = torch.zeros((1, 512, 512, 3), dtype=torch.float32)
            error_info = (
                f"❌ 图生图任务失败\n"
                f"🎨 模型名称: {model}\n"
                f"📣 错误信息: {generation_text}\n"
            )
            print(f"[HunyuanImg2Img] 任务失败：{generation_text}")
            return (placeholder, error_info, text_response)

        # 4) 下载生成的图片
        image_tensor = self._download_image_to_tensor(image_url)

        # 5) 生成信息文本
        generation_info_text = (
            f"✨ 任务类型: 图生图\n"
            f"🎨 模型名称: {model}\n"
            f"📝 提示词: {prompt}\n"
            f"📐 图片比例: {ratio}\n"
            f"🖼️ 参考图片数量: {len(resource_urls)}\n"
            f"🔗 图片链接: {image_url}\n"
            f"📄 生成详情: {generation_text[:200]}..."
        )

        return (image_tensor, generation_info_text, text_response)

    # ===================== 内部方法 =====================

    def _upload_reference_image(self, image_tensor):
        """
        上传参考图片到混元平台，获取 resourceUrl
        流程：
        1. 获取上传凭证（genUploadInfo）
        2. 上传图片到 COS
        3. 返回 resourceUrl

        参数：
            image_tensor: ComfyUI IMAGE 张量，形状为 [N,H,W,3] 或 [H,W,3]
        返回：
            resourceUrl: 上传后的图片资源URL
        """
        try:
            # 处理输入张量：如果是 batch，取第一张
            if len(image_tensor.shape) == 4:
                image_tensor = image_tensor[0]  # [H,W,3]

            # 转换为 PIL Image
            np_img = (image_tensor.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            pil_img = Image.fromarray(np_img)

            # 生成文件名
            file_name = f"comfyui_i2i_{int(time.time())}.webp"

            # 步骤1：获取上传凭证
            upload_info = self._get_upload_info(file_name)
            if not upload_info:
                print("[HunyuanImg2Img] 获取上传凭证失败")
                return None

            # 步骤2：上传图片到 COS
            upload_success = self._upload_to_cos(pil_img, upload_info)
            if not upload_success:
                print("[HunyuanImg2Img] 上传图片到 COS 失败")
                return None

            # 返回 resourceUrl
            return upload_info.get("resourceUrl")

        except Exception as e:
            print(f"[HunyuanImg2Img] 上传图片异常：{e}")
            return None

    def _get_upload_info(self, file_name):
        """
        获取图片上传凭证

        参数：
            file_name: 文件名
        返回：
            dict: 包含上传凭证信息的字典
        """
        url = f"{self.api_base}/api/new-portal/chat/resource/genUploadInfo"
        headers = dict(self.base_headers)

        payload = {
            "fileName": file_name,
            "docFrom": "localDoc"
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            print(f"[HunyuanImg2Img] 获取上传凭证状态：{resp.status_code}")

            if resp.status_code != 200:
                print(f"[HunyuanImg2Img] 获取上传凭证失败：{resp.text}")
                return None

            data = resp.json()

            # 检查响应中是否包含必要字段
            if "resourceUrl" not in data:
                print(f"[HunyuanImg2Img] 上传凭证响应缺少 resourceUrl：{data}")
                return None

            return data

        except Exception as e:
            print(f"[HunyuanImg2Img] 获取上传凭证异常：{e}")
            return None

    def _upload_to_cos(self, pil_img, upload_info):
        """
        上传图片到腾讯云 COS，使用临时密钥计算签名

        参数：
            pil_img: PIL Image 对象
            upload_info: 上传凭证信息
        返回：
            bool: 上传是否成功
        """
        try:
            # 从 upload_info 中提取必要信息
            bucket_name = upload_info.get("bucketName")
            region = upload_info.get("region")
            location = upload_info.get("location")
            secret_id = upload_info.get("encryptTmpSecretId")
            secret_key = upload_info.get("encryptTmpSecretKey")
            token = upload_info.get("encryptToken")
            start_time = upload_info.get("startTime")
            expired_time = upload_info.get("expiredTime")

            if not all([bucket_name, region, location, secret_id, secret_key]):
                print("[HunyuanImg2Img] COS 凭证信息不完整")
                return False

            # 准备图片数据
            img_buffer = BytesIO()
            pil_img.save(img_buffer, format='WEBP', quality=85)
            img_data = img_buffer.getvalue()
            content_length = len(img_data)

            # 构建 COS 上传 URL
            cos_host = f"{bucket_name}.cos.{region}.myqcloud.com"
            cos_url = f"https://{cos_host}/{location}"

            # 计算 COS 签名
            # 使用临时密钥的签名方式
            headers = self._calc_cos_auth(
                secret_id=secret_id,
                secret_key=secret_key,
                token=token,
                bucket=bucket_name,
                region=region,
                key=location,
                start_time=start_time,
                expired_time=expired_time,
                content_length=content_length
            )

            # 发送 PUT 请求上传图片
            resp = requests.put(
                cos_url,
                headers=headers,
                data=img_data,
                timeout=60
            )

            if resp.status_code in [200, 204]:
                return True
            else:
                print(f"[HunyuanImg2Img] COS 上传失败：{resp.status_code} {resp.text[:100]}")
                return False

        except Exception as e:
            print(f"[HunyuanImg2Img] COS 上传异常：{e}")
            import traceback
            traceback.print_exc()
            return False

    def _calc_cos_auth(self, secret_id, secret_key, token, bucket, region, key, start_time, expired_time, content_length):
        """
        计算 COS 上传的授权头
        使用腾讯云 COS 的临时密钥签名方式
        参考：https://cloud.tencent.com/document/product/436/7778
        """
        # 构建 COS Host
        cos_host = f"{bucket}.cos.{region}.myqcloud.com"

        # 确保时间戳是字符串格式
        if isinstance(start_time, int):
            start_time_str = str(start_time)
        else:
            start_time_str = str(start_time)

        if isinstance(expired_time, int):
            expired_time_str = str(expired_time)
        else:
            expired_time_str = str(expired_time)

        # 构建签名
        # 1. 构建 KeyTime
        key_time = f"{start_time_str};{expired_time_str}"

        # 2. 构建 SignKey（使用 SecretKey 对 KeyTime 进行 HMAC-SHA1 加密）
        sign_key = hmac.new(
            secret_key.encode('utf-8'),
            key_time.encode('utf-8'),
            hashlib.sha1
        ).hexdigest()

        # 3. 构建 HttpString
        # 格式：Method\nUri\nQueryString\nHeaders\n
        # 注意：key 不需要 URL 编码，保持原样
        # Headers 格式：key1=value1&key2=value2（用 & 连接，不是换行符）

        # 需要签名的头部（按字母顺序排序）
        # 包含 host 和 content-type，值需要 URL 编码
        header_list = ["content-type", "host"]
        headers_to_sign = {
            "content-type": quote("image/webp", safe=''),
            "host": cos_host
        }

        # 构建 HttpHeaders 字符串（用 & 连接，不是换行符）
        header_parts = []
        for k in sorted(headers_to_sign.keys()):
            header_parts.append(f"{k.lower()}={headers_to_sign[k]}")
        http_headers = "&".join(header_parts)

        http_string = f"put\n/{key}\n\n{http_headers}\n"

        # 4. 构建 StringToSign
        sha1_http = hashlib.sha1(http_string.encode('utf-8')).hexdigest()
        string_to_sign = f"sha1\n{key_time}\n{sha1_http}\n"

        # 5. 计算 Signature
        signature = hmac.new(
            sign_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        ).hexdigest()

        # 6. 构建 Authorization
        header_list_str = ";".join(sorted(header_list))
        authorization = (
            f"q-sign-algorithm=sha1&"
            f"q-ak={secret_id}&"
            f"q-sign-time={key_time}&"
            f"q-key-time={key_time}&"
            f"q-header-list={header_list_str}&"
            f"q-url-param-list=&"
            f"q-signature={signature}"
        )

        # 构建请求头
        headers = {
            "Host": cos_host,
            "Content-Type": "image/webp",
            "Content-Length": str(content_length),
            "Authorization": authorization,
        }

        # 如果有 token，添加到请求头
        if token:
            headers["x-cos-security-token"] = token

        return headers

    def _submit_img2img_task(self, model, prompt, resource_urls, ratio):
        """
        提交图生图任务，使用 SSE 流式接口（支持多张参考图片）

        参数：
            model: 模型名称
            prompt: 提示词
            resource_urls: 参考图片的 resourceUrl 列表（支持1-3张）
            ratio: 图片比例
        返回：
            (image_url, generation_text, text_response): 生成的图片URL、生成文本和纯文本响应
        """
        url = f"{self.api_base}/api/new-portal/chat/{self.cid}"
        headers = dict(self.base_headers)
        headers["Content-Type"] = "text/plain;charset=UTF-8"

        # 构建 multimedia 数组（支持多张图片）
        multimedia_list = []
        for idx, resource_url in enumerate(resource_urls):
            multimedia_list.append({
                "type": "image",
                "docType": "image",
                "url": resource_url,
                "fileName": os.path.basename(resource_url.split("?")[0]),
                "name": os.path.basename(resource_url.split("?")[0]),
                "size": 0,  # 大小未知，设为0
                "width": 0,
                "height": 0
            })

        # 构建请求体
        payload = {
            "model": "gpt_175B_0404",  # 固定值
            "prompt": prompt,
            "plugin": "Adaptive",
            "displayPrompt": prompt,
            "displayPromptType": 1,
            "options": {
                "imageIntention": {
                    "needIntentionModel": True,
                    "backendUpdateFlag": 2,
                    "userIntention": {"scale": ""},  # scale 为空字符串（API要求）
                    "intentionStatus": True
                }
            },
            "targetLang": None,
            "targetLangLabel": None,
            "sourceLang": None,
            "sourceLangLabel": None,
            "translateModelList": [],
            "podcast": {"voices": []},
            "displayImageIntentionLabels": [
                {"type": "scale", "disPlayValue": "", "startIndex": 0, "endIndex": 0}  # disPlayValue 为空字符串（API要求）
            ],
            "multimedia": multimedia_list,
            "agentId": "HunyuanDefault",
            "supportHint": 1,
            "version": "v2",
            "chatModelId": model
        }

        try:
            print(f"[HunyuanImg2Img] 正在生成图片，请稍候...")

            # 将 payload 转换为 JSON 字符串，并编码为 UTF-8 字节
            payload_json = json.dumps(payload, ensure_ascii=False)
            payload_bytes = payload_json.encode('utf-8')

            # 发送 SSE 请求
            resp = requests.post(
                url,
                headers=headers,
                data=payload_bytes,
                stream=True,
                timeout=self.max_wait_time
            )

            if resp.status_code != 200:
                print(f"[HunyuanImg2Img] 生成请求失败：{resp.status_code}")
                return None, f"HTTP错误：{resp.status_code}", ""

            # 解析 SSE 流
            return self._parse_sse_stream(resp)

        except Exception as e:
            print(f"[HunyuanImg2Img] 提交任务异常：{e}")
            return None, str(e), ""

    def _parse_sse_stream(self, response):
        """
        解析 SSE 流式响应

        参数：
            response: requests 的流式响应对象
        返回：
            (image_url, full_text, text_response): 图片URL、完整生成文本和纯文本响应
        """
        image_url = None
        full_text_parts = []
        text_response_parts = []  # 纯文本响应（整合所有 text 类型的消息）
        start_time = time.time()
        last_progress = 0  # 用于记录上一次打印的进度

        try:
            for line in response.iter_lines():
                # 检查超时
                if time.time() - start_time > self.max_wait_time:
                    print("[HunyuanImg2Img] SSE 流读取超时")
                    break

                if not line:
                    continue

                line_str = line.decode('utf-8')

                # 跳过 event: 行
                if line_str.startswith('event:'):
                    continue

                # 处理 data: 行
                if line_str.startswith('data:'):
                    data_content = line_str[5:].strip()

                    # 检查是否结束
                    if data_content == '[DONE]':
                        break

                    try:
                        data = json.loads(data_content)
                        msg_type = data.get('type')

                        # 处理进度（只打印每10%的进度，避免刷屏）
                        if msg_type == 'progress':
                            progress = data.get('value', 0)
                            progress_pct = int(progress * 100)
                            # 每10%打印一次，且避免重复打印
                            if progress_pct >= last_progress + 10:
                                print(f"[HunyuanImg2Img] 生成进度：{progress_pct}%")
                                last_progress = (progress_pct // 10) * 10

                        # 处理思考过程（静默收集，不打印）
                        elif msg_type == 'think':
                            content = data.get('content', '')
                            # 不打印，避免刷屏

                        # 处理文本输出（静默收集，不打印）
                        elif msg_type == 'text':
                            msg = data.get('msg', '')
                            full_text_parts.append(msg)
                            text_response_parts.append(msg)  # 收集纯文本响应
                            # 不打印，避免刷屏

                        # 处理图片输出
                        elif msg_type == 'image':
                            # 尝试获取无水印版本（urlKey），同时保存有水印版本作为备用
                            url_key = data.get('urlKey')
                            watermarked_url = data.get('imageUrlHigh') or data.get('imageUrlLow')
                            
                            if url_key:
                                # urlKey 是相对路径，尝试拼接成完整URL
                                # 根据观察，urlKey 格式如：/img2img/nomark/xxx/xxx.png
                                image_url = f"https://api.hunyuan.tencent.com{url_key}"
                                # 同时保存有水印URL作为备用
                                self._fallback_image_url = watermarked_url
                            else:
                                # 没有urlKey，使用有水印版本
                                image_url = watermarked_url
                                self._fallback_image_url = None

                        # 处理元数据（静默处理，不打印）
                        elif msg_type == 'meta':
                            pass

                    except json.JSONDecodeError:
                        # 非 JSON 数据，可能是纯文本
                        if data_content:
                            full_text_parts.append(data_content)

        except Exception as e:
            print(f"[HunyuanImg2Img] 解析 SSE 流异常：{e}")

        full_text = ''.join(full_text_parts)
        text_response = ''.join(text_response_parts)  # 整合纯文本响应
        return image_url, full_text, text_response

    def _download_image_to_tensor(self, image_url):
        """
        下载单张图片并转换为 ComfyUI IMAGE 张量

        参数：
            image_url: 图片URL
        返回：
            tensor: [1,H,W,3] 的张量
        """
        # 首先尝试主URL（无水印版本）
        try:
            resp = requests.get(image_url, timeout=60)
            resp.raise_for_status()

            img = Image.open(BytesIO(resp.content)).convert("RGB")
            np_img = np.array(img, dtype=np.float32) / 255.0
            tensor_img = torch.from_numpy(np_img).unsqueeze(0)  # [1,H,W,3]
            return tensor_img

        except Exception as e:
            # 主URL失败，尝试备用URL（有水印版本）
            if self._fallback_image_url and self._fallback_image_url != image_url:
                print(f"[HunyuanImg2Img] 无水印图片下载失败，尝试有水印版本...")
                try:
                    resp = requests.get(self._fallback_image_url, timeout=60)
                    resp.raise_for_status()

                    img = Image.open(BytesIO(resp.content)).convert("RGB")
                    np_img = np.array(img, dtype=np.float32) / 255.0
                    tensor_img = torch.from_numpy(np_img).unsqueeze(0)  # [1,H,W,3]
                    print(f"[HunyuanImg2Img] 有水印图片下载成功")
                    return tensor_img
                except Exception as e2:
                    print(f"[HunyuanImg2Img] 下载图片失败：{e2}")
                    raise RuntimeError(f"下载图片失败：{e2}")
            else:
                print(f"[HunyuanImg2Img] 下载图片失败：{e}")
                raise RuntimeError(f"下载图片失败：{e}")


# 节点注册
NODE_CLASS_MAPPINGS = {
    "Hunyuan_Img2Img": HunyuanImg2ImgNode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Hunyuan_Img2Img": "🦉Hunyuan Img2Img 图生图"
}
