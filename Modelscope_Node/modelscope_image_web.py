import os
import json
import requests
import time
import uuid
import random
from PIL import Image
from io import BytesIO
import torch
import numpy as np

# 节点主类
class ModelScopeImageWeb:
    """
    ComfyUI自定义节点：魔搭生图网页版
    支持文本到图像生成和图像到图像生成，调用魔搭的图像生成模型。
    支持最多三个Lora串联使用，实现更丰富的图像生成效果。
    
    功能特性：
    - 文生图模式：根据文本提示词生成图像
    - 图生图模式：基于参考图片进行图像转换和风格化
    - Lora支持：可串联使用最多3个Lora模型
    - 多种图片比例：支持1:1、4:3、16:9等多种比例
    
    输入参数：prompt, model, ratio, ref_image(可选), lora_name_1/2/3, lora_weight_1/2/3
    输出：image（生成的图片）, generation_info（生成信息）
    """
    def __init__(self):
        # 读取配置文件
        config_path = os.path.join(os.path.dirname(__file__), 'ms_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化API配置
        self.api_base_url = self.config.get('api_config', {}).get('base_url', 'https://www.modelscope.cn/api/v1/muse/predict')
        self.timeout = self.config.get('api_config', {}).get('timeout', 30)
        self.max_wait_time = self.config.get('api_config', {}).get('max_wait_time', 300)
        self.check_interval = self.config.get('api_config', {}).get('check_interval', 3)
        
        # 解析cookies
        self.cookies = self._parse_cookies(self.config.get('cookies', ''))
        
        # 构建请求头
        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': 'https://www.modelscope.cn',
            'Referer': 'https://www.modelscope.cn/aigc/imageGeneration',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'X-CSRF-TOKEN': self.config.get('csrf_token', ''),
            'X-Modelscope-Trace-Id': self._generate_trace_id(),
            'bx-v': '2.5.31',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'x-modelscope-accept-language': 'zh_CN'
        }
        
        # 加载模型配置
        self.models = self.config.get('models', {})
        
        # 加载lora配置
        self.lora_map = self.config.get('lora_map', {})
        
        # 加载比例配置
        self.ratio_map = self.config.get('ratio_map', {})
        self.ratios = self.config.get('ratios', [])

    @classmethod
    def INPUT_TYPES(cls):
        # 动态读取ModelScope模型选项
        config_path = os.path.join(os.path.dirname(__file__), 'ms_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            models = config.get('models', {})
        
        model_options = list(models.keys())
        if not model_options:
            model_options = ['qwen']  # 默认选项
        
        # 比例选项
        ratios = config.get('ratios', ['1:1', '1:2', '3:4', '4:3', '16:9', '9:16'])
        
        # Lora选项
        lora_map = config.get('lora_map', {})
        lora_options = ['none'] + list(lora_map.keys())
        
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "一只可爱的小猫咪"}),
                "model": (model_options, {"default": model_options[0]}),
                "ratio": (ratios, {"default": "1:1"}),
            },
            "optional": {
                "ref_image": ("IMAGE",),
                "lora_name_1": (lora_options, {"default": "none"}),
                "lora_weight_1": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 2.0, "step": 0.1}),
                "lora_name_2": (lora_options, {"default": "none"}),
                "lora_weight_2": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 2.0, "step": 0.1}),
                "lora_name_3": (lora_options, {"default": "none"}),
                "lora_weight_3": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 2.0, "step": 0.1}),
                "inference_steps": ("INT", {"default": 30, "min": 20, "max": 50, "step": 1}),
                "cfg_scale": ("FLOAT", {"default": 4.0, "min": 0.1, "max": 20.0, "step": 0.1}),
                "num_images": (["1", "2", "4"], {"default": "1"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "generation_info")
    FUNCTION = "generate"
    CATEGORY = "🦉FreeAPI/ModelScope"

    def generate(self, prompt, model, ratio, ref_image=None, lora_name_1="none", lora_weight_1=1.0, lora_name_2="none", lora_weight_2=1.0, lora_name_3="none", lora_weight_3=1.0, inference_steps=30, cfg_scale=4.0, num_images="1"):
        """
        主生成方法：
        调用ModelScope Image API进行文本到图像生成或图像到图像生成。
        支持最多三个Lora串联使用。
        
        Args:
            prompt: 文本提示词
            model: 使用的模型名称
            ratio: 图片比例（如1:1、4:3等）
            ref_image: 可选，参考图片（用于图生图模式）
            lora_name_1/2/3: Lora模型名称
            lora_weight_1/2/3: Lora权重（0.1-2.0）
            
        Returns:
            tuple: (生成的图片tensor, 生成信息JSON字符串)
        """
        try:
            # 判断是否为图生图模式
            is_img2img = ref_image is not None
            mode_text = "图生图" if is_img2img else "文生图"
            
            print(f"[魔搭生图网页版] 开始{mode_text}，参数: prompt='{prompt}', model='{model}', ratio='{ratio}'")
            print(f"[魔搭生图网页版] Lora参数: lora1='{lora_name_1}'(权重{lora_weight_1}), lora2='{lora_name_2}'(权重{lora_weight_2}), lora3='{lora_name_3}'(权重{lora_weight_3})")
            
            # 获取模型信息
            model_info = self.models.get(model, self.models.get('qwen', {}))
            if not model_info:
                raise ValueError(f"不支持的模型: {model}")
            
            # 收集所有有效的lora信息
            lora_list = []
            lora_names = []
            lora_weights = []
            
            # 检查第一个lora
            if lora_name_1 != "none":
                lora_config = self.lora_map.get(lora_name_1)
                if lora_config:
                    lora_list.append({
                        "name": lora_name_1,
                        "modelVersionId": int(lora_config.get("modelVersionId", "0")),
                        "scale": lora_weight_1
                    })
                    lora_names.append(lora_name_1)
                    lora_weights.append(lora_weight_1)
                    print(f"[魔搭生图网页版] 使用Lora1: {lora_name_1}, 权重: {lora_weight_1}")
                else:
                    print(f"[魔搭生图网页版] 警告: 不支持的Lora1: {lora_name_1}")
            
            # 检查第二个lora
            if lora_name_2 != "none":
                lora_config = self.lora_map.get(lora_name_2)
                if lora_config:
                    lora_list.append({
                        "name": lora_name_2,
                        "modelVersionId": int(lora_config.get("modelVersionId", "0")),
                        "scale": lora_weight_2
                    })
                    lora_names.append(lora_name_2)
                    lora_weights.append(lora_weight_2)
                    print(f"[魔搭生图网页版] 使用Lora2: {lora_name_2}, 权重: {lora_weight_2}")
                else:
                    print(f"[魔搭生图网页版] 警告: 不支持的Lora2: {lora_name_2}")
            
            # 检查第三个lora
            if lora_name_3 != "none":
                lora_config = self.lora_map.get(lora_name_3)
                if lora_config:
                    lora_list.append({
                        "name": lora_name_3,
                        "modelVersionId": int(lora_config.get("modelVersionId", "0")),
                        "scale": lora_weight_3
                    })
                    lora_names.append(lora_name_3)
                    lora_weights.append(lora_weight_3)
                    print(f"[魔搭生图网页版] 使用Lora3: {lora_name_3}, 权重: {lora_weight_3}")
                else:
                    print(f"[魔搭生图网页版] 警告: 不支持的Lora3: {lora_name_3}")
            
            # 根据lora触发词构建最终提示词
            final_prompt = self._build_prompt_with_trigger_words(prompt, lora_list) if lora_list else prompt
            if final_prompt != prompt:
                print(f"[魔搭生图网页版] 已添加触发词到提示词: '{final_prompt}'")

            # 处理图生图模式
            ref_image_url = None
            ref_image_id = None
            if is_img2img:
                # 上传参考图片并获取验证后的URL
                ref_image_url = self._upload_image(ref_image)
                if not ref_image_url:
                    raise RuntimeError("参考图片上传失败")
                
                # 获取图片尺寸信息（从tensor中获取原始尺寸）
                img_width, img_height = self._get_image_info(ref_image)
                
                # 注册图片到系统
                ref_image_id = self._register_image(ref_image_url, img_width, img_height)
                if not ref_image_id:
                    raise RuntimeError("参考图片注册失败")
                
                print(f"[魔搭生图网页版] 参考图片处理完成，URL: {ref_image_url}, ID: {ref_image_id}")

            # 判断使用快速模式还是专业模式
            has_lora = len(lora_list) > 0
            is_img2img = bool(ref_image_url)

            # 只要模型具备 checkpointModelVersionId，一律走专业模式（保证可用性与参数完整）
            if model_info.get("checkpointModelVersionId"):
                mode_type = "图生图" if is_img2img else "文生图"
                if has_lora:
                    print(f"[魔搭生图网页版] 使用专业模式提交任务（包含Lora配置）")
                else:
                    print(f"[魔搭生图网页版] 使用专业模式提交{mode_type}任务")
                task_id = self._submit_task_professional(final_prompt, model_info, ratio, lora_list, ref_image_url, ref_image_id, inference_steps, num_images, cfg_scale)
            else:
                # 无 checkpointModelVersionId 时回退到快速模式
                mode_type = "图生图" if is_img2img else "文生图"
                print(f"[魔搭生图网页版] 使用快速模式提交{mode_type}任务")
                task_id = self._submit_task_quick(final_prompt, model_info, ratio, ref_image_url, ref_image_id, num_images)
            
            if not task_id:
                raise RuntimeError("任务提交失败")
            
            print(f"[魔搭生图网页版] 任务提交成功，任务ID: {task_id}")
            
            # 等待任务完成（返回所有图片URL列表）
            image_urls = self._wait_for_completion(task_id)
            if not image_urls:
                raise RuntimeError("图片生成失败")
            
            # 获取剩余次数
            remaining_count = self._get_remaining_count()
            
            # 批量下载并转换为batch
            image_tensor = self._download_and_convert_images(image_urls)
            
            # 构建生成信息（兼容：保留第一张 image_url）
            generation_info = {
                "image_url": image_urls[0],
                "image_urls": image_urls,
                "remaining_count": remaining_count,
                "model": model,
                "ratio": ratio,
                "mode": mode_text,
                "lora_names": lora_names if lora_names else None,
                "lora_weights": lora_weights if lora_weights else None,
                "prompt_final": final_prompt,
                "prompt_original": prompt,
                "ref_image_url": ref_image_url if is_img2img else None,
                "ref_image_id": ref_image_id if is_img2img else None
            }
            
            print(f"[魔搭生图网页版] 图片生成成功，共 {len(image_urls)} 张: {image_urls}")
            print(f"[魔搭生图网页版] 剩余次数: {remaining_count}")
            
            return (image_tensor, json.dumps(generation_info, ensure_ascii=False))
            
        except Exception as e:
            print(f"[魔搭生图网页版] 生成失败: {str(e)}")
            raise RuntimeError(f"图片生成失败: {str(e)}")

    def _submit_task_professional(self, prompt, model_info, ratio, lora_list=None, ref_image_url=None, ref_image_id=None, inference_steps=30, num_images="1", cfg_scale=4.0):
        """
        专业模式提交任务（支持Lora配置和高级参数）
        Args:
            prompt: 提示词
            model_info: 模型信息
            ratio: 图片比例
            lora_list: lora信息列表，可选，最多支持3个lora串联
            ref_image_url: 参考图片URL，用于图生图
            ref_image_id: 参考图片ID，用于图生图
        Returns:
            str: 任务ID，失败返回None
        """
        try:
            # 判断是否为图生图模式
            is_img2img = ref_image_url is not None and ref_image_id is not None
            
            # 图生图模式或有lora时必须使用专业模式
            # 统一：若具备 checkpointModelVersionId 或为图生图，则使用专业模式，否则快速模式
            if is_img2img or model_info.get("checkpointModelVersionId"):
                # 使用专业模式支持图生图和多个lora串联
                url = f"{self.api_base_url}/task/submit"
                
                # 解析比例获取宽高
                width, height = self._parse_ratio_to_size(ratio)
                
                # 构建lora参数列表
                lora_args = []
                if lora_list:
                    for lora_info in lora_list:
                        lora_args.append({
                            "modelVersionId": lora_info["modelVersionId"],
                            "scale": lora_info["scale"]
                        })
                
                # 确定预测类型
                predict_type = "IMG_2_IMG" if is_img2img else "TXT_2_IMG"
                
                # 构建基础数据结构
                data = {
                    "modelArgs": {
                        "checkpointModelVersionId": model_info["checkpointModelVersionId"],
                        "loraArgs": lora_args,
                        "checkpointShowInfo": model_info.get("checkpointShowInfo", "")
                    },
                    "promptArgs": {
                        "prompt": prompt,
                        "negativePrompt": ""
                    },
                    "basicDiffusionArgs": {
                        "sampler": "Euler",
                        "guidanceScale": float(cfg_scale),
                        "seed": -1,
                        "numInferenceSteps": int(inference_steps),
                        "numImagesPerPrompt": int(num_images),
                        "width": width,
                        "height": height,
                        "advanced": False
                    },
                    "adetailerArgsMap": {},
                    "hiresFixFrontArgs": None,
                    "addWaterMark": False,
                    "advanced": False,
                    "predictType": predict_type,
                    "controlNetFullArgs": []
                }

                # 调试输出便于核验
                try:
                    print(f"[魔搭生图网页版] professional.basicDiffusionArgs: {json.dumps(data['basicDiffusionArgs'], ensure_ascii=False)}")
                except Exception:
                    pass
                
                # 如果是图生图，添加图片输入参数
                if is_img2img:
                    data["imageInputFrontArgs"] = {
                        "image": ref_image_url,
                        "imageId": ref_image_id
                    }
                
                if is_img2img:
                    print(f"[魔搭生图网页版] 使用专业模式提交图生图任务")
                elif lora_list:
                    lora_names = [lora["name"] for lora in lora_list]
                    print(f"[魔搭生图网页版] 使用专业模式提交任务，包含{len(lora_list)}个lora: {', '.join(lora_names)}")
                else:
                    print(f"[魔搭生图网页版] 使用专业模式提交任务")
            else:
                # 快速模式（无 checkpoint 且非图生图）
                url = f"{self.api_base_url}/task/quickSubmit"
                data = {
                    "predictType": "TXT_2_IMG",
                    "description": prompt,
                    "quickDiffusionArgs": {
                        "imageRatio": ratio,
                        "numImagesPerPrompt": int(num_images)
                    },
                    "styleType": model_info['styleType'],
                    "addWaterMark": False
                }
                # 调试输出便于核验
                try:
                    print(f"[魔搭生图网页版] quick.quickDiffusionArgs: {json.dumps(data['quickDiffusionArgs'], ensure_ascii=False)}")
                except Exception:
                    pass

                print(f"[魔搭生图网页版] 使用快速模式提交任务")
            
            response = requests.post(
                url,
                headers=self.headers,
                cookies=self.cookies,
                json=data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("Success") and result.get("Data", {}).get("success"):
                    task_id = result["Data"]["data"]["taskId"]
                    return task_id
                else:
                    print(f"[魔搭生图网页版] 任务提交失败: {result}")
                    return None
            else:
                print(f"[魔搭生图网页版] 任务提交HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[魔搭生图网页版] 提交任务时发生错误: {str(e)}")
            return None

    def _submit_task_quick(self, prompt, model_info, ratio, ref_image_url=None, ref_image_id=None, num_images="1"):
        """
        快速模式提交任务（文生图或图生图）
        Args:
            prompt: 提示词
            model_info: 模型信息
            ratio: 图片比例
            ref_image_url: 参考图片URL（可选，图生图时使用）
            ref_image_id: 参考图片ID（可选，图生图时使用）
        Returns:
            str: 任务ID，失败返回None
        """
        try:
            url = "https://www.modelscope.cn/api/v1/muse/predict/task/quickSubmit"
            
            # 构建快速模式的基础数据
            data = {
                "styleType": model_info["styleType"],
                "addWaterMark": False,
                "quickDiffusionArgs": {
                    "imageRatio": ratio,
                    "numImagesPerPrompt": int(num_images)
                }
            }
            
            # 判断是文生图还是图生图
            if ref_image_url and ref_image_id:
                # 图生图模式
                data["predictType"] = "IMG_2_IMG"
                data["description"] = prompt
                data["imageInputFrontArgs"] = {
                    "image": ref_image_url,
                    "imageId": ref_image_id
                }
            else:
                # 文生图模式
                data["predictType"] = "TXT_2_IMG"
                data["description"] = prompt
            
            response = requests.post(
                url,
                headers=self.headers,
                cookies=self.cookies,
                json=data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("Success") and result.get("Data", {}).get("success"):
                    task_id = result["Data"]["data"]["taskId"]
                    return task_id
                else:
                    print(f"[魔搭生图网页版] 快速模式任务提交失败: {result}")
                    return None
            else:
                print(f"[魔搭生图网页版] 快速模式任务提交HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[魔搭生图网页版] 快速模式提交任务时发生错误: {str(e)}")
            return None

    def _wait_for_completion(self, task_id):
        """
        等待任务完成
        Args:
            task_id: 任务ID
        Returns:
            list[str] | None: 图片URL列表，失败返回None
        """
        start_time = time.time()
        
        while time.time() - start_time < self.max_wait_time:
            try:
                status_info = self._check_task_status(task_id)
                if not status_info:
                    time.sleep(self.check_interval)
                    continue
                
                status = status_info.get("status")
                
                if status == "SUCCEED":
                    # 任务成功，获取所有图片URL
                    predict_result = status_info.get("predictResult", {})
                    images = predict_result.get("images", [])
                    urls = []
                    for item in images or []:
                        u = item.get("imageUrl")
                        if u:
                            urls.append(u)
                    if urls:
                        print(f"[魔搭生图网页版] 图片生成成功，共 {len(urls)} 张")
                        for i, u in enumerate(urls):
                            print(f"[魔搭生图网页版] 第{i+1}张: {u}")
                        return urls
                    print("[魔搭生图网页版] 任务成功但未找到图片URL")
                    return None
                
                elif status == "FAILED":
                    error_msg = status_info.get("errorMsg", "未知错误")
                    print(f"[魔搭生图网页版] 任务失败: {error_msg}")
                    return None
                
                elif status == "PENDING":
                    # 任务排队中
                    progress = status_info.get("progress", {})
                    detail = progress.get("detail", "排队中")
                    print(f"[魔搭生图网页版] {detail}")
                
                # 等待后继续检查
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"[魔搭生图网页版] 检查任务状态时发生错误: {str(e)}")
                time.sleep(self.check_interval)
        
        print(f"[魔搭生图网页版] 任务超时，等待时间: {self.max_wait_time}秒")
        return None

    def _check_task_status(self, task_id):
        """
        检查任务状态
        Args:
            task_id: 任务ID
        Returns:
            dict: 任务状态信息，失败返回None
        """
        try:
            url = f"{self.api_base_url}/task/status"
            params = {"taskId": task_id}
            
            response = requests.get(
                url,
                headers=self.headers,
                cookies=self.cookies,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("Success") and result.get("Data", {}).get("success"):
                    return result["Data"]["data"]
                else:
                    print(f"[魔搭生图网页版] 检查任务状态失败: {result}")
                    return None
            else:
                print(f"[魔搭生图网页版] 检查任务状态HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[魔搭生图网页版] 检查任务状态时发生错误: {str(e)}")
            return None

    def _get_remaining_count(self):
        """
        获取剩余次数
        Returns:
            dict: 包含total, used, remaining的字典
        """
        try:
            url = f"{self.api_base_url}/queryAIGCTicketAndQuotaNum"
            params = {"type": "IMAGE"}
            
            response = requests.get(
                url,
                headers=self.headers,
                cookies=self.cookies,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("Success") and result.get("Data", {}).get("success"):
                    data = result["Data"]["data"]
                    total = data.get("quotaNum", 0)
                    used = data.get("quotaUsed", 0)
                    remaining = total - used
                    return {
                        "total": total,
                        "used": used,
                        "remaining": remaining
                    }
            
            # 如果获取失败，返回默认值
            return {"total": 50, "used": 0, "remaining": 50}
                
        except Exception as e:
            print(f"[魔搭生图网页版] 获取剩余次数时发生错误: {str(e)}")
            return {"total": 50, "used": 0, "remaining": 50}

    def _download_and_convert_image(self, image_url):
        """
        下载单张图片并转换为ComfyUI的IMAGE格式（保留供内部复用）
        """
        try:
            print(f"[魔搭生图网页版] 开始下载图片: {image_url}")
            resp = requests.get(image_url, timeout=60)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            np_image = np.array(img, dtype=np.float32) / 255.0
            tensor_image = torch.from_numpy(np_image).unsqueeze(0)
            return tensor_image
        except Exception as e:
            print(f"[魔搭生图网页版] 错误详情: {e}")
            raise RuntimeError(f"图片下载或转换失败: {e}")

    def _download_and_convert_images(self, image_urls):
        """
        批量下载图片并堆叠为 [N, H, W, 3] 的 batch 张量
        - 若尺寸不一致，自动以第一张尺寸为目标进行统一 resize
        """
        tensors = []
        target_size = None  # (width, height)
        for idx, url in enumerate(image_urls):
            try:
                print(f"[魔搭生图网页版] 开始下载第{idx+1}张: {url}")
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                if target_size is None:
                    target_size = img.size  # (W,H)
                else:
                    if img.size != target_size:
                        # 统一尺寸
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                        print(f"[魔搭生图网页版] 尺寸不一致，已统一到: {target_size[0]}x{target_size[1]}")
                np_image = np.array(img, dtype=np.float32) / 255.0
                tensor_image = torch.from_numpy(np_image).unsqueeze(0)  # [1,H,W,3]
                tensors.append(tensor_image)
            except Exception as e:
                print(f"[魔搭生图网页版] 第{idx+1}张下载失败: {e}")
                continue
        if not tensors:
            raise RuntimeError("所有图片下载失败")
        batch = torch.cat(tensors, dim=0)  # [N,H,W,3]
        print(f"[魔搭生图网页版] 最终tensor batch: 形状={batch.shape}, dtype={batch.dtype}")
        return batch

    def _parse_ratio_to_size(self, ratio):
        """
        将比例转换为宽高
        Args:
            ratio: 比例字符串，如 "1:1", "9:16"
        Returns:
            tuple: (width, height)
        """
        try:
            # 从配置中直接获取分辨率
            if ratio in self.ratio_map:
                size_info = self.ratio_map[ratio]
                width = size_info["width"]
                height = size_info["height"]
                print(f"[魔搭生图网页版] 比例 {ratio} 对应分辨率: {width}x{height}")
                return width, height
            else:
                print(f"[魔搭生图网页版] 不支持的比例 {ratio}，使用默认分辨率 1328x1328")
                return 1328, 1328
        except Exception as e:
            print(f"[魔搭生图网页版] 解析比例时发生错误: {str(e)}")
            return 1328, 1328

    def _build_prompt_with_trigger_words(self, prompt, lora_list):
        """
        当存在lora的触发词时，将触发词添加到提示词开头（中文逗号分隔）
        Args:
            prompt (str): 原始提示词
            lora_list (list[dict]): 解析到的lora信息列表（元素含有 name, modelVersionId, scale）
        Returns:
            str: 处理后的提示词
        """
        try:
            if not lora_list:
                return prompt

            trigger_words = []
            for lora in lora_list:
                lora_name = lora.get("name")
                if not lora_name:
                    continue
                lora_def = self.lora_map.get(lora_name)
                if not lora_def:
                    continue
                trigger_word = str(lora_def.get("triggerWord", "")).strip()
                if trigger_word:
                    trigger_words.append(trigger_word)

            if not trigger_words:
                return prompt

            # 去重但保持顺序
            seen = set()
            ordered_unique = []
            for tw in trigger_words:
                if tw not in seen:
                    seen.add(tw)
                    ordered_unique.append(tw)

            prefix = "，".join(ordered_unique)
            if not prefix:
                return prompt

            return f"{prefix}，{prompt}".strip()
        except Exception as e:
            print(f"[魔搭生图网页版] 构建触发词提示时发生错误: {str(e)}")
            return prompt

    def _parse_cookies(self, cookie_string):
        """
        将cookie字符串转换为字典
        Args:
            cookie_string: cookie字符串，格式如 "name1=value1; name2=value2"
        Returns:
            dict: cookie字典
        """
        if not cookie_string:
            return {}
        
        cookies = {}
        try:
            # 分割cookie字符串
            cookie_pairs = cookie_string.split(';')
            for pair in cookie_pairs:
                pair = pair.strip()
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    cookies[name.strip()] = value.strip()
        except Exception as e:
            print(f"[魔搭生图网页版] 解析cookie字符串时发生错误: {str(e)}")
            return {}
        
        return cookies

    def _generate_trace_id(self):
        """生成跟踪ID"""
        return str(uuid.uuid4())

    def _upload_image(self, image_tensor):
        """
        上传图片到ModelScope
        Args:
            image_tensor: ComfyUI的IMAGE tensor格式
        Returns:
            str: 上传后的图片URL，失败返回None
        """
        try:
            print(f"[魔搭生图网页版] 开始上传参考图片")
            
            # 将tensor转换为PIL图片
            import io
            if image_tensor.dim() == 4:
                # 移除batch维度
                image_tensor = image_tensor.squeeze(0)
            
            # 转换为numpy数组并缩放到0-255
            np_image = (image_tensor.cpu().numpy() * 255).astype(np.uint8)
            pil_image = Image.fromarray(np_image)
            
            # 检查图片尺寸，如果太大则压缩
            width, height = pil_image.size
            max_size = 2048  # 最大尺寸限制
            if width > max_size or height > max_size:
                # 按比例缩放
                ratio = min(max_size / width, max_size / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"[魔搭生图网页版] 图片尺寸过大，已压缩: {width}x{height} -> {new_width}x{new_height}")
            
            # 保存为字节流，使用合适的质量设置
            img_buffer = io.BytesIO()
            pil_image.save(img_buffer, format='PNG', optimize=True)
            img_data = img_buffer.getvalue()
            
            # 生成文件名（默认PNG）
            filename = f"ms__{int(time.time() * 1000)}.png"
            
            # 检查文件大小（OSS通常有5MB限制）
            max_file_size = 5 * 1024 * 1024  # 5MB
            if len(img_data) > max_file_size:
                print(f"[魔搭生图网页版] 文件过大({len(img_data)} bytes)，尝试JPEG压缩")
                img_buffer = io.BytesIO()
                pil_image.save(img_buffer, format='JPEG', quality=85, optimize=True)
                img_data = img_buffer.getvalue()
                filename = f"ms__{int(time.time() * 1000)}.jpg"  # 更改为jpg扩展名
                print(f"[魔搭生图网页版] 压缩后文件大小: {len(img_data)} bytes")
            
            # 第零步：获取图片类型配置（重要的预处理步骤）
            print(f"[魔搭生图网页版] 开始获取图片类型配置...")
            if not self._get_image_type():
                print(f"[魔搭生图网页版] 获取图片类型失败，无法继续上传")
                return None
            
            # 第一步：获取上传URL
            upload_url_resp = self._get_upload_url(filename)
            if not upload_url_resp:
                print(f"[魔搭生图网页版] 获取上传URL失败，可能是认证问题")
                return None
            
            # 简化的认证检查
            if not self.cookies or not self.headers.get('X-CSRF-TOKEN'):
                print(f"[魔搭生图网页版] 错误：认证信息不完整")
                return None
            
            upload_url = upload_url_resp['UploadUrl']
            print(f"[魔搭生图网页版] 获取上传URL成功")
            print(f"[魔搭生图网页版] 上传URL: {upload_url[:100]}...")
            
            # 简化的URL验证
            import urllib.parse
            from urllib.parse import urlparse, parse_qs
            
            parsed_url = urlparse(upload_url)
            query_params = parse_qs(parsed_url.query)
            expires = query_params.get('Expires', [''])[0]
            
            # 简单的过期检查
            if expires.isdigit():
                current_time = int(time.time())
                expires_time = int(expires)
                if current_time > expires_time:
                    print(f"[魔搭生图网页版] 错误：上传URL已过期")
                    return None
            
            # 第二步：上传图片到OSS
            print(f"[魔搭生图网页版] 开始上传到OSS，图片大小: {len(img_data)} bytes")
            
            try:
                # 使用curl上传图片到OSS（已解决签名问题）
                print(f"[魔搭生图网页版] 上传图片到OSS...")
                
                import tempfile
                import subprocess
                
                # 创建临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                    temp_file.write(img_data)
                    temp_file_path = temp_file.name
                
                try:
                    # 关键修复：使用完整的浏览器头部，特别是Content-Type和OSS元数据
                    curl_cmd = [
                        'curl', '-X', 'PUT',
                        '--data-binary', f'@{temp_file_path}',
                        '--header', 'Accept: application/json, text/plain, */*',
                        '--header', 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                        '--header', 'Connection: keep-alive',
                        '--header', f'Content-Length: {len(img_data)}',
                        '--header', 'Content-Type: application/octet-stream',  # 关键！
                        '--header', 'Origin: https://www.modelscope.cn',
                        '--header', 'Referer: https://www.modelscope.cn/',
                        '--header', 'Sec-Fetch-Dest: empty',
                        '--header', 'Sec-Fetch-Mode: cors',
                        '--header', 'Sec-Fetch-Site: cross-site',
                        '--header', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0',
                        '--header', 'sec-ch-ua: "Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"',
                        '--header', 'sec-ch-ua-mobile: ?0',
                        '--header', 'sec-ch-ua-platform: "Windows"',
                        '--header', 'x-oss-meta-author: aliy',  # OSS元数据头部
                        '--silent',  # 静默模式，减少输出
                        '--max-time', '60',
                        upload_url
                    ]
                    
                    result = subprocess.run(
                        curl_cmd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if result.returncode == 0:
                        print(f"[魔搭生图网页版] curl上传成功！")
                        upload_success = True
                    else:
                        print(f"[魔搭生图网页版] curl上传失败")
                        upload_success = False
                        
                except subprocess.TimeoutExpired:
                    print(f"[魔搭生图网页版] curl超时")
                    upload_success = False
                except Exception as e:
                    print(f"[魔搭生图网页版] curl异常: {str(e)}")
                    upload_success = False
                finally:
                    # 清理临时文件
                    try:
                        import os
                        os.unlink(temp_file_path)
                    except:
                        pass
                
                # 为了兼容后续代码，创建一个模拟的response对象
                class MockResponse:
                    def __init__(self, success):
                        self.status_code = 200 if success else 403
                        self.headers = {}
                        self.text = ""
                        
                upload_response = MockResponse(upload_success)
                
            except Exception as e:
                print(f"[魔搭生图网页版] 上传过程异常: {str(e)}")
                return None
            
            print(f"[魔搭生图网页版] OSS响应状态码: {upload_response.status_code}")
            if upload_response.status_code != 200:
                print(f"[魔搭生图网页版] OSS响应头: {dict(upload_response.headers)}")
                print(f"[魔搭生图网页版] OSS响应内容: {upload_response.text[:500]}")
                print(f"[魔搭生图网页版] 图片上传失败: {upload_response.status_code}")
                return None
            
            # 从上传URL中提取实际的文件URL
            file_url = upload_url.split('?')[0]  # 移除查询参数
            print(f"[魔搭生图网页版] 图片上传成功: {file_url}")
            
            # 第三步：验证上传的图片（调用downloadUrl API）
            download_info = self._verify_uploaded_image(file_url)
            if download_info:
                # 格式化尺寸信息显示
                download_info_detail = download_info.get('DownloadInfo', {})
                width = download_info_detail.get('ImageWidth', 'Unknown')
                height = download_info_detail.get('ImageHeight', 'Unknown')
                print(f"[魔搭生图网页版] 图片验证成功，尺寸: {width}x{height}")
                return download_info.get('DownloadUrl', file_url)
            else:
                print(f"[魔搭生图网页版] 图片验证失败，使用原始URL")
                return file_url
            
        except Exception as e:
            print(f"[魔搭生图网页版] 上传图片时发生错误: {str(e)}")
            return None

    def _get_image_type(self):
        """
        获取图片类型配置（必需的预处理步骤）
        这个步骤用于初始化上传会话和验证用户权限
        Returns:
            bool: 成功返回True，失败返回False
        """
        try:
            url = "https://www.modelscope.cn/api/v1/muse/image/getImageType"
            
            # 添加必需的头部
            headers = self.headers.copy()
            headers['X-Modelscope-Trace-Id'] = f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
            
            response = requests.get(
                url,
                headers=headers,
                cookies=self.cookies,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('Success') and result.get('Data', {}).get('success'):
                    data = result['Data']['data']
                    image_types = [item['label'] for item in data]
                    print(f"[魔搭生图网页版] 获取图片类型成功: {image_types}")
                    
                    # 检查是否包含上传图片类型
                    has_upload = any(item['value'] == 'MUSE_UPLOAD' for item in data)
                    if has_upload:
                        print(f"[魔搭生图网页版] 确认支持图片上传功能")
                        return True
                    else:
                        print(f"[魔搭生图网页版] 警告：未找到图片上传类型")
                        return False
                else:
                    print(f"[魔搭生图网页版] 获取图片类型响应异常: {result}")
                    return False
            else:
                print(f"[魔搭生图网页版] 获取图片类型请求失败: {response.status_code}")
                if response.status_code == 403:
                    print(f"[魔搭生图网页版] 可能是认证问题，请检查cookies和CSRF token")
                return False
                
        except Exception as e:
            print(f"[魔搭生图网页版] 获取图片类型异常: {str(e)}")
            return False

    def _get_upload_url(self, filename):
        """
        获取图片上传URL
        Args:
            filename: 文件名
        Returns:
            dict: 包含UploadUrl的响应数据，失败返回None
        """
        try:
            url = "https://www.modelscope.cn/api/v1/rm/uploadUrl"
            data = {
                "FileName": filename,
                "Type": "AIGC_MUSE_IMG_PRIVATEZONE"
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                cookies=self.cookies,
                json=data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("Success") and result.get("Data"):
                    return result["Data"]
                else:
                    print(f"[魔搭生图网页版] 获取上传URL失败: {result}")
                    return None
            else:
                print(f"[魔搭生图网页版] 获取上传URL HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[魔搭生图网页版] 获取上传URL时发生错误: {str(e)}")
            return None

    def _verify_uploaded_image(self, file_url):
        """
        验证上传的图片（调用downloadUrl接口）
        Args:
            file_url: 图片文件URL
        Returns:
            dict: 包含DownloadUrl和图片信息的响应数据，失败返回None
        """
        try:
            url = "https://www.modelscope.cn/api/v1/rm/downloadUrl"
            data = {
                "FileUrl": file_url,
                "Type": "AIGC_MUSE_IMG_PRIVATEZONE"
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                cookies=self.cookies,
                json=data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("Success") and result.get("Data"):
                    return result["Data"]
                else:
                    print(f"[魔搭生图网页版] 图片验证失败: {result}")
                    return None
            else:
                print(f"[魔搭生图网页版] 图片验证HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[魔搭生图网页版] 验证图片时发生错误: {str(e)}")
            return None

    def _register_image(self, image_url, width, height):
        """
        将上传的图片注册到ModelScope系统
        Args:
            image_url: 图片URL
            width: 图片宽度
            height: 图片高度
        Returns:
            int: 图片ID，失败返回None
        """
        try:
            print(f"[魔搭生图网页版] 开始注册图片到系统")
            
            url = "https://www.modelscope.cn/api/v1/muse/image/create"
            data = [{
                "url": image_url,
                "width": str(width),
                "height": str(height),
                "sourceType": "MUSE_UPLOAD",
                "index": 0
            }]
            
            response = requests.post(
                url,
                headers=self.headers,
                cookies=self.cookies,
                json=data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("Success") and result.get("Data", {}).get("success"):
                    image_data = result["Data"]["data"]
                    if image_data and len(image_data) > 0:
                        image_id = image_data[0].get("id")
                        print(f"[魔搭生图网页版] 图片注册成功，ID: {image_id}")
                        return image_id
                    else:
                        print(f"[魔搭生图网页版] 图片注册失败: 无数据返回")
                        return None
                else:
                    print(f"[魔搭生图网页版] 图片注册失败: {result}")
                    return None
            else:
                print(f"[魔搭生图网页版] 图片注册HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[魔搭生图网页版] 注册图片时发生错误: {str(e)}")
            return None

    def _get_image_info(self, image_tensor):
        """
        获取图片的宽高信息
        Args:
            image_tensor: ComfyUI的IMAGE tensor格式
        Returns:
            tuple: (width, height)
        """
        if image_tensor.dim() == 4:
            # 格式: [batch, height, width, channels]
            height, width = image_tensor.shape[1], image_tensor.shape[2]
        elif image_tensor.dim() == 3:
            # 格式: [height, width, channels]
            height, width = image_tensor.shape[0], image_tensor.shape[1]
        else:
            # 默认尺寸
            height, width = 1024, 1024
        
        return width, height

# 节点注册
NODE_CLASS_MAPPINGS = {
    "ModelScope_Image_Web": ModelScopeImageWeb
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ModelScope_Image_Web": "🦉魔搭生图网页版"
}
