# Grok 图生视频节点使用说明

## 功能介绍

Grok 图生视频节点是一个 ComfyUI 自定义节点，可以将图像转换为视频。它通过调用 Grok AI 的 API 来实现图生视频功能。

## 配置文件说明

在使用节点之前，需要正确配置 [grok_config.json](file:///E:/ComfyUI/custom_nodes/Comfyui_Free_API/Grok_Node/grok_config.json) 文件。该文件包含了访问 Grok API 所需的认证信息和请求配置。

### 配置文件结构

```json
{
  "base_url": "https://grok.com",
  "assets_base_url": "https://assets.grok.com",
  "filtered_tags": "xaiartifact,xai:tool_usage_card,grok:render",
  "accounts": {
    "account_1": {
      "cookie": "你的完整Cookie字符串",
      "headers": {
        "user-agent": "浏览器User-Agent",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "x-statsig-id": "ZTpUeXBlRXJyb3I6IENhbm5vdCByZWFkIHByb3BlcnRpZXMgb2YgdW5kZWZpbmVkIChyZWFkaW5nICdjaGlsZE5vZGVzJyk=", // 固定值不要动
        "sentry-trace": "跟踪ID",
        "baggage": "跟踪信息"
      }
    },
    "account_2": {
      // 另一个账号的配置，结构与account_1相同
    }
  },
  "timeouts": {
    "connect": 10,
    "read": 20,
    "poll_interval": 2,
    "poll_timeout_secs": 180
  }
}
```

## 如何获取 Cookie 信息

获取有效的 Cookie 是使用该节点的关键步骤。请按照以下步骤操作：

### 步骤 1: 登录 Grok

1. 打开浏览器，访问 [Grok 官网](https://grok.com)
2. 使用你的账号登录

### 步骤 2: 获取 Cookie

1. 在浏览器中按 F12 打开开发者工具
2. 切换到 Network(网络) 标签
3. 刷新页面或执行任意操作以产生网络请求
4. 在请求列表中选择任意一个请求
5. 在请求详情中找到 Request Headers(请求头)
6. 找到 Cookie 字段，右键点击并选择复制值

### 步骤 3: 获取其他请求头信息

除了 Cookie，还需要获取以下请求头信息：

1. User-Agent: 浏览器用户代理字符串
2. x-statsig-id: 用于标识会话的固定值
3. sentry-trace 和 baggage: 用于错误跟踪的信息

这些信息都可以在请求头中找到。

### 步骤 4: 更新配置文件

将获取到的信息填入 [grok_config.json](file:///E:/ComfyUI/custom_nodes/Comfyui_Free_API/Grok_Node/grok_config.json) 文件中对应的位置。

## 注意事项

1. Cookie 会过期，如果节点无法正常工作，请重新获取 Cookie
2. 保持与获取 Cookie 时相同的网络环境和浏览器 User-Agent
3. 如果遇到 Cloudflare 验证问题，请确保 Cookie 中包含 cf_clearance 字段
4. 不要将配置文件中的敏感信息泄露给他人

## 节点使用

配置完成后，在 ComfyUI 中就可以使用 Grok 图生视频节点了：

1. 将图像连接到节点的 image 输入端
2. 选择要使用的账号（account_1 或 account_2）
3. 选择生成模式（normal/spicy/fun/custom）
4. 如果选择 custom 模式，可以输入自定义提示词
5. 运行节点，等待视频生成完成
6. 节点会输出视频的直链 URL，以及可选的视频对象

## 常见问题

### 403 错误
如果遇到 403 错误，通常是由于 Cookie 过期或不正确导致的，请重新获取 Cookie。

### Cloudflare 验证
如果遇到 Cloudflare 验证问题，请确保 Cookie 中包含 cf_clearance 字段，并保持与获取 Cookie 时相同的网络环境和浏览器 User-Agent。

### 生成失败
如果视频生成失败，请检查：
1. Cookie 是否有效
2. 网络连接是否正常

3. 图像是否符合要求
