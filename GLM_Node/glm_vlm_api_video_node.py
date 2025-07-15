import os
import json
import requests
import time
import jwt
import re

class GLMVLMAPIVideo:
    """
    ComfyUI自定义节点：GLM VLM API视频URL节点
    只支持视频URL推理，video_url为必填参数。
    输入参数：video_url, model, max_tokens, temperature, top_p, system_prompt, user_prompt
    输出：reasoning_content（思考过程）, answer（最终答案）, tokens_usage（API用量信息）
    """
    def __init__(self):
        # 读取配置文件，专门读取VLM.glm_vlm配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('VLM', {}).get('glm_vlm', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取GLM模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            glm_config = config.get('VLM', {}).get('glm_vlm', {})
        model_options = glm_config.get('model', ['glm-4.1v-thinking-flashx'])
        return {
            "required": {
                "video_url": ("STRING", {"tooltip": "视频URL地址，必填，支持http(s)链接"}),
                "model": (model_options, {"default": model_options[0]}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 8192, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "system_prompt": ("STRING", {"multiline": True, "default": "你是一个视觉推理专家。"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "请仔细描述这个视频。"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reasoning_content", "answer", "tokens_usage")
    FUNCTION = "infer"
    CATEGORY = "API/GLM"

    def infer(self, video_url, model, max_tokens, temperature, top_p, system_prompt, user_prompt):
        base_url = self.config.get('base_url', 'https://open.bigmodel.cn/api/paas/v4')
        api_key = self.config.get('api_key', '')
        if not api_key:
            return ("", "错误：未配置GLM API Key，请在config.json中设置glm_vlm.api_key", "")
        if not self._is_valid_url(video_url):
            return ("", "错误：请输入有效的视频URL（http/https开头）", "")
        messages = [
            {"role": "system", "content": system_prompt or "你是一个视觉推理专家。"},
            {"role": "user", "content": [
                {"type": "video_url", "video_url": {"url": video_url.strip()}},
                {"type": "text", "text": user_prompt}
            ]}
        ]
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p
        }
        try:
            headers = self._build_headers(api_key)
            resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            return self._parse_response(resp)
        except requests.exceptions.RequestException as e:
            return ("", f"API请求失败: {e}", "")
        except Exception as e:
            return ("", f"处理失败: {e}", "")

    def _is_valid_url(self, url):
        try:
            return url and url.strip().startswith(('http://', 'https://'))
        except:
            return False

    def _parse_response(self, resp):
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
                return ("", f"API返回异常: {str(data)}", tokens_usage)
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _format_tokens_usage(self, usage):
        if not usage:
            return ""
        return f"total_tokens={usage.get('total_tokens', '-')}, input_tokens={usage.get('prompt_tokens', '-')}, output_tokens={usage.get('completion_tokens', '-')}"

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

NODE_CLASS_MAPPINGS = {
    "GLM_VLM_API_VIDEO": GLMVLMAPIVideo
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "GLM_VLM_API_VIDEO": "GLM VLM API视频推理节点"
} 