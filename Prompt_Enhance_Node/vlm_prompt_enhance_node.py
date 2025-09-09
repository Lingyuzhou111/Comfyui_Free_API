# -*- coding: utf-8 -*-
"""
VLM Prompt Enhance Node

功能:
- 从 ComfyUI/custom_nodes/Comfyui_Free_API/config.json 的 "VLM" 段读取提供方、base_url、api_key、model 列表
- 在 ComfyUI 中提供一个节点，允许用户选择 "vlm_model"（展示为 "提供方:型号"）
- 读取 Prompt_Enhance_Node/vlm_sys_prompt .json 中的系统提示词模版名称作为下拉选项（若文件为空或不存在，则提供内置默认模版）
- 接收用户 user_prompt、image1、image2、max_tokens、temperature、top_p；当 preset_template 选择“手动输入”时，使用 sys_prompt 文本框内容作为系统提示词
- 按 OpenAI 兼容 Chat Completions 接口格式调用对应 base_url（需 /chat/completions），支持图文输入识别/反推等操作（可零图或多图）
- 输出:
  1) input_prompt: 展示最终提交给 API 的 system_prompt + user_prompt（便于检查上下文）
  2) output_prompt: API 响应生成内容

注意:
- 本实现仅用于合法、正当的提示词优化/图文理解，不包含任何恶意用途。
"""

import json
import os
import re
import time
import io
import base64
from typing import Dict, Any, List, Tuple, Optional

try:
    import requests
except Exception:
    requests = None

# 可选依赖
try:
    import numpy as np
except Exception:
    np = None

try:
    from PIL import Image
except Exception:
    Image = None


def _load_config(config_path: str) -> Dict[str, Any]:
    try:
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception:
        return {}


