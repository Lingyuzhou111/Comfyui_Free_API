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
    实现图像编辑API调用，基于最新的qwen-image-edit模型，参数自动读取config.json。
    输入参数：prompt(必选), image(必选)
    输出：image（编辑后的图像）
    """
    def __init__(self):
        # 读取配置文件，专门读取IMAGE.qwen_image_edit配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.config = config.get('IMAGE', {}).get('qwen_image_edit', {})
        except Exception as e:
            logger.error(f"[QwenImageEditAPI] 配置文件读取失败: {e}")
            self.config = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "将图中的人物改为站立姿势", "tooltip": "编辑指令，描述你想要对图像进行的修改"}),
                "image": ("IMAGE", {"tooltip": "需要编辑的输入图像"}),
            },
            "optional": {
                "negative_prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "反向提示词，描述不希望看到的内容"}),
                "prompt_extend": ("BOOLEAN", {"default": True, "tooltip": "是否开启智能改写，对短提示词效果提升明显"}),
                "watermark": ("BOOLEAN", {"default": False, "tooltip": "是否添加水印标识"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING",)
    RETURN_NAMES = ("image", "image_url", "edit_info",)
    FUNCTION = "edit_image"
    CATEGORY = "🦉FreeAPI/Qwen"

    def edit_image(self, prompt, image, negative_prompt="", prompt_extend=True, watermark=False):
        """
        主编辑方法：
        1. 将输入图像转换为base64或上传到云端获取URL
        2. 构造Qwen Image Edit API请求
        3. 发送请求，返回编辑后的图像
        
        Args:
            prompt: 编辑指令
            image: 输入图像
            negative_prompt: 反向提示词(可选)
            prompt_extend: 是否开启智能改写(可选)
            watermark: 是否添加水印(可选)
        """
        logger.info(f"[QwenImageEditAPI] 开始图像编辑...")
        logger.info(f"[QwenImageEditAPI] 编辑指令: {prompt}")
        logger.info(f"[QwenImageEditAPI] 智能改写: {'开启' if prompt_extend else '关闭'}")
        logger.info(f"[QwenImageEditAPI] 输入图像: {image.shape}")
        logger.info(f"[QwenImageEditAPI] 负面提示词: {negative_prompt if negative_prompt else '无'}")
        logger.info(f"[QwenImageEditAPI] 水印: {'开启' if watermark else '关闭'}")
        
        # 读取Qwen API参数
        base_url = self.config.get('base_url', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation')
        api_key = self.config.get('api_key', '')
        model = self.config.get('model', ["qwen-image-edit"])[0] if isinstance(self.config.get('model'), list) else self.config.get('model', 'qwen-image-edit')
        
        if not api_key:
            logger.error("[QwenImageEditAPI] 未配置Qwen API Key")
            return (image, "", "错误：未配置API Key")
        
        # 1. 图片转base64格式
        try:
            image_base64 = self._image_to_base64(image)
            logger.info(f"[QwenImageEditAPI] 📷 图片已转换为base64格式")
        except Exception as e:
            logger.error(f"[QwenImageEditAPI] ❌ 图片转base64失败: {e}")
            return (image, "", f"错误：图片转base64失败 - {e}")
        
        # 2. 构造API请求
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": image_base64
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            },
            "parameters": {
                "negative_prompt": negative_prompt,
                "prompt_extend": prompt_extend,
                "watermark": watermark
            }
        }
        
        # 3. 发送请求
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info("[QwenImageEditAPI] 🚀 发送API请求...")
            resp = requests.post(base_url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            
            result_data = resp.json()
            logger.info("[QwenImageEditAPI] ✅ API请求成功")
            
            # 解析响应
            choices = result_data.get("output", {}).get("choices", [])
            if choices and len(choices) > 0:
                content = choices[0].get("message", {}).get("content", [])
                
                # 查找图像内容
                image_content = None
                for item in content:
                    if "image" in item:
                        image_content = item["image"]
                        break
                
                if image_content:
                    logger.info("[QwenImageEditAPI] 🖼️ 获取到编辑结果，开始下载...")
                    edited_image = self._download_and_convert_image(image_content, image)
                    
                    # 生成编辑信息
                    edit_info = {
                        "model": model,
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "prompt_extend": prompt_extend,
                        "watermark": watermark,
                        "request_id": result_data.get("request_id", "")
                    }
                    
                    return (edited_image, image_content, json.dumps(edit_info, ensure_ascii=False, indent=2))
                else:
                    logger.error("[QwenImageEditAPI] ❌ 响应中未找到图像内容")
                    return (image, "", "错误：响应中未找到图像内容")
            else:
                logger.error("[QwenImageEditAPI] ❌ 响应格式异常")
                return (image, "", "错误：响应格式异常")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"[QwenImageEditAPI] ❌ API请求失败: {e}")
            return (image, "", f"错误：API请求失败 - {e}")
        except Exception as e:
            logger.error(f"[QwenImageEditAPI] ❌ 处理失败: {e}")
            return (image, "", f"错误：处理失败 - {e}")

    def _image_to_base64(self, image):
        """
        将ComfyUI的IMAGE转换为base64格式
        返回格式：data:image/jpeg;base64,{base64_data}
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
            
            # 保存为JPEG格式并转换为base64
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=95)
            image_data_bytes_jpeg = output_buffer.getvalue()
            image_base64 = base64.b64encode(image_data_bytes_jpeg).decode('utf-8')
            return f"data:image/jpeg;base64,{image_base64}"
            
        except Exception as e:
            logger.error(f"[QwenImageEditAPI] 图像转换失败: {e}")
            raise

    def _download_and_convert_image(self, image_url, original_image):
        """
        下载并转换图像为ComfyUI格式
        """
        try:
            logger.info(f"[QwenImageEditAPI] ⬇️ 开始下载图像: {image_url}")
            
            # 下载图像
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            
            logger.info(f"[QwenImageEditAPI] 图像数据接收完毕 (大小: {len(response.content)/1024:.1f} KB)")
            
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
            
            logger.info(f"[QwenImageEditAPI] ✅ 图像解码并转换为Tensor成功: {image_tensor.shape}")
            return image_tensor
            
        except Exception as e:
            logger.error(f"[QwenImageEditAPI] ❌ 图像下载失败: {e}")
            return original_image

# 节点注册
NODE_CLASS_MAPPINGS = {
    "Qwen_ImageEdit_API": QwenImageEditAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen_ImageEdit_API": "🦉Qwen Image Edit API节点"
}
