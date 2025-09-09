# -*- coding: utf-8 -*-
"""
Load Preset Prompt Node

功能:
- 扫描 custom_nodes/Comfyui_Free_API/Prompt_Enhance_Node/preset_prompts 下的 .md / .txt 文件
- 将文件名(不含扩展名)作为下拉选项 role_name
- 读取对应文件的完整文本作为 sys_prompt_preview 供前端展示/复用

设计要点:
- 与现有 LLM_Prompt_Enhance_Node 的节点注册风格保持一致
- 轻量无外部依赖，仅做本地读取
- 具备简单缓存与短周期自动刷新

注意:
- 本节点仅用于加载合法的系统提示词预设，不包含任何恶意用途
"""

import os
import time
from typing import Dict, List, Optional, Tuple

SUPPORTED_EXTS = {".md"}  # 下拉只展示 .md 作为模板文件


def _preset_dir() -> str:
    """
    返回预设目录绝对路径:
    custom_nodes/Comfyui_Free_API/Prompt_Enhance_Node/preset_prompts
    """
    return os.path.join(os.path.dirname(__file__), "preset_prompts")


def _scan_preset_files(dir_path: str) -> List[Tuple[str, str]]:
    """
    扫描目录，返回 [(显示名, 绝对路径)]，显示名为文件名(不含扩展名)
    仅包含 .md 模板（不扫描示例）
    """
    items: List[Tuple[str, str]] = []
    if not os.path.exists(dir_path):
        return items
    try:
        for fname in sorted(os.listdir(dir_path)):
            base, ext = os.path.splitext(fname)
            # 仅允许 .md 且排除 Example_ 前缀
            if ext.lower() == ".md" and not fname.startswith("Example_"):
                abs_path = os.path.join(dir_path, fname)
                if os.path.isfile(abs_path):
                    items.append((base, abs_path))
    except Exception:
        pass
    return items


def _read_text(path: str) -> str:
    """
    读取文本文件，失败时返回空串
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        # 尝试以系统默认编码作为兜底
        try:
            with open(path, "r", encoding=None) as f:
                return f.read()
        except Exception:
            return ""


class Load_Preset_Prompt_Node:
    """
    ComfyUI 节点定义:
    - 输入:
        1) role_name: 下拉，来自 preset_prompts 下的文件名(不含扩展名)
    - 输出:
        1) sys_prompt_preview: str（对应文件的完整文本）
    """

    @classmethod
    def INPUT_TYPES(cls):
        dir_path = _preset_dir()
        options = [name for name, _ in _scan_preset_files(dir_path)]
        if not options:
            options = ["未发现预设(请在preset_prompts放置.md或.txt)"]
        return {
            "required": {
                "role_name": (options,),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("sys_prompt_preview", "example_preview")
    FUNCTION = "load"
    CATEGORY = "🦉FreeAPI/Prompt Enhance"

    def __init__(self):
        self._cache_list: Optional[List[Tuple[str, str]]] = None  # [(name, path)]
        self._last_scan_ts: float = 0.0

    def _maybe_rescan(self):
        now = time.time()
        # 2 秒节流，避免频繁扫描磁盘
        if now - self._last_scan_ts < 2.0 and self._cache_list is not None:
            return
        dir_path = _preset_dir()
        self._cache_list = _scan_preset_files(dir_path)
        self._last_scan_ts = now

    def load(self, role_name: str):
        """
        主逻辑:
        1) 重新扫描(必要时)
        2) 根据 role_name 匹配文件
        3) 读取系统提示词全文
        4) 尝试读取示例输出 Example_{role_name}.txt，不存在则返回 None
        """
        self._maybe_rescan()
        role = str(role_name or "").strip()
        items = self._cache_list or []
        if not items:
            return ("未发现预设，请在 preset_prompts 目录中添加 .md 或 .txt 文件。", None)

        # 如果 UI 初始状态传入的是提示文案，则直接返回说明
        if role.startswith("未发现预设"):
            return ("未发现预设，请在 preset_prompts 目录中添加 .md 或 .txt 文件。", None)

        path_map: Dict[str, str] = {name: p for name, p in items}
        fpath = path_map.get(role)
        if not fpath:
            # 仅允许 .md 模板，若传入包含扩展名则剥离后匹配
            base, ext = os.path.splitext(role)
            if ext.lower() == ".md":
                fpath = path_map.get(base)
                if fpath:
                    role = base  # 同步 role 用于示例名
        if not fpath or not os.path.exists(fpath):
            return (f"[未找到预设(.md)] {role}", None)

        content = _read_text(fpath)
        if not content.strip():
            sys_preview = f"[内容为空或读取失败] {os.path.basename(fpath)}"
        else:
            sys_preview = content

        # 读取示例：仅匹配以 Example_ 开头且 .txt 后缀
        example_preview = None
        try:
            example_path = os.path.join(_preset_dir(), f"Example_{role}.txt")
            if os.path.isfile(example_path) and example_path.lower().endswith(".txt"):
                ex = _read_text(example_path)
                if ex.strip():
                    example_preview = ex
        except Exception:
            example_preview = None  # 静默失败

        return (sys_preview, example_preview)


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "Load_Preset_Prompt_Node": Load_Preset_Prompt_Node
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Load_Preset_Prompt_Node": "🦉Load Preset Prompt"
}