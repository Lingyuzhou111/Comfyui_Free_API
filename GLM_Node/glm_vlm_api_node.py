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
class GLMVLMAPI:
    """
    ComfyUI自定义节点：GLM VLM API
    只支持本地图片推理，image为必填参数。
    输入参数：image, model, max_tokens, temperature, top_p, system_prompt, user_prompt
    输出：reasoning_content（思考过程）, answer（最终答案）, tokens_usage（API用量信息）
    """
    def __init__(self):
        # 读取配置文件，容错匹配 VLM 下的提供方（优先“智谱官方”，否则回退到第一个含 model 列表的提供方）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg_all = json.load(f)
        vlm = cfg_all.get('VLM', {}) or {}
        provider_key = None
        if "智谱官方" in vlm and isinstance(vlm["智谱官方"], dict):
            provider_key = "智谱官方"
        else:
            for k, v in vlm.items():
                if isinstance(v, dict) and isinstance(v.get('model'), list):
                    provider_key = k
                    break
        self.config = vlm.get(provider_key, {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取模型选项（容错匹配“智谱官方”，否则回退到第一个包含 model 列表的提供方）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg_all = json.load(f)
        vlm = cfg_all.get('VLM', {}) or {}
        selected = {}
        if "智谱官方" in vlm and isinstance(vlm["智谱官方"], dict):
            selected = vlm["智谱官方"]
        else:
            for k, v in vlm.items():
                if isinstance(v, dict) and isinstance(v.get('model'), list):
                    selected = v
                    break
        model_options = selected.get('model', ['glm-4v-flash'])
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "本地图片输入"}),
                "model": (model_options, {"default": model_options[0]}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 8192, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "system_prompt": ("STRING", {"multiline": True, "default": "你是一个能分析图像的AI助手。请仔细观察图像，并根据用户的问题提供详细、准确的描述。"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "请描述这张图片。"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reasoning_content", "answer", "tokens_usage")
    FUNCTION = "infer"
    CATEGORY = "🦉FreeAPI/GLM"

    def infer(self, image, model, max_tokens, temperature, top_p, system_prompt, user_prompt):
        """
        主推理方法：
        只支持本地图片输入。
        """
        # 读取GLM API参数
        base_url = self.config.get('base_url', 'https://open.bigmodel.cn/api/paas/v4')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            return ("", "错误：未配置GLM API Key，请在config.json的 VLM 部分对应提供方下设置 api_key（例如“智谱官方”.api_key）", "")
        
        # 图片转base64
        try:
            # ComfyUI的IMAGE是torch.Tensor，需要转换为PIL Image
            if hasattr(image, 'cpu'):  # 是torch.Tensor
                import torch
                if image.dim() == 4:  # batch维度，取第一张
                    image = image[0]
                image_np = image.cpu().numpy()
                if image_np.shape[0] == 3:
                    image_np = image_np.transpose(1, 2, 0)
                image_np = (image_np * 255).clip(0, 255).astype('uint8')
                img = Image.fromarray(image_np)
            else:
                img = image
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG")
            image_data_bytes_jpeg = output_buffer.getvalue()
            image_base64 = base64.b64encode(image_data_bytes_jpeg).decode('utf-8')
        except Exception as e:
            return ("", f"图片处理失败: {e}", "")
        
        # 构造API请求
        messages = [
            {
                "role": "system",
                "content": system_prompt or "你是一个视觉推理专家。"
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
        
        # 发送请求并解析响应
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
        解析GLM API响应，提取reasoning_content和answer
        支持两种格式：
        1. 直接返回reasoning_content字段（如glm-4.1v-thinking-flash）
        2. 在content中使用<think>标签（兼容其他模型）
        """
        try:
            data = resp.json()
            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)
            if "choices" in data and data["choices"]:
                message = data["choices"][0]["message"]
                content = message.get("content", "")
                # 优先用reasoning_content字段
                reasoning_content = message.get("reasoning_content", None)
                if reasoning_content is None:
                    reasoning_content, answer = self._parse_content_tags(content)
                else:
                    answer = content
                return (reasoning_content or "", answer, tokens_usage)
            else:
                return ("", f"API返回异常: {str(data)}", tokens_usage)
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _parse_content_tags(self, content):
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

    def _format_tokens_usage(self, usage):
        if not usage:
            return ""
        return f"total_tokens={usage.get('total_tokens', '-')}, input_tokens={usage.get('prompt_tokens', '-')}, output_tokens={usage.get('completion_tokens', '-')}"

    def _build_headers(self, api_key):
        try:
            api_key_id, api_key_secret = api_key.split('.')
            payload = {
                "api_key": api_key_id,
                "exp": int(round(time.time() * 1000)) + 3600 * 1000,
                "timestamp": int(round(time.time() * 1000)),
            }
            token = jwt.encode(payload, api_key_secret, algorithm="HS256", headers={"alg": "HS256", "sign_type": "SIGN"})
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        except Exception as e:
            return {"Authorization": "Bearer error", "Content-Type": "application/json"}

# 节点注册
NODE_CLASS_MAPPINGS = {
    "GLM_VLM_API": GLMVLMAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "GLM_VLM_API": "🦉GLM VLM API节点"
}
