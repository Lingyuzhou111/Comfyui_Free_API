import os
import json
import requests
import time
import logging
import torch
import base64
import io

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
logger = setup_logger("SiliconflowAudioToURI")

# 节点主类
class SiliconflowAudioToURI:
    """
    ComfyUI自定义节点：Siliconflow 音频上传节点
    实现参考音频上传功能，专门针对Siliconflow TTS API，参数自动读取config.json。
    输入参数：audio, model, custom_name, text
    输出：uri（自定义音色的ID）
    """
    def __init__(self):
        # 读取配置文件，专门读取TTS.siliconflow_tts配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('TTS', {}).get('siliconflow_tts', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取Siliconflow TTS模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            siliconflow_config = config.get('TTS', {}).get('siliconflow_tts', {})
        model_options = siliconflow_config.get('model', ['FunAudioLLM/CosyVoice2-0.5B'])
        
        return {
            "required": {
                "audio": ("AUDIO", {"tooltip": "要上传的参考音频"}),
                "model": (model_options, {"default": model_options[0], "tooltip": "TTS模型选择"}),
                "custom_name": ("STRING", {"default": "Siliconflow_voice_v1", "tooltip": "用户自定义的音色名称"}),
                "text": ("STRING", {"multiline": True, "default": "在一无所知中, 梦里的一天结束了，一个新的轮回便会开始", "tooltip": "参考音频对应的文字内容"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("uri",)
    FUNCTION = "upload_audio"
    CATEGORY = "🦉FreeAPI/Siliconflow"

    def _audio_tensor_to_base64(self, audio_data: dict) -> str:
        """
        将ComfyUI的AUDIO格式转换为base64编码的音频数据
        返回格式：data:audio/mpeg;base64,{base64_string}
        """
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
            
            # 将音频数据转换为WAV格式的字节流
            audio_bytes = io.BytesIO()
            
            # 使用torchaudio保存为WAV格式
            import torchaudio
            torchaudio.save(audio_bytes, torch.tensor(waveform_np), sample_rate, format="wav")
            audio_bytes.seek(0)
            
            # 读取字节数据并转换为base64
            audio_data_bytes = audio_bytes.read()
            base64_string = base64.b64encode(audio_data_bytes).decode('utf-8')
            
            # 构造完整的data URI
            data_uri = f"data:audio/wav;base64,{base64_string}"
            
            # 简化模式：默认显示基本信息
            logger.info(f"音频转换完成: 采样率={sample_rate}, 数据大小={len(base64_string)} 字符")
            
            # 只有在明确启用详细日志时才显示base64相关信息
            if is_verbose_logging_enabled():
                logger.debug(f"详细音频信息: base64数据大小={len(base64_string)} 字符")
            
            return data_uri
            
        except Exception as e:
            logger.error(f"音频转换失败: {e}")
            return ""

    def upload_audio(self, audio, model, custom_name, text):
        """
        主方法：上传参考音频
        1. 验证输入参数
        2. 将音频转换为base64格式
        3. 构造Siliconflow音频上传API请求
        4. 发送请求，返回自定义音色的URI
        """
        # 读取Siliconflow TTS API参数
        base_url = self.config.get('base_url', 'https://api.siliconflow.cn/v1')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            logger.error("未配置Siliconflow TTS API Key")
            return ("错误：未配置Siliconflow TTS API Key，请在config.json中设置siliconflow_tts.api_key",)
        
        # 验证输入参数
        if not audio:
            logger.error("音频数据为空")
            return ("错误：音频数据不能为空",)
        
        if not custom_name or not custom_name.strip():
            logger.error("自定义音色名称为空")
            return ("错误：自定义音色名称不能为空",)
        
        if not text or not text.strip():
            logger.error("参考音频文字内容为空")
            return ("错误：参考音频的文字内容不能为空",)
        
        # 检查文本长度
        if len(text) > 1000:  # 保守估计，避免超出限制
            logger.error(f"文字内容过长: {len(text)} 字符")
            return (f"错误：文字内容过长，当前长度{len(text)}字符，建议控制在1000字符以内",)
        
        # 将音频转换为base64格式
        audio_base64 = self._audio_tensor_to_base64(audio)
        if not audio_base64:
            logger.error("音频转换失败")
            return ("错误：音频转换失败，无法生成base64编码",)
        
        # 构造Siliconflow音频上传API请求
        payload = {
            "model": model,
            "customName": custom_name.strip(),
            "audio": audio_base64,
            "text": text.strip()
        }
        
        # 发送请求
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            upload_url = f"{base_url}/uploads/audio/voice"
            
            logger.info(f"发送音频上传请求到: {upload_url}")
            
            # 简化模式：避免base64字符串刷屏（默认行为）
            log_payload = {
                "model": payload["model"],
                "customName": payload["customName"],
                "audio": f"data:audio/wav;base64,<{len(audio_base64.split(',')[1]) if ',' in audio_base64 else 0} bytes>",
                "text": payload["text"][:100] + "..." if len(payload["text"]) > 100 else payload["text"]
            }
            logger.info(f"请求参数: {json.dumps(log_payload, ensure_ascii=False)}")
            
            # 只有在明确启用详细日志时才显示完整数据
            if is_verbose_logging_enabled():
                logger.debug(f"详细请求参数: {json.dumps(payload, ensure_ascii=False)}")
            
            resp = requests.post(upload_url, headers=headers, json=payload, timeout=180)
            
            if resp.status_code != 200:
                error_msg = f"API请求失败，状态码: {resp.status_code}, 响应: {resp.text}"
                logger.error(error_msg)
                return (error_msg,)
            
            # 解析响应
            try:
                response_data = resp.json()
                logger.info(f"收到上传响应: {json.dumps(response_data, ensure_ascii=False)}")
                
                # 提取URI
                uri = response_data.get('uri', '')
                if not uri:
                    logger.error("响应中没有找到URI字段")
                    return ("错误：响应中没有找到URI字段",)
                
                # 确保URI是字符串类型
                if not isinstance(uri, str):
                    logger.error(f"URI类型错误: {type(uri)}, 值: {uri}")
                    uri = str(uri)
                
                # 清理URI字符串
                uri = uri.strip()
                if not uri:
                    logger.error("清理后的URI为空")
                    return ("错误：生成的URI为空",)
                
                logger.info(f"音频上传成功，获得URI: {uri}")
                logger.info(f"URI长度: {len(uri)} 字符")
                logger.info(f"URI内容验证: {repr(uri)}")
                logger.info(f"URI字节表示: {uri.encode('utf-8')}")
                
                # 验证URI格式
                if not uri.startswith('speech:'):
                    logger.warning(f"URI格式可能不正确: {uri}")
                
                # 返回完整的URI字符串
                logger.info(f"准备返回URI: {repr(uri)}")
                return (uri,)
                
            except json.JSONDecodeError as e:
                error_msg = f"响应JSON解析失败: {e}, 原始响应: {resp.text}"
                logger.error(error_msg)
                return (error_msg,)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"API请求异常: {e}"
            logger.error(error_msg)
            return (error_msg,)
        except Exception as e:
            error_msg = f"处理失败: {e}"
            logger.error(error_msg)
            return (error_msg,)

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Siliconflow_Audio_To_URI": SiliconflowAudioToURI
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Siliconflow_Audio_To_URI": "🦉Siliconflow 音频上传节点"
}
