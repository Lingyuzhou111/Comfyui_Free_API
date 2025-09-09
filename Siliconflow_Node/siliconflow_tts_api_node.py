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
logger = logging.getLogger("SiliconflowTTSAPI")

# 节点主类
class SiliconflowTTSAPI:
    """
    ComfyUI自定义节点：Siliconflow TTS API
    实现文本转语音API调用，专门针对Siliconflow TTS API，参数自动读取config.json。
    输入参数：text, voice, model, response_format, sample_rate, speed, gain, stream
    输出：audio（ComfyUI音频格式）, audio_url（音频文件URL）, generation_info（生成信息）
    """
    def __init__(self):
        # 读取配置文件，专门读取TTS.siliconflow_tts配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('TTS', {}).get('siliconflow_tts', {})
        
        # 读取自定义音色列表
        self.custom_voices = {}
        try:
            custom_voice_path = os.path.join(os.path.dirname(__file__), 'custom_voice_list.json')
            if os.path.exists(custom_voice_path):
                with open(custom_voice_path, 'r', encoding='utf-8') as f:
                    custom_voice_data = json.load(f)
                    
                # 构建音色名称到URI的映射
                for model, voices in custom_voice_data.items():
                    for voice in voices:
                        voice_name = voice.get('name', '')
                        voice_uri = voice.get('uri', '')
                        if voice_name and voice_uri:
                            self.custom_voices[voice_name] = {
                                'uri': voice_uri,
                                'model': model
                            }
                            
                logger.info(f"成功加载 {len(self.custom_voices)} 个自定义音色映射")
            else:
                logger.info("未找到 custom_voice_list.json 文件")
        except Exception as e:
            logger.warning(f"读取自定义音色列表失败: {e}")

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取Siliconflow TTS模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            siliconflow_config = config.get('TTS', {}).get('siliconflow_tts', {})
        model_options = siliconflow_config.get('model', ['FunAudioLLM/CosyVoice2-0.5B'])
        
        # 定义预设的音色选项（显示名称）
        preset_voice_options = [
            "沉稳男声_alex", "沉稳女声_anna", "激情女声_bella", "低沉男声_benjamin", 
            "磁性男声_charles", "温柔女声_claire", "欢快男声_david", "欢快女声_diana"
        ]
        
        # 读取自定义音色列表
        custom_voice_options = []
        try:
            custom_voice_path = os.path.join(os.path.dirname(__file__), 'custom_voice_list.json')
            if os.path.exists(custom_voice_path):
                with open(custom_voice_path, 'r', encoding='utf-8') as f:
                    custom_voice_data = json.load(f)
                    
                # 提取所有自定义音色的名称
                for model, voices in custom_voice_data.items():
                    for voice in voices:
                        voice_name = voice.get('name', '')
                        if voice_name and voice_name not in custom_voice_options:
                            custom_voice_options.append(voice_name)
                            
                logger.debug(f"成功加载 {len(custom_voice_options)} 个自定义音色: {custom_voice_options}")
            else:
                logger.info("未找到 custom_voice_list.json 文件，仅使用预设音色")
        except Exception as e:
            logger.warning(f"读取自定义音色列表失败: {e}，仅使用预设音色")
        
        # 合并预设音色和自定义音色
        voice_options = preset_voice_options + custom_voice_options
        
        # 为自定义音色添加标识
        if custom_voice_options:
            logger.debug(f"音色选项: {len(preset_voice_options)} 个预设音色 + {len(custom_voice_options)} 个自定义音色")
            logger.debug(f"自定义音色: {custom_voice_options}")
        else:
            logger.info(f"音色选项: {len(preset_voice_options)} 个预设音色")
        
        # 定义音频格式选项
        response_format_options = ["mp3", "wav", "pcm", "opus"]
        
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "你好，这是一个测试文本，用于生成语音。"}),
                "model": (model_options, {"default": model_options[0]}),
                "voice": (voice_options, {"default": "沉稳男声_alex"}),
                "response_format": (response_format_options, {"default": "mp3"}),
            },
            "optional": {
                "sample_rate": ("INT", {"default": 32000, "min": 8000, "max": 48000, "step": 1000, "tooltip": "音频采样率"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.25, "max": 4.0, "step": 0.1, "tooltip": "音频播放速度"}),
                "gain": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.1, "tooltip": "音频增益"}),
                "stream": ("BOOLEAN", {"default": False, "tooltip": "是否启用流式输出"}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "generation_info")
    FUNCTION = "generate_speech"
    CATEGORY = "🦉FreeAPI/Siliconflow"

    def _create_audio_tensor_from_binary(self, audio_binary: bytes, sample_rate: int = 32000) -> dict:
        """
        从二进制音频数据创建ComfyUI的AUDIO格式
        返回格式：{"waveform": torch.Tensor, "sample_rate": int}
        """
        try:
            # 将二进制数据转换为BytesIO
            audio_bytes = io.BytesIO(audio_binary)
            audio_bytes.seek(0)
            
            # 使用torchaudio加载音频
            waveform, detected_sample_rate = torchaudio.load(audio_bytes)
            
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
            
            # 如果检测到的采样率与预期不同，进行重采样
            if detected_sample_rate != sample_rate:
                waveform = torchaudio.functional.resample(waveform, detected_sample_rate, sample_rate)
            
            logger.info(f"音频转换完成: 形状={waveform.shape}, 采样率={sample_rate}")
            
            return {
                "waveform": waveform,
                "sample_rate": sample_rate
            }
            
        except Exception as e:
            logger.error(f"音频转换失败: {e}")
            # 返回一个空的音频数据作为fallback
            empty_waveform = torch.zeros(1, 1, sample_rate)  # 1秒的静音
            return {
                "waveform": empty_waveform,
                "sample_rate": sample_rate
            }

    def generate_speech(self, text, voice, model, response_format, sample_rate=32000, speed=1.0, gain=0.0, stream=False):
        """
        主方法：生成语音
        1. 验证输入参数
        2. 构造Siliconflow TTS API请求
        3. 发送请求，返回音频数据和生成信息
        """
        # 读取Siliconflow TTS API参数
        base_url = self.config.get('base_url', 'https://api.siliconflow.cn/v1')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", "错误：未配置Siliconflow TTS API Key，请在config.json中设置siliconflow_tts.api_key")
        
        # 验证输入参数
        if not text or not text.strip():
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", "错误：文本内容不能为空")
        
        if not voice:
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", "错误：音色不能为空")
        
        # 检查文本长度
        if len(text) > 4000:  # 保守估计，避免超出Token限制
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", f"错误：文本过长，当前长度{len(text)}字符，建议控制在4000字符以内")
        
        # 构造voice参数
        if voice in self.custom_voices:
            # 自定义音色：直接使用URI
            custom_voice_info = self.custom_voices[voice]
            voice_param = custom_voice_info['uri']
            # 如果自定义音色指定了模型，使用指定的模型
            if custom_voice_info['model'] != model:
                logger.info(f"自定义音色 '{voice}' 使用模型 {custom_voice_info['model']}，覆盖用户选择的模型 {model}")
                model = custom_voice_info['model']
            logger.info(f"使用自定义音色: {voice} -> {voice_param}")
        else:
            # 预设音色：从显示名称中提取原始英文名称
            if "_" in voice:
                # 新格式：沉稳男声_alex -> 提取 alex
                original_voice = voice.split("_")[-1]
                logger.info(f"从显示名称 '{voice}' 提取原始音色名称: {original_voice}")
            else:
                # 兼容旧格式（如果存在）
                original_voice = voice
                logger.info(f"使用原始音色名称: {original_voice}")
            
            # 构造完整的voice参数（包含模型前缀）
            voice_param = f"{model}:{original_voice}"
            logger.info(f"使用预设音色: {voice} -> {voice_param}")
        
        # 构造Siliconflow TTS API请求
        payload = {
            "model": model,
            "input": text.strip(),
            "voice": voice_param,
            "response_format": response_format,
            "sample_rate": sample_rate,
            "speed": speed,
            "gain": gain
        }
        
        if stream:
            payload["stream"] = True
        
        # 发送请求
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"发送TTS请求到: {base_url}/audio/speech")
            logger.info(f"音色类型: {'自定义音色' if voice in self.custom_voices else '预设音色'}")
            if voice not in self.custom_voices and "_" in voice:
                original_voice = voice.split("_")[-1]
                logger.info(f"音色处理: 显示名称 '{voice}' -> 原始名称 '{original_voice}' -> API参数 '{voice_param}'")
            logger.info(f"请求参数: {json.dumps(payload, ensure_ascii=False)}")
            
            resp = requests.post(f"{base_url}/audio/speech", headers=headers, json=payload, timeout=180)
            
            if resp.status_code != 200:
                error_msg = f"API请求失败，状态码: {resp.status_code}, 响应: {resp.text}"
                logger.error(error_msg)
                return (self._create_audio_tensor_from_binary(b"", sample_rate), "", error_msg)
            
            # 解析响应
            if stream:
                return self._parse_stream_response(resp, sample_rate)
            else:
                return self._parse_response(resp, sample_rate)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"API请求异常: {e}"
            logger.error(error_msg)
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", error_msg)
        except Exception as e:
            error_msg = f"处理失败: {e}"
            logger.error(error_msg)
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", error_msg)

    def _parse_response(self, resp, sample_rate):
        """
        解析非流式响应
        """
        try:
            # Siliconflow TTS API返回的是二进制音频数据
            audio_binary = resp.content
            
            if not audio_binary:
                return (self._create_audio_tensor_from_binary(b"", sample_rate), "", "未获取到音频数据")
            
            # 创建音频tensor
            audio_data = self._create_audio_tensor_from_binary(audio_binary, sample_rate)
            
            # 构造生成信息
            generation_info = self._format_generation_info(resp.headers, len(audio_binary))
            
            # 由于是直接返回二进制数据，没有URL，所以audio_url为空
            return (audio_data, "", generation_info)
            
        except Exception as e:
            error_msg = f"响应解析失败: {e}"
            logger.error(error_msg)
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", error_msg)

    def _parse_stream_response(self, resp, sample_rate):
        """
        解析流式响应
        """
        try:
            audio_binary = b""
            
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    audio_binary += chunk
            
            if not audio_binary:
                return (self._create_audio_tensor_from_binary(b"", sample_rate), "", "流式输出中未获取到音频数据")
            
            # 创建音频tensor
            audio_data = self._create_audio_tensor_from_binary(audio_binary, sample_rate)
            
            # 构造生成信息
            generation_info = self._format_generation_info(resp.headers, len(audio_binary))
            
            return (audio_data, "", generation_info)
            
        except Exception as e:
            error_msg = f"流式响应解析失败: {e}"
            logger.error(error_msg)
            return (self._create_audio_tensor_from_binary(b"", sample_rate), "", error_msg)

    def _format_generation_info(self, headers, content_length):
        """
        格式化生成信息，包含响应头信息和内容长度
        """
        info_parts = []
        
        # 添加内容长度
        info_parts.append(f"音频大小: {content_length} 字节")
        
        # 添加响应头信息
        if "content-type" in headers:
            info_parts.append(f"内容类型: {headers['content-type']}")
        if "content-length" in headers:
            info_parts.append(f"响应长度: {headers['content-length']}")
        
        # 添加时间戳
        info_parts.append(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return " | ".join(info_parts) if info_parts else "无详细信息"

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Siliconflow_TTS_API": SiliconflowTTSAPI
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Siliconflow_TTS_API": "🦉Siliconflow TTS API节点"
}
