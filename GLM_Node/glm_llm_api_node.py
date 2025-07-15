import os
import json
import requests
import time
import jwt
import re

# 节点主类
class GLMLLMAPI:
    """
    ComfyUI自定义节点：GLM LLM API
    支持文本对话，调用GLM大语言模型进行推理。
    输入参数：model, max_tokens, temperature, top_p, system_prompt, user_prompt
    输出：reasoning_content（思考过程）, answer（最终答案）, tokens_usage（API用量信息）
    """
    def __init__(self):
        # 读取配置文件，专门读取LLM.glm_llm配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('LLM', {}).get('glm_llm', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取GLM模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            glm_config = config.get('LLM', {}).get('glm_llm', {})
        model_options = glm_config.get('model', ['glm-4-flash-250414'])
        return {
            "required": {
                "model": (model_options, {"default": model_options[0]}),
                "max_tokens": ("INT", {"default": 2048, "min": 1, "max": 8192, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "system_prompt": ("STRING", {"multiline": True, "default": "你是一个智能的AI助手，能够帮助用户解决各种问题。"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "你好，请介绍一下你自己。"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reasoning_content", "answer", "tokens_usage")
    FUNCTION = "infer"
    CATEGORY = "API/GLM"

    def infer(self, model, max_tokens, temperature, top_p, system_prompt, user_prompt):
        """
        主推理方法：
        调用GLM LLM API进行文本对话推理。
        """
        # 读取GLM API参数
        base_url = self.config.get('base_url', 'https://open.bigmodel.cn/api/paas/v4')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            return ("", "错误：未配置GLM API Key，请在config.json中设置glm_llm.api_key", "")
        
        # 构造API请求
        messages = []
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        messages.append({
            "role": "user",
            "content": user_prompt
        })
        
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
        1. 直接返回reasoning_content字段（如glm-4.1-thinking-flash）
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
        """
        解析content中的<think>标签，提取推理内容和答案
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

    def _format_tokens_usage(self, usage):
        """
        格式化token使用统计信息
        """
        if not usage:
            return ""
        return f"total_tokens={usage.get('total_tokens', '-')}, input_tokens={usage.get('prompt_tokens', '-')}, output_tokens={usage.get('completion_tokens', '-')}"

    def _build_headers(self, api_key):
        """
        构建GLM API请求头，包含JWT认证
        """
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
    "GLM_LLM_API": GLMLLMAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "GLM_LLM_API": "GLM LLM API节点"
} 