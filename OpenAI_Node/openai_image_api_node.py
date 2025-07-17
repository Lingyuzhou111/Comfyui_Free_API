import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO
import re

# 节点主类
class OpenAIImageAPI:
    """
    ComfyUI自定义节点：OpenAI兼容图像API
    实现图像生成和图像编辑的通用API调用，支持任意兼容OpenAI格式的图像API接口。
    输入参数：base_url, model, api_key, user_prompt, image1-4(可选), size, quality, style, response_format
    输出：image（生成的图像）, tokens_usage（API用量信息）
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://api.openai.com/v1", "multiline": False}),
                "model": ("STRING", {"default": "dall-e-3", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "user_prompt": ("STRING", {"multiline": True, "default": "生成一只可爱的小猫"}),
                "size": (["1024x1024", "768x1344", "864x1152", "1344x768", "1152x864", "1440x720", "720x1440"], {"default": "1024x1024"}),
                "quality": (["standard", "hd"], {"default": "standard"}),
                "style": (["vivid", "natural"], {"default": "vivid"}),
                "response_format": (["url", "b64_json"], {"default": "url"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "tokens_usage")
    FUNCTION = "generate_image"
    CATEGORY = "API/OpenAI"

    def generate_image(self, base_url, model, api_key, user_prompt, size, quality, style, response_format, n, image1=None, image2=None, image3=None, image4=None):
        """
        主图像生成方法：
        1. 根据是否有输入图像决定是图像生成还是图像编辑
        2. 构造OpenAI兼容的图像API请求
        3. 发送请求，返回图像
        4. 解析响应并返回图像数据
        """
        if not api_key:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, "错误：未配置API Key，请在节点参数中设置api_key")
        
        if not base_url:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, "错误：未配置base_url，请在节点参数中设置base_url")
        
        # 检查是否有输入图像，决定使用哪个API端点
        input_images = [img for img in [image1, image2, image3, image4] if img is not None]
        
        if input_images:
            # 图像编辑模式
            return self._edit_images(base_url, model, api_key, user_prompt, input_images, size, quality, style, response_format)
        else:
            # 图像生成模式
            return self._generate_images(base_url, model, api_key, user_prompt, size, quality, style, response_format, n)

    def _generate_images(self, base_url, model, api_key, user_prompt, size, quality, style, response_format, n):
        """
        图像生成模式
        """
        try:
            # 构造请求载荷 - 使用messages格式适配特定API
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                "n": n,
                "size": size
                # 注意：不包含response_format字段，因为某些API不支持
            }
            
            # 添加可选参数
            if quality != "standard":
                payload["quality"] = quality
            if style != "vivid":
                payload["style"] = style
            
            # 发送请求
            headers = self._build_headers(api_key)
            api_url = f"{base_url.rstrip('/')}/chat/completions"
            print(f"正在请求图像生成API: {api_url}")
            print(f"请求参数: model={model}, size={size}, n={n}, quality={quality}, style={style}")
            print(f"请求头: {headers}")
            print(f"请求载荷: {self._safe_json_dumps(payload)}")
            
            resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
            
            # 不立即抛出异常，让_parse_image_response处理所有响应
            print(f"响应状态码: {resp.status_code}")
            print(f"响应头: {dict(resp.headers)}")
            
            return self._parse_image_response(resp, response_format)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"图像生成失败: {e}")

    def _edit_images(self, base_url, model, api_key, user_prompt, input_images, size, quality, style, response_format):
        """
        图像编辑模式
        """
        try:
            # 构造multipart/form-data请求
            headers = self._build_headers(api_key)
            # 移除Content-Type，让requests自动设置multipart边界
            headers.pop("Content-Type", None)
            
            api_url = f"{base_url.rstrip('/')}/chat/completions"
            print(f"正在请求图像编辑API: {api_url}")
            print(f"请求参数: model={model}, 输入图像数量={len(input_images)}, quality={quality}")
            print(f"请求头: {headers}")
            
            # 准备multipart数据
            files = []
            data = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
                # 注意：不包含response_format字段，因为某些API不支持
            }
            
            print(f"请求数据: {self._safe_json_dumps(data)}")
            print(f"图像文件数量: {len(files)}")
            
            # 添加可选参数
            if quality != "standard":
                data["quality"] = quality
            
            # 添加图像文件
            for i, img in enumerate(input_images):
                try:
                    # 将图像转换为PIL Image并保存为临时文件
                    pil_image = self._convert_to_pil(img)
                    img_buffer = BytesIO()
                    pil_image.save(img_buffer, format="PNG")
                    img_buffer.seek(0)
                    
                    files.append(("image[]", (f"image_{i+1}.png", img_buffer.getvalue(), "image/png")))
                    print(f"图像{i+1}处理成功: 尺寸={pil_image.size}, 大小={len(img_buffer.getvalue())} bytes")
                except Exception as e:
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, f"图像{i+1}处理失败: {e}")
            
            # 发送multipart请求
            resp = requests.post(api_url, headers=headers, data=data, files=files, timeout=120)
            
            # 不立即抛出异常，让_parse_image_response处理所有响应
            print(f"响应状态码: {resp.status_code}")
            print(f"响应头: {dict(resp.headers)}")
            
            return self._parse_image_response(resp, response_format)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"图像编辑失败: {e}")

    def _parse_image_response(self, resp, response_format):
        """
        解析图像API响应
        """
        try:
            # 检查HTTP状态码
            if resp.status_code != 200:
                error_text = resp.text
                print(f"API返回错误状态码: {resp.status_code}")
                print(f"错误响应内容: {error_text}")
                print(f"响应头: {dict(resp.headers)}")
                # 返回一个空的图像张量而不是None，避免ComfyUI错误
                empty_image = self._create_empty_image()
                if empty_image is None:
                    # 如果创建空图像失败，使用最后的备选方案
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"API错误 (状态码: {resp.status_code}): {error_text}")
            
            # 检查响应内容是否为空
            if not resp.text.strip():
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, "API返回空响应")
            
            # 尝试解析JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as json_error:
                print(f"JSON解析失败: {json_error}")
                print(f"响应内容: {resp.text[:500]}...")
                print(f"响应类型: {resp.headers.get('content-type', 'unknown')}")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"API响应格式错误: {resp.text[:200]}")
            
            print("API原始响应:", data)  # 调试输出
            
            # 检查是否有错误信息
            if "error" in data:
                error_info = data["error"]
                error_message = error_info.get("message", "未知错误")
                error_type = error_info.get("type", "未知类型")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"API错误 ({error_type}): {error_message}")
            
            # 解析响应数据 - 支持多种API格式
            if "data" in data and data["data"]:
                # 标准图像生成API格式
                image_data = data["data"][0]  # 取第一张图像
                print(f"找到图像数据: {list(image_data.keys())}")
                
                if response_format == "b64_json" and "b64_json" in image_data:
                    # 处理base64格式
                    b64_data = image_data["b64_json"]
                    print(f"处理base64图像数据，长度: {len(b64_data)}, 预览: {self._truncate_base64_log(b64_data)}")
                    image_bytes = base64.b64decode(b64_data)
                    pil_image = Image.open(BytesIO(image_bytes))
                    print(f"base64图像加载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}")
                elif "url" in image_data:
                    # 处理URL格式
                    image_url = image_data["url"]
                    print(f"下载图像: {image_url}")
                    img_resp = requests.get(image_url, timeout=30)
                    img_resp.raise_for_status()
                    pil_image = Image.open(BytesIO(img_resp.content))
                    print(f"URL图像下载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}, 大小={len(img_resp.content)} bytes")
                else:
                    print(f"未找到支持的图像格式，可用字段: {list(image_data.keys())}")
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, "API响应中未找到图像数据")
            elif "choices" in data and data["choices"]:
                # 聊天完成API格式（如fuio.tech）
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "")
                finish_reason = choice.get("finish_reason", "")
                
                print(f"聊天完成格式响应: finish_reason={finish_reason}")
                print(f"响应内容: {content[:200]}...")
                
                # 检查是否是处理中的状态
                if finish_reason == "processing" or "正在准备生成任务" in content:
                    # 对于异步API，我们需要轮询等待结果
                    return self._handle_async_response(data, resp.request.headers, response_format, resp.url)
                
                # 尝试从内容中提取图像URL或base64
                # 这里需要根据具体API的响应格式来解析
                # 暂时返回处理中状态
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"API返回聊天格式，需要进一步处理: {content[:100]}...")
            else:
                print(f"未找到支持的响应格式，可用字段: {list(data.keys())}")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, "API响应格式不支持")
            
            # 如果到达这里，说明找到了图像数据，进行后续处理
            # 转换为ComfyUI格式
            print(f"开始转换为ComfyUI格式...")
            comfyui_image = self._pil_to_comfyui(pil_image)
            if comfyui_image is None:
                print(f"ComfyUI格式转换失败，使用空图像")
                # 如果转换失败，使用空图像
                import torch
                comfyui_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            else:
                print(f"ComfyUI格式转换成功: 形状={comfyui_image.shape}, 类型={comfyui_image.dtype}")
            
            # 解析usage信息
            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)
            print(f"Token使用情况: {tokens_usage}")
            
            return (comfyui_image, tokens_usage)
                
        except Exception as e:
            print(f"响应解析异常: {e}")
            print(f"响应状态码: {resp.status_code}")
            print(f"响应头: {dict(resp.headers)}")
            print(f"响应内容: {resp.text[:500]}...")
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"响应解析失败: {e}")

    def _handle_async_response(self, initial_data, headers, response_format, api_url):
        """
        处理异步响应，轮询等待结果
        """
        import time
        
        # 获取请求ID用于轮询
        request_id = initial_data.get("id")
        if not request_id:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, "无法获取请求ID进行轮询")
        
        print(f"开始轮询等待结果，请求ID: {request_id}")
        
        # 轮询参数
        max_attempts = 30  # 最大轮询次数
        poll_interval = 10  # 轮询间隔（秒）
        
        for attempt in range(max_attempts):
            print(f"轮询尝试 {attempt + 1}/{max_attempts}")
            
            try:
                # 构造轮询请求
                poll_payload = {
                    "id": request_id
                }
                
                # 发送轮询请求
                poll_resp = requests.post(
                    api_url,
                    headers=headers,
                    json=poll_payload,
                    timeout=30
                )
                
                if poll_resp.status_code == 200:
                    poll_data = poll_resp.json()
                    print(f"轮询响应: {poll_data}")
                    
                    # 检查是否完成
                    if "choices" in poll_data and poll_data["choices"]:
                        choice = poll_data["choices"][0]
                        finish_reason = choice.get("finish_reason", "")
                        
                        if finish_reason != "processing":
                            # 任务完成，解析结果
                            print(f"任务完成，finish_reason: {finish_reason}")
                            return self._parse_image_response(poll_resp, response_format)
                        else:
                            print(f"任务仍在处理中，等待 {poll_interval} 秒...")
                            time.sleep(poll_interval)
                    else:
                        print(f"轮询响应格式异常: {poll_data}")
                        time.sleep(poll_interval)
                else:
                    print(f"轮询请求失败，状态码: {poll_resp.status_code}")
                    time.sleep(poll_interval)
                    
            except Exception as e:
                print(f"轮询异常: {e}")
                time.sleep(poll_interval)
        
        # 超时
        empty_image = self._create_empty_image()
        if empty_image is None:
            import torch
            empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
        return (empty_image, f"轮询超时，请检查后台任务状态")

    def _convert_to_pil(self, image):
        """
        将ComfyUI的IMAGE转换为PIL Image
        """
        try:
            print(f"开始转换图像，输入类型: {type(image)}")
            
            # ComfyUI的IMAGE是torch.Tensor，需要转换为PIL Image
            if hasattr(image, 'cpu'):  # 是torch.Tensor
                print(f"检测到torch.Tensor，形状: {image.shape}, 类型: {image.dtype}")
                # 转换为numpy数组，然后转为PIL Image
                import torch
                if image.dim() == 4:  # batch维度，取第一张
                    image = image[0]
                    print(f"取batch第一张，新形状: {image.shape}")
                # 转换为numpy并调整通道顺序 (C,H,W) -> (H,W,C)
                image_np = image.cpu().numpy()
                print(f"转换为numpy数组，形状: {image_np.shape}, 类型: {image_np.dtype}")
                if image_np.shape[0] == 3:  # 如果是(C,H,W)格式
                    image_np = image_np.transpose(1, 2, 0)
                    print(f"调整通道顺序后，形状: {image_np.shape}")
                # 确保值在0-255范围内
                image_np = (image_np * 255).clip(0, 255).astype('uint8')
                print(f"归一化到0-255，值范围: {image_np.min()}-{image_np.max()}")
                img = Image.fromarray(image_np)
                print(f"PIL图像创建成功: 尺寸={img.size}, 模式={img.mode}")
            elif hasattr(image, 'save'):  # 已经是PIL Image
                print(f"检测到PIL Image，尺寸={image.size}, 模式={image.mode}")
                img = image
            else:
                # 如果是numpy数组，直接转换
                import numpy as np
                if isinstance(image, np.ndarray):
                    print(f"检测到numpy数组，形状: {image.shape}, 类型: {image.dtype}")
                    if image.shape[0] == 3:  # 如果是(C,H,W)格式
                        image = image.transpose(1, 2, 0)
                        print(f"调整通道顺序后，形状: {image.shape}")
                    # 确保值在0-255范围内
                    if image.max() <= 1.0:  # 如果是0-1范围
                        image = (image * 255).clip(0, 255).astype('uint8')
                        print(f"归一化到0-255，值范围: {image.min()}-{image.max()}")
                    img = Image.fromarray(image)
                    print(f"PIL图像创建成功: 尺寸={img.size}, 模式={img.mode}")
                else:
                    raise Exception(f"不支持的图像格式: {type(image)}")
            
            return img
            
        except Exception as e:
            print(f"图像转换失败: {e}")
            raise Exception(f"图像转换失败: {e}")

    def _pil_to_comfyui(self, pil_image):
        """
        将PIL Image转换为ComfyUI格式
        参考GLM图像节点的标准处理方式，确保格式符合ComfyUI要求
        """
        try:
            import torch
            import numpy as np
            
            # 转换为RGB模式
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            
            # 转换为numpy数组，直接使用float32并归一化到0-1
            # 参考GLM图像节点的处理方式
            image_np = np.array(pil_image, dtype=np.float32) / 255.0
            
            # 确保数组形状正确 (H, W, 3)
            if len(image_np.shape) != 3 or image_np.shape[2] != 3:
                raise Exception(f"图像格式错误: 期望(H,W,3)，实际{image_np.shape}")
            
            # 转换为torch.Tensor，保持 (H, W, 3) 格式
            image_tensor = torch.from_numpy(image_np)
            
            # 确保tensor形状正确 (H, W, 3)
            if image_tensor.shape != (image_np.shape[0], image_np.shape[1], 3):
                raise Exception(f"Tensor形状错误: 期望(H,W,3)，实际{image_tensor.shape}")
            
            # 添加batch维度，最终格式为 (1, H, W, 3)
            image_tensor = image_tensor.unsqueeze(0)
            
            # 最终检查
            if image_tensor.shape[0] != 1 or image_tensor.shape[3] != 3:
                raise Exception(f"最终tensor形状错误: 期望(1,H,W,3)，实际{image_tensor.shape}")
            
            return image_tensor
            
        except Exception as e:
            print(f"ComfyUI格式转换失败: {e}")
            # 如果转换失败，返回一个安全的空图像
            try:
                import torch
                # 返回符合ComfyUI格式的空图像 (1, H, W, 3)
                return torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            except Exception as e2:
                print(f"创建安全空图像也失败: {e2}")
                return None

    def _format_tokens_usage(self, usage):
        """
        将tokens_usage格式化为易读的字符串
        """
        if not usage:
            return ""
        
        total_tokens = usage.get('total_tokens', '-')
        input_tokens = usage.get('input_tokens', '-')
        output_tokens = usage.get('output_tokens', '-')
        
        # 处理详细的token信息
        input_details = usage.get('input_tokens_details', {})
        if input_details:
            text_tokens = input_details.get('text_tokens', '-')
            image_tokens = input_details.get('image_tokens', '-')
            return f"total_tokens={total_tokens}, input_tokens={input_tokens}(text:{text_tokens},image:{image_tokens}), output_tokens={output_tokens}"
        
        return f"total_tokens={total_tokens}, input_tokens={input_tokens}, output_tokens={output_tokens}"

    def _create_empty_image(self):
        """
        创建一个空的图像张量，用于错误处理
        确保返回符合ComfyUI格式的图像张量 (1, H, W, 3)
        """
        try:
            import torch
            import numpy as np
            # 创建一个符合ComfyUI格式的空图像张量 (1, H, W, 3)
            # 使用numpy先创建，然后转换为torch tensor，确保格式正确
            empty_array = np.zeros((512, 512, 3), dtype=np.float32)
            # 转换为PIL Image，然后使用_pil_to_comfyui确保格式一致
            pil_image = Image.fromarray((empty_array * 255).astype(np.uint8))
            return self._pil_to_comfyui(pil_image)
        except Exception as e:
            print(f"创建空图像失败: {e}")
            # 如果转换失败，尝试直接创建torch tensor
            try:
                import torch
                # 返回符合ComfyUI格式的空图像 (1, H, W, 3)
                empty_tensor = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return empty_tensor
            except Exception as e2:
                print(f"创建torch tensor也失败: {e2}")
                # 最后的备选方案：返回None，让ComfyUI处理
                return None

    def _build_headers(self, api_key):
        """
        构建请求头
        """
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def _truncate_base64_log(self, base64_str, max_length=50):
        """
        截断base64字符串用于日志记录，避免刷屏
        """
        if not base64_str:
            return ""
        if len(base64_str) <= max_length:
            return base64_str
        return f"{base64_str[:max_length]}... (总长度: {len(base64_str)})"

    def _safe_json_dumps(self, obj, ensure_ascii=False, indent=2):
        """
        安全地序列化JSON对象，处理包含base64的字段
        """
        def _process_value(value):
            if isinstance(value, str) and len(value) > 100 and (
                value.startswith('data:image/') or 
                value.startswith('iVBORw0KGgo') or  # PNG base64开头
                value.startswith('/9j/') or          # JPEG base64开头
                all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in value[:20])  # base64特征
            ):
                return self._truncate_base64_log(value)
            elif isinstance(value, dict):
                return {k: _process_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [_process_value(v) for v in value]
            else:
                return value
        
        processed_obj = _process_value(obj)
        return json.dumps(processed_obj, ensure_ascii=ensure_ascii, indent=indent)

# 节点注册
NODE_CLASS_MAPPINGS = {
    "OpenAI_Image_API": OpenAIImageAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenAI_Image_API": "OpenAI兼容Image API节点"
} 