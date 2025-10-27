# Haiyi（海艺）图像/视频节点使用说明

适用于 `custom_nodes/Comfyui_Free_API/Haiyi_Node` 下的两个节点：
- `HAIYIImageNode`：海艺文生图/图生图
- `HAIYIVideoNode`：海艺文/图生视频（含多图参考 V2.0）

本文档详细说明了Cookie 获取、参数配置、返回值、错误处理与常见问题。

---

## 功能概述

- 统一读取 `haiyi_config.json`，携带海艺账号 Cookie 与通用请求头。
- 自动提交任务至海艺平台，并轮询 `/api/v1/task/batch-progress` 获取结果。
- 成功后自动追加“🪙 剩余积分: N”（来自 `payment/assets/get` 的 `temp_coins`）。
- 失败与被取消（如敏感词）时提供中文提示，并在视频节点返回占位 VIDEO 以避免下游报错；在图片节点返回占位 IMAGE。

---

## 配置文件

配置文件路径：`custom_nodes/Comfyui_Free_API/Haiyi_Node/haiyi_config.json`

示例结构：

```json
{
  "cookie": "deviceId=...; T=...; ...", 
  "timeout": 30,
  "max_wait_time": 300,
  "check_interval": 5,
  "headers": {
    "x-app-id": "web_global_seaart",
    "x-platform": "web",
    "user-agent": "Mozilla/5.0 (...)",
    "origin": "https://www.haiyi.art",
    "referer": "https://www.haiyi.art/"
  },
  "image_models": {
    "海艺影像 2.0": {
      "model_no": "...",
      "model_ver_no": "...",
      "ss": 52,
      "default_steps": 20,
      "default_cfg_scale": 2.5,
      "default_n_iter": 4
    },
    "Seedream 4.0": { "apply_id": "...", "ver_no": "...", "ss": 52 },
    "NanoBanana": { "apply_id": "...", "ver_no": "...", "ss": 52 }
  },
  "video_models": {
    "海艺影像 专业版": { "model_no": "...", "model_ver_no": "...", "ss": 52 },
    "VIDU Q2": { "model_no": "...", "model_ver_no": "...", "ss": 52 },
    "V2.0": { "model_no": "...", "model_ver_no": "...", "ss": 52 }
  }
}
```

注意：
- `cookie` 必须为你的海艺网站登录 Cookie 全串；失效会导致任何请求失败。
- `image_models` 与 `video_models` 的具体字段由海艺接口决定，示例仅为常用字段。

---

## 如何获取 Cookie（海艺）

1. 浏览器登录 https://www.haiyi.art
2. 打开开发者工具（F12）→ Network（网络）。
3. 刷新页面或执行任意操作产生请求，点开任一请求。
4. 在 Request Headers 中找到 `Cookie`，复制完整值。
5. 将其粘贴到 `haiyi_config.json` 的 `cookie` 字段。

建议：保持与获取 Cookie 时相同的网络与 User-Agent，Cookie 过期后需重新获取。

---

## 节点一：HAIYIImageNode（文/图生图）

- 类名：`HAIYIImageNode`
- 类别：`🦉FreeAPI/Haiyi`
- 输出：`(IMAGE, STRING)`

输入参数：
- `model`：从 `haiyi_config.json` 的 `image_models` 动态读取（默认 `Seedream 4.0`）。
- `prompt`：提示词，支持多行。
- 可选 `ratio`：生成比例，默认 `3:4`（映射到常见分辨率，如 1536×2048）。
- 可选 `image`：提供则走图生图流程；`海艺影像 2.0` 仅支持文生图，`image` 会被忽略。

行为与返回：
- 自动提交任务并轮询直至完成；
- 下载最多前 4 张图片，合并为批量张量 `[N,H,W,3]`（预览可见多图）；
- `generation_info` 展示关键信息与前 4 个图片直链，末尾追加当前账号 `temp_coins`：
  - 例：`🪙 剩余积分: 3260`
- 敏感词（code=70026）或提交失败：返回占位白图和中文错误提示。

---

## 节点二：HAIYIVideoNode（文/图生视频 + 多图参考V2.0）

