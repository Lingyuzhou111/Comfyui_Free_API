import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenVideoAPI")

# 节点主类
class QwenVideoAPI:
    """
    ComfyUI自定义节点：Qwen Video API
    实现视频生成API调用，支持文生视频、图生视频和首尾帧生视频功能，参数自动读取config.json。
    输入参数：model, resolution, ratio, prompt, prompt_extend, seed(可选), duration(可选), watermark(可选), first_frame_image(可选), last_frame_image(可选)
    输出：video_url（生成的视频URL）
    """
    def __init__(self):
        # 读取配置文件，专门读取VIDEO.qwen_video配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.config = config.get('VIDEO', {}).get('qwen_video', {})
        except Exception as e:
            logger.error(f"配置文件读取失败: {e}")
            self.config = {}

    @classmethod
    def INPUT_TYPES(cls):
        # 定义支持的模型选项（从config.json读取）
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                models = config.get('VIDEO', {}).get('qwen_video', {}).get('model', [])
        except:
            models = ["wan2.2-t2v-plus", "wan2.2-i2v-plus", "wanx2.1-i2v-turbo", "wanx2.1-kf2v-plus"]
        
        # 定义支持的分辨率选项
        resolution_options = ["480P", "720P", "1080P"]
        
        # 定义支持的宽高比选项
        ratio_options = ["16:9", "9:16", "4:3", "3:4", "1:1"]
        
        return {
            "required": {
                "model": (models, {"default": models[0] if models else "wan2.2-t2v-plus", "tooltip": "选择视频生成模型"}),
                "resolution": (resolution_options, {"default": "720P", "tooltip": "视频分辨率档位（wanx2.1-i2v-turbo仅支持480P和720P）"}),
                "ratio": (ratio_options, {"default": "16:9", "tooltip": "视频宽高比"}),
                "prompt": ("STRING", {"multiline": True, "default": "一只小猫在月光下奔跑", "tooltip": "文本提示词，描述想要生成的视频内容"}),
                "prompt_extend": ("BOOLEAN", {"default": True, "tooltip": "是否开启智能改写，对短提示词效果提升明显"}),
            },
            "optional": {
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1, "tooltip": "随机种子，-1为随机生成，相同种子可产生相似结果"}),
                "duration": ("INT", {"default": 5, "min": 5, "max": 5, "step": 1, "tooltip": "视频时长（秒），当前固定为5秒"}),
                "watermark": ("BOOLEAN", {"default": False, "tooltip": "是否添加水印标识"}),
                "first_frame_image": ("IMAGE", {"tooltip": "首帧图像，用于图生视频和首尾帧生视频"}),
                "last_frame_image": ("IMAGE", {"tooltip": "末帧图像，用于首尾帧生视频（需要同时提供首帧图像）"}),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING",)
    RETURN_NAMES = ("video", "video_url", "generation_info",)
    FUNCTION = "generate_video"
    CATEGORY = "API/Qwen"

    def generate_video(self, model, resolution, ratio, prompt, prompt_extend, seed=None, duration=5, watermark=False, first_frame_image=None, last_frame_image=None):
        """
        主生成方法：
        1. 根据模型类型选择对应的API URL
        2. 构造Qwen Video API请求，包含所有必要参数
        3. 发送请求，返回生成的视频URL
        
        Args:
            model: 选择的模型
            resolution: 视频分辨率档位
            ratio: 视频宽高比
            prompt: 文本提示词
            prompt_extend: 是否开启智能改写
            seed: 随机种子(可选)
            duration: 视频时长(可选)
            watermark: 是否添加水印(可选)
            first_frame_image: 首帧图像(可选)
            last_frame_image: 末帧图像(可选)
        """
        logger.info(f"[QwenVideoAPI] 开始视频生成...")
        logger.info(f"[QwenVideoAPI] 模型: {model}")
        logger.info(f"[QwenVideoAPI] 分辨率: {resolution}")
        logger.info(f"[QwenVideoAPI] 宽高比: {ratio}")
        logger.info(f"[QwenVideoAPI] 提示词: {prompt}")
        logger.info(f"[QwenVideoAPI] 智能改写: {'开启' if prompt_extend else '关闭'}")
        
        # 读取Qwen API参数
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            logger.error("未配置Qwen API Key")
            return (None, "API Key未配置", "错误: 未在config.json中配置Qwen API Key")
        
        # 根据模型选择API URL
        if model == "wan2.2-t2v-plus":
            # 文生视频
            base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis')
            video_type = "text_to_video"
        elif model == "wan2.2-i2v-plus" or model == "wanx2.1-i2v-turbo":
            # 图生视频（支持两个模型）
            base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis')
            video_type = "image_to_video"
        elif model == "wanx2.1-kf2v-plus":
            # 首尾帧生视频
            base_url = self.config.get('kf2v_base_url', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/image2video/video-synthesis')
            video_type = "keyframe_to_video"
        else:
            logger.error(f"不支持的模型: {model}")
            return (None, "不支持的模型", f"错误: 不支持的模型 '{model}'，支持的模型: wan2.2-t2v-plus, wan2.2-i2v-plus, wanx2.1-i2v-turbo, wanx2.1-kf2v-plus")
        
        # 转换分辨率和宽高比为具体尺寸
        size = self._get_video_size(resolution, ratio, model)
        if not size:
            logger.error(f"不支持的分辨率或宽高比组合: {resolution} {ratio}")
            return (None, "不支持的分辨率或宽高比组合", f"错误: 不支持的分辨率或宽高比组合 '{resolution} {ratio}'，请检查模型支持的分辨率规格")
        
        # 1. 构造API请求
        payload = {
            "model": model,
            "input": {
                "prompt": prompt
            },
            "parameters": {
                "size": size,
                "duration": duration,
                "prompt_extend": prompt_extend,
                "watermark": watermark
            }
        }
        
        # 根据视频类型添加特定参数
        if video_type == "image_to_video":
            # 图生视频：需要首帧图像
            if first_frame_image is None:
                logger.error("图生视频模式需要提供首帧图像")
                return (None, "图生视频模式需要提供首帧图像", f"错误: 模型 '{model}' 是图生视频模式，必须提供first_frame_image参数")
            
            try:
                first_frame_url = self._image_to_base64_url(first_frame_image)
                payload["input"]["img_url"] = first_frame_url
            except Exception as e:
                logger.error(f"首帧图像处理失败: {e}")
                return (None, "首帧图像处理失败", f"错误: 首帧图像处理失败 - {str(e)}")
        
        elif video_type == "keyframe_to_video":
            # 首尾帧生视频：需要首帧和末帧图像
            if first_frame_image is None or last_frame_image is None:
                logger.error("首尾帧生视频模式需要同时提供首帧和末帧图像")
                return (None, "首尾帧生视频模式需要同时提供首帧和末帧图像", f"错误: 模型 '{model}' 是首尾帧生视频模式，必须同时提供first_frame_image和last_frame_image参数")
            
            try:
                first_frame_url = self._image_to_base64_url(first_frame_image)
                last_frame_url = self._image_to_base64_url(last_frame_image)
                payload["input"]["first_frame_url"] = first_frame_url
                payload["input"]["last_frame_url"] = last_frame_url
            except Exception as e:
                logger.error(f"帧图像处理失败: {e}")
                return (None, "帧图像处理失败", f"错误: 首尾帧图像处理失败 - {str(e)}")
        
        # 添加可选参数
        if seed is not None and seed != -1:
            payload["parameters"]["seed"] = seed
            logger.info(f"[QwenVideoAPI] 随机种子: {seed}")
        
        # 2. 发送请求
        try:
            headers = {
                "X-DashScope-Async": "enable",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 打印调试信息
            logger.info(f"[QwenVideoAPI] 🔍 请求URL: {base_url}")
            
            # 创建用于日志的payload副本，简化base64编码显示
            log_payload = self._simplify_payload_for_log(payload)
            logger.info(f"[QwenVideoAPI] 🔍 请求体: {json.dumps(log_payload, ensure_ascii=False, indent=2)}")
            
            # 提交任务
            resp = requests.post(base_url, headers=headers, json=payload, timeout=180)
            
            # 打印响应信息
            logger.info(f"[QwenVideoAPI] 🔍 响应状态码: {resp.status_code}")
            
            if resp.status_code != 200:
                logger.error(f"❌ 响应内容: {resp.text}")
            
            resp.raise_for_status()
            task_data = resp.json()
            
            # 获取任务ID
            task_id = task_data.get("output", {}).get("task_id")
            if not task_id:
                logger.error("❌ 未获取到任务ID")
                return (None, "任务提交失败", f"错误: API响应中未获取到任务ID，响应内容: {task_data}")
            
            logger.info(f"[QwenVideoAPI] ✅ 任务提交成功，任务ID: {task_id}")
            
            # 轮询任务结果
            return self._poll_task_result(task_id, api_key)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API请求失败: {e}")
            error_info = f"API请求失败\n错误类型: {type(e).__name__}\n错误详情: {str(e)}\n请检查网络连接和API配置"
            return (None, f"API请求失败: {str(e)}", error_info)
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}")
            error_info = f"处理失败\n错误类型: {type(e).__name__}\n错误详情: {str(e)}"
            return (None, f"处理失败: {str(e)}", error_info)

    def _get_video_size(self, resolution, ratio, model):
        """
        根据分辨率档位和宽高比获取具体的视频尺寸
        """
        # 首尾帧生视频模型仅支持720P
        if model == "wanx2.1-kf2v-plus":
            logger.info("[QwenVideoAPI] 首尾帧生视频模型使用720P分辨率")
            return "1280*720"  # 固定720P分辨率
        
        # wanx2.1-i2v-turbo模型仅支持480P和720P
        if model == "wanx2.1-i2v-turbo":
            if resolution == "1080P":
                logger.error("[QwenVideoAPI] wanx2.1-i2v-turbo模型不支持1080P分辨率，仅支持480P和720P")
                return None
            logger.info(f"[QwenVideoAPI] wanx2.1-i2v-turbo模型使用{resolution}分辨率")
        
        # 480P档位的分辨率映射
        if resolution == "480P":
            size_map = {
                "16:9": "832*480",
                "9:16": "480*832",
                "1:1": "624*624"
            }
            return size_map.get(ratio)
        
        # 720P档位的分辨率映射
        elif resolution == "720P":
            size_map = {
                "16:9": "1280*720",
                "9:16": "720*1280",
                "1:1": "960*960",
                "4:3": "960*720",
                "3:4": "720*960"
            }
            return size_map.get(ratio)
        
        # 1080P档位的分辨率映射
        elif resolution == "1080P":
            size_map = {
                "16:9": "1920*1080",
                "9:16": "1080*1920",
                "1:1": "1440*1440",
                "4:3": "1632*1248",
                "3:4": "1248*1632"
            }
            return size_map.get(ratio)
        
        return None

    def _image_to_base64_url(self, image):
        """
        将ComfyUI的IMAGE转换为base64 URL格式
        """
        try:
            # ComfyUI的IMAGE是torch.Tensor，需要转换为PIL Image
            if hasattr(image, 'cpu'):  # 是torch.Tensor
                import torch
                if image.dim() == 4:  # batch维度，取第一张
                    image = image[0]
                
                # 转换为numpy数组
                image_np = image.cpu().numpy()
                
                # 根据图像格式进行不同的处理
                if len(image_np.shape) == 3:
                    if image_np.shape[0] == 3:  # (C,H,W)格式
                        # 转换为(H,W,C)格式
                        image_np = image_np.transpose(1, 2, 0)
                    elif image_np.shape[2] != 3:  # 不是(H,W,C)格式
                        raise ValueError(f"输入图像必须是3通道RGB图像，当前shape={image_np.shape}")
                else:
                    raise ValueError(f"输入图像必须是3维数组，当前shape={image_np.shape}")
                
                # 确保值在0-255范围内
                if image_np.max() <= 1.0:  # 如果是0-1范围
                    image_np = (image_np * 255).clip(0, 255).astype('uint8')
                else:  # 如果已经是0-255范围
                    image_np = image_np.clip(0, 255).astype('uint8')
                
                # 创建PIL图像
                img = Image.fromarray(image_np, mode='RGB')
            else:
                # 如果不是tensor，直接使用
                img = image
                # 确保是RGB格式
                if img.mode != 'RGB':
                    img = img.convert('RGB')
            
            # 保存为JPEG格式
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=95)
            image_data_bytes_jpeg = output_buffer.getvalue()
            image_base64 = base64.b64encode(image_data_bytes_jpeg).decode('utf-8')
            return f"data:image/jpeg;base64,{image_base64}"
            
        except Exception as e:
            logger.error(f"图像转换失败: {e}")
            raise

    def _poll_task_result(self, task_id, api_key, max_retries=120, retry_interval=5):
        """
        轮询任务结果，获取生成的视频URL
        """
        poll_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        for attempt in range(max_retries):
            try:
                resp = requests.get(poll_url, headers=headers, timeout=30)
                resp.raise_for_status()
                result_data = resp.json()
                
                task_status = result_data.get("output", {}).get("task_status")
                
                if task_status == "SUCCEEDED":
                    # 任务成功，获取结果视频URL
                    video_url = result_data.get("output", {}).get("video_url")
                    if video_url:
                        logger.info("[QwenVideoAPI] ✅ 任务成功，视频生成完成")
                        logger.info(f"[QwenVideoAPI] 🎬 视频URL: {video_url}")
                        
                        # 提取生成信息
                        generation_info = self._extract_generation_info(task_id, result_data)
                        
                        # 下载并转换视频为ComfyUI格式
                        video_object = self._download_and_convert_video(video_url)
                        
                        return (video_object, video_url, generation_info)
                    else:
                        logger.error("❌ 视频URL为空")
                        return (None, "视频URL为空", "任务成功但视频URL为空")
                
                elif task_status == "FAILED":
                    logger.error("❌ 任务执行失败")
                    failure_info = self._extract_failure_info(task_id, result_data)
                    return (None, "任务执行失败", failure_info)
                
                elif task_status in ["PENDING", "RUNNING"]:
                    # 任务还在进行中，等待后重试
                    if attempt % 10 == 0:  # 每10次重试打印一次状态
                        logger.info(f"[QwenVideoAPI] ⏳ 任务进行中... (第{attempt+1}次检查，预计需要2-5分钟)")
                    time.sleep(retry_interval)
                    continue
                
                else:
                    logger.warning(f"⚠️ 未知任务状态: {task_status}")
                    time.sleep(retry_interval)
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ 轮询请求失败: {e}")
                time.sleep(retry_interval)
                continue
            except Exception as e:
                logger.error(f"❌ 轮询处理失败: {e}")
                time.sleep(retry_interval)
                continue
        
        logger.error("❌ 轮询超时，视频生成可能仍在进行中")
        timeout_info = f"任务ID: {task_id}\n状态: 轮询超时\n建议: 请稍后手动查询任务状态"
        return (None, "轮询超时，请稍后手动查询任务状态", timeout_info)

    def _simplify_payload_for_log(self, payload):
        """
        简化payload用于日志显示，截断base64编码只显示前50个字符
        """
        import copy
        log_payload = copy.deepcopy(payload)
        
        # 简化input中的base64编码字段
        if "input" in log_payload:
            for key in ["img_url", "first_frame_url", "last_frame_url"]:
                if key in log_payload["input"]:
                    original_value = log_payload["input"][key]
                    if original_value and len(original_value) > 50:
                        # 保留data:image/jpeg;base64,前缀和前50个字符，然后添加省略号
                        if original_value.startswith("data:image/"):
                            prefix_end = original_value.find(",") + 1
                            if prefix_end > 0:
                                prefix = original_value[:prefix_end]
                                base64_part = original_value[prefix_end:]
                                if len(base64_part) > 50:
                                    log_payload["input"][key] = f"{prefix}{base64_part[:50]}... (长度: {len(base64_part)} 字符)"
                                else:
                                    log_payload["input"][key] = original_value
                            else:
                                log_payload["input"][key] = f"{original_value[:50]}... (长度: {len(original_value)} 字符)"
                        else:
                            log_payload["input"][key] = f"{original_value[:50]}... (长度: {len(original_value)} 字符)"
        
        return log_payload

    def _download_and_convert_video(self, video_url):
        """
        下载并转换视频为ComfyUI格式
        """
        try:
            logger.info(f"[QwenVideoAPI] ⬇️ 开始下载视频...")
            
            # 导入必要的模块
            try:
                from comfy_api_nodes.apinode_utils import download_url_to_video_output
            except ImportError:
                logger.error("[QwenVideoAPI] ❌ 无法导入 comfy_api_nodes.apinode_utils.download_url_to_video_output")
                logger.info("[QwenVideoAPI] 💡 返回None，仅提供video_url输出")
                return None
            
            # 下载视频
            video_object = download_url_to_video_output(video_url, timeout=120)
            
            logger.info(f"[QwenVideoAPI] ✅ 视频下载并转换为ComfyUI格式成功")
            return video_object
            
        except Exception as e:
            logger.error(f"[QwenVideoAPI] ❌ 视频下载转换失败: {e}")
            logger.info("[QwenVideoAPI] 💡 返回None，仅提供video_url输出")
            return None

    def _extract_generation_info(self, task_id, result_data):
        """
        提取生成信息，格式化为可读字符串
        """
        try:
            output = result_data.get("output", {})
            usage = result_data.get("usage", {})
            
            # 提取基本信息
            info_lines = [
                "✅ 视频生成成功",
                f"任务ID: {task_id}",
                f"提交时间: {output.get('submit_time', '未知')}",
                f"开始时间: {output.get('scheduled_time', '未知')}",
                f"完成时间: {output.get('end_time', '未知')}",
                ""
            ]
            
            # 提取提示词信息
            orig_prompt = output.get('orig_prompt', '未知')
            actual_prompt = output.get('actual_prompt', '未知')
            
            info_lines.extend([
                "📝 提示词信息:",
                f"原始提示词: {orig_prompt}",
                ""
            ])
            
            # 如果智能改写生效，显示改写后的提示词
            if actual_prompt and actual_prompt != orig_prompt and actual_prompt != '未知':
                info_lines.extend([
                    f"智能改写后: {actual_prompt}",
                    ""
                ])
            
            # 提取视频规格信息
            video_duration = usage.get('video_duration', '未知')
            video_ratio = usage.get('video_ratio', '未知')
            video_count = usage.get('video_count', '未知')
            
            info_lines.extend([
                "🎬 视频规格:",
                f"时长: {video_duration}秒",
                f"分辨率: {video_ratio}",
                f"生成数量: {video_count}个",
                ""
            ])
            
            # 提取任务统计信息
            task_metrics = output.get('task_metrics', {})
            if task_metrics:
                info_lines.extend([
                    "📊 任务统计:",
                    f"总数: {task_metrics.get('TOTAL', 0)}",
                    f"成功: {task_metrics.get('SUCCEEDED', 0)}",
                    f"失败: {task_metrics.get('FAILED', 0)}",
                    ""
                ])
            
            # 添加请求ID
            request_id = result_data.get('request_id', '未知')
            info_lines.append(f"请求ID: {request_id}")
            
            return "\n".join(info_lines)
            
        except Exception as e:
            logger.error(f"提取生成信息失败: {e}")
            return f"任务ID: {task_id}\n状态: 生成成功\n注意: 无法解析详细信息 ({str(e)})"

    def _extract_failure_info(self, task_id, result_data):
        """
        提取失败信息，格式化为可读字符串
        """
        try:
            output = result_data.get("output", {})
            
            info_lines = [
                "❌ 视频生成失败",
                f"任务ID: {task_id}",
                f"提交时间: {output.get('submit_time', '未知')}",
                f"失败时间: {output.get('end_time', '未知')}",
                ""
            ]
            
            # 提取错误信息
            error_code = output.get('error_code', '未知')
            error_message = output.get('error_message', '未知')
            
            if error_code != '未知' or error_message != '未知':
                info_lines.extend([
                    "🔍 错误详情:",
                    f"错误代码: {error_code}",
                    f"错误信息: {error_message}",
                    ""
                ])
            
            # 提取任务统计信息
            task_metrics = output.get('task_metrics', {})
            if task_metrics:
                info_lines.extend([
                    "📊 任务统计:",
                    f"总数: {task_metrics.get('TOTAL', 0)}",
                    f"成功: {task_metrics.get('SUCCEEDED', 0)}",
                    f"失败: {task_metrics.get('FAILED', 0)}",
                    ""
                ])
            
            # 添加请求ID
            request_id = result_data.get('request_id', '未知')
            info_lines.append(f"请求ID: {request_id}")
            
            return "\n".join(info_lines)
            
        except Exception as e:
            logger.error(f"提取失败信息失败: {e}")
            return f"任务ID: {task_id}\n状态: 执行失败\n注意: 无法解析详细错误信息 ({str(e)})"

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Qwen_Video_API": QwenVideoAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_Video_API": "Qwen Video API节点"
} 
