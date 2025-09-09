#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI自定义节点：Siliconflow 自定义音色列表获取节点
实现获取所有自定义音色的功能，专门针对Siliconflow TTS API。
输入参数：api_key（可选，从config.json读取）
输出：uri_list（自定义音色URI列表）
"""

import os
import json
import requests
import logging
import time

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
logger = setup_logger("SiliconflowVoiceURIList")

# 节点主类
class SiliconflowVoiceURIList:
    """
    ComfyUI自定义节点：Siliconflow 自定义音色列表获取节点
    实现获取所有自定义音色的功能，专门针对Siliconflow TTS API。
    输入参数：api_key（可选，从config.json读取）
    输出：uri_list（自定义音色URI列表）
    """
    
    def __init__(self):
        # 读取配置文件，专门读取TTS.siliconflow_tts配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.config = config.get('TTS', {}).get('siliconflow_tts', {})
        except Exception as e:
            logger.warning(f"读取配置文件失败: {e}")
            self.config = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {
                    "default": "", 
                    "multiline": False,
                    "tooltip": "Siliconflow API Key（留空则从config.json读取）"
                }),
            },
            "optional": {
                "force_refresh": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "强制刷新音色列表（忽略缓存）"
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("uri_list",)
    FUNCTION = "get_voice_list"
    CATEGORY = "🦉FreeAPI/Siliconflow"

    def get_voice_list(self, api_key="", force_refresh=False):
        """
        主方法：获取自定义音色列表
        1. 验证API Key
        2. 调用Siliconflow API获取音色列表
        3. 解析响应，返回URI列表
        """
        # 获取API Key
        if not api_key.strip():
            api_key = self.config.get('api_key', '')
            if not api_key:
                logger.error("未配置Siliconflow TTS API Key")
                return ("错误：未配置Siliconflow TTS API Key，请在config.json中设置siliconflow_tts.api_key或在节点中输入",)
        else:
            api_key = api_key.strip()
            logger.info("使用节点输入的API Key")
        
        # 获取base_url
        base_url = self.config.get('base_url', 'https://api.siliconflow.cn/v1')
        
        # 构造API请求
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            voice_list_url = f"{base_url}/audio/voice/list"
            
            logger.info(f"发送获取音色列表请求到: {voice_list_url}")
            logger.info(f"强制刷新: {force_refresh}")
            
            # 发送GET请求
            resp = requests.get(voice_list_url, headers=headers, timeout=60)
            
            if resp.status_code != 200:
                error_msg = f"API请求失败，状态码: {resp.status_code}, 响应: {resp.text}"
                logger.error(error_msg)
                return (error_msg,)
            
            # 解析响应
            try:
                response_data = resp.json()
                
                # 记录响应摘要（避免日志过长）
                response_summary = {
                    "status": "success",
                    "has_results": "results" in response_data or "result" in response_data,
                    "results_count": len(response_data.get('results', []) or response_data.get('result', [])),
                    "response_keys": list(response_data.keys())
                }
                logger.info(f"收到音色列表响应摘要: {json.dumps(response_summary, ensure_ascii=False)}")
                
                # 提取音色列表 - 支持多种可能的字段名
                results = response_data.get('results', []) or response_data.get('result', [])
                if not results:
                    logger.info("未找到任何自定义音色")
                    return ("未找到任何自定义音色",)
                
                logger.info(f"找到 {len(results)} 个自定义音色")
                
                # 去重和排序处理
                unique_voices = self._deduplicate_and_sort_voices(results)
                logger.info(f"去重后剩余 {len(unique_voices)} 个唯一音色")
                
                # 格式化音色列表
                voice_list = self._format_voice_list(unique_voices)
                
                logger.info(f"音色列表格式化完成，长度: {len(voice_list)} 字符")
                return (voice_list,)
                
            except json.JSONDecodeError as e:
                error_msg = f"响应JSON解析失败: {e}, 原始响应: {resp.text[:200]}..."
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

    def _deduplicate_and_sort_voices(self, voices):
        """
        去重和排序音色列表
        优先保留最新的URI（URI中包含时间戳信息）
        """
        try:
            # 按名称分组
            voice_groups = {}
            for voice in voices:
                custom_name = voice.get('customName', '')
                if not custom_name:
                    continue
                
                if custom_name not in voice_groups:
                    voice_groups[custom_name] = []
                voice_groups[custom_name].append(voice)
            
            # 从每组中选择最新的音色（基于URI中的时间戳）
            unique_voices = []
            for custom_name, group in voice_groups.items():
                if len(group) == 1:
                    unique_voices.append(group[0])
                else:
                    # 多个同名音色，选择最新的
                    latest_voice = max(group, key=lambda x: x.get('uri', ''))
                    unique_voices.append(latest_voice)
                    logger.info(f"音色 '{custom_name}' 有 {len(group)} 个版本，选择最新版本")
            
            # 按名称排序
            unique_voices.sort(key=lambda x: x.get('customName', ''))
            
            return unique_voices
            
        except Exception as e:
            logger.error(f"音色去重排序失败: {e}")
            return voices

    def _format_voice_list(self, results):
        """
        格式化音色列表，生成易读的文本格式
        """
        try:
            formatted_list = []
            formatted_list.append("🎵 Siliconflow 自定义音色列表")
            formatted_list.append("=" * 50)
            formatted_list.append(f"总计: {len(results)} 个音色")
            formatted_list.append("")
            
            # 按模型分组显示
            model_groups = {}
            for voice in results:
                model = voice.get('model', '未知模型')
                if model not in model_groups:
                    model_groups[model] = []
                model_groups[model].append(voice)
            
            for model, voices in sorted(model_groups.items()):
                formatted_list.append(f"🔧 模型: {model}")
                formatted_list.append(f"   音色数量: {len(voices)} 个")
                formatted_list.append("")
                
                for i, voice in enumerate(voices, 1):
                    # 基本信息
                    formatted_list.append(f"🎭 音色 {i}:")
                    formatted_list.append(f"   名称: {voice.get('customName', '未知')}")
                    formatted_list.append(f"   URI: {voice.get('uri', '未知')}")
                    
                    # 文本内容（截断显示）
                    text = voice.get('text', '')
                    if text:
                        if len(text) > 80:  # 缩短显示长度
                            text = text[:80] + "..."
                        formatted_list.append(f"   文本: {text}")
                    
                    formatted_list.append("")
                
                formatted_list.append("-" * 30)
                formatted_list.append("")
            
            # 添加使用说明
            formatted_list.append("📝 使用说明:")
            formatted_list.append("• 复制上述URI到TTS节点的voice参数中")
            formatted_list.append("• 支持在TTS节点中使用自定义音色")
            formatted_list.append("• 音色名称建议使用有意义的描述")
            formatted_list.append("• 同名音色已自动选择最新版本")
            
            return "\n".join(formatted_list)
            
        except Exception as e:
            logger.error(f"格式化音色列表失败: {e}")
            # 返回简单的JSON格式作为fallback
            return json.dumps(results, ensure_ascii=False, indent=2)

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Siliconflow_Voice_URI_List": SiliconflowVoiceURIList
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Siliconflow_Voice_URI_List": "🦉Siliconflow 自定义音色列表"
}
