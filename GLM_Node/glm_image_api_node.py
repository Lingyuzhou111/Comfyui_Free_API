import os
import json
import requests
import time
import jwt
from PIL import Image
from io import BytesIO
import torch
import numpy as np

# 节点主类
class GLMImageAPI:
    """
    ComfyUI自定义节点：GLM Image API
    支持文本到图像生成，调用智谱AI的图像生成模型。
    输入参数：model, quality, size, prompt
    输出：image（生成的图片）
    """
    def __init__(self):
        # 读取配置文件，专门读取IMAGE.glm_image配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = config.get('IMAGE', {}).get('glm_image', {})

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取GLM图像模型选项
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            glm_config = config.get('IMAGE', {}).get('glm_image', {})
        model_options = glm_config.get('model', ['cogview-4-250304'])
        
        # 质量选项
        quality_options = ["standard", "hd"]
        
        # 尺寸选项
        size_options = [
            "1024x1024",
            "768x1344", 
            "864x1152",
            "1344x768",
            "1152x864",
            "1440x720",
            "720x1440"
        ]
        
        return {
            "required": {
                "model": (model_options, {"default": model_options[0]}),
                "quality": (quality_options, {"default": "standard"}),
                "size": (size_options, {"default": "1024x1024"}),
                "prompt": ("STRING", {"multiline": True, "default": "一只可爱的小猫咪"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "generate"
    CATEGORY = "API/GLM"

    def generate(self, model, quality, size, prompt):
        """
        主生成方法：
        调用GLM Image API进行文本到图像生成。
        """
        # 读取GLM API参数
        base_url = self.config.get('base_url', 'https://open.bigmodel.cn/api/paas/v4/images/generations')
        api_key = self.config.get('api_key', '')
        
        if not api_key:
            raise ValueError("错误：未配置GLM API Key，请在config.json中设置glm_image.api_key")
        
        # 构造API请求
        payload = {
            "model": model,
            "prompt": prompt,
            "quality": quality,
            "size": size
        }
        
        # 发送请求并解析响应
        try:
            headers = self._build_headers(api_key)
            resp = requests.post(base_url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            return self._parse_response(resp)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API请求失败: {e}")
        except Exception as e:
            raise RuntimeError(f"处理失败: {e}")

    def _parse_response(self, resp):
        """
        解析GLM Image API响应，下载图片并转换为ComfyUI格式
        """
        try:
            data = resp.json()
            print(f"[GLM Image API] API响应: {data}")
            
            if "data" in data and data["data"]:
                image_url = data["data"][0]["url"]
                print(f"[GLM Image API] 图片URL: {image_url}")
                return self._download_and_convert_image(image_url)
            else:
                raise RuntimeError(f"API返回异常: {str(data)}")
        except Exception as e:
            raise RuntimeError(f"响应解析失败: {e}")

    def _download_and_convert_image(self, image_url):
        """
        下载图片并转换为ComfyUI的IMAGE格式
        """
        try:
            print(f"[GLM Image API] 开始下载图片: {image_url}")
            
            # 下载图片
            resp = requests.get(image_url, timeout=60)
            resp.raise_for_status()
            print(f"[GLM Image API] 图片下载成功，大小: {len(resp.content)} bytes")
            
            # 使用PIL打开图片并转换为RGB
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            print(f"[GLM Image API] 图片信息: 尺寸={img.size}, 模式={img.mode}")
            
            # 转换为numpy数组，参考jimeng_image_node.py的处理方式
            np_image = np.array(img, dtype=np.float32) / 255.0
            print(f"[GLM Image API] 数组信息: 形状={np_image.shape}, 数据类型={np_image.dtype}")
            
            # 转换为torch.Tensor并添加batch维度，参考jimeng_image_node.py
            tensor_image = torch.from_numpy(np_image).unsqueeze(0)
            print(f"[GLM Image API] 最终tensor: 形状={tensor_image.shape}, 数据类型={tensor_image.dtype}")
            
            return (tensor_image,)
            
        except Exception as e:
            print(f"[GLM Image API] 错误详情: {e}")
            raise RuntimeError(f"图片下载或转换失败: {e}")

    def _build_headers(self, api_key):
        """
        构建GLM API请求头，包含JWT认证
        """
        try:
            api_key_id, api_key_secret = api_key.split('.')
            payload = {
                "api_key": api_key_id,
                "exp": int(round(time.time() * 1000)) + 3600 * 1000,
                "timestamp": int(round(time.time() * 1000)),
            }
            token = jwt.encode(payload, api_key_secret, algorithm="HS256", headers={"alg": "HS256", "sign_type": "SIGN"})
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        except Exception as e:
            return {"Authorization": "Bearer error", "Content-Type": "application/json"}

# 节点注册
NODE_CLASS_MAPPINGS = {
    "GLM_Image_API": GLMImageAPI
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "GLM_Image_API": "GLM Image API节点"
} 