- 类名：`HAIYIVideoNode`
- 类别：`🦉FreeAPI/Haiyi`
- 输出：`(VIDEO, STRING)`

输入参数：
- `video_model`：从 `video_models` 动态读取；若含 `V2.0`，界面显示为“多图参考V2.0”。
- `prompt`：提示词，多行。
- 可选 `image1..image4`：参考图（多图参考仅在选择“多图参考V2.0”时生效）。
- `duration`：时长（5/6/8/10s，默认 5）。
- `aspect_ratio`：纵横比（默认 `16:9`）。
- `quality_mode`：画质等级（部分分支使用，若未在 UI 暴露，内部默认值为 `360p`）。
- `audio_effect`：是否添加音效（布尔）。
- `hd_mode`：高清质量开关（true→`gen_mode=1`，false→`gen_mode=0`）。

行为与返回：
- 多图参考（V2.0）：依次上传参考图获取 URL，提交 `multi-img-to-video`；
- 单图：上传首帧并走 `img-to-video`；
- 文生视频：走 `text-to-video`；
- 轮询完成后下载视频并输出 `VIDEO`，`generation_info` 包含视频直链与任务信息，末尾同样追加 `🪙 剩余积分: N`；
- 若被系统取消（轮询 `status=4`），或失败超时：返回占位 `VIDEO` 与中文提示，避免后续节点报错。

---

## 自动查询剩余积分（temp_coins）

两个节点在成功生成后都会调用：
- `POST https://www.haiyi.art/api/v1/payment/assets/get`
- 仅解析 `data.temp_coins` 并在 `generation_info` 末尾追加：`🪙 剩余积分: N`
- 查询失败不会影响主流程，只记录日志。

你也可以用本目录的样例请求文件进行对照：
- `curl_获取账号积分.txt`

---

## 错误处理与兜底策略

- 敏感词拦截：海艺返回 `status.code=70026` 时，立即返回中文提示；
- 轮询取消：`status=4`（系统取消，如敏感）时提前结束并提示；
- 图片：失败时返回占位白图（尺寸默认 256×256）；
- 视频：失败时返回占位 `VIDEO`，以避免下游 `NoneType` 相关异常；
- 全流程打印关键日志（参数摘要、上传结果、进度、直链等），便于排查问题。

---

## 常见问题（FAQ）

1) 生成失败/超时怎么办？
- 检查 Cookie 是否有效、网络是否稳定、提示词是否合规。
- 观察日志中最近一次响应 `raw` 内容，以便定位。

2) 为什么提示“敏感词/系统取消”？
- 海艺端可能识别为敏感内容。请修改提示词或参考图后重试。

3) 只有一张预览图？
- 本节点已将多图下载为 `[N,H,W,3]` 批量张量。请确认工作流的预览节点是否支持 batch 预览。

4) 为什么看不到 `🪙 剩余积分`？
- 仅在生成成功且 `payment/assets/get` 请求成功时追加；若 Cookie 过期或接口变更，会跳过追加并输出日志。

5) `quality_mode` 没有在 UI 中出现？
- 某些分支内部有默认值（如 `360p`）。如需暴露到 UI，可在 `INPUT_TYPES` 中开启对应枚举。

---

## 小贴士

- 定期更新 `cookie`，并保持 `user-agent` 与获取时一致，减少被风控拦截概率。
- 合理设置 `max_wait_time` 与 `check_interval`，在不同机型与网络下权衡等待时长与轮询频率。
- 若希望扩展更多模型，只需在 `haiyi_config.json` 的 `image_models`/`video_models` 中添加映射。

---

## 路径速查

- 配置：`custom_nodes/Comfyui_Free_API/Haiyi_Node/haiyi_config.json`
- 节点：
  - 图片：`custom_nodes/Comfyui_Free_API/Haiyi_Node/haiyi_image.py`
  - 视频：`custom_nodes/Comfyui_Free_API/Haiyi_Node/haiyi_video.py`
- 积分示例：`custom_nodes/Comfyui_Free_API/Haiyi_Node/curl_获取账号积分.txt`

如需进一步功能（如更多参数暴露、更多错误分支提示、多账号切换等），欢迎提出具体需求。