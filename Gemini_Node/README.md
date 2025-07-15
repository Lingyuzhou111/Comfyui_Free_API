# Gemini VLM API节点

## 概述

Gemini VLM API节点是ComfyUI_Free_API插件的一部分，用于调用Google Gemini的视觉语言模型进行图片分析。

## 功能特性

- 🖼️ **图片分析**: 支持输入图片进行视觉推理
- 🤖 **多模型支持**: 支持多种Gemini模型
- ⚙️ **参数配置**: 支持temperature、top_p等参数调节
- 📊 **用量统计**: 提供详细的API用量信息
- 🔍 **智能解析**: 自动解析思考过程和答案

## 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `image` | IMAGE | - | 输入图片（ComfyUI标准格式） |
| `model` | 下拉框 | gemini-2.5-flash | 模型选择（从配置文件读取） |
| `max_tokens` | INT | 512 | 最大输出token数 |
| `temperature` | FLOAT | 0.8 | 温度参数（0.0-2.0） |
| `top_p` | FLOAT | 0.6 | top_p参数（0.0-1.0） |
| `system_prompt` | STRING | 默认系统提示词 | 系统提示词（可选） |
| `user_prompt` | STRING | "请描述这张图片。" | 用户提示词 |

## 输出参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `reasoning_content` | STRING | 思考过程（如果模型支持） |
| `answer` | STRING | 最终答案 |
| `tokens_usage` | STRING | API用量统计信息 |

## 配置要求

在`config.json`中配置Gemini VLM参数：

```json
{
  "VLM": {
    "gemini_vlm": {
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
      "api_key": "your_gemini_api_key",
      "model": [
        "gemini-2.5-flash-lite-preview-06-17",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.5-flash",
        "gemini-2.5-pro"
      ]
    }
  }
}
```

## 使用方法

### 1. 在ComfyUI中使用

1. 启动ComfyUI
2. 在节点选择器中找到 `API/Gemini` 分类
3. 选择 `Gemini VLM API节点`
4. 拖拽到工作流中
5. 连接图片输入节点
6. 配置参数并运行

### 2. 示例工作流

```
图片加载节点 → Gemini VLM API节点 → 文本显示节点
                        ↓
                   保存结果节点
```

### 3. 参数配置建议

- **图片分析**: 使用默认的system_prompt和user_prompt
- **详细描述**: 设置较高的max_tokens（如1024）
- **创意回答**: 提高temperature（如1.2）
- **精确回答**: 降低temperature（如0.3）

## 网络问题解决

如果遇到网络连接问题，可以使用网络诊断工具：

```bash
cd Gemini_Node
python network_diagnosis.py
```

### 常见问题

1. **连接超时**
   - 检查网络连接
   - 使用代理或VPN
   - 增加超时时间

2. **API Key错误**
   - 确认API Key正确
   - 检查API Key权限
   - 验证API Key是否过期

3. **模型不可用**
   - 检查模型名称是否正确
   - 确认API Key有权限访问该模型
   - 尝试其他可用模型

## 测试验证

运行测试脚本验证节点功能：

```bash
cd Gemini_Node
python test_gemini_vlm_node.py
```

## 技术细节

### 图片处理
- 自动将ComfyUI的IMAGE格式转换为base64
- 支持多种图片格式（JPEG、PNG等）
- 自动处理图片尺寸和通道

### API调用
- 使用OpenAI兼容的API格式
- 支持Bearer token认证
- 完善的错误处理和重试机制

### 响应解析
- 自动解析API响应
- 提取思考过程和答案
- 格式化用量统计信息

## 更新日志

- **v1.0.0**: 初始版本，支持基本的图片分析功能
- **v1.0.1**: 添加网络诊断工具和错误处理
- **v1.0.2**: 优化URL格式处理和调试信息

## 注意事项

1. **网络要求**: 需要能够访问Google API服务器
2. **API配额**: 注意API调用的配额限制
3. **图片大小**: 建议图片尺寸不超过2048x2048
4. **响应时间**: 根据网络状况，响应时间可能较长

## 相关链接

- [Gemini API文档](https://ai.google.dev/docs)
- [ComfyUI文档](https://github.com/comfyanonymous/ComfyUI)
- [网络诊断工具](./network_diagnosis.py) 