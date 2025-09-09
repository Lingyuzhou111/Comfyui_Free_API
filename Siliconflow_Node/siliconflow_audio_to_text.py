#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI自定义节点：Siliconflow 音频转文字节点
实现音频转录功能，专门针对Siliconflow Audio API，参数自动读取config.json。
输入参数：audio, model
输出：text（识别出的文字内容）
"""

import os
import json
import requests
import logging
import torch
import io
import tempfile

# 内嵌日志配置功能
def setup_logger(name):
    """
    简化版logger设置，类似basicConfig但支持环境变量
    """
    # 默认配置
    DEFAULT_LOG_LEVEL = 'INFO'
    DEFAULT_VERBOSE_LOGS = False
    
    # 获取环境变量配置
    log_level = os.getenv('SILICONFLOW_LOG_LEVEL', DEFAULT_LOG_LEVEL).upper()
    verbose_logs = os.getenv('SILICONFLOW_VERBOSE_LOGS', str(DEFAULT_VERBOSE_LOGS)).lower() == 'true'
    
    # 验证日志级别
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if log_level not in valid_levels:
        log_level = DEFAULT_LOG_LEVEL
    
    # 设置全局日志配置（类似basicConfig）
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 返回logger
    logger = logging.getLogger(name)
    
    # 存储verbose设置到logger对象中
    logger.verbose_enabled = verbose_logs
    
    return logger

def is_verbose_logging_enabled(logger=None):
    """
    检查是否启用详细日志
    """
    if logger and hasattr(logger, 'verbose_enabled'):
        return logger.verbose_enabled
    
    # 如果没有logger参数，直接检查环境变量
    DEFAULT_VERBOSE_LOGS = False
    return os.getenv('SILICONFLOW_VERBOSE_LOGS', str(DEFAULT_VERBOSE_LOGS)).lower() == 'true'

# 设置logger
logger = setup_logger("SiliconflowAudioToText")

# 节点主类
class SiliconflowAudioToText:
    """
    ComfyUI自定义节点：Siliconflow 音频转文字节点
    实现音频转录功能，专门针对Siliconflow Audio API，参数自动读取config.json。
    输入参数：audio, model
    输出：text（识别出的文字内容）
    """
    def __init__(self):
        # 读取配置文件，专门读取TTS.siliconflow_tts配置（复用API配置）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('TTS', {}).get('siliconflow_tts', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取Siliconflow TTS模型选项（复用模型配置）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            siliconflow_config = config.get('TTS', {}).get('siliconflow_tts', {})
        
        # 获取模型选项，如果没有配置则使用默认值
        model_options = siliconflow_config.get('model', ['FunAudioLLM/SenseVoiceSmall'])
        
        # 确保默认模型在选项中
        if 'FunAudioLLM/SenseVoiceSmall' not in model_options:
            model_options.insert(0, 'FunAudioLLM/SenseVoiceSmall')
        
        return {
            "required": {
                "audio": ("AUDIO", {"tooltip": "要转录的音频文件"}),
                "model": (model_options, {"default": "FunAudioLLM/SenseVoiceSmall", "tooltip": "音频转录模型选择"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "transcribe_audio"
    CATEGORY = "🦉FreeAPI/Siliconflow"

    def _audio_tensor_to_wav_file(self, audio_data: dict) -> str:
        """
        将ComfyUI的AUDIO格式转换为临时WAV文件
        返回临时文件路径
        """
        temp_file_path = ""
        try:
            waveform = audio_data.get("waveform")
            sample_rate = audio_data.get("sample_rate", 32000)
            
            if waveform is None:
                logger.error("音频数据中没有找到waveform")
                return ""
            
            # 确保波形格式正确 [1, C, T] -> [C, T]
            if waveform.dim() == 3:  # [1, C, T] -> [C, T]
                waveform = waveform.squeeze(0)
            
            # 转换为numpy数组
            if isinstance(waveform, torch.Tensor):
                waveform_np = waveform.numpy()
            else:
                waveform_np = waveform
            
            # 创建临时文件，使用更安全的命名方式
            temp_file = tempfile.NamedTemporaryFile(
                suffix='.wav', 
                prefix='siliconflow_audio_',
                delete=False,
                dir=tempfile.gettempdir()
            )
            temp_file_path = temp_file.name
            temp_file.close()
            
            # 使用torchaudio保存为WAV格式
            import torchaudio
            torchaudio.save(temp_file_path, torch.tensor(waveform_np), sample_rate, format="wav")
            
            logger.info(f"音频转换完成: 采样率={sample_rate}, 临时文件={temp_file_path}")
            
            return temp_file_path
            
        except Exception as e:
            logger.error(f"音频转换失败: {e}")
            # 如果创建失败，尝试清理已创建的临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            return ""

    def _safe_cleanup_temp_file(self, temp_file_path: str, max_retries: int = 3):
        """
        安全清理临时文件，支持重试机制
        """
        if not temp_file_path or not os.path.exists(temp_file_path):
            return
        
        for attempt in range(max_retries):
            try:
                os.unlink(temp_file_path)
                logger.info(f"临时文件清理成功 (尝试 {attempt + 1}): {temp_file_path}")
                return
            except PermissionError as e:
                if attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 0.2  # 递增等待时间
                    logger.info(f"文件被占用，等待 {wait_time:.1f}s 后重试 (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"临时文件清理失败，已达到最大重试次数: {temp_file_path}")
                    logger.warning(f"错误信息: {e}")
            except Exception as e:
                logger.warning(f"临时文件清理异常: {e}")
                break

    def transcribe_audio(self, audio, model):
        """
        主方法：音频转文字
        1. 验证输入参数
        2. 将音频转换为WAV文件
        3. 构造Siliconflow音频转录API请求
        4. 发送请求，返回识别出的文字
        """
        # 读取Siliconflow API参数
        base_url = self.config.get('base_url', 'https://api.siliconflow.cn/v1')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            logger.error("未配置Siliconflow API Key")
            return ("错误：未配置Siliconflow API Key，请在config.json中设置siliconflow_tts.api_key",)
        
        # 验证输入参数
        if not audio:
            logger.error("音频数据为空")
            return ("错误：音频数据不能为空",)
        
        # 将音频转换为WAV文件
        temp_wav_path = self._audio_tensor_to_wav_file(audio)
        if not temp_wav_path:
            logger.error("音频转换失败")
            return ("错误：音频转换失败，无法生成WAV文件",)
        
        # 构造Siliconflow音频转录API请求
        try:
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            transcription_url = f"{base_url}/audio/transcriptions"
            
            logger.info(f"发送音频转录请求到: {transcription_url}")
            logger.info(f"使用模型: {model}")
            
            # 使用with语句确保文件正确关闭
            with open(temp_wav_path, 'rb') as audio_file:
                # 准备multipart/form-data请求
                files = {
                    'file': ('audio.wav', audio_file, 'audio/wav')
                }
                
                data = {
                    'model': model
                }
                
                # 发送POST请求
                resp = requests.post(
                    transcription_url, 
                    headers=headers, 
                    files=files, 
                    data=data, 
                    timeout=180
                )
            
            # 使用安全清理方法
            self._safe_cleanup_temp_file(temp_wav_path)
            
            if resp.status_code != 200:
                error_msg = f"API请求失败，状态码: {resp.status_code}, 响应: {resp.text}"
                logger.error(error_msg)
                return (error_msg,)
            
            # 解析响应
            try:
                response_data = resp.json()
                logger.info(f"收到转录响应: {json.dumps(response_data, ensure_ascii=False)}")
                
                # 提取文字内容
                text = response_data.get('text', '')
                if not text:
                    logger.error("响应中没有找到text字段")
                    return ("错误：响应中没有找到text字段",)
                
                # 清理文字内容
                text = text.strip()
                if not text:
                    logger.error("转录的文字内容为空")
                    return ("错误：转录的文字内容为空",)
                
                logger.info(f"音频转录成功，识别文字: {text}")
                logger.info(f"文字长度: {len(text)} 字符")
                
                return (text,)
                
            except json.JSONDecodeError as e:
                error_msg = f"响应JSON解析失败: {e}, 原始响应: {resp.text}"
                logger.error(error_msg)
                return (error_msg,)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"API请求异常: {e}"
            logger.error(error_msg)
            # 确保异常情况下也清理临时文件
            if 'temp_wav_path' in locals():
                self._safe_cleanup_temp_file(temp_wav_path)
            return (error_msg,)
        except Exception as e:
            error_msg = f"处理失败: {e}"
            logger.error(error_msg)
            # 确保异常情况下也清理临时文件
            if 'temp_wav_path' in locals():
                self._safe_cleanup_temp_file(temp_wav_path)
            return (error_msg,)

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Siliconflow_Audio_To_Text": SiliconflowAudioToText
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Siliconflow_Audio_To_Text": "🦉Siliconflow 音频转文字节点"
}
