# -*- coding: utf-8 -*-
"""
LLM Prompt Enhance Node

功能:
- 从 ComfyUI/custom_nodes/Comfyui_Free_API/config.json 的 "LLM" 段读取提供方、base_url、api_key、model 列表
- 在 ComfyUI 中提供一个节点，允许用户选择 "llm_model"（展示为 "提供方:型号"）
- 读取 Prompt_Enhance_Node/llm_sys_prompt.json 中的系统提示词模版名称作为下拉选项（若文件为空或不存在，则提供内置默认模版）
- 接收用户 user_prompt、max_tokens、temperature、top_p；当 preset_template 选择“手动输入”时，使用 sys_prompt 文本框内容作为系统提示词
- 按 OpenAI 兼容 Chat Completions 接口格式调用对应 base_url（需 /chat/completions），返回增强后的提示词
- 输出:
  1) context: 展示最终提交给 API 的 system_prompt + user_prompt（便于检查上下文）
  2) result: API 响应生成内容（增强后的提示词）

注意:
- 本实现仅用于合法、正当的提示词优化工作，不包含任何恶意用途。
- 严格避免泄露系统信息与内部配置。
"""

import json
import os
import re
import time
from typing import Dict, Any, List, Tuple, Optional

try:
    import requests
except Exception:
    requests = None

# 读取配置工具
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

