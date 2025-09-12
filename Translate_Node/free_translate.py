# -*- coding: utf-8 -*-
"""
Free Translate Node for ComfyUI (Free API via suol.cc)
- 功能: 调用公开翻译接口 https://api.suol.cc/v1/zs_fanyi.php
        支持有道(youdao)与翻译君(qqfy)两种来源, 多语种互译
- 输入:
    text (STRING): 需要翻译的文本
    provider (CHOICE): 翻译来源 youdao / qqfy
    src_lang (CHOICE): 源语言(可选, 接口允许为空; 本节点提供下拉列表)
    tgt_lang (CHOICE): 目标语言(必选)
    timeout_sec (INT): 请求超时秒数
- 输出:
    text (STRING): 接口 JSON 返回的 msg 字段 (翻译结果)

接口参数:
- type: youdao 或 qqfy
- from: 源语言字符串(可选)
- to:   目标语言字符串(必填)
- msg:  原文

返回示例:
{
  "code": 200,
  "type": "有道翻译",
  "types": "英文",
  "text": "你好",
  "msg": "Hello",
  "tips": "慕名API：http://xiaoapi.cn"
}

设计目标:
- 零第三方依赖 (仅使用 Python 标准库)
- 提供来源-语言的合法性校验, 下拉选项动态匹配
- 健壮的错误处理, 便于在 ComfyUI 中定位问题

使用:
- 在 ComfyUI 中搜索 "Free Translate"
- 选择来源(provider), 再选择源/目标语言, 输入文本, 获得翻译结果
"""

from typing import Tuple, Dict, List
import sys
import json
import urllib.parse
import urllib.request
import urllib.error

API_ENDPOINT = "https://api.suol.cc/v1/zs_fanyi.php"

# 两个来源的可选语言
YOUDAO_LANGS: List[str] = [
    "中文", "英文", "日语", "韩语", "西班牙语", "俄语", "法语", "德语", "葡萄牙语"
]
QQFY_LANGS: List[str] = [
    "中文", "英文", "日语", "韩语", "西班牙语", "俄语", "法语", "德语",
    "泰语", "越南语", "印尼语", "马来语", "葡萄牙语", "土耳其语"
]

# 默认源语言选项首项使用 "自动检测" 以表达可留空的意味(提交时会转为空字符串, 即不传 from)
AUTO_DETECT_LABEL = "自动检测"

