import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO
import re

# 节点主类
class OpenAIChatAPI:
    """
    ComfyUI自定义节点：OpenAI兼容API
    实现文本对话和图像分析的通用API调用，支持任意兼容OpenAI格式的API接口。
    输入参数：base_url, model, api_key, system_prompt, user_prompt, image(可选), max_tokens, temperature, top_p
    输出：reasoning_content（思考过程）, answer（最终答案）, tokens_usage（API用量信息）
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://api.openai.com/v1", "multiline": False}),
                "model": ("STRING", {"default": "gpt-4o", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "system_prompt": ("STRING", {"multiline": True, "default": "你是一个有帮助的AI助手。"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "你好！"}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 4096, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reasoning_content", "answer", "tokens_usage")
    FUNCTION = "chat"
    CATEGORY = "API/OpenAI"

    def chat(self, base_url, model, api_key, system_prompt, user_prompt, max_tokens, temperature, top_p, image=None):
        """
        主聊天方法：
        1. 根据是否有image决定是文本对话还是图像分析
        2. 构造OpenAI兼容的API请求
        3. 发送请求，返回文本
        4. 解析reasoning_content和answer
        """
        if not api_key:
            return ("", "", "错误：未配置API Key，请在节点参数中设置api_key")
        
        if not base_url:
            return ("", "", "错误：未配置base_url，请在节点参数中设置base_url")
        
        # 1. 构造消息列表
        messages = []
        
        # 添加系统提示词
        if system_prompt:
            messages.append({
                "role": "assistant",
                "content": system_prompt
            })
        
        # 处理用户消息
        if image is not None:
            # 图像分析模式
            try:
                # 将image转为base64
                image_base64 = self._image_to_base64(image)
                print(f"[OpenAIChatAPI] 图像转换为base64成功，长度: {len(image_base64)}, 预览: {self._truncate_base64_log(image_base64)}")
                
                # 构造包含图像的消息
                user_content = [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
                
                messages.append({
                    "role": "user",
                    "content": user_content
                })
                
            except Exception as e:
                return ("", f"图像处理失败: {e}", "")
        else:
            # 纯文本对话模式
            messages.append({
                "role": "user",
                "content": user_prompt
            })
        
        # 2. 构造请求载荷
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p
        }
        
        # 3. 发送请求
        try:
            headers = self._build_headers(api_key)
            # 确保URL格式正确，避免双斜杠
            api_url = f"{base_url.rstrip('/')}/chat/completions"
            print(f"[OpenAIChatAPI] 正在请求OpenAI兼容API: {api_url}")
            print(f"[OpenAIChatAPI] 请求参数: model={model}, max_tokens={max_tokens}")
            #print(f"[OpenAIChatAPI] 请求头: {headers}")
            #print(f"[OpenAIChatAPI] 请求载荷: {self._safe_json_dumps(payload)}")
            
            resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
            
            # 不立即抛出异常，让_parse_response处理所有响应
            print(f"[OpenAIChatAPI] 响应状态码: {resp.status_code}")
            #print(f"[OpenAIChatAPI] 响应头: {dict(resp.headers)}")
            
            return self._parse_response(resp)
                
        except requests.exceptions.ConnectTimeout as e:
            return ("", f"网络连接超时: 无法连接到API服务器。请检查网络连接或使用代理。错误: {e}", "")
        except requests.exceptions.Timeout as e:
            return ("", f"请求超时: API响应时间过长。请稍后重试或减少max_tokens。错误: {e}", "")
        except requests.exceptions.ConnectionError as e:
            return ("", f"网络连接错误: 无法建立到API的连接。请检查网络设置。错误: {e}", "")
        except requests.exceptions.RequestException as e:
            return ("", f"API请求失败: {e}", "")
        except Exception as e:
            return ("", f"处理失败: {e}", "")

    def _image_to_base64(self, image):
        """
        将ComfyUI的IMAGE转换为base64编码
        """
        try:
            # ComfyUI的IMAGE是torch.Tensor，需要转换为PIL Image
            if hasattr(image, 'cpu'):  # 是torch.Tensor
                # 转换为numpy数组，然后转为PIL Image
                import torch
                if image.dim() == 4:  # batch维度，取第一张
                    image = image[0]
                # 转换为numpy并调整通道顺序 (C,H,W) -> (H,W,C)
                image_np = image.cpu().numpy()
                if image_np.shape[0] == 3:  # 如果是(C,H,W)格式
                    image_np = image_np.transpose(1, 2, 0)
                # 确保值在0-255范围内
                image_np = (image_np * 255).clip(0, 255).astype('uint8')
                img = Image.fromarray(image_np)
            elif hasattr(image, 'save'):  # 已经是PIL Image
                img = image
            else:
                # 如果是numpy数组，直接转换
                import numpy as np
                if isinstance(image, np.ndarray):
                    if image.shape[0] == 3:  # 如果是(C,H,W)格式
                        image = image.transpose(1, 2, 0)
                    # 确保值在0-255范围内
                    if image.max() <= 1.0:  # 如果是0-1范围
                        image = (image * 255).clip(0, 255).astype('uint8')
                    img = Image.fromarray(image)
                else:
                    raise Exception(f"不支持的图像格式: {type(image)}")
            
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG")
            image_data_bytes_jpeg = output_buffer.getvalue()
            image_base64 = base64.b64encode(image_data_bytes_jpeg).decode('utf-8')
            return image_base64
            
        except Exception as e:
            raise Exception(f"图像转换失败: {e}")

    def _parse_response(self, resp):
        """
        解析OpenAI兼容API响应，尝试提取思考过程和答案
        """
        try:
            # 首先检查HTTP状态码
            if resp.status_code != 200:
                error_text = resp.text
                print(f"[OpenAIChatAPI] API返回错误状态码: {resp.status_code}")
                print(f"[OpenAIChatAPI] 错误响应内容: {error_text}")
                return ("", f"API错误 (状态码: {resp.status_code}): {error_text}", "")
            
            # 检查响应内容是否为空
            if not resp.text.strip():
                return ("", "API返回空响应", "")
            
            # 尝试解析JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as json_error:
                print(f"[OpenAIChatAPI] JSON解析失败: {json_error}")
                print(f"[OpenAIChatAPI] 响应内容: {resp.text[:500]}...")  # 只打印前500个字符
                return ("", f"API响应格式错误: {resp.text[:200]}", "")
            
            print("API原始响应:", data)  # 调试输出
            
            # 检查是否有错误信息
            if "error" in data:
                error_info = data["error"]
                error_message = error_info.get("message", "未知错误")
                error_type = error_info.get("type", "未知类型")
                return ("", f"API错误 ({error_type}): {error_message}", "")
            
            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)
            
            if "choices" in data and data["choices"]:
                message = data["choices"][0]["message"]
                content = message.get("content", "")
                finish_reason = data["choices"][0].get("finish_reason", "")
                
                if not content:
                    # 如果内容为空，输出友好提示
                    return ("", f"未返回内容，finish_reason={finish_reason}", tokens_usage)
                
                # 尝试解析思考过程和答案
                reasoning_content, answer = self._parse_content_tags(content)
                
                return (reasoning_content or "", answer, tokens_usage)
            else:
                return ("", "API未返回choices内容", tokens_usage)
                
        except Exception as e:
            print(f"[OpenAIChatAPI] 响应解析异常: {e}")
            print(f"[OpenAIChatAPI] 响应状态码: {resp.status_code}")
            print(f"[OpenAIChatAPI] 响应头: {dict(resp.headers)}")
            print(f"[OpenAIChatAPI] 响应内容: {resp.text[:500]}...")
            return ("", f"响应解析失败: {e}", "")

    def _parse_content_tags(self, content):
        """
        解析API响应，尝试提取思考过程和答案
        支持多种格式的标签解析
        """
        try:
            # 1. 尝试提取<think>标签内容
            think_pattern = r'<think>(.*?)</think>'
            think_match = re.search(think_pattern, content, re.DOTALL)
            
            if think_match:
                # 找到<think>标签，提取思考过程
                reasoning_content = think_match.group(1).strip()
                # 移除<think>标签，剩余内容作为答案
                answer = content.replace(think_match.group(0), "").strip()
                return (reasoning_content, answer)
            
            # 2. 尝试提取<answer>标签
            answer_pattern = r'<answer>(.*?)</answer>'
            answer_match = re.search(answer_pattern, content, re.DOTALL)
            
            if answer_match:
                answer = answer_match.group(1).strip()
                reasoning_content = ""
                return (reasoning_content, answer)
            
            # 3. 尝试提取<answer>后面的内容（不闭合标签）
            answer_pattern_open = r'<answer>(.*)'
            answer_match_open = re.search(answer_pattern_open, content, re.DOTALL)
            
            if answer_match_open:
                answer = answer_match_open.group(1).strip()
                reasoning_content = ""
                return (reasoning_content, answer)
            
            # 4. 尝试提取<reasoning>标签
            reasoning_pattern = r'<reasoning>(.*?)</reasoning>'
            reasoning_match = re.search(reasoning_pattern, content, re.DOTALL)
            
            if reasoning_match:
                reasoning_content = reasoning_match.group(1).strip()
                # 移除<reasoning>标签，剩余内容作为答案
                answer = content.replace(reasoning_match.group(0), "").strip()
                return (reasoning_content, answer)
            
            # 5. 没有特殊标签，整个内容作为答案
            answer = content.strip()
            reasoning_content = ""
            return (reasoning_content, answer)
            
        except Exception as e:
            # 解析失败，返回原始内容作为答案
            return ("", content.strip())

    def _format_tokens_usage(self, usage):
        """
        将tokens_usage格式化为易读的字符串
        """
        if not usage:
            return ""
        
        total_tokens = usage.get('total_tokens', '-')
        prompt_tokens = usage.get('prompt_tokens', '-')
        completion_tokens = usage.get('completion_tokens', '-')
        
        return f"total_tokens={total_tokens}, input_tokens={prompt_tokens}, output_tokens={completion_tokens}"

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
    "OpenAI_Chat_API": OpenAIChatAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenAI_Chat_API": "OpenAI兼容Chat API节点"
} 
