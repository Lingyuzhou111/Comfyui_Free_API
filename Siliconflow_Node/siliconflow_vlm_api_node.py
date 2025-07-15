import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO
import time
import jwt
import re

# 节点主类
class SiliconflowVLMAPI:
    """
    ComfyUI自定义节点：Siliconflow VLM API
    实现图片视觉推理API调用，专门针对Siliconflow API，参数自动读取config.json。
    输入参数：image, model, max_tokens, temperature, top_p, system_prompt, user_prompt
    输出：answer（最终答案）, reasoning_content（思考过程）, tokens_usage（API用量信息）
    """
    def __init__(self):
        # 读取配置文件，专门读取VLM.siliconflow_vlm配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('VLM', {}).get('siliconflow_vlm', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取Siliconflow模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            siliconflow_config = config.get('VLM', {}).get('siliconflow_vlm', {})
        model_options = siliconflow_config.get('model', ['THUDM/GLM-4.1V-9B-Thinking'])
        return {
            "required": {
                "image": ("IMAGE",),
                "model": (model_options, {"default": model_options[0]}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 4096, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "system_prompt": ("STRING", {"multiline": True, "default": "你是一个能分析图像的AI助手。请仔细观察图像，并根据用户的问题提供详细、准确的描述。"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "请描述这张图片。"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reasoning_content", "answer", "tokens_usage")
    FUNCTION = "infer"
    CATEGORY = "API/Siliconflow"

    def infer(self, image, model, max_tokens, temperature, top_p, system_prompt, user_prompt):
        """
        主推理方法：
        1. 将image转为base64
        2. 构造Siliconflow API请求
        3. 发送请求，返回文本
        4. 解析reasoning_content和answer
        """
        # 读取Siliconflow API参数
        base_url = self.config.get('base_url', 'https://api.siliconflow.cn/v1')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            return ("", "", "错误：未配置Siliconflow API Key，请在config.json中设置siliconflow_vlm.api_key")
        
        # 1. 图片转base64
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
            else:
                # 如果不是tensor，直接使用
                img = image
            
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG")
            image_data_bytes_jpeg = output_buffer.getvalue()
            image_base64 = base64.b64encode(image_data_bytes_jpeg).decode('utf-8')
        except Exception as e:
            return ("", f"图片处理失败: {e}", "")
        
        # 2. 构造Siliconflow API请求
        messages = [
            {
                "role": "system",
                "content": system_prompt or "你是一个能分析图像的AI助手。请仔细观察图像，并根据用户的问题提供详细、准确的描述。"
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": user_prompt}
                ]
            }
        ]
        
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
            resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            
            return self._parse_response(resp)
                
        except requests.exceptions.RequestException as e:
            return ("", f"API请求失败: {e}", "")
        except Exception as e:
            return ("", f"处理失败: {e}", "")

    def _parse_response(self, resp):
        """
        解析Siliconflow响应，尝试提取思考过程和答案
        参考LLM_Party插件的解析逻辑
        """
        try:
            data = resp.json()
            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)
            if "choices" in data and data["choices"]:
                message = data["choices"][0]["message"]
                content = message.get("content", "")
                reasoning_content = message.get("reasoning_content", None)
                if reasoning_content is None:
                    reasoning_content, answer = self._parse_content_tags(content)
                else:
                    answer = content
                return (reasoning_content or "", answer, tokens_usage)
            else:
                return ("", "", tokens_usage)
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _parse_content_tags(self, content):
        """
        解析Siliconflow响应，尝试提取思考过程和答案
        参考LLM_Party插件的解析逻辑
        """
        try:
            # 使用正则表达式提取<think>标签内容
            pattern = r'<think>(.*?)</think>'
            match = re.search(pattern, content, re.DOTALL)
            
            if match:
                # 找到<think>标签，提取思考过程
                reasoning_content = match.group(1).strip()
                # 移除<think>标签，剩余内容作为答案
                answer = content.replace(match.group(0), "").strip()
            else:
                # 没有<think>标签，尝试其他格式
                # 尝试提取<answer>标签
                answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                if answer_match:
                    answer = answer_match.group(1).strip()
                    reasoning_content = ""
                else:
                    # 尝试提取<answer>后面的内容
                    answer_match = re.search(r'<answer>(.*)', content, re.DOTALL)
                    if answer_match:
                        answer = answer_match.group(1).strip()
                        reasoning_content = ""
                    else:
                        # 没有特殊标签，整个内容作为答案
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
        return f"total_tokens={usage.get('total_tokens', '-')}, input_tokens={usage.get('prompt_tokens', '-')}, output_tokens={usage.get('completion_tokens', '-')}"

    def _build_headers(self, api_key):
        # Siliconflow使用Bearer token认证
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Siliconflow_VLM_API": SiliconflowVLMAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Siliconflow_VLM_API": "Siliconflow VLM API节点"
} 