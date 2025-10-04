#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用视频URL转VIDEO节点
将视频URL转换为ComfyUI的VIDEO类型，供其他节点使用
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import logging
import re
import asyncio
from comfy_api.input_impl import VideoFromFile
from urllib.parse import urlparse
import tempfile
import mimetypes
import os

class DownloadVideoFromUrlNode:
    """
    通用视频URL转VIDEO节点
    支持各种视频URL格式，自动处理下载和转换
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_url": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "tooltip": "输入视频URL，支持http/https链接"
                }),
                "timeout": ("INT", {
                    "default": 120,
                    "min": 30,
                    "max": 600,
                    "step": 10,
                    "tooltip": "下载超时时间（秒）"
                }),
                "max_retries": ("INT", {
                    "default": 3,
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "tooltip": "下载重试次数"
                }),
                "retry_delay": ("INT", {
                    "default": 2,
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "tooltip": "重试间隔（秒）"
                }),
                "user_agent_type": (["Chrome桌面版", "Edge桌面版", "Firefox桌面版", "Safari桌面版", "Chrome移动端", "iOS Safari", "自定义"], {
                    "default": "Chrome桌面版",
                    "tooltip": "选择User-Agent类型，用于绕过网站访问限制"
                }),
                "skip_url_test": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "跳过URL可访问性测试，直接尝试下载（适用于某些拒绝HEAD请求的服务器）"
                })
            },
            "optional": {
                "custom_user_agent": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip": "自定义User-Agent（仅在选择'自定义'时使用）"
                })
            }
        }
    
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("video", "status_info")
    FUNCTION = "convert_url_to_video"
    CATEGORY = "🦉FreeAPI/OpenAI"
    OUTPUT_NODE = True
    
    def __init__(self):
        """初始化节点"""
        self.session = self._create_session()
    
    def _create_session(self):
        """创建HTTP会话，配置重试机制"""
        session = requests.Session()
        
        # 设置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _validate_url(self, url: str) -> bool:
        """验证URL格式"""
        if not url or not isinstance(url, str):
            return False
        
        url = url.strip()
        if not url:
            return False
        
        # 检查是否是有效的HTTP/HTTPS URL
        if not url.startswith(("http://", "https://")):
            return False
        
        return True
    
    def _clean_url(self, url: str) -> str:
        """清理URL，移除转义字符"""
        if isinstance(url, str):
            return url.replace('\\u0026', '&').strip()
        return url
    
    def _get_user_agent(self, user_agent_type: str, custom_user_agent: str = "") -> str:
        """根据类型获取User-Agent字符串"""
        user_agents = {
            "Chrome桌面版": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Firefox桌面版": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Safari桌面版": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
            "Chrome移动端": "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
            "iOS Safari": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
            "Edge桌面版": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
            "自定义": custom_user_agent if custom_user_agent else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        }
        
        user_agent = user_agents.get(user_agent_type, user_agents["Chrome桌面版"])
        print(f"[DownloadVideoFromUrl] 🖥️ 使用User-Agent: {user_agent_type}")
        return user_agent

    def _test_url_accessibility(self, url: str, timeout: int = 30) -> bool:
        """测试URL是否可访问"""
        try:
            print(f"[DownloadVideoFromUrl] 🔍 测试URL可访问性: {url[:50]}...")
            
            # 发送HEAD请求测试URL
            response = self.session.head(url, timeout=timeout, allow_redirects=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'video' in content_type or 'application/octet-stream' in content_type:
                    print(f"[DownloadVideoFromUrl] ✅ URL可访问，内容类型: {content_type}")
                    return True
                else:
                    print(f"[DownloadVideoFromUrl] ⚠️ URL可访问但内容类型可能不是视频: {content_type}")
                    return True  # 仍然尝试下载
            elif response.status_code == 403:
                print(f"[DownloadVideoFromUrl] ⚠️ URL返回403错误，可能是User-Agent被拒绝或URL已过期")
                print(f"[DownloadVideoFromUrl] 🔄 尝试使用GET请求直接下载...")
                # 对于403错误，我们仍然尝试下载，因为有些服务器会拒绝HEAD请求但允许GET请求
                return True
            else:
                print(f"[DownloadVideoFromUrl] ❌ URL不可访问，状态码: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[DownloadVideoFromUrl] ❌ URL测试失败: {e}")
            print(f"[DownloadVideoFromUrl] 🔄 尝试直接下载...")
            # 如果测试失败，仍然尝试下载
            return True
    
    def _download_video_sync(self, url: str, timeout: int) -> VideoFromFile:
        """
        同步下载视频到临时文件，并返回 VideoFromFile 对象。
        1) 通过 Content-Type 或 URL 后缀确定扩展名
        2) 使用 requests 流式写入，避免占用大量内存
        """
        resp = self.session.get(url, stream=True, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()

        # 判定扩展名
        ctype = (resp.headers.get("content-type") or "").lower()
        ext_map = {
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
            "video/x-matroska": ".mkv",
            "application/octet-stream": ".mp4",
        }
        ct_main = ctype.split(";")[0].strip() if ctype else ""
        ext = ext_map.get(ct_main, None)
        if not ext:
            # 尝试从 URL 推断
            parsed = urlparse(url)
            _, url_ext = os.path.splitext(parsed.path)
            if url_ext and len(url_ext) <= 5:
                ext = url_ext
            else:
                # 再尝试 mimetypes
                guess = mimetypes.guess_extension(ct_main) if ct_main else None
                ext = guess or ".mp4"

        # 保存到临时文件
        tmp = tempfile.NamedTemporaryFile(prefix="download_video_", suffix=ext, delete=False)
        tmp_path = tmp.name
        with tmp as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        resp.close()

        return VideoFromFile(tmp_path)

    def convert_url_to_video(self, video_url, timeout, max_retries, retry_delay, user_agent_type, skip_url_test, custom_user_agent=""):
        """
        将视频URL转换为VIDEO对象
        
        Args:
            video_url (str): 视频URL
            timeout (int): 下载超时时间
            max_retries (int): 最大重试次数
            retry_delay (int): 重试间隔
            user_agent_type (str): User-Agent类型选择
            skip_url_test (bool): 是否跳过URL可访问性测试
            custom_user_agent (str, optional): 自定义User-Agent字符串
        
        Returns:
            tuple: (video_object, status_info)
        """
        try:
            print(f"[DownloadVideoFromUrl] 🎬 开始处理视频URL")
            
            # 从文本中提取第一个有效的 http/https URL（兼容多行/列表/字典输入）
            candidate_urls = []
            # 将各种输入统一为字符串，避免分成“https:”与“//”
            if isinstance(video_url, (list, tuple)):
                video_text = "\n".join(str(x) for x in video_url if x is not None)
            elif isinstance(video_url, dict):
                video_text = str(video_url.get("text", "")) or str(video_url)
            else:
                video_text = str(video_url or "")
            # 修复被换行/空格打断的协议分隔符，如:
            # "https:\n//example.com" 或 "http: //example.com" -> "https://example.com"
            normalized_text = re.sub(r'(?i)\b(https?):\s*//', r'\1://', video_text)
            candidate_urls = re.findall(r'https?://[^\s<>\'"]+', normalized_text, flags=re.IGNORECASE)
            if not candidate_urls:
                error_msg = f"❌ 未在输入文本中找到有效的 http/https 链接。原始输入: {normalized_text[:200]}"
                print(f"[DownloadVideoFromUrl] {error_msg}")
                raise ValueError(error_msg)
            extracted_url = candidate_urls[0].rstrip(')\']",.> ')
            
            # 清理与验证
            cleaned_url = self._clean_url(extracted_url)
            if not self._validate_url(cleaned_url):
                error_msg = f"❌ 无效的视频URL: {extracted_url}"
                print(f"[DownloadVideoFromUrl] {error_msg}")
                raise ValueError(error_msg)
            
            print(f"[DownloadVideoFromUrl] ✅ URL格式验证通过: {cleaned_url}")
            
            # 定义多个User-Agent用于轮换
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
                "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
            ]
            
            # 获取初始User-Agent
            if user_agent_type == "自定义" and custom_user_agent:
                user_agents.insert(0, custom_user_agent)
            else:
                initial_ua = self._get_user_agent(user_agent_type, custom_user_agent)
                user_agents.insert(0, initial_ua)
            
            # 尝试不同的User-Agent
            for ua_index, user_agent in enumerate(user_agents):
                print(f"[DownloadVideoFromUrl] 🖥️ 尝试User-Agent {ua_index + 1}/{len(user_agents)}: {user_agent[:50]}...")
                self.session.headers.update({"User-Agent": user_agent})
                
                # 测试URL可访问性（如果未跳过）
                if not skip_url_test:
                    if not self._test_url_accessibility(cleaned_url, timeout=min(timeout, 30)):
                        print(f"[DownloadVideoFromUrl] ⚠️ User-Agent {ua_index + 1} 无法访问URL，尝试下一个...")
                        continue
                else:
                    print(f"[DownloadVideoFromUrl] ⏭️ 跳过URL可访问性测试，直接尝试下载...")
                
                # 下载并转换视频
                print(f"[DownloadVideoFromUrl] 📥 开始下载视频...")
                start_time = time.time()
                
                try:
                    # 使用同步下载，直接返回可用的 VideoFromFile 对象，避免协程传递
                    video_output = self._download_video_sync(cleaned_url, timeout=timeout)
                    
                    download_time = time.time() - start_time
                    print(f"[DownloadVideoFromUrl] ✅ 视频下载完成，耗时: {download_time:.2f}秒")
                    
                    # 校验返回对象
                    if video_output is None:
                        raise RuntimeError("下载函数返回了空视频对象（None），无法继续。")
                    
                    # 获取视频信息
                    try:
                        width, height = video_output.get_dimensions()
                        duration = getattr(video_output, 'duration_seconds', '未知')
                        status_info = f"✅ 视频转换成功\n完整URL: {cleaned_url}\n尺寸: {width}x{height}\n时长: {duration}秒\n下载耗时: {download_time:.2f}秒\n使用User-Agent: {ua_index + 1}"
                    except Exception as info_error:
                        status_info = f"✅ 视频转换成功\n完整URL: {cleaned_url}\n下载耗时: {download_time:.2f}秒\n使用User-Agent: {ua_index + 1}\n(无法获取详细信息: {info_error})"
                    
                    return (video_output, status_info)
                    
                except Exception as download_error:
                    print(f"[DownloadVideoFromUrl] ❌ User-Agent {ua_index + 1} 下载失败: {download_error}")
                    
                    # 尝试重试
                    for attempt in range(1, max_retries + 1):
                        print(f"[DownloadVideoFromUrl] 🔄 重试 {attempt}/{max_retries} (User-Agent {ua_index + 1})")
                        time.sleep(retry_delay)
                        
                        try:
                            video_output = self._download_video_sync(cleaned_url, timeout=timeout)
                            print(f"[DownloadVideoFromUrl] ✅ 重试成功！")
                            
                            download_time = time.time() - start_time
                            status_info = f"✅ 视频转换成功（重试{attempt}次）\n完整URL: {cleaned_url}\n下载耗时: {download_time:.2f}秒\n使用User-Agent: {ua_index + 1}"
                            
                            return (video_output, status_info)
                            
                        except Exception as retry_error:
                            print(f"[DownloadVideoFromUrl] ❌ 重试 {attempt} 失败: {retry_error}")
                            if attempt == max_retries:
                                print(f"[DownloadVideoFromUrl] ⚠️ User-Agent {ua_index + 1} 所有重试都失败，尝试下一个User-Agent...")
                                break
            
            # 所有User-Agent都失败了
            error_msg = f"❌ 所有User-Agent都无法下载视频\n完整URL: {cleaned_url}\n已尝试 {len(user_agents)} 个不同的User-Agent"
            print(f"[DownloadVideoFromUrl] {error_msg}")
            # 抛出异常以阻断图执行，避免下游节点拿到 None
            raise RuntimeError(error_msg)
            
        except Exception as e:
            error_msg = f"❌ 视频URL处理失败: {e}\nURL: {video_url}"
            print(f"[DownloadVideoFromUrl] {error_msg}")
            # 抛出异常以阻断图执行，避免下游节点拿到 None
            raise

# ComfyUI节点注册
NODE_CLASS_MAPPINGS = {
    "DownloadVideoFromUrl": DownloadVideoFromUrlNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DownloadVideoFromUrl": "🦉Download Video From Url"
} 