class FreeTranslateNode:
    """
    ComfyUI 节点定义: Free Translate (suol.cc)
    """

    CATEGORY = "🦉FreeAPI/Translate"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "translate"

    @classmethod
    def _language_options_for(cls, provider: str) -> List[str]:
        if provider == "youdao":
            return YOUDAO_LANGS
        # 默认按 qqfy 处理, 以容错
        return QQFY_LANGS

    @classmethod
    def INPUT_TYPES(cls):
        """
        通过动态枚举给出 Provider 及对应语言下拉。
        ComfyUI 目前的机制下, 下拉选项通常是静态的。
        这里我们提供两套语言全集, 并在运行时做校验与容错。
        """
        # 前端显示中文，但内部仍用 youdao/qqfy
        providers = ["有道", "翻译君"]

        # 将两套语言合并给下拉, 但 UI 上给出提示:
        # - 选择 youdao 时, 仅在 YOUDAO_LANGS 内的选项才会被接受
        # - 选择 qqfy 时, 仅在 QQFY_LANGS 内的选项才会被接受
        # 为了更直观, 我们添加 "自动检测" 选项到源语言首位
        merged_langs = sorted(set(YOUDAO_LANGS + QQFY_LANGS), key=lambda x: x)
        src_lang_options = [AUTO_DETECT_LABEL] + merged_langs
        tgt_lang_options = merged_langs

        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入需要翻译的文本"
                }),
                "provider": (providers, {
                    "default": "有道"
                }),
                "src_lang": (src_lang_options, {
                    "default": AUTO_DETECT_LABEL
                }),
                "tgt_lang": (tgt_lang_options, {
                    "default": "英文"
                }),
            }
        }

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # 保持默认行为
        return None

    def _http_get_json(self, url: str, timeout: int) -> Dict:
        """
        GET 请求并尝试解析 JSON, 返回 dict
        出错返回包含 error 信息的字典
        """
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": "ComfyUI-FreeAPI-FreeTranslate/1.0 (+https://github.com/comfyanonymous/ComfyUI)"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                text = data.decode("utf-8", errors="replace")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # 如果不是 JSON, 也返回原文便于排查
                    return {"code": -2, "error": "Invalid JSON", "raw": text}
        except urllib.error.HTTPError as e:
            msg = f"HTTPError: {e.code} - {e.reason}"
            print(f"[FreeTranslateNode] {msg}", file=sys.stderr)
            return {"code": -1, "error": msg}
        except urllib.error.URLError as e:
            msg = f"URLError: {getattr(e, 'reason', e)}"
            print(f"[FreeTranslateNode] {msg}", file=sys.stderr)
            return {"code": -1, "error": msg}
        except Exception as e:
            msg = f"Exception: {repr(e)}"
            print(f"[FreeTranslateNode] {msg}", file=sys.stderr)
            return {"code": -1, "error": msg}

    def _validate_lang(self, provider: str, lang: str, is_src: bool) -> str:
        """
        校验语言是否属于对应 provider 的可选范围。
        - 对于源语言, 若选择 '自动检测', 返回空字符串表示不传 from。
        - 不合法时进行容错: 自动回退为 provider 对应集合内的第一个语言(避免接口报错)。
        """
        if is_src and lang == AUTO_DETECT_LABEL:
            return ""  # 不传 from

        allowed = self._language_options_for(provider)
        if lang in allowed:
            return lang

        # 容错回退
        fallback = allowed[0] if allowed else ""
        print(f"[FreeTranslateNode] Language '{lang}' not allowed for provider '{provider}', fallback to '{fallback}'", file=sys.stderr)
        return fallback

    def translate(self,
                  text: str,
                  provider: str = "有道",
                  src_lang: str = AUTO_DETECT_LABEL,
                  tgt_lang: str = "英文",
                  timeout_sec: int = 15) -> Tuple[str]:
        """
        执行翻译:
        - 校验 provider 取值
        - 按 provider 校验/修正 src_lang 与 tgt_lang
        - 构造 URL 参数并请求
        - 返回 JSON 的 msg 字段; 若失败, 返回可读的错误信息
        """
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        msg = text.strip()
        if not msg:
            return ("",)

        # 将前端中文选项映射为接口需要的英文标识
        provider_map = {"有道": "youdao", "翻译君": "qqfy"}
        provider = provider_map.get(provider, "youdao")
        src = self._validate_lang(provider, src_lang, is_src=True)
        tgt = self._validate_lang(provider, tgt_lang, is_src=False)

        # 组装查询参数
        params = {
            "type": provider,
            "to": tgt,
            "msg": msg
        }
        if src:
            params["from"] = src  # 仅当不是自动检测时才携带

        qs = urllib.parse.urlencode(params, safe="/:+")  # 允许少量安全字符
        url = f"{API_ENDPOINT}?{qs}"

        # 固定超时 15 秒（前端不展示）
        data = self._http_get_json(url, timeout=15)

        # 正常返回
        if isinstance(data, dict) and data.get("code") == 200:
            result = data.get("msg", "")
            if isinstance(result, str):
                return (result,)
            # 若 msg 不是字符串, 退回文本化
            return (json.dumps(result, ensure_ascii=False),)

        # 异常返回
        if isinstance(data, dict):
            # 优先展示接口原始内容, 便于定位
            if "raw" in data:
                return (f"[Translate Error] Invalid JSON: {data['raw']}",)
            err = data.get("error", "Unknown error")
            return (f"[Translate Error] {err}",)

        # 极端情况, 返回原始文本化
        try:
            return (json.dumps(data, ensure_ascii=False),)
        except Exception:
            return (str(data),)


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "FreeTranslateNode": FreeTranslateNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FreeTranslateNode": "🦉Free Translate"
}