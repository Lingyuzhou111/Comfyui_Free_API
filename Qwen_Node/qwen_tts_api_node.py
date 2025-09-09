import os
import json
import requests
import time
import logging
import torch
import torchaudio
import numpy as np
import av
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenTTSAPI")

# 节点主类
class QwenTTSAPI:
    """
    ComfyUI自定义节点：Qwen TTS API
    实现文本转语音API调用，专门针对Qwen TTS API，参数自动读取config.json。
    输入参数：text, voice, model, stream
    输出：audio_url（音频文件URL）, generation_info（生成信息）, audio（ComfyUI音频格式）
    """
    def __init__(self):
        # 读取配置文件，专门读取TTS.qwen_tts配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('TTS', {}).get('qwen_tts', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取Qwen TTS模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            qwen_config = config.get('TTS', {}).get('qwen_tts', {})
        model_options = qwen_config.get('model', ['qwen-tts'])
        
        # 定义可用的音色选项（中文名称+描述）
        voice_options = [
            "Cherry_芊悦(阳光积极、亲切自然的小姐姐)",
            "Serena_苏瑶(温柔小姐姐)", 
            "Ethan_晨煦(阳光、温暖、活力、朝气的北方男孩)",
            "Chelsie_千雪(二次元虚拟女友)",
            "Dylan_晓东(北京胡同里长大的少年)",
            "Jada_阿珍(风风火火的沪上阿姨)",
            "Sunny_晴儿(甜到你心里的川妹子)"
        ]
        
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "你好，这是一个测试文本，用于生成语音。"}),
                "voice": (voice_options, {"default": "Cherry_芊悦(阳光积极、亲切自然的小姐姐)"}),
                "model": (model_options, {"default": model_options[0]}),
            },
            "optional": {
                "stream": ("BOOLEAN", {"default": False, "tooltip": "是否启用流式输出"}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING" )
    RETURN_NAMES = ("audio", "audio_url", "generation_info")
    FUNCTION = "generate_speech"
    CATEGORY = "🦉FreeAPI/Qwen"

    def _extract_voice_name(self, voice_option):
        """
        从音色选项中提取英文音色名称
        例如：从 "Cherry_芊悦(阳光积极、亲切自然的小姐姐)" 提取 "Cherry"
        """
        if "_" in voice_option:
            return voice_option.split("_")[0].strip()
        return voice_option.strip()

    def _download_audio_to_tensor(self, audio_url: str) -> dict:
        """
        从音频URL下载音频并转换为ComfyUI的AUDIO格式
        返回格式：{"waveform": torch.Tensor, "sample_rate": int}
        """
        # 如果URL为空或无效，返回静音音频
        if not audio_url or audio_url == "" or audio_url.startswith("错误") or audio_url.startswith("流式输出"):
            logger.info("[QwenTTSAPI] 返回静音音频作为fallback")
            empty_waveform = torch.zeros(1, 1, 16000)  # 1秒的静音
            return {
                "waveform": empty_waveform,
                "sample_rate": 16000
            }
        
        try:
            logger.info(f"[QwenTTSAPI] 开始下载音频: {audio_url}")
            
            # 下载音频文件
            response = requests.get(audio_url, timeout=180)
            response.raise_for_status()
            
            # 将音频数据转换为BytesIO
            audio_bytes = io.BytesIO(response.content)
            audio_bytes.seek(0)
            
            # 使用torchaudio加载音频
            waveform, sample_rate = torchaudio.load(audio_bytes)
            
            # 确保波形格式正确 [B, C, T] -> [1, C, T]
            if waveform.dim() == 2:  # [C, T] -> [1, C, T]
                waveform = waveform.unsqueeze(0)
            
            # 转换为float32并归一化到[-1, 1]范围
            if waveform.dtype != torch.float32:
                waveform = waveform.float()
            
            # 如果音频值超出[-1, 1]范围，进行归一化
            max_val = torch.max(torch.abs(waveform))
            if max_val > 1.0:
                waveform = waveform / max_val
            
            logger.info(f"[QwenTTSAPI] 音频转换完成: 形状={waveform.shape}, 采样率={sample_rate}")
            
            return {
                "waveform": waveform,
                "sample_rate": sample_rate
            }
            
        except Exception as e:
            logger.error(f"音频下载转换失败: {e}")
            # 返回一个空的音频数据作为fallback
            empty_waveform = torch.zeros(1, 1, 16000)  # 1秒的静音
            return {
                "waveform": empty_waveform,
                "sample_rate": 16000
            }

    def generate_speech(self, text, voice, model, stream=False):
        """
        主方法：生成语音
        1. 验证输入参数
        2. 构造Qwen TTS API请求
        3. 发送请求，返回音频URL、生成信息和ComfyUI音频格式
        """
        # 读取Qwen TTS API参数
        base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            return (self._download_audio_to_tensor(""), "", "错误：未配置Qwen TTS API Key，请在config.json中设置qwen_tts.api_key")
        
        # 验证输入参数
        if not text or not text.strip():
            return (self._download_audio_to_tensor(""), "", "错误：文本内容不能为空")
        
        if not voice:
            return (self._download_audio_to_tensor(""), "", "错误：音色不能为空")
        
        # 检查文本长度（Qwen TTS限制512 Token，这里用字符数粗略估算）
        if len(text) > 1000:  # 保守估计，避免超出Token限制
            return (self._download_audio_to_tensor(""), "", f"错误：文本过长，当前长度{len(text)}字符，建议控制在1000字符以内")
        
        # 从音色选项中提取英文名称
        voice_name = self._extract_voice_name(voice)
        
        # 构造Qwen TTS API请求
        payload = {
            "model": model,
            "input": {
                "text": text.strip(),
                "voice": voice_name
            }
        }
        
        if stream:
            payload["stream"] = True
        
        # 发送请求
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"[QwenTTSAPI] 发送TTS请求到: {base_url}")
            logger.info(f"[QwenTTSAPI] 请求参数: {json.dumps(payload, ensure_ascii=False)}")
            
            resp = requests.post(base_url, headers=headers, json=payload, timeout=180)
            
            if resp.status_code != 200:
                error_msg = f"API请求失败，状态码: {resp.status_code}, 响应: {resp.text}"
                logger.error(error_msg)
                return (self._download_audio_to_tensor(""), "", error_msg)
            
            # 解析响应
            if stream:
                return self._parse_stream_response(resp)
            else:
                return self._parse_response(resp)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"API请求异常: {e}"
            logger.error(error_msg)
            return (self._download_audio_to_tensor(""), "", error_msg)
        except Exception as e:
            error_msg = f"处理失败: {e}"
            logger.error(error_msg)
            return (self._download_audio_to_tensor(""), "", error_msg)

    def _parse_response(self, resp):
        """
        解析非流式响应
        """
        try:
            data = resp.json()
            logger.info(f"[QwenTTSAPI] 收到TTS响应: {json.dumps(data, ensure_ascii=False)}")
            
            # 提取音频URL
            audio_url = ""
            if "output" in data and "audio" in data["output"]:
                audio_info = data["output"]["audio"]
                audio_url = audio_info.get("url", "")
                
                # 如果没有URL但有data，说明是流式输出
                if not audio_url and audio_info.get("data"):
                    audio_url = "流式输出音频数据"
            
            # 构造生成信息
            generation_info = self._format_generation_info(data)
            
            if not audio_url:
                return (self._download_audio_to_tensor(""), "", f"未获取到音频URL，响应内容: {str(data)}")
            
            # 下载音频并转换为tensor
            audio_data = self._download_audio_to_tensor(audio_url)
            
            return (audio_data, audio_url, generation_info)
            
        except json.JSONDecodeError as e:
            error_msg = f"响应JSON解析失败: {e}, 原始响应: {resp.text}"
            logger.error(error_msg)
            return (self._download_audio_to_tensor(""), "", error_msg)
        except Exception as e:
            error_msg = f"响应解析失败: {e}"
            logger.error(error_msg)
            return (self._download_audio_to_tensor(""), "", error_msg)

    def _parse_stream_response(self, resp):
        """
        解析流式响应
        """
        try:
            audio_url = ""
            generation_info = ""
            
            for line in resp.iter_lines():
                if not line:
                    continue
                
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    continue
                
                # 提取音频信息
                if "output" in data and "audio" in data["output"]:
                    audio_info = data["output"]["audio"]
                    if audio_info.get("url"):
                        audio_url = audio_info.get("url")
                    elif audio_info.get("data"):
                        audio_url = "流式输出音频数据"
                
                # 提取生成信息
                if "usage" in data:
                    generation_info = self._format_generation_info(data)
            
            if not audio_url:
                return (self._download_audio_to_tensor(""), "", "流式输出中未获取到音频信息")
            
            # 下载音频并转换为tensor
            audio_data = self._download_audio_to_tensor(audio_url)
            
            return (audio_data, audio_url, generation_info)
            
        except Exception as e:
            error_msg = f"流式响应解析失败: {e}"
            logger.error(error_msg)
            return (self._download_audio_to_tensor(""), "", error_msg)

    def _format_generation_info(self, data):
        """
        格式化生成信息，包含Token使用情况和请求ID
        """
        info_parts = []
        
        # 添加请求ID
        if "request_id" in data:
            info_parts.append(f"请求ID: {data['request_id']}")
        
        # 添加完成状态
        if "output" in data and "finish_reason" in data["output"]:
            finish_reason = data["output"]["finish_reason"]
            status = "完成" if finish_reason == "stop" else "生成中"
            info_parts.append(f"状态: {status}")
        
        # 添加Token使用信息
        if "usage" in data:
            usage = data["usage"]
            if "total_tokens" in usage:
                info_parts.append(f"总Token: {usage['total_tokens']}")
            if "input_tokens" in usage:
                info_parts.append(f"输入Token: {usage['input_tokens']}")
            if "output_tokens" in usage:
                info_parts.append(f"输出Token: {usage['output_tokens']}")
        
        # 添加音频信息
        if "output" in data and "audio" in data["output"]:
            audio_info = data["output"]["audio"]
            if "id" in audio_info:
                info_parts.append(f"音频ID: {audio_info['id']}")
            if "expires_at" in audio_info:
                expires_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(audio_info["expires_at"]))
                info_parts.append(f"过期时间: {expires_time}")
        
        return " | ".join(info_parts) if info_parts else "无详细信息"

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Qwen_TTS_API": QwenTTSAPI
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_TTS_API": "🦉Qwen TTS API节点"
}
