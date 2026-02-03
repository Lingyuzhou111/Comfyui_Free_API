import os
import json
import requests
from PIL import Image
from io import BytesIO
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ModelscopeImageAPI")

class ModelscopeImageAPI:
    """
    ComfyUI自定义节点：Modelscope魔搭平台文生图API
    实现文生图API调用，支持多种模型和参数配置，参数自动读取config.json。
    输入参数：model, prompt, ratio, resolution, seed(可选), steps(可选), guidance(可选), lora(可选)
    输出：image（生成的图像）
    """
    
    # 默认配置
    DEFAULT_CONFIG = {
        "default_seed": -1,
        "default_steps": 30,
        "default_guidance": 3.5,
        "default_ratio": "1:1",
        "1.5k_ratios": {
            "1:1": {"width": 1328, "height": 1328},
            "2:3": {"width": 1056, "height": 1584},
            "3:4": {"width": 1104, "height": 1472},
            "4:3": {"width": 1472, "height": 1104},
            "3:2": {"width": 1584, "height": 1056},
            "16:9": {"width": 1664, "height": 936},
            "9:16": {"width": 936, "height": 1664},
            "21:9": {"width": 2016, "height": 864}
        },
        "1k_ratios": {
            "1:1": {"width": 1024, "height": 1024},
            "2:3": {"width": 832, "height": 1248},
            "3:4": {"width": 864, "height": 1152},
            "4:3": {"width": 1152, "height": 864},
            "3:2": {"width": 1248, "height": 832},
            "16:9": {"width": 1344, "height": 768},
            "9:16": {"width": 768, "height": 1344},
            "21:9": {"width": 1512, "height": 648}
        }
    }
    
    def __init__(self):
        # 从 ms_api_config.json 读取配置
        config_path = os.path.join(os.path.dirname(__file__), 'ms_api_config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.config = config.get('modelscope_image_api', {})
                self.lora_map = config.get('lora_map', {})
                self.models = config.get('checkpoint', [])
        except Exception as e:
            logger.error(f"配置文件读取失败: {e}")
            self.config = {}
            self.lora_map = {}
            self.models = []
    
    @classmethod
    def INPUT_TYPES(cls):
        # 从 ms_api_config.json 读取模型和LoRA配置
        config_path = os.path.join(os.path.dirname(__file__), 'ms_api_config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                models = config.get('checkpoint', [])
                lora_map = config.get('lora_map', {})
        except:
            models = ["Tongyi-MAI/Z-Image", "Tongyi-MAI/Z-Image-Turbo", "Qwen/Qwen-Image-2512"]
            lora_map = {}
        
        # 构建LoRA选项列表，添加"none"选项表示不使用
        lora_options = ["none"] + list(lora_map.keys())
        
        # 定义支持的宽高比选项
        ratio_options = ["1:1", "2:3", "3:4", "4:3", "3:2", "9:16", "16:9", "21:9"]
        
        # 定义分辨率选项
        resolution_options = ["1k", "1.5k"]
        
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "A golden cat", "tooltip": "正向提示词，描述想要生成的图像内容"}),
                "model": (models, {"default": models[0] if models else "Tongyi-MAI/Z-Image", "tooltip": "选择文生图模型"}),
                "ratio": (ratio_options, {"default": "1:1", "tooltip": "输出图像的宽高比"}),
                "resolution": (resolution_options, {"default": "1k", "tooltip": "输出图像分辨率（1k或1.5k）"}),
            },
            "optional": {
                "seed": ("INT", {"default": cls.DEFAULT_CONFIG["default_seed"], "min": -1, "max": 2147483647, "step": 1, "tooltip": "随机种子，-1为随机生成，相同种子可产生相似结果"}),
                "steps": ("INT", {"default": cls.DEFAULT_CONFIG["default_steps"], "min": 1, "max": 100, "step": 1, "tooltip": "推理步数，影响生成质量和速度"}),
                "guidance": ("FLOAT", {"default": cls.DEFAULT_CONFIG["default_guidance"], "min": 1.0, "max": 20.0, "step": 0.1, "tooltip": "引导系数，控制提示词对生成结果的影响程度"}),
                # 最多支持3个LoRA
                "lora_name_1": (lora_options, {"default": "none", "tooltip": "选择第1个LoRA模型"}),
                "lora_weight_1": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01, "tooltip": "第1个LoRA的权重系数"}),
                "lora_name_2": (lora_options, {"default": "none", "tooltip": "选择第2个LoRA模型"}),
                "lora_weight_2": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01, "tooltip": "第2个LoRA的权重系数"}),
                "lora_name_3": (lora_options, {"default": "none", "tooltip": "选择第3个LoRA模型"}),
                "lora_weight_3": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01, "tooltip": "第3个LoRA的权重系数"}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("image", "generation_info",)
    FUNCTION = "generate_image"
    CATEGORY = "🦉FreeAPI/ModelScope"
    
    def generate_image(self, model, prompt, ratio, resolution, seed=None, steps=None, guidance=None,
                        lora_name_1="none", lora_weight_1=1.0,
                        lora_name_2="none", lora_weight_2=1.0,
                        lora_name_3="none", lora_weight_3=1.0):
        """
        主生成方法：
        1. 构造Modelscope API请求，包含所有必要参数
        2. 发送请求，返回生成的图像
        
        Args:
            model: 选择的模型
            prompt: 正向提示词
            ratio: 宽高比
            resolution: 分辨率（1k或1.5k）
            seed: 随机种子(可选)
            steps: 推理步数(可选)
            guidance: 引导系数(可选)
            lora_name_1/2/3: LoRA模型名称(可选)
            lora_weight_1/2/3: LoRA权重系数(可选)
        """
        # 读取Modelscope API参数
        base_url = self.config.get('base_url', 'https://api-inference.modelscope.cn/v1/images/generations')
        api_key = self.config.get('api_key', '')
        
        logger.info(f"[ModelscopeImageAPI] 正在请求图像生成API: {base_url}")
        logger.info(f"[ModelscopeImageAPI] 请求参数: model={model}, ratio={ratio}, resolution={resolution}")
        
        if not api_key:
            logger.error("[ModelscopeImageAPI] 未配置Modelscope API Key")
            error_info = "错误: 未配置Modelscope API Key\n请在config.json中配置IMAGE.modelscope_image.api_key"
            # 返回一个默认的黑色图像
            import torch
            import numpy as np
            default_image = torch.zeros((1, 1024, 1024, 3), dtype=torch.float32)
            return (default_image, error_info)
        
        # 获取尺寸配置
        size_config = self.DEFAULT_CONFIG.get(f"{resolution}_ratios", self.DEFAULT_CONFIG["1k_ratios"])
        if ratio not in size_config:
            ratio = "1:1"  # 默认回退到1:1
        width = size_config[ratio]["width"]
        height = size_config[ratio]["height"]
        # 魔搭API使用 size 参数（如 "1024x1024"），而不是分开的 width/height
        size_str = f"{width}x{height}"
        
        # 1. 构造API请求
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size_str  # 魔搭API期望的尺寸格式
        }
        
        logger.info(f"[ModelscopeImageAPI] 请求尺寸: {size_str} ({resolution}, 比例 {ratio})")
        
        # 添加可选参数
        if seed is not None and seed != -1:
            payload["seed"] = seed
            logger.info(f"[ModelscopeImageAPI] 随机种子: {seed}")
        
        if steps is not None:
            payload["num_inference_steps"] = steps
            logger.info(f"[ModelscopeImageAPI] 推理步数: {steps}")
        
        if guidance is not None:
            payload["guidance_scale"] = guidance
            logger.info(f"[ModelscopeImageAPI] 引导系数: {guidance}")
        
        # 处理LoRA配置（最多3个）
        loras_config = {}
        trigger_words = []  # 收集触发词
        lora_list = [
            (lora_name_1, lora_weight_1),
            (lora_name_2, lora_weight_2),
            (lora_name_3, lora_weight_3)
        ]
        
        for lora_name, lora_weight in lora_list:
            if lora_name and lora_name != "none" and lora_name in self.lora_map:
                lora_info = self.lora_map[lora_name]
                repoid = lora_info.get("repoid", "")
                trigger_word = lora_info.get("triggerWord", "").strip()
                
                if repoid:
                    loras_config[repoid] = lora_weight
                    logger.info(f"[ModelscopeImageAPI] LoRA配置: {lora_name} -> {repoid} (权重: {lora_weight})")
                    
                    # 收集非空触发词
                    if trigger_word:
                        trigger_words.append(trigger_word)
                        logger.info(f"[ModelscopeImageAPI] LoRA触发词: {lora_name} -> '{trigger_word}'")
        
        # 自动拼接触发词到提示词前面
        if trigger_words:
            original_prompt = prompt
            trigger_prefix = ", ".join(trigger_words)
            prompt = f"{trigger_prefix}, {prompt}"
            logger.info(f"[ModelscopeImageAPI] 提示词已添加触发词: '{trigger_prefix}'")
            logger.info(f"[ModelscopeImageAPI] 原提示词: {original_prompt}")
            logger.info(f"[ModelscopeImageAPI] 新提示词: {prompt}")
        
        # 更新payload中的prompt
        payload["prompt"] = prompt
        
        # 根据LoRA数量构造正确的格式
        lora_warning = None  # 用于存储LoRA权重警告信息
        
        if len(loras_config) == 1:
            # 单个LoRA: 使用字符串格式
            payload["loras"] = list(loras_config.keys())[0]
            logger.info(f"[ModelscopeImageAPI] 使用单个LoRA: {payload['loras']}")
        elif len(loras_config) > 1:
            # 多个LoRA: 使用字典格式
            total_weight = sum(loras_config.values())
            logger.info(f"[ModelscopeImageAPI] 使用多个LoRA: {loras_config}, 总权重: {total_weight:.2f}")
            
            # 检查权重之和是否等于1.0（允许0.01的误差）
            if abs(total_weight - 1.0) > 0.01:
                lora_warning = f"⚠️ 提醒: 多个LoRA权重之和为 {total_weight:.2f}，建议调整为 1.0 以获得最佳效果"
                logger.warning(f"[ModelscopeImageAPI] {lora_warning}")
            
            payload["loras"] = loras_config
        
        # 2. 发送请求
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-ModelScope-Async-Mode": "true"
            }
            
            # 打印请求详情（参考OpenAIImageAPI格式）
            logger.info(f"[ModelscopeImageAPI] 请求载荷: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            
            # 提交任务
            resp = requests.post(
                base_url,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                timeout=180
            )
            
            # 打印响应信息
            logger.info(f"[ModelscopeImageAPI] 响应状态码: {resp.status_code}")
            
            if resp.status_code != 200:
                logger.error(f"[ModelscopeImageAPI] 响应内容: {resp.text}")
            
            resp.raise_for_status()
            task_data = resp.json()
            
            # 打印初始响应（参考OpenAIImageAPI格式）
            logger.info(f"[ModelscopeImageAPI] 魔搭初始响应: {json.dumps(task_data, ensure_ascii=False, indent=2)}")
            
            # 获取任务ID
            task_id = task_data.get("task_id")
            if not task_id:
                logger.error("[ModelscopeImageAPI] 未获取到任务ID")
                error_info = f"错误: API响应中未获取到任务ID，响应内容: {task_data}"
                error_image = self._create_error_image()
                return (error_image[0], error_info)
            
            logger.info(f"[ModelscopeImageAPI] 任务提交成功，任务ID: {task_id}")
            
            # 轮询任务结果，传递LoRA警告信息
            return self._poll_task_result(task_id, api_key, base_url, lora_warning)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[ModelscopeImageAPI] API请求失败: {e}")
            error_info = f"[ModelscopeImageAPI] API请求失败\n错误类型: {type(e).__name__}\n错误详情: {str(e)}\n请检查网络连接和API配置"
            error_image = self._create_error_image()
            return (error_image[0], error_info)
        except Exception as e:
            logger.error(f"[ModelscopeImageAPI] 处理失败: {e}")
            error_info = f"[ModelscopeImageAPI] 处理失败\n错误类型: {type(e).__name__}\n错误详情: {str(e)}"
            error_image = self._create_error_image()
            return (error_image[0], error_info)
    
    def _poll_task_result(self, task_id, api_key, base_url, lora_warning=None, max_retries=60, retry_interval=5):
        """
        轮询任务结果，获取生成的图像
        Args:
            lora_warning: LoRA权重警告信息（可选）
        """
        # 从base_url中提取基础域名
        base_domain = base_url.replace('/v1/images/generations', '')
        poll_url = f"{base_domain}/v1/tasks/{task_id}"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-ModelScope-Task-Type": "image_generation"
        }
        
        logger.info(f"[ModelscopeImageAPI] 开始轮询魔搭任务: task_id={task_id}, url={poll_url}")
        
        for attempt in range(max_retries):
            try:
                resp = requests.get(poll_url, headers=headers, timeout=30)
                resp.raise_for_status()
                result_data = resp.json()
                
                task_status = result_data.get("task_status")
                
                if task_status == "SUCCEED":
                    # 任务成功，获取结果图像
                    output_images = result_data.get("output_images", [])
                    if output_images and len(output_images) > 0:
                        image_url = output_images[0]
                        logger.info(f"[ModelscopeImageAPI] 任务完成，下载图片: {image_url}")
                        
                        # 提取生成信息（包含image_url和LoRA警告）
                        generation_info = self._extract_generation_info(task_id, result_data, image_url, lora_warning)
                        
                        # 下载并转换图像为ComfyUI格式
                        image_object = self._download_and_convert_image(image_url)
                        
                        return (image_object[0], generation_info)
                    else:
                        logger.error("[ModelscopeImageAPI] 没有获取到结果图像")
                        failure_info = self._extract_failure_info(task_id, result_data)
                        error_image = self._create_error_image()
                        return (error_image[0], failure_info)
                
                elif task_status == "FAILED":
                    logger.error("[ModelscopeImageAPI] 任务执行失败")
                    failure_info = self._extract_failure_info(task_id, result_data)
                    error_image = self._create_error_image()
                    return (error_image[0], failure_info)
                
                elif task_status in ["PENDING", "RUNNING", "WAITING", "PROCESSING"]:
                    # 任务还在进行中，等待后重试
                    logger.info(f"[ModelscopeImageAPI] 魔搭轮询尝试 {attempt+1}/{max_retries}, 状态: {task_status}")
                    time.sleep(retry_interval)
                    continue
                
                else:
                    logger.warning(f"[ModelscopeImageAPI] 未知任务状态: {task_status}")
                    time.sleep(retry_interval)
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"[ModelscopeImageAPI] 轮询请求失败: {e}")
                time.sleep(retry_interval)
                continue
            except Exception as e:
                logger.error(f"[ModelscopeImageAPI] 轮询处理失败: {e}")
                time.sleep(retry_interval)
                continue
        
        logger.error("[ModelscopeImageAPI] 轮询超时，返回错误图像")
        timeout_info = f"任务ID: {task_id}\n状态: 轮询超时\n建议: 请稍后手动查询任务状态"
        error_image = self._create_error_image()
        return (error_image[0], timeout_info)
    
    def _download_and_convert_image(self, image_url):
        """
        下载并转换图像为ComfyUI格式
        """
        try:
            # 下载图像
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            
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
            
            logger.info(f"[ModelscopeImageAPI] 图像下载完成: 尺寸={image.size}, 大小={len(response.content)/1024:.1f}KB, shape={image_tensor.shape}")
            return (image_tensor,)
            
        except Exception as e:
            logger.error(f"[ModelscopeImageAPI] 图像下载失败: {e}")
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
            
            logger.warning("[ModelscopeImageAPI] 返回错误提示图像")
            return (image_tensor,)
            
        except Exception as e:
            logger.error(f"[ModelscopeImageAPI] 创建错误图像失败: {e}")
            # 最后的备选方案：返回纯黑图像
            import torch
            default_image = torch.zeros((1, 1024, 1024, 3), dtype=torch.float32)
            return (default_image,)
    
    def _extract_generation_info(self, task_id, result_data, image_url=None, lora_warning=None):
        """
        提取生成信息，格式化为可读字符串
        """
        try:
            info_lines = [
                "✅ 图像生成成功",
                f"任务ID: {task_id}",
                ""
            ]
            
            # 添加LoRA权重警告（如果有）
            if lora_warning:
                info_lines.extend([
                    lora_warning,
                    ""
                ])
            
            # 提取结果图像信息
            if image_url:
                info_lines.extend([
                    "🖼️ 生成结果:",
                    f"图像URL: {image_url}",
                    ""
                ])
            else:
                output_images = result_data.get('output_images', [])
                if output_images and len(output_images) > 0:
                    info_lines.extend([
                        "🖼️ 生成结果:",
                        f"图像URL: {output_images[0]}",
                        f"生成数量: {len(output_images)}张",
                        ""
                    ])
            
            # 提取任务状态信息
            task_status = result_data.get('task_status', '未知')
            info_lines.extend([
                "📋 任务状态:",
                f"状态: {task_status}",
                ""
            ])
            
            return "\n".join(info_lines)
            
        except Exception as e:
            logger.error(f"提取生成信息失败: {e}")
            return f"任务ID: {task_id}\n状态: 生成成功\n注意: 无法解析详细信息 ({str(e)})"
    
    def _extract_failure_info(self, task_id, result_data):
        """
        提取失败信息，格式化为可读字符串
        """
        try:
            info_lines = [
                "❌ 图像生成失败",
                f"任务ID: {task_id}",
                ""
            ]
            
            # 提取错误信息
            error_code = result_data.get('error_code', '未知')
            error_message = result_data.get('error_message', '未知')
            
            if error_code != '未知' or error_message != '未知':
                info_lines.extend([
                    "🔍 错误详情:",
                    f"错误代码: {error_code}",
                    f"错误信息: {error_message}",
                    ""
                ])
            
            # 提取任务状态
            task_status = result_data.get('task_status', '未知')
            info_lines.extend([
                "📋 任务状态:",
                f"状态: {task_status}",
                ""
            ])
            
            return "\n".join(info_lines)
            
        except Exception as e:
            logger.error(f"提取失败信息失败: {e}")
            return f"任务ID: {task_id}\n状态: 执行失败\n注意: 无法解析详细错误信息 ({str(e)})"


# 节点注册
NODE_CLASS_MAPPINGS = {
    "Modelscope_Image_API": ModelscopeImageAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Modelscope_Image_API": "🦉魔搭生图API版"
}
