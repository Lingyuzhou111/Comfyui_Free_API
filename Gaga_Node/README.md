# 🦉Gaga 图生视频节点使用说明

文件:
- gaga_avart_i2v.py: ComfyUI 自定义节点
- gaga_config.json: 配置文件，含 base_url 与完整 Cookie 认证头（单一键值对）

## 1. 安装与配置
1) 将本目录复制/保持在 `custom_nodes/Comfyui_Free_API/Gaga_Node`。
2) 编辑 `gaga_config.json`：
   - base_url: 填 `https://gaga.art`
   - cookie: 从浏览器登录后复制“整段 Cookie”（例如 `session=...; _ga=...; _ga_83KR1LTYE4=...`），不要拆分（建议把完整的cookie和json文件发给AI，让AI自动帮你填充）。
   - headers.user-agent: 可保持默认或替换为你的浏览器 UA
   - timeouts/poll 配置：默认即可

示例：
```json
{
  "base_url": "https://gaga.art",
  "cookie": "session=xxxxx; _ga=xxxxx; _ga_83KR1LTYE4=xxxx",
  "headers": { "user-agent": "Mozilla/5.0 ..." },
  "timeouts": { "connect": 10, "read": 20, "poll_interval": 3, "poll_timeout_secs": 300 },
  "model": "test-performer",
  "defaults": { "resolution": "540p", "enhancementType": "i2v_performer_performer-v3-6_gemini", "nSampleSteps": 32, "enablePromptEnhancement": true, "enableWatermark": true }
}
```

## 2. 节点参数
- 必选
  - image: 输入图片（ComfyUI IMAGE 张量）
  - prompt: 文本提示词
- 可选
  - aspectRatio: 下拉，仅 16:9（默认 16:9）
  - duration: 下拉，5 或 10（默认 10）
  - cropArea_x: 默认 0
  - cropArea_y: 默认 0
- 输出
  - video_url: 文本类型，来源于 `resultVideoURL`

## 3. 工作流程
1) 将 IMAGE 编码为 PNG 字节；
2) POST `/api/v1/assets` 上传图片（multipart/form-data），得到 `id`、`width`、`height`；
3) 根据图片尺寸与 16:9 计算裁剪区域（width/height自动匹配，x/y按边界裁剪）；
4) POST `/api/v1/generations/performer` 提交任务，包含 prompt、aspectRatio、duration、cropArea、extraInferArgs；
5) 轮询 GET `/api/v1/generations/{id}?chunks=true`，直到 `status=Success`，返回 `resultVideoURL`。

## 4. 注意事项
- Cookie 必须为整串复制；若风控导致 403，请更新 Cookie 且保持相同出口 IP/UA。
- 日志不会打印图像的实际内容，仅进行必要的简短提示。
- 目前仅支持 16:9 比例；如需更多比例可在代码中扩展 `_compute_crop`。

## 5. 常见报错
- “配置不完整”：未填写 `gaga_config.json` 的 base_url 或 cookie。
- “上传图片失败/提交任务失败”：服务端返回非 200；请检查 Cookie 与网络。
- “轮询超时”：生成时间较长或风控阻断；可提高 `poll_timeout_secs`。