import os
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenCheckTaskAPI")

# 节点主类
class QwenCheckTaskAPI:
    """
    ComfyUI自定义节点：Qwen Check Task API
    专门用于查询Qwen任务状态，适用于处理超时或需要手动查询的情况
    输入参数：task_id
    输出：generation_info（任务状态和详细信息）
    """
    def __init__(self):
        # 读取配置文件，获取API密钥
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 从VIDEO.qwen_video配置中获取API密钥
                self.config = config.get('VIDEO', {}).get('qwen_video', {})
        except Exception as e:
            logger.error(f"配置文件读取失败: {e}")
            self.config = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {
                    "multiline": False, 
                    "default": "", 
                    "tooltip": "输入要查询的任务ID，可从之前的视频生成任务中获取"
                }),
            },
            "optional": {
                "auto_refresh": ("BOOLEAN", {
                    "default": False, 
                    "tooltip": "是否自动刷新（仅在任务进行中时生效）"
                }),
                "refresh_interval": ("INT", {
                    "default": 5, 
                    "min": 1, 
                    "max": 60, 
                    "step": 1, 
                    "tooltip": "自动刷新间隔（秒），仅在开启自动刷新时有效"
                }),
                "max_refresh_count": ("INT", {
                    "default": 10, 
                    "min": 1, 
                    "max": 100, 
                    "step": 1, 
                    "tooltip": "最大刷新次数，避免无限等待"
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("generation_info",)
    FUNCTION = "check_task_status"
    CATEGORY = "🦉FreeAPI/Qwen"

    def check_task_status(self, task_id, auto_refresh=False, refresh_interval=5, max_refresh_count=10):
        """
        查询任务状态的主方法
        
        Args:
            task_id: 要查询的任务ID
            auto_refresh: 是否自动刷新（仅在任务进行中时）
            refresh_interval: 自动刷新间隔（秒）
            max_refresh_count: 最大刷新次数
        """
        logger.info(f"开始查询任务状态...")
        logger.info(f"任务ID: {task_id}")
        logger.info(f"自动刷新: {'开启' if auto_refresh else '关闭'}")
        
        # 验证输入
        if not task_id or not task_id.strip():
            error_info = "❌ 错误: 任务ID不能为空\n请输入有效的任务ID"
            logger.error("任务ID为空")
            return (error_info,)
        
        task_id = task_id.strip()
        
        # 读取API配置
        api_key = self.config.get('api_key', '')
        if not api_key:
            error_info = "❌ 错误: 未配置Qwen API Key\n请在config.json中配置VIDEO.qwen_video.api_key"
            logger.error("未配置Qwen API Key")
            return (error_info,)
        
        # 查询任务状态
        try:
            refresh_count = 0
            
            while refresh_count <= max_refresh_count:
                result_info = self._query_single_task(task_id, api_key)
                
                if not auto_refresh or refresh_count >= max_refresh_count:
                    # 不需要自动刷新或已达到最大次数，直接返回结果
                    return (result_info,)
                
                # 解析任务状态，判断是否需要继续刷新
                task_status = self._extract_task_status(result_info)
                
                if task_status in ["SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"]:
                    # 任务已完成（成功、失败、取消或未知），不需要继续刷新
                    logger.info(f"✅ 任务已完成，状态: {task_status}")
                    return (result_info,)
                
                elif task_status in ["PENDING", "RUNNING"]:
                    # 任务还在进行中，继续刷新
                    refresh_count += 1
                    if refresh_count <= max_refresh_count:
                        logger.info(f"⏳ 任务进行中，{refresh_interval}秒后第{refresh_count}次刷新...")
                        time.sleep(refresh_interval)
                        continue
                    else:
                        # 达到最大刷新次数
                        final_info = result_info + f"\n\n⚠️ 已达到最大刷新次数 ({max_refresh_count})\n任务可能仍在进行中，请稍后手动查询"
                        return (final_info,)
                else:
                    # 未知状态，直接返回
                    return (result_info,)
            
            return (result_info,)
            
        except Exception as e:
            error_info = f"❌ 查询任务状态失败\n错误类型: {type(e).__name__}\n错误详情: {str(e)}\n任务ID: {task_id}"
            logger.error(f"查询任务状态失败: {e}")
            return (error_info,)

    def _query_single_task(self, task_id, api_key):
        """
        执行单次任务状态查询
        """
        query_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        logger.info(f"🔍 查询URL: {query_url}")
        
        try:
            # 发送查询请求
            response = requests.get(query_url, headers=headers, timeout=30)
            
            logger.info(f"🔍 响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"❌ 响应内容: {response.text}")
                
                # 处理常见的HTTP错误
                if response.status_code == 404:
                    return f"❌ 任务不存在\n任务ID: {task_id}\n错误: 找不到指定的任务，请检查任务ID是否正确"
                elif response.status_code == 401:
                    return f"❌ 认证失败\n任务ID: {task_id}\n错误: API密钥无效或已过期"
                elif response.status_code == 403:
                    return f"❌ 权限不足\n任务ID: {task_id}\n错误: 没有权限访问该任务"
                else:
                    return f"❌ 查询失败\n任务ID: {task_id}\nHTTP状态码: {response.status_code}\n响应内容: {response.text}"
            
            response.raise_for_status()
            result_data = response.json()
            
            # 解析并格式化结果
            return self._format_task_info(task_id, result_data)
            
        except requests.exceptions.Timeout:
            return f"❌ 查询超时\n任务ID: {task_id}\n错误: 请求超时，请检查网络连接或稍后重试"
        except requests.exceptions.ConnectionError:
            return f"❌ 连接失败\n任务ID: {task_id}\n错误: 无法连接到服务器，请检查网络连接"
        except requests.exceptions.RequestException as e:
            return f"❌ 请求失败\n任务ID: {task_id}\n错误类型: {type(e).__name__}\n错误详情: {str(e)}"
        except json.JSONDecodeError:
            return f"❌ 响应解析失败\n任务ID: {task_id}\n错误: 服务器返回的数据格式错误"
        except Exception as e:
            return f"❌ 未知错误\n任务ID: {task_id}\n错误类型: {type(e).__name__}\n错误详情: {str(e)}"

    def _format_task_info(self, task_id, result_data):
        """
        格式化任务信息为可读字符串
        """
        try:
            output = result_data.get("output", {})
            usage = result_data.get("usage", {})
            request_id = result_data.get("request_id", "未知")
            
            # 获取任务状态
            task_status = output.get("task_status", "UNKNOWN")
            
            # 状态信息映射
            status_map = {
                "PENDING": "⏳ 任务排队中",
                "RUNNING": "🔄 任务处理中", 
                "SUCCEEDED": "✅ 任务执行成功",
                "FAILED": "❌ 任务执行失败",
                "CANCELED": "⚠️ 任务取消成功",
                "UNKNOWN": "❓ 任务不存在或状态未知"
            }
            
            status_display = status_map.get(task_status, f"❓ 未知状态: {task_status}")
            
            # 构建信息列表
            info_lines = [
                status_display,
                f"任务ID: {task_id}",
                f"请求ID: {request_id}",
                ""
            ]
            
            # 添加时间信息
            submit_time = output.get("submit_time", "未知")
            scheduled_time = output.get("scheduled_time", "未知")
            end_time = output.get("end_time", "未知")
            
            info_lines.extend([
                "⏰ 时间信息:",
                f"提交时间: {submit_time}",
                f"开始时间: {scheduled_time}",
                f"完成时间: {end_time if end_time != '未知' else '尚未完成'}",
                ""
            ])
            
            # 根据任务状态添加相应信息
            if task_status == "SUCCEEDED":
                # 成功状态：添加结果信息
                video_url = output.get("video_url", "未知")
                orig_prompt = output.get("orig_prompt", "未知")
                actual_prompt = output.get("actual_prompt", "未知")
                
                info_lines.extend([
                    "🎬 生成结果:",
                    f"视频URL: {video_url}",
                    "",
                    "📝 提示词信息:",
                    f"原始提示词: {orig_prompt}",
                ])
                
                # 如果有智能改写后的提示词
                if actual_prompt and actual_prompt != orig_prompt and actual_prompt != "未知":
                    info_lines.extend([
                        f"智能改写后: {actual_prompt}",
                    ])
                
                info_lines.append("")
                
                # 添加用量信息
                if usage:
                    video_duration = usage.get("video_duration", "未知")
                    video_ratio = usage.get("video_ratio", "未知") 
                    video_count = usage.get("video_count", "未知")
                    
                    info_lines.extend([
                        "📊 视频规格:",
                        f"时长: {video_duration}秒",
                        f"分辨率: {video_ratio}",
                        f"生成数量: {video_count}个",
                        ""
                    ])
                
            elif task_status == "FAILED":
                # 失败状态：添加错误信息
                error_code = output.get("code", "未知")
                error_message = output.get("message", "未知")
                
                info_lines.extend([
                    "🔍 错误信息:",
                    f"错误代码: {error_code}",
                    f"错误详情: {error_message}",
                    ""
                ])
                
            elif task_status in ["PENDING", "RUNNING"]:
                # 进行中状态：添加等待提示
                info_lines.extend([
                    "💡 提示:",
                    "任务正在处理中，请耐心等待",
                    "可以开启自动刷新功能定期查询状态",
                    "视频生成通常需要2-5分钟",
                    ""
                ])
            
            # 添加任务统计信息（如果有）
            task_metrics = output.get("task_metrics", {})
            if task_metrics:
                info_lines.extend([
                    "📈 任务统计:",
                    f"总数: {task_metrics.get('TOTAL', 0)}",
                    f"成功: {task_metrics.get('SUCCEEDED', 0)}",
                    f"失败: {task_metrics.get('FAILED', 0)}",
                    ""
                ])
            
            return "\n".join(info_lines)
            
        except Exception as e:
            logger.error(f"格式化任务信息失败: {e}")
            return f"任务ID: {task_id}\n查询成功，但无法解析详细信息\n原始响应: {result_data}\n解析错误: {str(e)}"

    def _extract_task_status(self, info_text):
        """
        从信息文本中提取任务状态，用于判断是否需要继续刷新
        """
        try:
            if "任务排队中" in info_text or "PENDING" in info_text:
                return "PENDING"
            elif "任务处理中" in info_text or "RUNNING" in info_text:
                return "RUNNING"
            elif "任务执行成功" in info_text or "SUCCEEDED" in info_text:
                return "SUCCEEDED"
            elif "任务执行失败" in info_text or "FAILED" in info_text:
                return "FAILED"
            elif "任务取消成功" in info_text or "CANCELED" in info_text:
                return "CANCELED"
            else:
                return "UNKNOWN"
        except:
            return "UNKNOWN"

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Qwen_Check_Task_API": QwenCheckTaskAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_Check_Task_API": "🦉Qwen任务状态查询节点"
} 