import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenImageEditAPI")

# 节点主类
class QwenImageEditAPI:
    """
    ComfyUI自定义节点：Qwen Image Edit API
    实现图像编辑API调用，支持多种编辑功能，参数自动读取config.json。
    输入参数：prompt, function, image, strength, mask(可选)
    输出：image（编辑后的图像）
    """
    def __init__(self):
        # 读取配置文件，专门读取IMAGE.qwen_imageedit配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.config = config.get('IMAGE', {}).get('qwen_imageedit', {})
        except Exception as e:
            logger.error(f"配置文件读取失败: {e}")
            self.config = {}

    @classmethod
    def INPUT_TYPES(cls):
        # 定义支持的function选项（中文显示）
        function_options = [
            "指令编辑",                   # description_edit
            "局部重绘",                   # description_edit_with_mask
            "全局风格化",                 # stylization_all
            "局部风格化",                 # stylization_local
            "去文字水印",                 # remove_watermark
            "扩图",                      # expand
            "图像超分",                   # super_resolution
            "图像上色",                   # colorization
            "线稿生图",                   # doodle
            "参考卡通形象生图"            # control_cartoon_feature
        ]
        
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "请编辑这张图片", "tooltip": "编辑指令，描述你想要的效果"}),
                "function": (function_options, {"default": "指令编辑", "tooltip": "选择编辑功能类型"}),
                "image": ("IMAGE", {"tooltip": "输入图像"}),
                "strength": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "修改强度，0.0=接近原图，1.0=最大修改"}),
            },
            "optional": {
                "mask": ("IMAGE", {"tooltip": "蒙版图像，用于局部重绘功能"}),
                "top_scale": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 3.0, "step": 0.1, "tooltip": "上方扩图比例，仅扩图功能有效"}),
                "bottom_scale": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 3.0, "step": 0.1, "tooltip": "下方扩图比例，仅扩图功能有效"}),
                "left_scale": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 3.0, "step": 0.1, "tooltip": "左侧扩图比例，仅扩图功能有效"}),
                "right_scale": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 3.0, "step": 0.1, "tooltip": "右侧扩图比例，仅扩图功能有效"}),
                "upscale_factor": ("INT", {"default": 2, "min": 1, "max": 4, "step": 1, "tooltip": "超分放大倍数，仅图像超分功能有效"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "edit_image"
    CATEGORY = "API/Qwen"

    def edit_image(self, prompt, function, image, strength, mask=None, top_scale=None, bottom_scale=None, left_scale=None, right_scale=None, upscale_factor=None):
        """
        主编辑方法：
        1. 将image转为base64
        2. 构造Qwen Image Edit API请求，包含strength参数和功能特定参数
        3. 发送请求，返回编辑后的图像
        
        Args:
            prompt: 编辑指令
            function: 编辑功能类型
            image: 输入图像
            strength: 修改强度 (0.0-1.0)
            mask: 蒙版图像(可选)
            top_scale: 上方扩图比例(可选，仅扩图功能)
            bottom_scale: 下方扩图比例(可选，仅扩图功能)
            left_scale: 左侧扩图比例(可选，仅扩图功能)
            right_scale: 右侧扩图比例(可选，仅扩图功能)
            upscale_factor: 超分放大倍数(可选，仅超分功能)
        """
        # 将中文选项转换为英文API参数
        function_mapping = {
            "指令编辑": "description_edit",
            "局部重绘": "description_edit_with_mask",
            "全局风格化": "stylization_all",
            "局部风格化": "stylization_local",
            "去文字水印": "remove_watermark",
            "扩图": "expand",
            "图像超分": "super_resolution",
            "图像上色": "colorization",
            "线稿生图": "doodle",
            "参考卡通形象生图": "control_cartoon_feature"
        }
        
        # 转换function参数
        api_function = function_mapping.get(function, function)
        logger.info(f"用户选择: {function} -> API参数: {api_function}")
        logger.info(f"修改强度: {strength:.2f}")
        
        # 简化的调试信息
        logger.info(f"输入图像: {image.shape}")
        
        # 读取Qwen API参数
        base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/image2image/image-synthesis')
        api_key = self.config.get('api_key', '')
        model = self.config.get('model', 'wanx2.1-imageedit')
        
        if not api_key:
            logger.error("未配置Qwen API Key")
            return (image,)  # 返回原图
        
        # 临时测试模式：直接返回原图，跳过API调用
        # logger.info("启用测试模式：直接返回原图")
        # return (image,)
        
        # 1. 图片转base64
        try:
            base_image_url = self._image_to_base64_url(image)
            mask_image_url = None
            if mask is not None and api_function == "description_edit_with_mask":
                mask_image_url = self._image_to_base64_url(mask)
        except Exception as e:
            logger.error(f"❌ 图片处理失败: {e}")
            return (image,)  # 返回原图
        
        # 2. 构造API请求
        payload = {
            "model": model,
            "input": {
                "function": api_function,
                "prompt": prompt,
                "base_image_url": base_image_url
            },
            "parameters": {
                "n": 1,
                "strength": strength
            }
        }
        
        # 根据功能类型添加特定参数
        if api_function == "expand":
            # 扩图功能：添加四个方向的缩放参数
            if top_scale is not None:
                payload["parameters"]["top_scale"] = top_scale
            if bottom_scale is not None:
                payload["parameters"]["bottom_scale"] = bottom_scale
            if left_scale is not None:
                payload["parameters"]["left_scale"] = left_scale
            if right_scale is not None:
                payload["parameters"]["right_scale"] = right_scale
            logger.info(f"扩图参数: top={top_scale}, bottom={bottom_scale}, left={left_scale}, right={right_scale}")
        
        elif api_function == "super_resolution":
            # 图像超分功能：添加放大倍数参数
            if upscale_factor is not None:
                payload["parameters"]["upscale_factor"] = upscale_factor
            logger.info(f"超分参数: upscale_factor={upscale_factor}")
        
        # 如果是局部重绘且有蒙版，添加mask_image_url
        if api_function == "description_edit_with_mask" and mask_image_url:
            payload["input"]["mask_image_url"] = mask_image_url
        
        # 3. 发送请求
        try:
            headers = {
                "X-DashScope-Async": "enable",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 提交任务
            resp = requests.post(base_url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            task_data = resp.json()
            
            # 获取任务ID
            task_id = task_data.get("output", {}).get("task_id")
            if not task_id:
                logger.error("❌ 未获取到任务ID")
                return (image,)
            
            # 轮询任务结果
            return self._poll_task_result(task_id, api_key, image)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API请求失败: {e}")
            return (image,)  # 返回原图
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}")
            return (image,)  # 返回原图

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

    def _poll_task_result(self, task_id, api_key, original_image, max_retries=30, retry_interval=2):
        """
        轮询任务结果，获取编辑后的图像
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
                            logger.info("✅ 任务成功，开始下载结果图像")
                            return self._download_and_convert_image(image_url, original_image)
                        else:
                            logger.error("❌ 图像URL为空")
                            return (original_image,)
                    else:
                        logger.error("❌ 没有获取到结果")
                        return (original_image,)
                
                elif task_status == "FAILED":
                    logger.error("❌ 任务执行失败")
                    return (original_image,)
                
                elif task_status in ["PENDING", "RUNNING"]:
                    # 任务还在进行中，等待后重试
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
        
        logger.error("❌ 轮询超时，返回原图")
        return (original_image,)

    def _download_and_convert_image(self, image_url, original_image):
        """
        下载并转换图像为ComfyUI格式
        """
        try:
            logger.info(f"⬇️ 开始下载图像...")
            
            # 下载图像
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            
            logger.info(f"图像数据接收完毕 (大小: {len(response.content)/1024:.1f} KB)")
            
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
            
            logger.info(f"✅ 图像解码并转换为Tensor成功: {image_tensor.shape}")
            return (image_tensor,)
            
        except Exception as e:
            logger.error(f"❌ 图像下载失败: {e}")
            return (original_image,)

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Qwen_ImageEdit_API": QwenImageEditAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_ImageEdit_API": "Qwen Image Edit API节点"
} 