# 读取系统模版工具
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
        "通用增强:图文提示词润色": (
            "你是资深AIGC提示词工程师。目标:在不改变意图的前提下，将用户用于AI绘画/视频生成的提示词进行结构化、具体化与可控化，"
            "要求:\n"
            "1) 明确主体/风格/构图/光照/配色/材质/分辨率/负面元素。\n"
            "2) 保留用户关键元素，消除歧义；补充必要细节词汇；避免冗余与自相矛盾描述。\n"
            "3) 只输出最终可用于模型的英文prompt文本（可用逗号/句子组织），不添加解释。"
        ),
        "影视向增强:镜头语言强化": (
            "你是电影分镜指导AI。将提示词改写为更具镜头语言的英文描述，包含镜头类型（wide shot、close-up）、"
            "机位/移动（low angle, dolly-in）、光效（rim light, volumetric light）、氛围/色温；"
            "保持原意并补充可视化细节。仅输出英文提示词。"
        ),
        "角色立绘:细节刻画": (
            "你是角色美术提示工程师。将提示词改写为角色立绘向的英文描述，强调外观（发型、瞳色、服饰、配件）、"
            "风格（anime/realistic/illustration）、姿态、表情、背景简洁度、画质关键词。保持原意并提升可控性。仅输出英文提示词。"
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

def _build_llm_options(config: Dict[str, Any]) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    """
    返回:
    - options: ["提供方:型号", ...]
    - map_info: {"提供方:型号": {"base_url": "...", "api_key": "...", "model": "型号"}}
    """
    options: List[str] = []
    map_info: Dict[str, Dict[str, str]] = {}
    if not config:
        return options, map_info

    llm = config.get("LLM", {})
    for provider, info in llm.items():
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

def _chat_completions(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """
    OpenAI 兼容接口:
      POST {base_url}/chat/completions
    body:
      {"model": "...", "messages": [{"role":"system","content":...},{"role":"user","content":...}],
       "max_tokens":..., "temperature":..., "top_p":...}
    """
    if requests is None:
        return False, "requests 库不可用，请安装后重试。"

    try:
        url = _normalize_base_url(base_url) + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
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

class LLM_Prompt_Enhance_Node:
    """
    ComfyUI 节点定义:
    - 输入:
        1) llm_model: 下拉，来自 config.json 的 LLM 组合项 ("提供方:型号")
        2) preset_template: 下拉，首位为“手动输入”，其余来自 llm_sys_prompt.json；如果文件为空则提供内置模版
        3) sys_prompt: 文本框（sys_prompt，自定义系统提示词仅在预设模板为“手动输入”时才生效）
        4) user_prompt: 文本框
        5) max_tokens: 整数（默认 2048）
        6) temperature: 浮点（默认 0.8）
        7) top_p: 浮点（默认 0.6）
    - 输出:
        1) context: str（system + user 最终提交内容）
        2) result: str（API 响应增强结果）
    """

    @classmethod
    def INPUT_TYPES(cls):
        # 加载配置与模版
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # custom_nodes/Comfyui_Free_API
        config_path = os.path.join(base_dir, "config.json")
        templates_path = os.path.join(os.path.dirname(__file__), "llm_sys_prompt.json")

        config = _load_config(config_path)
        llm_options, _ = _build_llm_options(config)
        if not llm_options:
            llm_options = []

        sys_templates = _load_sys_templates(templates_path)
        template_names = ["手动输入"] + (list(sys_templates.keys()) if sys_templates else ["通用增强:图文提示词润色"])

        return {
            "required": {
                "llm_model": (llm_options if llm_options else ["未检测到模型配置"],),
                "preset_template": (template_names,),
                "sys_prompt": ("STRING", {"multiline": True, "default": "自定义系统提示词仅在预设模板为“手动输入”时才会生效", "tooltip": "当选择“手动输入”时，此处作为system提示词使用"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "随机提示词"}),
                "max_tokens": ("INT", {"default": 2048, "min": 1, "max": 8192, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05}),
                "control_after_generate": (["固定", "增加", "减少", "随机"], {"default": "固定", "tooltip": "固定: 使用上一轮缓存结果；其他: 正常生成"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("context", "result")
    FUNCTION = "enhance"
    CATEGORY = "🦉FreeAPI/Prompt Enhance"

    def __init__(self):
        self._cached_map_info: Optional[Dict[str, Dict[str, str]]] = None
        self._cached_templates: Optional[Dict[str, str]] = None
        self._last_reload_ts: float = 0.0
        # 缓存上一轮增强结果（仅在 control_after_generate=固定 时复用）
        self._last_result: Optional[str] = None

    def _maybe_reload(self):
        now = time.time()
        if now - self._last_reload_ts < 2.0:
            return
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # custom_nodes/Comfyui_Free_API
        config_path = os.path.join(base_dir, "config.json")
        templates_path = os.path.join(os.path.dirname(__file__), "llm_sys_prompt.json")

        config = _load_config(config_path)
        _, map_info = _build_llm_options(config)
        self._cached_map_info = map_info or {}

        self._cached_templates = _load_sys_templates(templates_path)
        self._last_reload_ts = now

    def enhance(
        self,
        llm_model: str,
        preset_template: str,
        sys_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.8,
        top_p: float = 0.6,
        control_after_generate: str = "固定",
    ):
        """
        主执行逻辑:
        1) 解析 llm_model -> base_url, api_key, model
        2) 选择系统模版或手动系统提示词，拼装最终提交的 system + user
        3) 请求 OpenAI 兼容接口，得到结果
        4) 返回 context 与 result
        """
        self._maybe_reload()

        user_prompt = (user_prompt or "").strip()

        map_info = self._cached_map_info or {}
        model_info = map_info.get(str(llm_model).replace("：", ":"))
        if not model_info:
            context = f"[System] 无法找到模型映射: {llm_model}\n[User] {user_prompt}"
            return (context, "模型未配置或配置读取失败")

        base_url = (model_info.get("base_url") or "").strip()
        api_key = (model_info.get("api_key") or "").strip()
        model = (model_info.get("model") or "").strip()

        sys_templates = self._cached_templates or _load_sys_templates(
            os.path.join(os.path.dirname(__file__), "llm_sys_prompt.json")
        )

        manual_mode = str(preset_template).strip() == "手动输入"
        if manual_mode:
            system_prompt = (sys_prompt or "").strip()
        else:
            system_prompt = sys_templates.get(preset_template) or sys_templates.get("通用增强:图文提示词润色") or ""

        context = f"[System]\n{system_prompt}\n\n[User]\n{user_prompt}"

        if not base_url or not model:
            return (context, "base_url 或 model 为空，请检查配置")

        # 当选择“固定”并且已有缓存时，直接返回缓存，不再请求API
        if str(control_after_generate).strip() == "固定" and isinstance(self._last_result, str) and self._last_result:
            print("[LLM Prompt Enhance] control_after_generate=固定，已跳过API请求，复用上一轮缓存结果。")
            return (context, self._last_result)

        ok, result = _chat_completions(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            top_p=float(top_p),
        )

        result = result if ok else f"请求失败: {result}"
        # 仅当请求成功时更新缓存
        if ok:
            self._last_result = result
        return (context, result)


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "LLM_Prompt_Enhance_Node": LLM_Prompt_Enhance_Node
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LLM_Prompt_Enhance_Node": "🦉LLM Prompt Enhance"
}
