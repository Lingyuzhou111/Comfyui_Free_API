import os
import json
import requests
from PIL import Image
from io import BytesIO
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenImageAPI")

# 节点主类
class QwenImageAPI:
    """
    ComfyUI自定义节点：Qwen Image API
    实现文生图API调用，支持多种模型和参数配置，参数自动读取config.json。
    输入参数：model, size, prompt, prompt_extend, seed(可选), n(可选), watermark(可选)
    输出：image（生成的图像）
    """
    def __init__(self):
        # 读取配置文件，专门读取IMAGE.qwen_image配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.config = config.get('IMAGE', {}).get('qwen_image', {})
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
                models = config.get('IMAGE', {}).get('qwen_image', {}).get('model', [])
        except:
            models = ["wanx2.2-t2i-turbo", "wanx2.2-t2i-plus", "wanx2.1-t2i-turbo", "wanx2.1-t2i-plus"]
        
        # 定义支持的尺寸选项
        size_options = [
            "1024x1024",
            "864x1152",
            "1152x864",
            "768x1344", 
            "1344x768",
            "1328x1328", 
            "1140x1472",
            "1472x1140",
            "928x1664",
            "1664x928"
        ]
        
        return {
            "required": {
                "model": (models, {"default": models[0] if models else "wanx2.2-t2i-turbo", "tooltip": "选择文生图模型"}),
                "size": (size_options, {"default": "1024x1024", "tooltip": "输出图像尺寸"}),
                "prompt_extend": ("BOOLEAN", {"default": True, "tooltip": "是否开启智能改写，对短提示词效果提升明显"}),
                "prompt": ("STRING", {"multiline": True, "default": "一只可爱的小猫，坐在花园里", "tooltip": "正向提示词，描述想要生成的图像内容"}),
            },
            "optional": {
                "negative_prompt": ("STRING", {"multiline": True, "default": "低分辨率、错误、最差质量、低质量、残缺、多余的手指、比例不良", "tooltip": "反向提示词，描述不希望看到的内容"}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1, "tooltip": "随机种子，-1为随机生成，相同种子可产生相似结果"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1, "tooltip": "生成图片数量，最多4张"}),
                "watermark": ("BOOLEAN", {"default": False, "tooltip": "是否添加水印标识"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING",)
    RETURN_NAMES = ("image", "image_url", "generation_info",)
    FUNCTION = "generate_image"
    CATEGORY = "API/Qwen"

    def generate_image(self, model, size, prompt, prompt_extend, negative_prompt=None, seed=None, n=1, watermark=False):
        """
        主生成方法：
        1. 构造Qwen Image API请求，包含所有必要参数
        2. 发送请求，返回生成的图像
        
        Args:
            model: 选择的模型
            size: 图像尺寸
            prompt: 正向提示词
            prompt_extend: 是否开启智能改写
            negative_prompt: 反向提示词(可选)
            seed: 随机种子(可选)
            n: 生成数量(可选)
            watermark: 是否添加水印(可选)
        """
        logger.info(f"[QwenImageAPI] 开始文生图生成...")
        logger.info(f"[QwenImageAPI] 模型: {model}")
        logger.info(f"[QwenImageAPI] 尺寸: {size}")
        logger.info(f"[QwenImageAPI] 提示词: {prompt}")
        logger.info(f"[QwenImageAPI] 智能改写: {'开启' if prompt_extend else '关闭'}")
        
        # 读取Qwen API参数
        base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            logger.error("未配置Qwen API Key")
            error_info = "❌ 错误: 未配置Qwen API Key\n请在config.json中配置IMAGE.qwen_image.api_key"
            # 返回一个默认的黑色图像
            import torch
            import numpy as np
            default_image = torch.zeros((1, 1024, 1024, 3), dtype=torch.float32)
            return (default_image, "API Key未配置", error_info)
        
        # 1. 构造API请求
        payload = {
            "model": model,
            "input": {
                "prompt": prompt
            },
            "parameters": {
                "size": size.replace('x', '*'),  # 将1024x1024转换为1024*1024
                "n": n,
                "watermark": watermark,
                "prompt_extend": prompt_extend
            }
        }
        
        # 添加可选参数
        if negative_prompt:
            payload["input"]["negative_prompt"] = negative_prompt
            logger.info(f"[QwenImageAPI] 反向提示词: {negative_prompt}")
        
        if seed is not None and seed != -1:
            payload["parameters"]["seed"] = seed
            logger.info(f"[QwenImageAPI] 随机种子: {seed}")
        
        # 2. 发送请求
        try:
            headers = {
                "X-DashScope-Async": "enable",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 打印调试信息
            logger.debug(f"[QwenImageAPI] 🔍 请求URL: {base_url}")
            logger.debug(f"[QwenImageAPI] 🔍 请求头: {headers}")
            logger.debug(f"[QwenImageAPI] 🔍 请求体: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            
            # 提交任务
            resp = requests.post(base_url, headers=headers, json=payload, timeout=180)
            
            # 打印响应信息
            logger.info(f"[QwenImageAPI] 🔍 响应状态码: {resp.status_code}")
            logger.debug(f"[QwenImageAPI] 🔍 响应头: {dict(resp.headers)}")
            
            if resp.status_code != 200:
                logger.error(f"[QwenImageAPI] ❌ 响应内容: {resp.text}")
            
            resp.raise_for_status()
            task_data = resp.json()
            
            # 获取任务ID
            task_id = task_data.get("output", {}).get("task_id")
            if not task_id:
                logger.error("[QwenImageAPI] ❌ 未获取到任务ID")
                error_info = f"错误: API响应中未获取到任务ID，响应内容: {task_data}"
                error_image = self._create_error_image()
                return (error_image[0], "任务提交失败", error_info)
            
            logger.info(f"✅ 任务提交成功，任务ID: {task_id}")
            
            # 轮询任务结果
            return self._poll_task_result(task_id, api_key)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API请求失败: {e}")
            error_info = f"[QwenImageAPI] API请求失败\n错误类型: {type(e).__name__}\n错误详情: {str(e)}\n请检查网络连接和API配置"
            error_image = self._create_error_image()
            return (error_image[0], f"API请求失败: {str(e)}", error_info)
        except Exception as e:
            logger.error(f"[QwenImageAPI] ❌ 处理失败: {e}")
            error_info = f"[QwenImageAPI] 处理失败\n错误类型: {type(e).__name__}\n错误详情: {str(e)}"
            error_image = self._create_error_image()
            return (error_image[0], f"处理失败: {str(e)}", error_info)

    def _poll_task_result(self, task_id, api_key, max_retries=60, retry_interval=2):
        """
        轮询任务结果，获取生成的图像
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
                    # 任务成功，获取结果图像
                    results = result_data.get("output", {}).get("results", [])
                    if results and len(results) > 0:
                        image_url = results[0].get("url")
                        if image_url:
                            logger.info("[QwenImageAPI] ✅ 任务成功，开始下载结果图像")
                            logger.info(f"[QwenImageAPI] 🖼️ 图像URL: {image_url}")
                            
                            # 提取生成信息
                            generation_info = self._extract_generation_info(task_id, result_data)
                            
                            # 下载并转换图像为ComfyUI格式
                            image_object = self._download_and_convert_image(image_url)
                            
                            return (image_object[0], image_url, generation_info)
                        else:
                            logger.error("[QwenImageAPI] ❌ 图像URL为空")
                            failure_info = self._extract_failure_info(task_id, result_data)
                            error_image = self._create_error_image()
                            return (error_image[0], "图像URL为空", failure_info)
                    else:
                        logger.error("[QwenImageAPI] ❌ 没有获取到结果")
                        failure_info = self._extract_failure_info(task_id, result_data)
                        error_image = self._create_error_image()
                        return (error_image[0], "没有获取到结果", failure_info)
                
                elif task_status == "FAILED":
                    logger.error("[QwenImageAPI] ❌ 任务执行失败")
                    failure_info = self._extract_failure_info(task_id, result_data)
                    error_image = self._create_error_image()
                    return (error_image[0], "任务执行失败", failure_info)
                
                elif task_status in ["PENDING", "RUNNING"]:
                    # 任务还在进行中，等待后重试
                    if attempt % 10 == 0:  # 每10次重试打印一次状态
                        logger.info(f"[QwenImageAPI] ⏳ 任务进行中... (第{attempt+1}次检查)")
                    time.sleep(retry_interval)
                    continue
                
                else:
                    logger.warning(f"[QwenImageAPI] ⚠️ 未知任务状态: {task_status}")
                    time.sleep(retry_interval)
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"[QwenImageAPI] ❌ 轮询请求失败: {e}")
                time.sleep(retry_interval)
                continue
            except Exception as e:
                logger.error(f"[QwenImageAPI] ❌ 轮询处理失败: {e}")
                time.sleep(retry_interval)
                continue
        
        logger.error("[QwenImageAPI] ❌ 轮询超时，返回错误图像")
        timeout_info = f"任务ID: {task_id}\n状态: 轮询超时\n建议: 请稍后手动查询任务状态"
        error_image = self._create_error_image()
        return (error_image[0], "[QwenImageAPI] 轮询超时，请稍后手动查询任务状态", timeout_info)

    def _download_and_convert_image(self, image_url):
        """
        下载并转换图像为ComfyUI格式
        """
        try:
            logger.info(f"[QwenImageAPI] ⬇️ 开始下载图像...")
            
            # 下载图像
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            
            logger.info(f"[QwenImageAPI] 图像数据接收完毕 (大小: {len(response.content)/1024:.1f} KB)")
            
            # 将图像数据转换为PIL Image
            image = Image.open(BytesIO(response.content))
            
            # 确保图像是RGB格式
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 转换为numpy数组
            import numpy as np
            image_np = np.array(image).astype(np.float32) / 255.0
            
            # 转换为torch tensor，格式为 [batch, height, width, channels]
            import torch
            image_tensor = torch.from_numpy(image_np)[None,]
            
            logger.info(f"[QwenImageAPI] ✅ 图像解码并转换为Tensor成功: {image_tensor.shape}")
            return (image_tensor,)
            
        except Exception as e:
            logger.error(f"❌ 图像下载失败: {e}")
            return self._create_error_image()

    def _create_error_image(self):
        """
        创建错误提示图像
        """
        try:
            import torch
            import numpy as np
            
            # 创建一个1024x1024的错误提示图像
            error_image = np.zeros((1024, 1024, 3), dtype=np.float32)
            
            # 添加红色边框和文字提示
            error_image[0:10, :, 0] = 1.0  # 上边框红色
            error_image[-10:, :, 0] = 1.0   # 下边框红色
            error_image[:, 0:10, 0] = 1.0   # 左边框红色
            error_image[:, -10:, 0] = 1.0   # 右边框红色
            
            # 转换为torch tensor
            image_tensor = torch.from_numpy(error_image)[None,]
            
            logger.warning("⚠️ 返回错误提示图像")
            return (image_tensor,)
            
        except Exception as e:
            logger.error(f"❌ 创建错误图像失败: {e}")
            # 最后的备选方案：返回纯黑图像
            import torch
            default_image = torch.zeros((1, 1024, 1024, 3), dtype=torch.float32)
            return (default_image,)

    def _extract_generation_info(self, task_id, result_data):
        """
        提取生成信息，格式化为可读字符串
        """
        try:
            output = result_data.get("output", {})
            usage = result_data.get("usage", {})
            
            # 提取基本信息
            info_lines = [
                "✅ 图像生成成功",
                f"任务ID: {task_id}",
                f"提交时间: {output.get('submit_time', '未知')}",
                f"开始时间: {output.get('scheduled_time', '未知')}",
                f"完成时间: {output.get('end_time', '未知')}",
                ""
            ]
            
            # 提取结果信息
            results = output.get('results', [])
            if results and len(results) > 0:
                result = results[0]
                image_url = result.get('url', '未知')
                
                info_lines.extend([
                    "🖼️ 生成结果:",
                    f"图像URL: {image_url}",
                    ""
                ])
            
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
            
            # 提取图像规格信息
            image_count = usage.get('image_count', len(results) if results else '未知')
            
            info_lines.extend([
                "🎨 图像规格:",
                f"生成数量: {image_count}张",
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
                "❌ 图像生成失败",
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
    "Qwen_Image_API": QwenImageAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_Image_API": "Qwen Image API节点"
} 
