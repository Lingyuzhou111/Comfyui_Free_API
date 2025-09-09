import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO
import time
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenVLMAPI")

# 节点主类
class QwenVLMAPI:
    """
    ComfyUI自定义节点：Qwen VLM API
    实现图片视觉推理API调用，专门针对Qwen API，参数自动读取config.json。
    输入参数：image, model, max_tokens, temperature, top_p, system_prompt, user_prompt
    输出：reasoning_content（思考过程）, answer（最终答案）, tokens_usage（API用量信息）
    """
    def __init__(self):
        # 读取配置文件，容错匹配 VLM 下的提供方（支持重命名为“千问百炼”等）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg_all = json.load(f)
        vlm = cfg_all.get('VLM', {}) or {}
        provider_key = None
        if "千问百炼" in vlm and isinstance(vlm["千问百炼"], dict):
            provider_key = "千问百炼"
        else:
            for k, v in vlm.items():
                if isinstance(v, dict) and isinstance(v.get('model'), list):
                    provider_key = k
                    break
        self.config = vlm.get(provider_key, {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取模型选项（容错匹配提供方）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg_all = json.load(f)
        vlm = cfg_all.get('VLM', {}) or {}
        selected = {}
        if "千问百炼" in vlm and isinstance(vlm["千问百炼"], dict):
            selected = vlm["千问百炼"]
        else:
            for k, v in vlm.items():
                if isinstance(v, dict) and isinstance(v.get('model'), list):
                    selected = v
                    break
        model_options = selected.get('model', ['qwen-omni-turbo-latest'])
        return {
            "required": {
                "image": ("IMAGE",),
                "model": (model_options, {"default": model_options[0]}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 8192, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "system_prompt": ("STRING", {"multiline": True, "default": "你是一个能分析图像的AI助手。请仔细观察图像，并根据用户的问题提供详细、准确的描述。"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "请描述这张图片。"}),
                "stream": ("BOOLEAN", {"default": False, "tooltip": "是否启用流式输出"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reasoning_content", "answer", "tokens_usage")
    FUNCTION = "infer"
    CATEGORY = "🦉FreeAPI/Qwen"

    def infer(self, image, model, max_tokens, temperature, top_p, system_prompt, user_prompt, stream=False):
        """
        主推理方法：
        1. 将image转为base64
        2. 构造Qwen API请求
        3. 发送请求，返回文本
        """
        # 读取Qwen API参数
        base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            return ("", "错误：未配置Qwen API Key，请在config.json的 VLM 部分对应提供方下设置 api_key（例如“千问百炼”.api_key）", "")
        
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
            logger.info(f"图片处理失败: {e}")
            return ("", f"图片处理失败: {e}", "")
        
        # 2. 构造Qwen API请求
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
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            if stream:
                payload["stream"] = True
                resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=180, stream=True)
                return self._parse_stream_response(resp)
            else:
                resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=180)
                return self._parse_response(resp)
        except requests.exceptions.RequestException as e:
            logger.info(f"API请求失败: {e}")
            return ("", f"API请求失败: {e}", "")
        except Exception as e:
            logger.info(f"处理失败: {e}")
            return ("", f"处理失败: {e}", "")

    def _parse_response(self, resp):
        try:
            data = resp.json()
            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)
            if "choices" in data and data["choices"]:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                reasoning_content = message.get("reasoning_content", None)
                if reasoning_content is None:
                    reasoning_content, answer = self._parse_content_tags(content)
                else:
                    answer = content
                if not answer and not reasoning_content:
                    answer = str(message)
                return (reasoning_content or "", answer, tokens_usage)
            else:
                return ("", f"API返回异常: {str(data)}", tokens_usage)
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _parse_stream_response(self, resp):
        reasoning_content = ""
        answer_content = ""
        tokens_usage = ""
        try:
            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8").strip()
                if not line_str or line_str == "" or line_str == "data: [DONE]":
                    continue
                if line_str.startswith("data: "):
                    line_str = line_str[6:]
                    if line_str.strip() == "[DONE]":
                        continue
                try:
                    data = json.loads(line_str)
                except Exception:
                    continue
                if "usage" in data and data["usage"]:
                    tokens_usage = self._format_tokens_usage(data["usage"])
                if "choices" in data and data["choices"]:
                    delta = data["choices"][0].get("delta", {})
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        reasoning_content += delta["reasoning_content"]
                    if "content" in delta and delta["content"]:
                        answer_content += delta["content"]
            return (reasoning_content, answer_content, tokens_usage)
        except Exception as e:
            return ("", f"流式响应解析失败: {e}", "")

    def _format_tokens_usage(self, usage):
        if not usage:
            return ""
        return f"total_tokens={usage.get('total_tokens', '-')}, input_tokens={usage.get('prompt_tokens', '-')}, output_tokens={usage.get('completion_tokens', '-')}"

    def _parse_content_tags(self, content):
        """
        解析content中的标签（兼容<think>和<answer>标签，保证健壮性）
        """
        try:
            pattern = r'<think>(.*?)</think>'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                reasoning_content = match.group(1).strip()
                answer = content.replace(match.group(0), "").strip()
            else:
                answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                if answer_match:
                    answer = answer_match.group(1).strip()
                    reasoning_content = ""
                else:
                    answer_match = re.search(r'<answer>(.*)', content, re.DOTALL)
                    if answer_match:
                        answer = answer_match.group(1).strip()
                        reasoning_content = ""
                    else:
                        answer = content.strip()
                        reasoning_content = ""
            return (reasoning_content, answer)
        except Exception as e:
            return ("", content.strip())

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Qwen_VLM_API": QwenVLMAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_VLM_API": "🦉Qwen VLM API节点"
} 