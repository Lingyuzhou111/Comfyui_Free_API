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
                "api_endpoint": (["/chat/completions", "/responses"], {"default": "/chat/completions"}),
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
    CATEGORY = "🦉FreeAPI/OpenAI"

    def chat(self, base_url, api_endpoint, model, api_key, system_prompt, user_prompt, max_tokens, temperature, top_p, image=None):
        """
        主聊天方法：
        1. 根据是否有image决定是文本对话还是图像分析
        2. 按 api_endpoint 构造 OpenAI 兼容请求：
           - /chat/completions：沿用 messages 格式
           - /responses：使用 input 字段；纯文本为字符串，含图像为多模态数组
        3. 发送请求，返回文本
        4. 分支解析响应，提取 answer 与 usage；尽力提取 reasoning（若存在）
        """
        if not api_key:
            return ("", "", "错误：未配置API Key，请在节点参数中设置api_key")
        
        if not base_url:
            return ("", "", "错误：未配置base_url，请在节点参数中设置base_url")
        
        # 1/2. 构造请求载荷（根据 api_endpoint 分支）
        try:
            headers = self._build_headers(api_key)
            # 流式 SSE 兼容：部分网关要求此头
            headers["Accept"] = "text/event-stream"
            endpoint = api_endpoint.strip()
            base = base_url.rstrip('/')
            if endpoint not in ["/chat/completions", "/responses"]:
                endpoint = "/chat/completions"  # 兜底
            
            # Chat Completions 分支（沿用原实现）
            if endpoint == "/chat/completions":
                messages = []
                if system_prompt:
                    # 注意：标准为 role: system，这里修正此前的 role: assistant
                    messages.append({"role": "system", "content": system_prompt})
                if image is not None:
                    try:
                        image_base64 = self._image_to_base64(image)
                        print(f"[OpenAIChatAPI] 图像转换为base64成功，长度: {len(image_base64)}, 预览: {self._truncate_base64_log(image_base64)}")
                        user_content = [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                        ]
                        messages.append({"role": "user", "content": user_content})
                    except Exception as e:
                        return ("", f"图像处理失败: {e}", "")
                else:
                    messages.append({"role": "user", "content": user_prompt})
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p
                }
                api_url = f"{base}{endpoint}"
                print(f"[OpenAIChatAPI] 请求: {api_url} (chat/completions)")
                print(f"[OpenAIChatAPI] 请求参数: model={model}, max_tokens={max_tokens}")
                resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
                print(f"[OpenAIChatAPI] 响应状态码: {resp.status_code}")
                return self._parse_response(resp)
            
            # Responses 分支（新接口）
            else:
                # 构造 input（Responses 规范）：优先使用 instructions 字段承载 system_prompt
                input_payload = None
                instructions = None
                if image is None:
                    # 仅文本 -> 使用 responses 规范的 input_text 类型；不在 input 中混入 system
                    input_payload = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": user_prompt}
                            ]
                        }
                    ]
                else:
                    # 文本 + 图像
                    try:
                        image_base64 = self._image_to_base64(image)
                        print(f"[OpenAIChatAPI] 图像转换为base64成功，长度: {len(image_base64)}, 预览: {self._truncate_base64_log(image_base64)}")
                        content_items = [
                            {"type": "input_text", "text": user_prompt},
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_base64}"}
                        ]
                        # 使用 input 数组，仅包含 user；system 通过 instructions 字符串传递
                        input_payload = [
                            {
                                "role": "user",
                                "content": content_items
                            }
                        ]
                    except Exception as e:
                        return ("", f"图像处理失败: {e}", "")
                
                # 构造更通用、保守的 payload：不再传 text / tools / tool_choice
                payload = {
                    "model": model,
                    "input": input_payload,
                    "stream": True
                }
                # 满足某些实现对 instructions 的强制要求：使用结构化对象而非字符串
                # 当前网关要求 instructions 为字符串：其后端会调用 .startsWith
                try:
                    payload["instructions"] = (system_prompt or "")
                except Exception:
                    payload["instructions"] = ""
                # 可选的温控参数：仅当用户设置时再添加，避免部分网关校验失败
                try:
                    if temperature is not None:
                        payload["temperature"] = float(temperature)
                    if top_p is not None:
                        payload["top_p"] = float(top_p)
                except Exception:
                    pass
                
                api_url = f"{base}{endpoint}"
                print(f"[OpenAIChatAPI] 请求: {api_url} (responses)")
                print(f"[OpenAIChatAPI] 请求参数: model={model}")
                #print(f"[OpenAIChatAPI] 载荷: {self._safe_json_dumps(payload)}")
                resp = requests.post(api_url, headers=headers, json=payload, timeout=120, stream=True)
                print(f"[OpenAIChatAPI] 响应状态码: {resp.status_code}")
                # SSE 的 Content-Type 经常没有声明 charset；requests 对 text/*
                # 默认可能按 ISO-8859-1 解码，中文随后会变成“æ...”这类乱码。
                # 在 iter_lines(decode_unicode=True) 之前显式指定 UTF-8。
                resp.encoding = "utf-8"
                # 显式记录：响应头关键信息（避免打印所有敏感头）
                try:
                    hdrs = dict(resp.headers)
                    keys_to_log = ["Content-Type", "Content-Encoding", "Transfer-Encoding", "Cache-Control", "Connection"]
                    safe_hdrs = {k: hdrs.get(k) for k in keys_to_log if k in hdrs}
                    print(f"[OpenAIChatAPI] 响应头: {self._safe_json_dumps(safe_hdrs)}")
                except Exception as _:
                    pass
                if resp.status_code != 200:
                    safe_payload = dict(payload)
                    if isinstance(safe_payload.get("input"), str) and len(safe_payload["input"]) > 200:
                        safe_payload["input"] = safe_payload["input"][:200] + "...(truncated)"
                    print(f"[OpenAIChatAPI] Responses 调试载荷: {self._safe_json_dumps(safe_payload)}")
                    return ("", f"API错误 (状态码: {resp.status_code}): {resp.text}", "")
                # 解析SSE流（内部新增原始行采样日志）
                reasoning_content, answer, tokens_usage = self._parse_responses_stream(resp)
                # 若未解析到任何文本，自动降级为非流式请求一次，避免代理的 SSE 兼容性问题
                if not answer:
                    try:
                        safe_payload = dict(payload)
                        safe_payload["stream"] = False
                        resp2 = requests.post(api_url, headers=headers, json=safe_payload, timeout=120)
                        print(f"[OpenAIChatAPI] 降级为非流式请求，状态码: {resp2.status_code}")
                        if resp2.status_code == 200:
                            return self._parse_response(resp2, is_responses_api=True)
                        else:
                            return ("", f"非流式降级失败 (状态码: {resp2.status_code}): {resp2.text}", tokens_usage)
                    except Exception as _e:
                        print(f"[OpenAIChatAPI] 非流式降级异常: {_e}")
                return (reasoning_content or "", answer, tokens_usage)
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

    def _parse_response(self, resp, is_responses_api: bool = False):
        """
        解析OpenAI兼容API响应：
        - chat/completions：解析 choices[0].message.content
        - responses：解析 output[*].content[*] 中 type=output_text 的 text
        """
        try:
            # 某些兼容网关不在响应头声明 charset；统一按 UTF-8 读取文本。
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                error_text = resp.text
                print(f"[OpenAIChatAPI] API返回错误状态码: {resp.status_code}")
                print(f"[OpenAIChatAPI] 错误响应内容: {error_text}")
                return ("", f"API错误 (状态码: {resp.status_code}): {error_text}", "")
            
            if not resp.text.strip():
                return ("", "API返回空响应", "")
            
            try:
                data = resp.json()
            except json.JSONDecodeError as json_error:
                print(f"[OpenAIChatAPI] JSON解析失败: {json_error}")
                print(f"[OpenAIChatAPI] 响应内容: {resp.text[:500]}...")
                return ("", f"API响应格式错误: {resp.text[:200]}", "")
            
            print("API原始响应:", data)
            
            # 通用错误字段
            if "error" in data and data["error"]:
                err = data["error"]
                msg = err.get("message", str(err))
                typ = err.get("type", "unknown_error")
                return ("", f"API错误 ({typ}): {msg}", "")
            
            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)
            
            if not is_responses_api:
                # 旧 chat/completions 解析
                if "choices" in data and data["choices"]:
                    message = data["choices"][0].get("message", {})
                    content = message.get("content", "")
                    finish_reason = data["choices"][0].get("finish_reason", "")
                    if not content:
                        return ("", f"未返回内容，finish_reason={finish_reason}", tokens_usage)
                    reasoning_content, answer = self._parse_content_tags(content)
                    return (reasoning_content or "", answer, tokens_usage)
                else:
                    return ("", "API未返回choices内容", tokens_usage)
            else:
                # 新 responses 解析
                output = data.get("output", [])
                texts = []
                if isinstance(output, list):
                    for item in output:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "message":
                            contents = item.get("content", [])
                            for c in contents:
                                if isinstance(c, dict) and c.get("type") == "output_text":
                                    t = c.get("text")
                                    if t:
                                        texts.append(t)
                        elif item.get("type") == "output_text":
                            # 某些实现可能直接平铺 output_text
                            t = item.get("text")
                            if t:
                                texts.append(t)
                # fallback：有些实现提供 data.get("text") 作为汇总
                if not texts and isinstance(data.get("text"), dict):
                    fmt = data["text"].get("format", {})
                    # 无需使用 format.type，只要有 text 字段已在上面处理
                # 合并文本
                answer = "".join(texts).strip() if texts else ""
                if not answer:
                    # 作为兜底，尝试常见字段
                    answer = data.get("output_text") or data.get("message") or ""
                    answer = (answer or "").strip()
                # 编码纠偏，避免UTF-8被按Latin-1显示的伪乱码
                answer = self._normalize_text(answer)
                if not answer:
                    return ("", "API未返回output文本内容", tokens_usage)
                # Responses 当前不提供思维链字段，保持空
                return ("", answer, tokens_usage)
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
        将tokens_usage格式化为易读的字符串，兼容多种字段命名
        """
        if not usage:
            return ""
        # 常见字段名兜底
        total_tokens = usage.get('total_tokens') or usage.get('total') or usage.get('tokens') or '-'
        prompt_tokens = (
            usage.get('prompt_tokens')
            or usage.get('input_tokens')
            or (usage.get('input', {}) if isinstance(usage.get('input'), dict) else None)
            or usage.get('prompt')
            or '-'
        )
        if isinstance(prompt_tokens, dict):
            prompt_tokens = prompt_tokens.get('tokens') or prompt_tokens.get('count') or '-'
        completion_tokens = (
            usage.get('completion_tokens')
            or usage.get('output_tokens')
            or (usage.get('output', {}) if isinstance(usage.get('output'), dict) else None)
            or usage.get('completion')
            or '-'
        )
        if isinstance(completion_tokens, dict):
            completion_tokens = completion_tokens.get('tokens') or completion_tokens.get('count') or '-'
        return f"total_tokens={total_tokens}, input_tokens={prompt_tokens}, output_tokens={completion_tokens}"

    def _build_headers(self, api_key):
        """
        构建请求头
        """
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            # 明确声明期望 SSE 文本，且禁止压缩，避免 gzip/br 导致的“乱码”
            "Accept": "text/event-stream, application/json",
            "Cache-Control": "no-cache",
            "Accept-Encoding": "identity"
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

    def _normalize_text(self, s: str) -> str:
        """
        规范化文本编码，避免出现 'å½ç¶...' 这类UTF-8被按Latin-1解码的伪乱码。
        策略：
        - 若是str，优先返回原文
        - 发现典型伪乱码特征时，尝试：先以latin-1编码成bytes，再按utf-8解码
        - 若失败则返回原文
        """
        if not isinstance(s, str) or not s:
            return s or ""
        # 乱码经常出现在英文开头之后，因此不能只检查前几个字符。
        suspicious = ("Ã", "Â", "Ð", "Ñ", "å", "æ", "ç", "ð", "þ")
        if any(ch in s for ch in suspicious):
            try:
                # 只有完整的 Latin-1 -> UTF-8 逆转成功时才替换，避免 errors="ignore"
                # 静默丢掉真实内容。
                repaired = s.encode("latin-1").decode("utf-8")
                if repaired != s:
                    return repaired
            except Exception:
                pass
        return s

    def _parse_responses_stream(self, resp):
        """
        解析 Responses 的SSE流，将增量文本拼接为最终答案。
        兼容点：
        - 解析 event: 与 data: 组合
        - 识别多种事件名：response.output_text.delta / response.delta / message.delta / output_text.delta / delta
        - 对非UTF-8字符与BOM进行清理
        - 在 completed 事件上提取 usage
        - 显式日志：采样首批原始行与最近的 data 片段，便于定位“乱码/编码/事件名差异”
        """
        answer_parts = []
        tokens_usage = ""
        curr_event = None
        raw_samples = []  # 采样前若干行
        last_data_snippets = []  # 最近的 data 片段

        def _clean(s: str) -> str:
            if not isinstance(s, str):
                return ""
            # 去除可能的BOM与不可见控制字符
            s = s.replace("\ufeff", "").replace("\u200b", "").strip()
            return s

        try:
            # iter_lines(decode_unicode=True) 使用 resp.encoding 解码每一行。
            # 服务端未返回 charset 时必须在这里明确指定 UTF-8。
            resp.encoding = "utf-8"
            for raw in resp.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                line = raw.strip()
                # 记录原始行样本（最多10条）
                if len(raw_samples) < 10:
                    try:
                        raw_samples.append(line[:200])
                    except Exception:
                        pass
                if not line:
                    continue

                # 处理 event: 行
                if line.startswith("event:"):
                    curr_event = line[len("event:"):].strip()
                    continue

                if not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    continue
                # 记录最近的 data 片段（最多5条）
                try:
                    if len(last_data_snippets) >= 5:
                        last_data_snippets.pop(0)
                    last_data_snippets.append(data_str[:200])
                except Exception:
                    pass

                # 清理后再解析
                data_str = _clean(data_str)
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    # 某些实现会双重 JSON 编码或返回部分片段，忽略不可解析的数据
                    continue

                # 事件类型优先：payload.type，其次 curr_event
                typ = payload.get("type") or curr_event or ""

                # 识别增量字段
                delta_text = None
                if typ in ("response.output_text.delta", "response.delta", "message.delta", "output_text.delta", "delta"):
                    dt = payload.get("delta")
                    if isinstance(dt, str):
                        delta_text = dt
                    elif isinstance(dt, dict):
                        # 兼容某些实现把 text 放在 delta.text
                        t = dt.get("text")
                        if isinstance(t, str):
                            delta_text = t
                # 有些实现不带 type，只带 delta 字段
                if delta_text is None and isinstance(payload.get("delta"), str):
                    delta_text = payload["delta"]

                if isinstance(delta_text, str) and delta_text:
                    answer_parts.append(_clean(delta_text))
                    continue

                # 识别 completed/usage
                if typ in ("response.completed", "completed", "response.complete"):
                    resp_obj = payload.get("response") or {}
                    usage = resp_obj.get("usage") or payload.get("usage") or {}
                    tokens_usage = self._format_tokens_usage(usage)
                    break

            # 若没有解析到任何文本增量，打印采样日志辅助排查
            if not answer_parts:
                try:
                    print(f"[OpenAIChatAPI] SSE原始行样本(最多10): {self._safe_json_dumps(raw_samples)}")
                    print(f"[OpenAIChatAPI] SSE最近data片段(最多5): {self._safe_json_dumps(last_data_snippets)}")
                except Exception:
                    pass
            normalized_answer = self._normalize_text("".join(answer_parts).strip())
            return ("", normalized_answer, tokens_usage)
        except Exception as e:
            return ("", f"SSE解析失败: {e}", tokens_usage)

# 节点注册
NODE_CLASS_MAPPINGS = {
    "OpenAI_Chat_API": OpenAIChatAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenAI_Chat_API": "🦉OpenAI兼容Chat API节点"
} 
