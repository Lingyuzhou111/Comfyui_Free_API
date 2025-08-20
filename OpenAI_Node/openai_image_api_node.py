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
    实现图像生成和图像编辑的通用API调用，支持多种API格式：
    1. 传统images/generations端点（OpenAI、魔搭、SiliconFlow、火山方舟等）
    2. chat/completions端点（使用于使用聊天格式的图像生成平台）
    
    输入参数：base_url, model, api_key, user_prompt, image1-4(可选), size, num_images, api_endpoint
    输出：image（生成的图像）, generation_info（生成信息，包含image_url和total_tokens）
    
    支持功能：
    - 文生图：纯文本提示词生成图像
    - 图生图：基于输入图像和提示词生成新图像
    - 多平台兼容：自动适配不同平台的API格式差异
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://api.openai.com/v1", "multiline": False}),
                "api_endpoint": (["images/generations", "chat/completions"], {"default": "images/generations"}),
                "model": ("STRING", {"default": "dall-e-3", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "user_prompt": ("STRING", {"multiline": True, "default": "生成一只可爱的小猫"}),
                "size": (["1024x1024", "768x1344", "1344x768", "864x1152", "1152x864", "1328x1328", "928x1664", "1664x928", "1104x1472", "1472x1104", "1024x1536", "1536x1024"], {"default": "1024x1024"}),
                "num_images": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "generation_info")
    FUNCTION = "generate_image"
    CATEGORY = "API/OpenAI"

    def generate_image(self, base_url, model, api_key, user_prompt, size, num_images, api_endpoint, image1=None, image2=None, image3=None, image4=None):
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
        
        # 验证gpt-image-1模型的尺寸限制
        if model == "gpt-image-1":
            valid_sizes = ["1024x1024", "1536x1024", "1024x1536"]
            if size not in valid_sizes:
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"错误：gpt-image-1模型仅支持尺寸 {valid_sizes}，当前尺寸：{size}")
        
        # 检查是否有输入图像，决定使用哪个API端点
        input_images = [img for img in [image1, image2, image3, image4] if img is not None]
        
        # 根据选择的API端点决定请求方式
        if api_endpoint == "chat/completions":
            # 使用chat/completions端点
            return self._chat_completions_request(base_url, model, api_key, user_prompt, input_images, size, num_images)
        else:
            # 使用传统的images端点
            if input_images:
                # 图像编辑模式
                return self._edit_images(base_url, model, api_key, user_prompt, input_images, size)
            else:
                # 图像生成模式
                return self._generate_images(base_url, model, api_key, user_prompt, size, num_images)

    def _generate_images(self, base_url, model, api_key, user_prompt, size, num_images):
        """
        图像生成模式
        """
        try:
            # 根据API端点选择合适的请求格式
            api_url = f"{base_url.rstrip('/')}/images/generations"

            # 检测不同平台的API类型并设置对应的response_format
            is_modelscope = "modelscope.cn" in base_url
            is_siliconflow = "siliconflow.cn" in base_url
            is_volcengine = "volces.com" in base_url
            
            # 为不同平台设置固定的response_format
            if is_modelscope or is_siliconflow or is_volcengine:
                response_format = "url"  # 其他平台默认返回URL
            else:
                response_format = "b64_json"  # OpenAI兼容API默认返回base64
            
            if is_modelscope:
                # 魔搭平台API格式
                payload = {
                    "model": model,
                    "prompt": user_prompt,
                    "n": num_images,
                    "size": size,
                    'steps': 30,
                    'guidance': 4.0
                }
            elif is_siliconflow:
                # SiliconFlow平台API格式
                payload = {
                    "model": model,
                    "prompt": user_prompt,
                    "image_size": size,
                    "batch_size": num_images,
                    "num_inference_steps": 20, # 固定值
                    "guidance_scale": 7.5 # 固定值
                }
            elif is_volcengine:
                # 火山方舟平台API格式
                payload = {
                    "model": model,
                    "prompt": user_prompt,
                    "response_format": response_format,
                    "size": size,
                    "guidance_scale": 3, # 固定值
                    "watermark": False # 固定值
                }
            else:
                # OpenAI兼容格式
                payload = {
                    "model": model,
                    "prompt": user_prompt,
                    "n": num_images,
                    "size": size,
                    "response_format": response_format
                }
           
            # 发送请求
            headers = self._build_headers(api_key)
            # 魔搭平台建议使用异步模式，以适配如 Qwen/Qwen-Image 等需要 task_id 轮询的模型
            if is_modelscope:
                headers["X-ModelScope-Async-Mode"] = "true"
            print(f"[OpenAIImageAPI] 正在请求图像生成API: {api_url}")
            print(f"[OpenAIImageAPI] 请求参数: model={model}, size={size}, n={num_images}")
            if is_modelscope:
                print(f"[OpenAIImageAPI] API类型: 魔搭平台")
            elif is_siliconflow:
                print(f"[OpenAIImageAPI] API类型: SiliconFlow平台")
                print(f"[OpenAIImageAPI] SiliconFlow参数: num_inference_steps={20}, guidance_scale={7.5}")
            elif is_volcengine:
                print(f"[OpenAIImageAPI] API类型: 火山方舟平台")
                print(f"[OpenAIImageAPI] 火山方舟参数: guidance_scale={3}, watermark=False")
            else:
                print(f"[OpenAIImageAPI] API类型: OpenAI兼容")
            #print(f"[OpenAIImageAPI] 请求头: {headers}")
            print(f"[OpenAIImageAPI] 请求载荷: {self._safe_json_dumps(payload)}")
            
            resp = requests.post(api_url, headers=headers, json=payload, timeout=300)
            
            # 不立即抛出异常，让后续逻辑处理响应
            print(f"[OpenAIImageAPI] 响应状态码: {resp.status_code}")
            #print(f"[OpenAIImageAPI] 响应头: {dict(resp.headers)}")

            # 魔搭平台部分模型（如 Qwen/Qwen-Image）会返回 task_id，需要轮询任务结果
            if is_modelscope:
                try:
                    data = resp.json()
                    print(f"[OpenAIImageAPI] 魔搭初始响应: {self._safe_json_dumps(data)}")
                except Exception:
                    data = None

                # 400 时，尝试使用最小载荷进行一次重试（仅 model + prompt）
                if resp.status_code == 400:
                    try:
                        minimal_payload = {
                            "model": model,
                            "prompt": user_prompt
                        }
                        print("检测到 400，使用最小参数重试魔搭提交...")
                        print(f"[OpenAIImageAPI] 最小载荷: {self._safe_json_dumps(minimal_payload)}")
                        resp_retry = requests.post(api_url, headers=headers, json=minimal_payload, timeout=300)
                        print(f"[OpenAIImageAPI] 重试响应状态码: {resp_retry.status_code}")
                        print(f"[OpenAIImageAPI] 重试响应头: {dict(resp_retry.headers)}")
                        try:
                            data_retry = resp_retry.json()
                            print(f"[OpenAIImageAPI] 重试响应JSON: {self._safe_json_dumps(data_retry)}")
                        except Exception:
                            data_retry = None
                        # 若拿到 task_id，进入轮询
                        if data_retry and isinstance(data_retry, dict) and data_retry.get("task_id"):
                            return self._poll_modelscope_task(base_url, data_retry.get("task_id"), api_key)
                        # 否则走通用解析
                        return self._parse_image_response(resp_retry)
                    except Exception as _:
                        # 重试过程失败则继续走通用处理
                        pass

                # 首次响应就包含 task_id，直接轮询
                if data and isinstance(data, dict) and data.get("task_id"):
                    return self._poll_modelscope_task(base_url, data.get("task_id"), api_key)

                # 否则走通用解析（支持部分模型直接同步返回 images）
                return self._parse_image_response(resp)

            # 非魔搭平台直接按通用解析
            return self._parse_image_response(resp)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"图像生成失败: {e}")

    def _chat_completions_request(self, base_url, model, api_key, user_prompt, input_images, size, num_images):
        """
        使用chat/completions端点进行图像生成（支持文生图和图生图）
        适用于使用OpenAI聊天格式的图像生成平台
        """
        try:
            # 构建API端点URL
            api_url = f"{base_url.rstrip('/')}/chat/completions"
            
            print(f"[OpenAIImageAPI] 正在请求Chat Completions API: {api_url}")
            print(f"[OpenAIImageAPI] 请求参数: model={model}, 输入图像数量={len(input_images)}")
            
            # 构建消息内容
            content = [{"type": "text", "text": user_prompt}]
            
            # 如果有输入图像，添加到消息内容中（图生图模式）
            if input_images:
                print(f"[OpenAIImageAPI] 图生图模式: 处理 {len(input_images)} 张输入图像")
                for i, img in enumerate(input_images):
                    try:
                        # 将图像转换为PIL Image
                        pil_image = self._convert_to_pil(img)
                        
                        # 转换为base64
                        img_buffer = BytesIO()
                        pil_image.save(img_buffer, format="PNG")
                        img_buffer.seek(0)
                        
                        image_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                        base64_url = f"data:image/png;base64,{image_base64}"
                        
                        # 添加图像到消息内容
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": base64_url,
                                "detail": "high"
                            }
                        })
                        
                        print(f"[OpenAIImageAPI] 图像{i+1}处理成功: 尺寸={pil_image.size}, base64长度={len(image_base64)}")
                        
                    except Exception as e:
                        print(f"[OpenAIImageAPI] 图像{i+1}处理失败: {e}")
                        empty_image = self._create_empty_image()
                        if empty_image is None:
                            import torch
                            empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                        return (empty_image, f"图像{i+1}处理失败: {e}")
            else:
                print(f"[OpenAIImageAPI] 文生图模式: 纯文本提示词生成")
            
            # 构建请求载荷（参考lmarena-api.js的格式）
            payload = {
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": content
                }],
                "max_tokens": 1000,
                "temperature": 0.7
            }
            
            # 发送请求
            headers = self._build_headers(api_key)
            print(f"[OpenAIImageAPI] 请求载荷: {self._safe_json_dumps(payload)}")
            
            resp = requests.post(api_url, headers=headers, json=payload, timeout=300)
            
            print(f"[OpenAIImageAPI] 响应状态码: {resp.status_code}")
            print(f"[OpenAIImageAPI] 响应头: {dict(resp.headers)}")
            
            # 解析chat/completions格式的响应
            return self._parse_chat_completions_response(resp)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"Chat Completions请求失败: {e}")

    def _edit_images(self, base_url, model, api_key, user_prompt, input_images, size):
        """
        图像编辑模式
        """
        try:
            # 检测是否是火山方舟平台API
            is_volcengine = "volces.com" in base_url
            
            if is_volcengine:
                # 火山方舟平台图生图API
                return self._edit_images_volcengine(base_url, model, api_key, user_prompt, input_images, size)
            else:
                # 其他平台的图像编辑API
                return self._edit_images_standard(base_url, model, api_key, user_prompt, input_images, size)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"图像编辑失败: {e}")

    def _edit_images_volcengine(self, base_url, model, api_key, user_prompt, input_images, size):
        """
        火山方舟平台图像编辑模式
        """
        try:
            # 火山方舟平台使用标准的JSON格式，但需要将图像转换为base64
            headers = self._build_headers(api_key)
            api_url = f"{base_url.rstrip('/')}/images/generations"
            
            print(f"[OpenAIImageAPI] 正在请求火山方舟图像编辑API: {api_url}")
            print(f"[OpenAIImageAPI] 请求参数: model={model}, 输入图像数量={len(input_images)}")
            print(f"[OpenAIImageAPI] 请求头: {headers}")
            
            # 处理第一张输入图像（火山方舟只支持单张图像）
            if input_images:
                try:
                    pil_image = self._convert_to_pil(input_images[0])
                    img_buffer = BytesIO()
                    pil_image.save(img_buffer, format="PNG")
                    img_buffer.seek(0)
                    
                    # 转换为base64
                    import base64
                    image_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                    
                    print(f"[OpenAIImageAPI] 图像处理成功: 尺寸={pil_image.size}, 大小={len(img_buffer.getvalue())} bytes")
                    
                    # 构造火山方舟图生图请求
                    payload = {
                        "model": model,
                        "prompt": user_prompt,
                        "image": f"data:image/png;base64,{image_base64}",
                        "response_format": "url", # 火山方舟固定返回URL
                        "size": "adaptive", # 火山方舟图生图固定使用adaptive
                        "guidance_scale": 5.5, # 固定值
                        "watermark": False # 固定值
                    }
                    
                    print(f"[OpenAIImageAPI] 请求载荷: {self._safe_json_dumps(payload)}")
                    
                    resp = requests.post(api_url, headers=headers, json=payload, timeout=300)
                    
                    print(f"[OpenAIImageAPI] 响应状态码: {resp.status_code}")
                    print(f"[OpenAIImageAPI] 响应头: {dict(resp.headers)}")
                    
                    return self._parse_image_response(resp)
                    
                except Exception as e:
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, f"图像处理失败: {e}")
            else:
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, "没有输入图像")
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"火山方舟图像编辑失败: {e}")

    def _edit_images_standard(self, base_url, model, api_key, user_prompt, input_images, size):
        """
        标准图像编辑模式（其他平台）
        """
        try:
            # 构造multipart/form-data请求
            headers = self._build_headers(api_key)
            # 移除Content-Type，让requests自动设置multipart边界
            headers.pop("Content-Type", None)
            
            api_url = f"{base_url.rstrip('/')}/images/edits"
            print(f"[OpenAIImageAPI] 正在请求图像编辑API: {api_url}")
            print(f"[OpenAIImageAPI] 请求参数: model={model}, 输入图像数量={len(input_images)}")
            print(f"[OpenAIImageAPI] 请求头: {headers}")
            
            # 准备multipart数据
            files = []
            data = {
                "model": model,
                "prompt": user_prompt,
                "n": "1",
                "size": size,
                "quality": "auto"
            }
            
            print(f"[OpenAIImageAPI] 请求数据: {self._safe_json_dumps(data)}")
            print(f"[OpenAIImageAPI] 图像文件数量: {len(files)}")

            
            # 添加图像文件
            for i, img in enumerate(input_images):
                try:
                    # 将图像转换为PIL Image并保存为临时文件
                    pil_image = self._convert_to_pil(img)
                    img_buffer = BytesIO()
                    pil_image.save(img_buffer, format="PNG")
                    img_buffer.seek(0)
                    
                    # OpenAI图生图支持多张输入图像，添加所有图像
                    files.append(("image", (f"image_{i+1}.png", img_buffer.getvalue(), "image/png")))
                    print(f"[OpenAIImageAPI] 图像{i+1}处理成功: 尺寸={pil_image.size}, 大小={len(img_buffer.getvalue())} bytes")
                except Exception as e:
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, f"图像{i+1}处理失败: {e}")
            
            # 发送multipart请求
            resp = requests.post(api_url, headers=headers, data=data, files=files, timeout=300)
            
            # 不立即抛出异常，让_parse_image_response处理所有响应
            print(f"[OpenAIImageAPI] 响应状态码: {resp.status_code}")
            print(f"[OpenAIImageAPI] 响应头: {dict(resp.headers)}")
            
            return self._parse_image_response(resp)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"图像编辑失败: {e}")

    def _parse_image_response(self, resp):
        """
        解析图像API响应
        """
        try:
            # 检查HTTP状态码
            if resp.status_code != 200:
                error_text = resp.text
                print(f"[OpenAIImageAPI] API返回错误状态码: {resp.status_code}")
                print(f"[OpenAIImageAPI] 错误响应内容: {error_text}")
                print(f"[OpenAIImageAPI] 响应头: {dict(resp.headers)}")
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
                print(f"[OpenAIImageAPI] JSON解析失败: {json_error}")
                print(f"[OpenAIImageAPI] 响应内容: {resp.text[:500]}...")
                print(f"[OpenAIImageAPI] 响应类型: {resp.headers.get('content-type', 'unknown')}")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"API响应格式错误: {resp.text[:200]}")
            
            print(f"[OpenAIImageAPI] API原始响应: {self._safe_json_dumps(data)}")  # 调试输出，截断长base64字符串
            
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
            
            # 初始化变量
            pil_image = None
            image_url = None
            
            # 解析响应数据 - 支持多种API格式
            if "data" in data and data["data"]:
                # 标准图像生成API格式
                image_data = data["data"][0]  # 取第一张图像
                print(f"[OpenAIImageAPI] 找到图像数据: {list(image_data.keys())}")
                
                if "b64_json" in image_data:
                    # 处理base64格式（优先，因为OpenAI兼容API默认返回此格式）
                    b64_data = image_data["b64_json"]
                    print(f"[OpenAIImageAPI] 处理base64图像数据，长度: {len(b64_data)}, 预览: {self._truncate_base64_log(b64_data)}")
                    # 处理可能包含数据URI前缀的base64数据
                    if b64_data.startswith('data:image/'):
                        # 移除数据URI前缀，只保留base64数据部分
                        b64_data = b64_data.split(',', 1)[1]
                    image_bytes = base64.b64decode(b64_data)
                    pil_image = Image.open(BytesIO(image_bytes))
                    print(f"[OpenAIImageAPI] base64图像加载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}")
                elif "url" in image_data:
                    # 处理URL格式
                    image_url = image_data["url"]
                    print(f"[OpenAIImageAPI] 下载图像: {image_url}")
                    img_resp = requests.get(image_url, timeout=30)
                    img_resp.raise_for_status()
                    pil_image = Image.open(BytesIO(img_resp.content))
                    print(f"[OpenAIImageAPI] URL图像下载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}, 大小={len(img_resp.content)} bytes")
                else:
                    print(f"[OpenAIImageAPI] 未找到支持的图像格式，可用字段: {list(image_data.keys())}")
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, "API响应中未找到图像数据")
            elif "images" in data and data["images"]:
                # 魔搭平台API格式
                image_data = data["images"][0]  # 取第一张图像
                print(f"[OpenAIImageAPI] 找到魔搭平台图像数据: {list(image_data.keys())}")
                
                if "url" in image_data:
                    # 处理URL格式
                    image_url = image_data["url"]
                    print(f"[OpenAIImageAPI] 下载魔搭平台图像: {image_url}")
                    img_resp = requests.get(image_url, timeout=30)
                    img_resp.raise_for_status()
                    pil_image = Image.open(BytesIO(img_resp.content))
                    print(f"[OpenAIImageAPI] 魔搭平台图像下载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}, 大小={len(img_resp.content)} bytes")
                else:
                    print(f"[OpenAIImageAPI] 未找到支持的魔搭平台图像格式，可用字段: {list(image_data.keys())}")
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, "魔搭平台API响应中未找到图像数据")
            elif "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                # SiliconFlow平台API格式 - 可能直接返回图像数据
                image_data = data["data"][0]  # 取第一张图像
                print(f"[OpenAIImageAPI] 找到SiliconFlow图像数据: {list(image_data.keys())}")
                
                if "url" in image_data:
                    # 处理URL格式
                    image_url = image_data["url"]
                    print(f"[OpenAIImageAPI] 下载SiliconFlow图像: {image_url}")
                    img_resp = requests.get(image_url, timeout=30)
                    img_resp.raise_for_status()
                    pil_image = Image.open(BytesIO(img_resp.content))
                    print(f"[OpenAIImageAPI] SiliconFlow图像下载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}, 大小={len(img_resp.content)} bytes")
                elif "b64_json" in image_data:
                    # 处理base64格式
                    b64_data = image_data["b64_json"]
                    print(f"[OpenAIImageAPI] 处理SiliconFlow base64图像数据，长度: {len(b64_data)}, 预览: {self._truncate_base64_log(b64_data)}")
                    image_bytes = base64.b64decode(b64_data)
                    pil_image = Image.open(BytesIO(image_bytes))
                    print(f"[OpenAIImageAPI] SiliconFlow base64图像加载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}")
                else:
                    print(f"[OpenAIImageAPI] 未找到支持的SiliconFlow图像格式，可用字段: {list(image_data.keys())}")
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, "SiliconFlow API响应中未找到图像数据")
            elif "choices" in data and data["choices"]:
                # 聊天完成API格式（如fuio.tech）
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "")
                finish_reason = choice.get("finish_reason", "")
                
                print(f"[OpenAIImageAPI] 聊天完成格式响应: finish_reason={finish_reason}")
                print(f"[OpenAIImageAPI] 响应内容: {content[:200]}...")
                
                # 检查是否是处理中的状态
                if finish_reason == "processing" or "正在准备生成任务" in content:
                    # 对于异步API，我们需要轮询等待结果
                    return self._handle_async_response(data, resp.request.headers, resp.url)
                
                # 尝试从内容中提取图像URL或base64
                # 这里需要根据具体API的响应格式来解析
                # 暂时返回处理中状态
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"API返回聊天格式，需要进一步处理: {content[:100]}...")
            else:
                print(f"[OpenAIImageAPI] 未找到支持的响应格式，可用字段: {list(data.keys())}")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, "API响应格式不支持")
            
            # 如果到达这里，说明找到了图像数据，进行后续处理
            # 转换为ComfyUI格式
            print(f"[OpenAIImageAPI] 开始转换为ComfyUI格式...")
            comfyui_image = self._pil_to_comfyui(pil_image)
            if comfyui_image is None:
                print(f"[OpenAIImageAPI] ComfyUI格式转换失败，使用空图像")
                # 如果转换失败，使用空图像
                import torch
                comfyui_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            else:
                print(f"[OpenAIImageAPI] ComfyUI格式转换成功: 形状={comfyui_image.shape}, 类型={comfyui_image.dtype}")
            
            # 格式化生成信息
            generation_info = self._format_generation_info(data, image_url)
            print(f"[OpenAIImageAPI] 生成信息: {generation_info}")
            
            return (comfyui_image, generation_info)
                
        except Exception as e:
            print(f"[OpenAIImageAPI] 响应解析异常: {e}")
            print(f"[OpenAIImageAPI] 响应状态码: {resp.status_code}")
            print(f"[OpenAIImageAPI] 响应头: {dict(resp.headers)}")
            print(f"[OpenAIImageAPI] 响应内容: {resp.text[:500]}...")
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"响应解析失败: {e}")

    def _parse_chat_completions_response(self, resp):
        """
        解析chat/completions格式的API响应
        用于处理平台返回的聊天格式响应
        """
        try:
            # 检查HTTP状态码
            if resp.status_code != 200:
                error_text = resp.text
                print(f"[OpenAIImageAPI] Chat Completions API返回错误状态码: {resp.status_code}")
                print(f"[OpenAIImageAPI] 错误响应内容: {error_text}")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"Chat Completions API错误 (状态码: {resp.status_code}): {error_text}")
            
            # 检查响应内容是否为空
            if not resp.text.strip():
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, "Chat Completions API返回空响应")
            
            # 尝试解析JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as json_error:
                print(f"[OpenAIImageAPI] Chat Completions JSON解析失败: {json_error}")
                print(f"[OpenAIImageAPI] 响应内容: {resp.text[:500]}...")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"Chat Completions API响应格式错误: {resp.text[:200]}")
            
            print(f"[OpenAIImageAPI] Chat Completions API原始响应: {self._safe_json_dumps(data)}")
            
            # 检查是否有错误信息
            if "error" in data:
                error_info = data["error"]
                error_message = error_info.get("message", "未知错误")
                error_type = error_info.get("type", "未知类型")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"Chat Completions API错误 ({error_type}): {error_message}")
            
            # 解析choices数据（标准chat/completions格式）
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                message = choice.get("message", {})
                
                # 检查是否有attachments字段（生成的图像）
                attachments = message.get("attachments") or message.get("experimental_attachments")
                
                if attachments and len(attachments) > 0:
                    # 找到生成的图像URL
                    image_url = attachments[0].get("url")
                    if image_url:
                        print(f"[OpenAIImageAPI] 从Chat Completions响应中找到图像URL: {image_url}")
                        try:
                            # 下载图像
                            img_resp = requests.get(image_url, timeout=30)
                            img_resp.raise_for_status()
                            pil_image = Image.open(BytesIO(img_resp.content))
                            print(f"[OpenAIImageAPI] Chat Completions图像下载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}")
                            
                            # 转换为ComfyUI格式
                            comfyui_image = self._pil_to_comfyui(pil_image)
                            if comfyui_image is None:
                                print(f"[OpenAIImageAPI] ComfyUI格式转换失败，使用空图像")
                                import torch
                                comfyui_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                            else:
                                print(f"[OpenAIImageAPI] Chat Completions ComfyUI格式转换成功: 形状={comfyui_image.shape}")
                            
                            # 格式化生成信息
                            generation_info = self._format_generation_info(data, image_url)
                            print(f"[OpenAIImageAPI] Chat Completions生成信息: {generation_info}")
                            
                            return (comfyui_image, generation_info)
                            
                        except Exception as e:
                            print(f"[OpenAIImageAPI] Chat Completions图像下载失败: {e}")
                            empty_image = self._create_empty_image()
                            if empty_image is None:
                                import torch
                                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                            return (empty_image, f"Chat Completions图像下载失败: {e}")
                    else:
                        print(f"[OpenAIImageAPI] Chat Completions响应中未找到图像URL")
                        empty_image = self._create_empty_image()
                        if empty_image is None:
                            import torch
                            empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                        return (empty_image, "Chat Completions响应中未找到图像URL")
                else:
                    # 检查消息内容是否包含图像信息
                    content = message.get("content", "")
                    print(f"[OpenAIImageAPI] Chat Completions消息内容: {content[:200]}...")
                    
                    # 尝试从内容中提取图像URL（某些平台可能在文本中返回URL）
                    # 首先尝试提取Markdown格式的图像链接 ![alt](url)
                    markdown_pattern = r'!\[.*?\]\((https?://[^)]+\.(?:jpg|jpeg|png|gif|webp|bmp)[^)]*)\)'
                    markdown_urls = re.findall(markdown_pattern, content, re.IGNORECASE)
                    print(f"[OpenAIImageAPI] Markdown格式URL提取结果: {markdown_urls}")
                    
                    # 如果没找到Markdown格式，尝试直接提取URL（支持查询参数）
                    if not markdown_urls:
                        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]()]+\.(?:jpg|jpeg|png|gif|webp|bmp)(?:\?[^\s<>"{}|\\^`\[\]()]*)?'
                        urls = re.findall(url_pattern, content, re.IGNORECASE)
                        print(f"[OpenAIImageAPI] 直接URL提取结果: {urls}")
                    else:
                        urls = markdown_urls
                        print(f"[OpenAIImageAPI] 使用Markdown URL提取结果")
                    
                    if urls:
                        image_url = urls[0]
                        print(f"[OpenAIImageAPI] 从Chat Completions文本内容中提取到图像URL: {image_url}")
                        try:
                            # 下载图像
                            img_resp = requests.get(image_url, timeout=30)
                            img_resp.raise_for_status()
                            pil_image = Image.open(BytesIO(img_resp.content))
                            print(f"[OpenAIImageAPI] 提取URL图像下载成功: 尺寸={pil_image.size}")
                            
                            # 转换为ComfyUI格式
                            comfyui_image = self._pil_to_comfyui(pil_image)
                            if comfyui_image is None:
                                import torch
                                comfyui_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                            
                            # 格式化生成信息
                            generation_info = self._format_generation_info(data, image_url)
                            
                            return (comfyui_image, generation_info)
                            
                        except Exception as e:
                            print(f"[OpenAIImageAPI] 提取URL图像下载失败: {e}")
                            empty_image = self._create_empty_image()
                            if empty_image is None:
                                import torch
                                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                            return (empty_image, f"提取URL图像下载失败: {e}")
                    else:
                        empty_image = self._create_empty_image()
                        if empty_image is None:
                            import torch
                            empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                        return (empty_image, f"Chat Completions响应中未找到图像数据: {content[:100]}...")
            else:
                print(f"[OpenAIImageAPI] Chat Completions响应格式异常，可用字段: {list(data.keys())}")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, "Chat Completions响应格式不支持")
                
        except Exception as e:
            print(f"[OpenAIImageAPI] Chat Completions响应解析异常: {e}")
            print(f"[OpenAIImageAPI] 响应状态码: {resp.status_code}")
            print(f"[OpenAIImageAPI] 响应内容: {resp.text[:500]}...")
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"Chat Completions响应解析失败: {e}")

    def _handle_async_response(self, initial_data, headers, api_url):
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
        
        print(f"[OpenAIImageAPI] 开始轮询等待结果，请求ID: {request_id}")
        
        # 轮询参数
        max_attempts = 30  # 最大轮询次数
        poll_interval = 10  # 轮询间隔（秒）
        
        for attempt in range(max_attempts):
            print(f"[OpenAIImageAPI] 轮询尝试 {attempt + 1}/{max_attempts}")
            
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
                    print(f"[OpenAIImageAPI] 轮询响应: {poll_data}")
                    
                    # 检查是否完成
                    if "choices" in poll_data and poll_data["choices"]:
                        choice = poll_data["choices"][0]
                        finish_reason = choice.get("finish_reason", "")
                        
                        if finish_reason != "processing":
                            # 任务完成，解析结果
                            print(f"[OpenAIImageAPI] 任务完成，finish_reason: {finish_reason}")
                            return self._parse_image_response(poll_resp)
                        else:
                            print(f"[OpenAIImageAPI] 任务仍在处理中，等待 {poll_interval} 秒...")
                            time.sleep(poll_interval)
                    else:
                        print(f"[OpenAIImageAPI] 轮询响应格式异常: {poll_data}")
                        time.sleep(poll_interval)
                else:
                    print(f"[OpenAIImageAPI] 轮询请求失败，状态码: {poll_resp.status_code}")
                    time.sleep(poll_interval)
                    
            except Exception as e:
                print(f"[OpenAIImageAPI] 轮询异常: {e}")
                time.sleep(poll_interval)
        
        # 超时
        empty_image = self._create_empty_image()
        if empty_image is None:
            import torch
            empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
        return (empty_image, f"轮询超时，请检查后台任务状态")

    def _poll_modelscope_task(self, base_url, task_id, api_key):
        """
        轮询魔搭（ModelScope）异步任务，直到成功或超时。
        成功后下载图片并转换为 ComfyUI 格式。
        """
        import time
        try:
            tasks_url = f"https://api-inference.modelscope.cn/v1/tasks/{task_id}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "X-ModelScope-Task-Type": "image_generation"
            }

            max_attempts = 60  # 最长约 5 分钟（60*5s）
            poll_interval = 5

            print(f"[OpenAIImageAPI] 开始轮询魔搭任务: task_id={task_id}, url={tasks_url}")
            for attempt in range(max_attempts):
                print(f"[OpenAIImageAPI] 魔搭轮询尝试 {attempt + 1}/{max_attempts}")
                resp = requests.get(tasks_url, headers=headers, timeout=60)
                if resp.status_code != 200:
                    print(f"[OpenAIImageAPI] 任务查询失败: {resp.status_code}, {resp.text[:200]}")
                    time.sleep(poll_interval)
                    continue

                data = resp.json()
                #print(f"[OpenAIImageAPI] 任务查询返回: {self._safe_json_dumps(data)}")
                status = data.get("task_status") or data.get("status")

                if status == "SUCCEED":
                    output_images = data.get("output_images") or []
                    if not output_images:
                        # 兼容可能的字段
                        images = data.get("images") or []
                        if images and isinstance(images[0], dict):
                            image_url = images[0].get("url")
                        else:
                            image_url = images[0] if images else None
                    else:
                        image_url = output_images[0]

                    if not image_url:
                        raise Exception("任务成功但未返回图片URL")

                    print(f"[OpenAIImageAPI] 任务完成，下载图片: {image_url}")
                    img_resp = requests.get(image_url, timeout=60)
                    img_resp.raise_for_status()
                    pil_image = Image.open(BytesIO(img_resp.content))
                    if pil_image.mode != "RGB":
                        pil_image = pil_image.convert("RGB")

                    comfyui_image = self._pil_to_comfyui(pil_image)
                    if comfyui_image is None:
                        import torch
                        comfyui_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)

                    # 构造生成信息，至少包含 image_url
                    gen_info = self._format_generation_info({"images": [{"url": image_url}]}, image_url)
                    return (comfyui_image, gen_info)

                if status == "FAILED":
                    raise Exception(f"任务失败: {self._safe_json_dumps(data)}")

                # 继续等待
                time.sleep(poll_interval)

            # 超时
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, "魔搭任务轮询超时")

        except Exception as e:
            print(f"[OpenAIImageAPI] 魔搭任务轮询异常: {e}")
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"魔搭任务轮询失败: {e}")

    def _convert_to_pil(self, image):
        """
        将ComfyUI的IMAGE转换为PIL Image
        """
        try:
            print(f"[OpenAIImageAPI] 开始转换图像，输入类型: {type(image)}")
            
            # ComfyUI的IMAGE是torch.Tensor，需要转换为PIL Image
            if hasattr(image, 'cpu'):  # 是torch.Tensor
                print(f"[OpenAIImageAPI] 检测到torch.Tensor，形状: {image.shape}, 类型: {image.dtype}")
                # 转换为numpy数组，然后转为PIL Image
                import torch
                if image.dim() == 4:  # batch维度，取第一张
                    image = image[0]
                    print(f"[OpenAIImageAPI] 取batch第一张，新形状: {image.shape}")
                # 转换为numpy并调整通道顺序 (C,H,W) -> (H,W,C)
                image_np = image.cpu().numpy()
                print(f"[OpenAIImageAPI] 转换为numpy数组，形状: {image_np.shape}, 类型: {image_np.dtype}")
                if image_np.shape[0] == 3:  # 如果是(C,H,W)格式
                    image_np = image_np.transpose(1, 2, 0)
                    print(f"[OpenAIImageAPI] 调整通道顺序后，形状: {image_np.shape}")
                # 确保值在0-255范围内
                image_np = (image_np * 255).clip(0, 255).astype('uint8')
                print(f"[OpenAIImageAPI] 归一化到0-255，值范围: {image_np.min()}-{image_np.max()}")
                img = Image.fromarray(image_np)
                print(f"[OpenAIImageAPI] PIL图像创建成功: 尺寸={img.size}, 模式={img.mode}")
            elif hasattr(image, 'save'):  # 已经是PIL Image
                print(f"[OpenAIImageAPI] 检测到PIL Image，尺寸={image.size}, 模式={image.mode}")
                img = image
            else:
                # 如果是numpy数组，直接转换
                import numpy as np
                if isinstance(image, np.ndarray):
                    print(f"[OpenAIImageAPI] 检测到numpy数组，形状: {image.shape}, 类型: {image.dtype}")
                    if image.shape[0] == 3:  # 如果是(C,H,W)格式
                        image = image.transpose(1, 2, 0)
                        print(f"[OpenAIImageAPI] 调整通道顺序后，形状: {image.shape}")
                    # 确保值在0-255范围内
                    if image.max() <= 1.0:  # 如果是0-1范围
                        image = (image * 255).clip(0, 255).astype('uint8')
                        print(f"[OpenAIImageAPI] 归一化到0-255，值范围: {image.min()}-{image.max()}")
                    img = Image.fromarray(image)
                    print(f"[OpenAIImageAPI] PIL图像创建成功: 尺寸={img.size}, 模式={img.mode}")
                else:
                    raise Exception(f"不支持的图像格式: {type(image)}")
            
            return img
            
        except Exception as e:
            print(f"[OpenAIImageAPI] 图像转换失败: {e}")
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
            print(f"[OpenAIImageAPI] ComfyUI格式转换失败: {e}")
            # 如果转换失败，返回一个安全的空图像
            try:
                import torch
                # 返回符合ComfyUI格式的空图像 (1, H, W, 3)
                return torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            except Exception as e2:
                print(f"[OpenAIImageAPI] 创建安全空图像也失败: {e2}")
                return None

    def _format_generation_info(self, data, image_url):
        """
        格式化生成信息，包含image_url和total_tokens
        """
        generation_info = []
        
        # 添加image_url（必选）
        if image_url:
            generation_info.append(f"image_url:\n{image_url}")
        
        # 提取total_tokens（可选）
        total_tokens = None
        
        # 从不同位置尝试提取total_tokens
        if "usage" in data:
            usage = data["usage"]
            total_tokens = usage.get('total_tokens')
        
        # 如果usage中没有，尝试从其他位置提取
        if not total_tokens and "total_tokens" in data:
            total_tokens = data["total_tokens"]
        
        if total_tokens is not None:
            generation_info.append(f"total_tokens: {total_tokens}")
        
        # 如果没有找到任何信息，返回默认信息
        if not generation_info:
            return "image_url: unknown, total_tokens: unknown"
        
        return "\n\n".join(generation_info)

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
            print(f"[OpenAIImageAPI] 创建空图像失败: {e}")
            # 如果转换失败，尝试直接创建torch tensor
            try:
                import torch
                # 返回符合ComfyUI格式的空图像 (1, H, W, 3)
                empty_tensor = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return empty_tensor
            except Exception as e2:
                print(f"[OpenAIImageAPI] 创建torch tensor也失败: {e2}")
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
