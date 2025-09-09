import os
import json
import requests
import time
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenLLMAPI")

# 节点主类
class QwenLLMAPI:
    """
    ComfyUI自定义节点：Qwen LLM API
    实现文本对话API调用，专门针对Qwen API，参数自动读取config.json。
    输入参数：model, max_tokens, temperature, top_p, system_prompt, user_prompt, enable_thinking, thinking_budget, stream
    输出：reasoning_content（思考过程）, answer（最终答案）, tokens_usage（API用量信息）
    """
    def __init__(self):
        # 读取配置文件，容错匹配 LLM 下的提供方（支持重命名为“千问百炼”等）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg_all = json.load(f)
        llm = cfg_all.get('LLM', {}) or {}
        # 优先匹配“千问百炼”，否则回退到第一个含有 model 列表的提供方
        provider_key = None
        if "千问百炼" in llm and isinstance(llm["千问百炼"], dict):
            provider_key = "千问百炼"
        else:
            # 遍历找到第一个含有 model 列表的项
            for k, v in llm.items():
                if isinstance(v, dict) and isinstance(v.get('model'), list):
                    provider_key = k
                    break
        self.config = llm.get(provider_key, {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取模型选项（容错匹配提供方）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg_all = json.load(f)
        llm = cfg_all.get('LLM', {}) or {}
        selected = {}
        if "千问百炼" in llm and isinstance(llm["千问百炼"], dict):
            selected = llm["千问百炼"]
        else:
            for k, v in llm.items():
                if isinstance(v, dict) and isinstance(v.get('model'), list):
                    selected = v
                    break
        model_options = selected.get('model', ['qwen-turbo-2025-04-28'])
        return {
            "required": {
                "model": (model_options, {"default": model_options[0]}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 8192, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "system_prompt": ("STRING", {"multiline": True, "default": "你是一个有用的AI助手。"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "你好，请介绍一下你自己。"}),
                "enable_thinking": ("BOOLEAN", {"default": False, "tooltip": "是否启用思考过程"}),
                "thinking_budget": ("INT", {"default": 50, "min": 1, "max": 1000, "step": 1, "tooltip": "思考过程的最大Token数"}),
                "stream": ("BOOLEAN", {"default": False, "tooltip": "是否启用流式输出"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reasoning_content", "answer", "tokens_usage")
    FUNCTION = "infer"
    CATEGORY = "🦉FreeAPI/Qwen"

    def infer(self, model, max_tokens, temperature, top_p, system_prompt, user_prompt, enable_thinking=False, thinking_budget=50, stream=False):
        """
        主推理方法：
        1. 构造Qwen API请求
        2. 发送请求，返回文本
        3. 解析响应，提取思考过程和答案
        """
        # 读取Qwen API参数
        base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            return ("", "错误：未配置Qwen API Key，请在config.json的 LLM 部分对应提供方下设置 api_key（例如“千问百炼”.api_key）", "")
        
        # 1. 构造消息列表
        messages = []
        if system_prompt and system_prompt.strip():
            messages.append({
                "role": "system",
                "content": system_prompt.strip()
            })
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
        
        # 3. 添加思考过程相关参数
        if enable_thinking:
            payload["extra_body"] = {
                "enable_thinking": True,
                "thinking_budget": thinking_budget
            }
        
        # 4. 发送请求
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
        """
        解析非流式响应
        """
        try:
            data = resp.json()
            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)
            
            if "choices" in data and data["choices"]:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                
                # 检查是否有独立的reasoning_content字段
                reasoning_content = message.get("reasoning_content", None)
                
                if reasoning_content is not None:
                    # 如果有独立的reasoning_content字段，直接使用
                    answer = content
                else:
                    # 否则尝试从content中解析思考过程
                    reasoning_content, answer = self._parse_content_tags(content)
                
                if not answer and not reasoning_content:
                    answer = str(message)
                
                return (reasoning_content or "", answer, tokens_usage)
            else:
                return ("", f"API返回异常: {str(data)}", tokens_usage)
                
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _parse_stream_response(self, resp):
        """
        解析流式响应
        """
        reasoning_content = ""
        answer_content = ""
        tokens_usage = ""
        is_answering = False
        
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
                
                # 处理usage信息
                if "usage" in data and data["usage"]:
                    tokens_usage = self._format_tokens_usage(data["usage"])
                
                # 处理choices信息
                if "choices" in data and data["choices"]:
                    delta = data["choices"][0].get("delta", {})
                    
                    # 处理思考过程
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        reasoning_content += delta["reasoning_content"]
                    
                    # 处理回复内容
                    if "content" in delta and delta["content"]:
                        answer_content += delta["content"]
            
            return (reasoning_content, answer_content, tokens_usage)
            
        except Exception as e:
            return ("", f"流式响应解析失败: {e}", "")

    def _format_tokens_usage(self, usage):
        """
        格式化Token使用信息
        """
        if not usage:
            return ""
        return f"total_tokens={usage.get('total_tokens', '-')}, input_tokens={usage.get('prompt_tokens', '-')}, output_tokens={usage.get('completion_tokens', '-')}"

    def _parse_content_tags(self, content):
        """
        解析content中的标签（兼容<think>和<answer>标签，保证健壮性）
        """
        try:
            # 尝试匹配<think>标签
            pattern = r'<think>(.*?)</think>'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                reasoning_content = match.group(1).strip()
                answer = content.replace(match.group(0), "").strip()
            else:
                # 尝试匹配<answer>标签
                answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                if answer_match:
                    answer = answer_match.group(1).strip()
                    reasoning_content = ""
                else:
                    # 尝试匹配不完整的<answer>标签
                    answer_match = re.search(r'<answer>(.*)', content, re.DOTALL)
                    if answer_match:
                        answer = answer_match.group(1).strip()
                        reasoning_content = ""
                    else:
                        # 如果没有标签，整个内容作为答案
                        answer = content.strip()
                        reasoning_content = ""
            return (reasoning_content, answer)
        except Exception as e:
            return ("", content.strip())

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Qwen_LLM_API": QwenLLMAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_LLM_API": "🦉Qwen LLM API节点"
} 