import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO
import re

# 节点主类
class GeminiImageAPI:
    """
    ComfyUI自定义节点：Gemini图像API
    实现图像生成和图像编辑的Gemini API调用，支持文生图和图生图模式。
    输入参数：prompt(必选), image1-4(可选), model
    输出：image（生成的图像）, tokens_usage（API用量信息）
    """
    def __init__(self):
        # 读取配置文件，专门读取IMAGE.gemini_image配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('IMAGE', {}).get('gemini_image', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取Gemini图像模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            gemini_config = config.get('IMAGE', {}).get('gemini_image', {})
        model_options = gemini_config.get('model', ['gemini-2.0-flash-preview-image-generation'])
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "生成一只可爱的小猫"}),
                "model": (model_options, {"default": model_options[0]}),
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
    CATEGORY = "API/Gemini"

    def generate_image(self, prompt, model, image1=None, image2=None, image3=None, image4=None):
        """
        主图像生成方法：
        1. 根据是否有输入图像决定是文生图还是图生图
        2. 构造Gemini API请求
        3. 发送请求，返回图像
        4. 解析响应并返回图像数据
        """
        # 读取Gemini API参数
        base_url = self.config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, "错误：未配置Gemini API Key，请在config.json中设置gemini_image.api_key")
        
        # 检查是否有输入图像，决定使用哪个模式
        input_images = [img for img in [image1, image2, image3, image4] if img is not None]
        
        if input_images:
            # 图生图模式
            return self._edit_images(base_url, api_key, model, prompt, input_images)
        else:
            # 文生图模式
            return self._generate_images(base_url, api_key, model, prompt)

    def _generate_images(self, base_url, api_key, model, prompt):
        """
        文生图模式
        """
        try:
            # 构造Gemini API请求载荷 - 使用原生Gemini格式
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"]
                }
            }
            
            # 发送请求 - 使用正确的Gemini API端点
            headers = self._build_headers(api_key)
            # 修正API URL格式 - 使用正确的Google Gemini API端点
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            print(f"正在请求Gemini文生图API: {api_url}")
            print(f"请求参数: model={model}")
            print(f"请求载荷: {self._safe_json_dumps(payload)}")
            
            # 详细记录请求头信息，用于调试401认证错误
            print(f"=== 请求头详细信息 ===")
            print(f"Authorization: Bearer {api_key[:10]}...{api_key[-10:] if len(api_key) > 20 else '***'}")
            print(f"Content-Type: {headers.get('Content-Type', '未设置')}")
            print(f"API Key长度: {len(api_key)} 字符")
            print(f"API Key是否为空: {not api_key}")
            print(f"API Key是否包含空格: {'是' if ' ' in api_key else '否'}")
            print(f"API Key是否以'AIza'开头: {'是' if api_key.startswith('AIza') else '否'}")
            print(f"=== 请求头详细信息结束 ===")
            
            resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
            
            print(f"响应状态码: {resp.status_code}")
            print(f"响应头: {dict(resp.headers)}")
            
            return self._parse_image_response(resp)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"文生图失败: {e}")

    def _edit_images(self, base_url, api_key, model, prompt, input_images):
        """
        图生图模式
        """
        try:
            # 构造Gemini原生API请求载荷
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"]
                }
            }
            
            # 添加图像到payload中
            for i, img in enumerate(input_images):
                try:
                    # 将图像转换为PIL Image并转换为base64
                    pil_image = self._convert_to_pil(img)
                    img_buffer = BytesIO()
                    pil_image.save(img_buffer, format="PNG")
                    img_buffer.seek(0)
                    image_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                    
                    # 添加图像到parts中
                    payload["contents"][0]["parts"].append({
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": image_base64
                        }
                    })
                    print(f"图像{i+1}处理成功: 尺寸={pil_image.size}, 大小={len(img_buffer.getvalue())} bytes")
                except Exception as e:
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, f"图像{i+1}处理失败: {e}")
            
            # 发送请求
            headers = self._build_headers(api_key)
            # 修正API URL格式 - 使用正确的Google Gemini API端点
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            print(f"正在请求Gemini图生图API: {api_url}")
            print(f"请求参数: model={model}, 输入图像数量={len(input_images)}")
            print(f"请求载荷: {self._safe_json_dumps(payload)}")
            
            # 详细记录请求头信息，用于调试401认证错误
            print(f"=== 请求头详细信息 ===")
            print(f"Authorization: Bearer {api_key[:10]}...{api_key[-10:] if len(api_key) > 20 else '***'}")
            print(f"Content-Type: {headers.get('Content-Type', '未设置')}")
            print(f"API Key长度: {len(api_key)} 字符")
            print(f"API Key是否为空: {not api_key}")
            print(f"API Key是否包含空格: {'是' if ' ' in api_key else '否'}")
            print(f"API Key是否以'AIza'开头: {'是' if api_key.startswith('AIza') else '否'}")
            print(f"=== 请求头详细信息结束 ===")
            
            resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
            
            print(f"响应状态码: {resp.status_code}")
            print(f"响应头: {dict(resp.headers)}")
            
            return self._parse_image_response(resp)
                
        except Exception as e:
            empty_image = self._create_empty_image()
            if empty_image is None:
                import torch
                empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
            return (empty_image, f"图生图失败: {e}")

    def _parse_image_response(self, resp):
        """
        解析Gemini图像API响应
        """
        try:
            # 检查HTTP状态码
            if resp.status_code != 200:
                error_text = resp.text
                print(f"API返回错误状态码: {resp.status_code}")
                print(f"错误响应内容: {error_text}")
                print(f"响应头: {dict(resp.headers)}")
                
                # 针对401认证错误提供详细的诊断信息
                if resp.status_code == 401:
                    print(f"=== 401认证错误诊断信息 ===")
                    print(f"错误类型: UNAUTHENTICATED (未认证)")
                    print(f"可能的原因:")
                    print(f"1. API Key无效或已过期")
                    print(f"2. API Key格式不正确")
                    print(f"3. API Key权限不足")
                    print(f"4. 请求的模型需要特殊权限")
                    print(f"5. 账户余额不足或配额用完")
                    print(f"建议解决方案:")
                    print(f"1. 检查config.json中的api_key配置")
                    print(f"2. 确认API Key是否以'AIza'开头")
                    print(f"3. 在Google AI Studio重新生成API Key")
                    print(f"4. 检查API Key的权限设置")
                    print(f"5. 确认账户状态和配额")
                    print(f"=== 401认证错误诊断信息结束 ===")
                
                empty_image = self._create_empty_image()
                if empty_image is None:
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
                error_code = error_info.get("code", "未知代码")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, f"API错误 ({error_code}): {error_message}")
            
            # 解析Gemini响应数据
            if "candidates" in data and data["candidates"]:
                candidate = data["candidates"][0]
                content = candidate.get("content", {})
                parts = content.get("parts", [])
                
                print(f"找到响应内容，parts数量: {len(parts)}")
                
                # 查找图像部分
                for part in parts:
                    if "inlineData" in part:
                        inline_data = part["inlineData"]
                        mime_type = inline_data.get("mimeType", "")
                        data_content = inline_data.get("data", "")
                        
                        if mime_type.startswith("image/"):
                            print(f"找到图像数据: mime_type={mime_type}, 数据长度={len(data_content)}")
                            # 解码base64图像数据
                            image_bytes = base64.b64decode(data_content)
                            pil_image = Image.open(BytesIO(image_bytes))
                            print(f"图像加载成功: 尺寸={pil_image.size}, 模式={pil_image.mode}")
                            
                            # 转换为ComfyUI格式
                            print(f"开始转换为ComfyUI格式...")
                            comfyui_image = self._pil_to_comfyui(pil_image)
                            if comfyui_image is None:
                                print(f"ComfyUI格式转换失败，使用空图像")
                                import torch
                                comfyui_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                            else:
                                print(f"ComfyUI格式转换成功: 形状={comfyui_image.shape}, 类型={comfyui_image.dtype}")
                            
                            # 解析usage信息
                            usage = data.get("usageMetadata", {})
                            tokens_usage = self._format_tokens_usage(usage)
                            print(f"Token使用情况: {tokens_usage}")
                            
                            return (comfyui_image, tokens_usage)
                
                # 如果没有找到图像，检查是否有文本响应
                text_parts = [part.get("text", "") for part in parts if "text" in part]
                if text_parts:
                    text_response = " ".join(text_parts)
                    print(f"API返回文本响应: {text_response[:200]}...")
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, f"API返回文本而非图像: {text_response[:100]}...")
                else:
                    print(f"未找到图像或文本内容")
                    empty_image = self._create_empty_image()
                    if empty_image is None:
                        import torch
                        empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                    return (empty_image, "API响应中未找到图像数据")
            else:
                print(f"未找到candidates字段，可用字段: {list(data.keys())}")
                empty_image = self._create_empty_image()
                if empty_image is None:
                    import torch
                    empty_image = torch.zeros(1, 512, 512, 3, dtype=torch.float32)
                return (empty_image, "API响应格式不支持")
                
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
        
        total_tokens = usage.get('totalTokenCount', '-')
        input_tokens = usage.get('inputTokenCount', '-')
        output_tokens = usage.get('outputTokenCount', '-')
        
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
        # 验证API Key格式
        if not api_key:
            print("警告: API Key为空")
        elif not api_key.startswith('AIza'):
            print(f"警告: API Key格式可能不正确，应以'AIza'开头，当前开头: {api_key[:4]}")
        elif len(api_key) < 30:
            print(f"警告: API Key长度可能过短，当前长度: {len(api_key)}")
        
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

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
                return f"{value[:50]}... (总长度: {len(value)})"
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
    "Gemini_Image_API": GeminiImageAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Gemini_Image_API": "Gemini图像API节点"
} 