def _load_sys_templates(templates_path: str) -> Dict[str, str]:
    """
    期望文件格式:
    {
      "模板中文名A": "这里是system prompt内容A",
      "模板中文名B": "这里是system prompt内容B"
    }
    若文件为空或不存在，则返回默认模版集合。
    """
    defaults = {
        "图文理解:精确描述": (
            "你是资深视觉理解专家。请对输入图像进行客观、具体的英文描述，覆盖主体、场景、构图、光线、颜色、材质、文字信息、动作与关系；"
            "避免臆测不可见信息，避免冗余，重要信息靠前。仅输出英文描述。"
        ),
        "反推提示词:StableDiffusion风格": (
            "你是提示词反推工程师。请基于图像内容产出适用于图像生成模型的英文提示词，包含主体、风格、镜头、光效、构图、材质、分辨率关键词，"
            "并提供必要的负面提示词（negative prompts）。仅输出最终提示词文本。"
        ),
        "OCR与布局:要点提取": (
            "你是OCR与版面分析助理。识别图中文字与关键元素的空间布局（左/右/上/下、相邻关系），"
            "以结构化英文段落输出，不输出多余解释。"
        ),
    }
    try:
        if not os.path.exists(templates_path):
            return defaults
        with open(templates_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return defaults
            data = json.loads(content)
            if isinstance(data, dict) and data:
                cleaned = {str(k): str(v) for k, v in data.items() if isinstance(k, str)}
                return cleaned or defaults
            return defaults
    except Exception:
        return defaults


def _build_vlm_options(config: Dict[str, Any]) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    """
    返回:
    - options: ["提供方:型号", ...]
    - map_info: {"提供方:型号": {"base_url": "...", "api_key": "...", "model": "型号"}}
    """
    options: List[str] = []
    map_info: Dict[str, Dict[str, str]] = {}
    if not config:
        return options, map_info

    vlm = config.get("VLM", {})
    for provider, info in vlm.items():
        try:
            base_url = str(info.get("base_url", "")).strip()
            api_key = str(info.get("api_key", "")).strip()
            models = info.get("model", [])
            if not isinstance(models, list):
                continue
            for m in models:
                model_name = str(m).strip()
                label = f"{provider}:{model_name}".replace("：", ":")
                options.append(label)
                map_info[label] = {"base_url": base_url, "api_key": api_key, "model": model_name}
        except Exception:
            continue
    return options, map_info


def _normalize_base_url(url: str) -> str:
    u = url.strip()
    u = re.sub(r"\s+", " ", u).strip()
    u = u.rstrip("/")
    return u


def _image_tensor_to_data_url(img) -> Optional[str]:
    """
    将ComfyUI的IMAGE张量转为 data:image/png;base64,... 字符串
    支持: torch.Tensor 或 numpy.ndarray 或 PIL.Image
    """
    try:
        if img is None:
            return None
        try:
            import torch
        except Exception:
            torch = None

        array = None
        if torch is not None and isinstance(img, torch.Tensor):
            t = img
            if t.dim() == 4:
                t = t[0]
            if t.shape[0] in (3, 4):
                t = t.permute(1, 2, 0)
            t = t.detach().cpu().float().clamp(0, 1).numpy()
            array = (t * 255.0).round().astype("uint8")
        elif np is not None and isinstance(img, np.ndarray):
            array = img
            if array.dtype != np.uint8:
                array = (np.clip(array, 0, 1) * 255.0).round().astype("uint8")
        elif Image is not None and isinstance(img, Image.Image):
            pass
        else:
            return None

        if Image is None:
            return None

        if isinstance(img, Image.Image):
            pil = img
        else:
            if array.ndim == 2:
                mode = "L"
            elif array.shape[2] == 4:
                mode = "RGBA"
            else:
                mode = "RGB"
            pil = Image.fromarray(array, mode=mode)

        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def _chat_completions_with_images(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_urls: List[str],
    max_tokens: int,
    temperature: float,
    top_p: float,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """
    OpenAI 兼容接口，图文输入:
      POST {base_url}/chat/completions
    messages:
      - system: system_prompt
      - user: [{"type":"text","text": ...}, {"type":"image_url","image_url":{"url": ...}}, ...]
    """
    if requests is None:
        return False, "requests 库不可用，请安装后重试。"

    try:
        url = _normalize_base_url(base_url) + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        user_content = []
        if user_prompt:
            user_content.append({"type": "text", "text": user_prompt})
        for u in image_urls:
            user_content.append({"type": "image_url", "image_url": {"url": u}})

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content if user_content else user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {resp.text}"

        data = resp.json()
        if isinstance(data, dict):
            choices = data.get("choices") or []
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return True, content.strip()
                for key in ["reasoning_content", "text", "output", "answer"]:
                    val = msg.get(key)
                    if isinstance(val, str) and val.strip():
                        return True, val.strip()
            for key in ["output", "answer", "text", "message"]:
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    return True, v.strip()
        return False, json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return False, f"Exception: {e}"


class VLM_Prompt_Enhance_Node:
    """
    ComfyUI 节点定义:
    - 输入:
        1) vlm_model: 下拉，来自 config.json 的 VLM 组合项 ("提供方:型号")
        2) preset_template: 下拉，首位为“手动输入”，其余来自 vlm_sys_prompt .json；如果文件为空则提供内置模版
        3) sys_prompt: 文本框（sys_prompt，自定义系统提示词仅在预设模板为“手动输入”时才生效）
        4) user_prompt: 文本框
        5) max_tokens: 整数（默认 2048）
        6) temperature: 浮点（默认 0.8）
        7) top_p: 浮点（默认 0.6）
    - 可选:
        8) image1: IMAGE（可选）
        9) image2: IMAGE（可选）
    - 输出:
        1) input_prompt: str（system + user 最终提交内容）
        2) output_prompt: str（API 响应增强结果）
    """

    @classmethod
    def INPUT_TYPES(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # custom_nodes/Comfyui_Free_API
        config_path = os.path.join(base_dir, "config.json")
        templates_path = os.path.join(os.path.dirname(__file__), "vlm_sys_prompt .json")

        config = _load_config(config_path)
        vlm_options, _ = _build_vlm_options(config)
        if not vlm_options:
            vlm_options = []

        sys_templates = _load_sys_templates(templates_path)
        template_names = ["手动输入"] + (list(sys_templates.keys()) if sys_templates else ["图文理解:精确描述"])

        return {
            "required": {
                "vlm_model": (vlm_options if vlm_options else ["未检测到模型配置"],),
                "preset_template": (template_names,),
                "sys_prompt": ("STRING", {"multiline": True, "default": "自定义系统提示词仅在预设模板为“手动输入”时才会生效", "tooltip": "当选择“手动输入”时，此处作为system提示词使用"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "无需任何解释和铺垫，直接输出结果"}),
                "max_tokens": ("INT", {"default": 2048, "min": 1, "max": 8192, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("input_prompt", "output_prompt")
    FUNCTION = "enhance"
    CATEGORY = "🦉FreeAPI/Prompt Enhance"

    def __init__(self):
        self._cached_map_info: Optional[Dict[str, Dict[str, str]]] = None
        self._cached_templates: Optional[Dict[str, str]] = None
        self._last_reload_ts: float = 0.0

    def _maybe_reload(self):
        now = time.time()
        if now - self._last_reload_ts < 2.0:
            return
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # custom_nodes/Comfyui_Free_API
        config_path = os.path.join(base_dir, "config.json")
        templates_path = os.path.join(os.path.dirname(__file__), "vlm_sys_prompt .json")

        config = _load_config(config_path)
        _, map_info = _build_vlm_options(config)
        self._cached_map_info = map_info or {}

        self._cached_templates = _load_sys_templates(templates_path)
        self._last_reload_ts = now

    def enhance(
        self,
        vlm_model: str,
        preset_template: str,
        sys_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.8,
        top_p: float = 0.6,
        image1=None,
        image2=None,
    ):
        """
        主执行逻辑:
        1) 解析 vlm_model -> base_url, api_key, model
        2) 选择系统模版或手动系统提示词，拼装最终提交的 system + user + images(0~2张)
        3) 请求 OpenAI 兼容接口，得到结果
        4) 返回 input_prompt 与 output_prompt
        """
        self._maybe_reload()

        user_prompt = (user_prompt or "").strip()

        # 处理图片 -> data url 列表
        image_urls: List[str] = []
        for img in (image1, image2):
            data_url = _image_tensor_to_data_url(img)
            if data_url:
                image_urls.append(data_url)

        map_info = self._cached_map_info or {}
        model_info = map_info.get(str(vlm_model).replace("：", ":"))
        if not model_info:
            input_prompt = f"[System] 无法找到模型映射: {vlm_model}\n[User] {user_prompt}\n[Images] {len(image_urls)}"
            return (input_prompt, "模型未配置或配置读取失败")

        base_url = (model_info.get("base_url") or "").strip()
        api_key = (model_info.get("api_key") or "").strip()
        model = (model_info.get("model") or "").strip()

        sys_templates = self._cached_templates or _load_sys_templates(
            os.path.join(os.path.dirname(__file__), "vlm_sys_prompt .json")
        )

        manual_mode = str(preset_template).strip() == "手动输入"
        if manual_mode:
            system_prompt = (sys_prompt or "").strip()
        else:
            system_prompt = sys_templates.get(preset_template) or sys_templates.get("图文理解:精确描述") or ""

        input_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_prompt}\n\n[Images]\n{len(image_urls)} image(s)"

        if not base_url or not model:
            return (input_prompt, "base_url 或 model 为空，请检查配置")

        ok, result = _chat_completions_with_images(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_urls=image_urls,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            top_p=float(top_p),
        )

        output_prompt = result if ok else f"请求失败: {result}"
        return (input_prompt, output_prompt)


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "VLM_Prompt_Enhance_Node": VLM_Prompt_Enhance_Node
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VLM_Prompt_Enhance_Node": "🦉VLM Prompt Enhance"
}