# OpenAI兼容API节点

## 概述

OpenAI兼容API节点是ComfyUI Free API插件中的一个通用节点，支持调用任意兼容OpenAI格式的API接口进行文本对话和图像分析。

## 功能特性

- ✅ **通用兼容**: 支持所有兼容OpenAI格式的API接口
- ✅ **文本对话**: 支持纯文本对话功能
- ✅ **图像分析**: 支持图像分析功能
- ✅ **智能解析**: 自动解析思考过程和答案
- ✅ **灵活配置**: 支持自定义API端点和模型
- ✅ **错误处理**: 完善的错误处理和重试机制

## 支持的API服务

节点支持所有兼容OpenAI格式的API，包括但不限于：

- OpenAI官方API
- Azure OpenAI
- 各种开源模型的API服务
- 第三方AI服务提供商的兼容API

## 输入参数

### 必选参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| base_url | STRING | https://api.openai.com/v1 | API基础URL |
| model | STRING | gpt-4o | 模型名称 |
| api_key | STRING | "" | API密钥 |
| system_prompt | STRING | "你是一个有帮助的AI助手。" | 系统提示词 |
| user_prompt | STRING | "你好！" | 用户问题 |
| max_tokens | INT | 512 | 最大输出长度 |
| temperature | FLOAT | 0.7 | 创造性程度 |
| top_p | FLOAT | 1.0 | 核采样参数 |

### 可选参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| image | IMAGE | 输入图像（用于图像分析） |

## 输出参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| reasoning_content | STRING | 思考过程（如果API返回包含思考标签的内容） |
| answer | STRING | 最终答案 |
| tokens_usage | STRING | API用量信息 |

## 使用方法

### 1. 文本对话

1. 在ComfyUI中添加`OpenAI兼容API节点`
2. 设置必选参数：
   - `base_url`: 输入API基础URL
   - `model`: 输入模型名称
   - `api_key`: 输入你的API密钥
   - `system_prompt`: 设置系统提示词
   - `user_prompt`: 输入你的问题
3. 调整可选参数：
   - `max_tokens`: 控制输出长度
   - `temperature`: 控制创造性
   - `top_p`: 控制输出多样性
4. 连接`Text Display`节点查看结果

### 2. 图像分析

1. 在ComfyUI中添加`OpenAI兼容API节点`
2. 连接输入图像到`image`参数
3. 设置参数：
   - `base_url`: 输入支持视觉的API基础URL
   - `model`: 输入支持视觉的模型名称
   - `api_key`: 输入你的API密钥
   - `user_prompt`: 输入图像分析问题
4. 连接`Text Display`节点查看分析结果

## 配置示例

### OpenAI官方API

```json
{
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o",
  "api_key": "sk-your-openai-api-key",
  "system_prompt": "你是一个专业的AI助手。",
  "user_prompt": "请解释什么是人工智能？"
}
```

### 第三方兼容API

```json
{
  "base_url": "https://your-api-provider.com/v1",
  "model": "your-model-name",
  "api_key": "your-api-key",
  "system_prompt": "你是一个专业的编程助手。",
  "user_prompt": "请帮我优化这段代码。"
}
```

## 响应解析

节点会自动解析以下格式的响应：

- `<think>思考内容</think>` - 提取思考过程
- `<reasoning>推理过程</reasoning>` - 提取推理过程
- `<answer>答案内容</answer>` - 提取答案内容

如果API返回这些标签，节点会自动分离思考过程和答案。

## 错误处理

节点包含完善的错误处理机制：

- **网络连接错误**: 自动重试并提供详细错误信息
- **API密钥错误**: 提示检查API密钥配置
- **模型不支持**: 提示检查模型名称
- **图像处理错误**: 提供图像转换失败的具体原因

## 注意事项

1. **API密钥安全**: 不要在公开场合分享你的API密钥
2. **网络连接**: 确保网络连接稳定，某些API可能需要代理
3. **模型兼容性**: 确保选择的模型支持你的使用场景（文本/图像）
4. **费用控制**: 注意API调用费用，合理设置max_tokens参数
5. **图像格式**: 支持常见的图像格式，会自动转换为JPEG格式

## 常见问题

### Q: 为什么我的API调用失败？
A: 检查以下几点：
- API密钥是否正确
- base_url是否正确
- 模型名称是否正确
- 网络连接是否正常

### Q: 如何提高响应质量？
A: 尝试：
- 调整temperature参数（0.3-0.7通常较好）
- 使用更详细的system_prompt
- 增加max_tokens值
- 选择更高级的模型

### Q: 图像分析不工作怎么办？
A: 确保：
- 选择的模型支持视觉功能
- 图像格式正确
- API服务支持图像分析

## 示例工作流

查看`Examples`文件夹中的示例：
- `openai_chat_example.json` - 文本对话示例
- `openai_vlm_example.json` - 图像分析示例

## 测试

运行测试脚本验证节点功能：

```bash
cd OpenAI_Node
python test_openai_node.py
```

## 更新日志

### v1.1.0 (2024-12-XX)
- ✅ 新增OpenAI兼容API节点
- ✅ 支持文本对话和图像分析
- ✅ 完善的错误处理机制
- ✅ 自动响应解析功能
- ✅ 详细的文档和示例 