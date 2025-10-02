import json
import requests
import re
import time
from typing import Optional, Any
from comfy_api_nodes.apinode_utils import VideoFromFile

class OpenAISoraAPI:
    """
    ComfyUI自定义节点：302.ai Sora-2 视频生成（OpenAI兼容流式接口）
    - 参考 openai_chat_api_node.py 的结构与风格
    - 通过 302.ai 的 /chat/completions 接口，以 stream=True 获取流式增量内容
    - 适配示例返回：每行均为 JSON，字段为 choices[0].delta.content
    - 超时时间：600 秒（10 分钟）
    输入参数：
      - base_url: 默认 https://api.302.ai/v1
      - model: 默认 sora-2
      - api_key: 必填
      - system_prompt: 可选，用于设定系统指令
      - user_prompt: 必填，视频生成描述
    输出：
      - reasoning_content: 保留为空（""），与参考节点保持一致
      - answer: 汇总的增量内容（通常包含进度与最终信息）
      - tokens_usage: 由于返回中未提供 usage，这里一般为空字符串
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://api.302.ai/v1", "multiline": False}),
                "model": ("STRING", {"default": "sora-2", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "user_prompt": ("STRING", {"multiline": True, "default": "请描述要生成的视频内容"}),
            },
            "optional": {
                # 可选图像输入：提供则走“图生视频（image-to-video）”，不提供则为“文生视频（text-to-video）”
                "image": ("IMAGE",),
                # 新版302AI接口兼容参数：async与callback
                "async_flag": ("BOOLEAN", {"default": False}),
                "callback": ("STRING", {"default": "", "multiline": False}),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "tokens_usage")
    FUNCTION = "generate"
    CATEGORY = "🦉FreeAPI/OpenAI"

    def generate(self, base_url, model, api_key, user_prompt, image=None, async_flag=False, callback=""):
        """
        调用 302.ai 的 sora-2 模型进行视频生成（流式）。
        请求：
          POST {base_url}/chat/completions
          headers:
            - Authorization: Bearer {api_key}
            - Accept: application/json
            - Content-Type: application/json
          json:
            {
              "model": model,
              "messages": [{"role": "system","content": system_prompt}, {"role":"user","content": user_prompt}],
              "stream": true
            }
        解析：
          - 逐行读取，每行是 JSON，取 choices[0].delta.content 累加
          - 若流式无内容，降级为非流式请求（stream=false）再解析
        超时：
          - timeout=600 秒
        """
        if not api_key:
            return (None, "", "错误：未配置API Key，请在节点参数中设置 api_key")
        if not base_url:
            return (None, "", "错误：未配置 base_url，请在节点参数中设置 base_url")
        if not user_prompt.strip():
            return (None, "", "错误：user_prompt 为空，请提供视频描述")

        try:
            headers = self._build_headers(api_key)
            # 兼容新版302AI：支持在URL上附加 async 与 callback 参数
            base_path = f"{base_url.rstrip('/')}/chat/completions"
            query_params = []
            # 仅当用户显式设置时附加 async=false/true
            if isinstance(async_flag, bool):
                query_params.append(f"async={'true' if async_flag else 'false'}")
            # 如提供callback则附加
            if isinstance(callback, str) and callback.strip():
                # 对callback进行URL编码，避免特殊字符影响请求
                from urllib.parse import quote_plus
                cb = quote_plus(callback.strip())
                query_params.append(f"callback={cb}")
            api_url = base_path if not query_params else f"{base_path}?{'&'.join(query_params)}"

            # 构建聊天内容：
            # - 若提供 image：按 OpenAI 多模态格式使用 content 数组，携带文本与图片
            # - 若不提供 image：保持纯文本 content 字符串，兼容各类兼容接口
            if image is not None:
                try:
                    from io import BytesIO
                    import base64
                    from PIL import Image as _PILImage  # 仅用于确保PIL可用
                    pil_image = self._convert_to_pil(image)
                    buf = BytesIO()
                    pil_image.save(buf, format="PNG")
                    buf.seek(0)
                    image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    base64_url = f"data:image/png;base64,{image_base64}"
                    content = [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_url,
                                "detail": "high"
                            }
                        }
                    ]
                    print(f"[OpenAISoraAPI] 图生视频模式: 已附带输入图像，尺寸={pil_image.size}, base64长度={len(image_base64)}")
                except Exception as e:
                    return (None, f"输入图像处理失败: {e}", "")
                messages = [{"role": "user", "content": content}]
            else:
                print(f"[OpenAISoraAPI] 文生视频模式: 纯文本提示词")
                messages = [{"role": "user", "content": user_prompt}]

            payload = {
                "model": model,
                "messages": messages,
                "stream": False
            }

            print(f"[OpenAISoraAPI] 请求: {api_url} (chat/completions, stream=False)")
            print(f"[OpenAISoraAPI] 模型: {model}")
            # 打印裁剪后的提示词，便于用户确认任务内容
            _preview = (user_prompt[:120] + "...") if len(user_prompt) > 120 else user_prompt
            print(f"[OpenAISoraAPI] 提交Sora任务 | 提示词: {_preview}")
            # 打印精简后的载荷（避免输出完整base64）
            try:
                print(f"[OpenAISoraAPI] 请求载荷(精简): {self._safe_json_dumps(payload)}")
            except Exception:
                pass
            resp = requests.post(api_url, headers=headers, json=payload, timeout=600, stream=False)
            print(f"[OpenAISoraAPI] 响应状态码: {resp.status_code}")

            if resp.status_code != 200:
                return (None, f"API错误 (状态码: {resp.status_code}): {resp.text}", "")

            rc2, answer, tokens_usage = self._parse_non_stream(resp)

            # 若流式无内容或解析失败，降级为非流式
            if (not answer) or (isinstance(answer, str) and answer.startswith("流式解析失败")):
                try:
                    safe_payload = dict(payload)
                    safe_payload["stream"] = False
                    print(f"[OpenAISoraAPI] 流式不可用（原因: {answer[:120] if isinstance(answer, str) else '未知'}），降级为非流式请求")
                    resp2 = requests.post(api_url, headers=headers, json=safe_payload, timeout=600)
                    if resp2.status_code == 200:
                        rc2, answer2, tu2 = self._parse_non_stream(resp2)
                        video_url2 = self._extract_video_url(answer2)
                        video2 = self._download_and_convert_video(video_url2)
                        return (video2, video_url2 or "", tu2)
                    else:
                        return (None, f"非流式降级失败 (状态码: {resp2.status码}): {resp2.text}", tokens_usage)
                except Exception as _e:
                    print(f"[OpenAISoraAPI] 非流式降级异常: {_e}")

            # 正常流式结果：提取视频URL并下载
            video_url = self._extract_video_url(answer)

            # 若未能提取到视频URL，记录第一阶段的详细摘要，便于后续二阶段轮询
            if not video_url:
                try:
                    print("[OpenAISoraAPI] ⚠ 未提取到视频直链，输出流式文本摘要以便二阶段轮询")
                    # 打印首末片段（避免刷屏）
                    preview_head = answer[:400] if isinstance(answer, str) else ""
                    preview_tail = answer[-400:] if isinstance(answer, str) else ""
                    print(f"[OpenAISoraAPI] ▶ 首段(最多400字): {preview_head}")
                    if len(answer or "") > 800:
                        print("[OpenAISoraAPI] ... (中间省略)")
                    print(f"[OpenAISoraAPI] ◀ 末段(最多400字): {preview_tail}")
                    # 提取可能的任务ID或进度信息
                    try:
                        # 常见任务/作业ID样式
                        task_id_matches = re.findall(r'(?i)(task[_\s-]?id|job[_\s-]?id|task|job)\s*[:=]\s*([a-zA-Z0-9\-_]+)', answer or "")
                        if task_id_matches:
                            # 打印前3个
                            sample_ids = [m[1] for m in task_id_matches[:3]]
                            print(f"[OpenAISoraAPI] 可能的任务ID: {', '.join(sample_ids)}")
                    except Exception as _id_e:
                        print(f"[OpenAISoraAPI] 任务ID提取异常: {_id_e}")
                    # 收集所有URL，帮助定位任务详情页
                    try:
                        all_urls = re.findall(r'https?://[^\s)>\]]+', answer or "", flags=re.IGNORECASE)
                        if all_urls:
                            # 去重并打印前5个
                            uniq_urls = []
                            for u in all_urls:
                                if u not in uniq_urls:
                                    uniq_urls.append(u)
                            print(f"[OpenAISoraAPI] 文本中发现的URL({min(len(uniq_urls),5)}个示例): {uniq_urls[:5]}")
                        else:
                            print("[OpenAISoraAPI] 文本中未发现任何URL")
                    except Exception as _url_e:
                        print(f"[OpenAISoraAPI] URL提取异常: {_url_e}")
                    print("[OpenAISoraAPI] 建议：依据任务ID或上述URL进行二阶段轮询/查询，以获取视频直链(mp4/webm)")
                except Exception as _log_e:
                    print(f"[OpenAISoraAPI] 摘要日志输出异常: {_log_e}")

            video_output = self._download_and_convert_video(video_url)
            return (video_output, video_url or "", tokens_usage)
        except requests.exceptions.ConnectTimeout as e:
            return (None, f"网络连接超时: 无法连接到API服务器。请检查网络连接或代理。错误: {e}", "")
        except requests.exceptions.Timeout as e:
            return (None, f"请求超时: API响应时间过长。请稍后重试。错误: {e}", "")
        except requests.exceptions.ConnectionError as e:
            return (None, f"网络连接错误: 无法建立到API的连接。请检查网络设置。错误: {e}", "")
        except requests.exceptions.RequestException as e:
            return (None, f"API请求失败: {e}", "")
        except Exception as e:
            return (None, f"处理失败: {e}", "")

    def _build_headers(self, api_key: str):
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _convert_to_pil(self, image):
        """
        将ComfyUI的IMAGE/常见输入转换为PIL Image（RGB）。
        - 支持 torch.Tensor (N,H,W,3) 或 (H,W,3)，数值范围[0,1]或[0,255]
        - 支持PIL Image
        - 支持numpy数组
        """
        try:
            from PIL import Image
            if hasattr(image, "cpu"):  # torch.Tensor
                import torch
                import numpy as np
                t = image
                if t.dim() == 4:
                    t = t[0]
                # 期望 (H,W,3)
                if t.shape[-1] == 3:
                    arr = t.detach().cpu().numpy()
                elif t.shape[0] == 3 and t.dim() == 3:
                    # 兼容 (3,H,W) -> (H,W,3)
                    arr = t.detach().cpu().numpy().transpose(1, 2, 0)
                else:
                    raise ValueError(f"不支持的Tensor形状: {tuple(t.shape)}")
                # 归一化
                if arr.max() <= 1.0:
                    arr = (arr * 255.0).clip(0, 255).astype("uint8")
                else:
                    arr = arr.clip(0, 255).astype("uint8")
                img = Image.fromarray(arr)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                return img
            elif hasattr(image, "save"):  # PIL
                from PIL import Image as _Image
                img = image
                if img.mode != "RGB":
                    img = img.convert("RGB")
                return img
            else:
                import numpy as np
                if isinstance(image, np.ndarray):
                    arr = image
                    if arr.ndim == 3 and arr.shape[0] == 3:
                        arr = arr.transpose(1, 2, 0)
                    if arr.max() <= 1.0:
                        arr = (arr * 255.0).clip(0, 255).astype("uint8")
                    else:
                        arr = arr.clip(0, 255).astype("uint8")
                    from PIL import Image
                    img = Image.fromarray(arr)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    return img
                raise ValueError(f"不支持的图像类型: {type(image)}")
        except Exception as e:
            print(f"[OpenAISoraAPI] 图像转换失败: {e}")
            raise

    def _safe_json_dumps(self, obj, ensure_ascii=False, indent=2):
        """
        序列化JSON时截断超长/疑似base64字段，避免日志刷屏。
        """
        import json as _json

        def _truncate_base64(value: str):
            if not isinstance(value, str):
                return value
            if len(value) > 100 and (
                value.startswith("data:image/") or
                value[:8] in ("iVBORw0K", "/9j/")  # 常见PNG/JPEG开头
            ):
                return value[:50] + f"... (len={len(value)})"
            return value

        def _walk(v):
            if isinstance(v, dict):
                return {k: _walk(_truncate_base64(val)) for k, val in v.items()}
            if isinstance(v, list):
                return [_walk(_truncate_base64(x)) for x in v]
            return _truncate_base64(v)

        return _json.dumps(_walk(obj), ensure_ascii=ensure_ascii, indent=indent)

    def _parse_302_stream(self, resp):
        """
        解析 302.ai 的流式响应。
        示例行：
          {"choices":[{"delta":{"content":"...","role":"assistant"},"index":0}],"id":"...","model":"sora-2","object":"chat.completion.chunk"}
        策略：
          - 逐行解析 JSON
          - 提取 choices[0].delta.content 累加
          - 无 usage 字段，tokens_usage 保持为空
        """
        answer_parts = []
        tokens_usage = ""
        # 进度与心跳跟踪
        last_progress = -1   # 最近一次打印的百分比进度（0-100）
        chunk_count = 0      # 已接收的增量块数量
        printed_url = False  # 是否已打印过URL
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                line = raw.strip()
                if not line:
                    continue

                # 可能伴随时间戳行，如 "21:56:01"，跳过非 JSON 行
                if not (line.startswith("{") and line.endswith("}")):
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "choices" in payload and isinstance(payload["choices"], list) and payload["choices"]:
                    delta = payload["choices"][0].get("delta", {})
                    if isinstance(delta, dict):
                        piece = delta.get("content")
                        if isinstance(piece, str) and piece:
                            # 进度日志：尽量识别诸如 "进度 36.."、"41.."、"60.." 等
                            text = piece.strip()
                            # 优先匹配包含“进度”的片段
                            prog_candidates = []
                            if "进度" in text or "progress" in text.lower():
                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)
                                if not prog_candidates:
                                    prog_candidates = re.findall(r'进度[^0-9]*?(\d{1,3})', text)
                            else:
                                # 一般性匹配 "41.." 这类
                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)

                            # 过滤到 0-100 的最大值作为当前进度
                            curr_prog = None
                            for p in prog_candidates:
                                try:
                                    v = int(p)
                                    if 0 <= v <= 100:
                                        curr_prog = v if (curr_prog is None or v > curr_prog) else curr_prog
                                except Exception:
                                    pass
                            if curr_prog is not None and curr_prog > last_progress:
                                last_progress = curr_prog
                                print(f"[OpenAISoraAPI][{time.strftime('%H:%M:%S')}] 任务进度: {last_progress}%")

                            # 首次发现 URL 则提示
                            if not printed_url and ("http://" in text or "https://" in text):
                                urls = re.findall(r'https?://\S+', text)
                                if urls:
                                    print(f"[OpenAISoraAPI] 可能的视频URL: {urls[0]}")
                                    printed_url = True

                            # 心跳：每收到一定数量块打印一次累计长度
                            chunk_count += 1
                            if chunk_count % 20 == 0:
                                total_len = sum(len(x) for x in answer_parts) + len(text)
                                print(f"[OpenAISoraAPI] 流式接收中... 已接收 {chunk_count} 块，累计字符 {total_len}")

                            answer_parts.append(piece)

            # 合并并做简单的编码清理
            answer = self._normalize_text("".join(answer_parts).strip())
            try:
                total_len = len(answer or "")
                print(f"[OpenAISoraAPI] 流式结束，累计字符={total_len}")
                if total_len:
                    head = answer[:300]
                    print(f"[OpenAISoraAPI] 流式文本首段(最多300字): {head}")
            except Exception as _sum_e:
                print(f"[OpenAISoraAPI] 流式摘要输出异常: {_sum_e}")
            return ("", answer, tokens_usage)
        except Exception as e:
            return ("", f"流式解析失败: {e}", tokens_usage)

    def _parse_non_stream(self, resp):
        """
        非流式响应解析（兼容 OpenAI chat/completions）
        预期结构：
          {"choices":[{"message":{"role":"assistant","content":"..."},"finish_reason":"..." }], "usage": {...}}
        """
        try:
            if resp.status_code != 200:
                return ("", f"API错误 (状态码: {resp.status_code}): {resp.text}", "")
            if not resp.text.strip():
                return ("", "API返回空响应", "")

            try:
                data = resp.json()
            except json.JSONDecodeError as json_error:
                return ("", f"API响应格式错误: {str(json_error)}", "")

            # 错误字段
            if "error" in data and data["error"]:
                err = data["error"]
                msg = err.get("message", str(err))
                typ = err.get("type", "unknown_error")
                return ("", f"API错误 ({typ}): {msg}", "")

            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)

            if "choices" in data and data["choices"]:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                if not content:
                    finish_reason = data["choices"][0].get("finish_reason", "")
                    return ("", f"未返回内容，finish_reason={finish_reason}", tokens_usage)
                reasoning_content, answer = self._parse_content_tags(content)
                return ("", answer, tokens_usage)

            return ("", "API未返回choices内容", tokens_usage)
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _parse_content_tags(self, content: str):
        """
        复用与参考节点一致的标签解析逻辑：
        - <think>...</think> 抽取思考
        - <answer>...</answer> 抽取答案
        - <reasoning>...</reasoning> 抽取思考
        """
        try:
            think_pattern = r'<think>(.*?)</think>'
            think_match = re.search(think_pattern, content, re.DOTALL)
            if think_match:
                reasoning_content = think_match.group(1).strip()
                answer = content.replace(think_match.group(0), "").strip()
                return (reasoning_content, answer)

            answer_pattern = r'<answer>(.*?)</answer>'
            answer_match = re.search(answer_pattern, content, re.DOTALL)
            if answer_match:
                return ("", answer_match.group(1).strip())

            answer_pattern_open = r'<answer>(.*)'
            answer_match_open = re.search(answer_pattern_open, content, re.DOTALL)
            if answer_match_open:
                return ("", answer_match_open.group(1).strip())

            reasoning_pattern = r'<reasoning>(.*?)</reasoning>'
            reasoning_match = re.search(reasoning_pattern, content, re.DOTALL)
            if reasoning_match:
                reasoning_content = reasoning_match.group(1).strip()
                answer = content.replace(reasoning_match.group(0), "").strip()
                return (reasoning_content, answer)

            return ("", content.strip())
        except Exception:
            return ("", content.strip())

    def _format_tokens_usage(self, usage):
        if not usage:
            return ""
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

    def _normalize_text(self, s: str) -> str:
        if not isinstance(s, str) or not s:
            return s or ""
        sample = s[:8]
        suspicious = ("Ã", "å", "æ", "ç", "ð", "þ")
        if any(ch in sample for ch in suspicious):
            try:
                return s.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            except Exception:
                return s
        return s

    def _extract_video_url(self, text: str) -> Optional[str]:
        """
        从返回文本中提取视频URL。
        优先匹配指向 mp4/webm 等视频资源的URL；若未匹配到，则回退匹配任意 http/https 链接。
        """
        if not isinstance(text, str) or not text:
            return None
        try:
            # 优先匹配视频直链
            m = re.findall(r'(https?://[^\s)>\]]+\.(?:mp4|webm)(?:\?[^\s)>\]]*)?)', text, flags=re.IGNORECASE)
            if m:
                return m[0]
            # 其次匹配 markdown 的 [在线播放](url) 格式
            m2 = re.findall(r'\((https?://[^\s)]+)\)', text, flags=re.IGNORECASE)
            if m2:
                return m2[0]
            # 再次匹配任意 http/https 链接
            m3 = re.findall(r'(https?://[^\s)>\]]+)', text, flags=re.IGNORECASE)
            if m3:
                return m3[0]
            return None
        except Exception:
            return None

    def _download_and_convert_video(self, video_url: str) -> Optional[Any]:
        """
        下载视频URL并转换为VIDEO对象（同步实现）。
        - 使用 requests 同步下载到内存(BytesIO)，再构造 VideoFromFile
        - 不依赖事件循环/协程，保证返回真实 VIDEO 对象
        - 出错返回 None，保证节点稳定
        """
        try:
            if not video_url or not isinstance(video_url, str):
                print(f"[OpenAISoraAPI] 无效的视频URL: {video_url}")
                return None
            if not video_url.startswith(("http://", "https://")):
                print(f"[OpenAISoraAPI] 不支持的URL格式: {video_url}")
                return None

            print(f"[OpenAISoraAPI] 🎬 开始下载视频: {video_url[:80]}...")
            import io as _io
            try:
                # 同步下载到内存
                with requests.get(video_url, timeout=120, stream=True) as r:
                    r.raise_for_status()
                    buf = _io.BytesIO()
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            buf.write(chunk)
                    buf.seek(0)
                # 构造 Comfy VIDEO 对象
                video_output = VideoFromFile(buf)
                # 基本类型校验
                if not hasattr(video_output, "get_dimensions"):
                    print(f"[OpenAISoraAPI] ❌ 视频对象类型异常：{type(video_output)}，缺少 get_dimensions()")
                    return None
                print(f"[OpenAISoraAPI] ✅ 视频下载完成")
                return video_output
            except requests.exceptions.RequestException as req_err:
                print(f"[OpenAISoraAPI] ❌ 视频下载失败(网络): {req_err}")
                return None
            except Exception as conv_err:
                print(f"[OpenAISoraAPI] ❌ 视频构造失败: {conv_err}")
                return None
        except Exception as e:
            print(f"[OpenAISoraAPI] 视频下载转换过程出错: {e}")
            return None

# 节点注册
NODE_CLASS_MAPPINGS = {
    "OpenAI_Sora_API": OpenAISoraAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenAI_Sora_API": "🦉OpenAI Sora API节点"
}
