# Siliconflow Node 模块

本模块包含基于Siliconflow API的ComfyUI自定义节点，支持视觉推理和文本对话功能。

## 节点列表

### 1. Siliconflow VLM API节点
- **文件**: `siliconflow_vlm_api_node.py`
- **功能**: 图片视觉推理
- **输入参数**: 
  - `image`: 图片输入
  - `model`: 模型选择
  - `max_tokens`: 最大token数
  - `temperature`: 温度参数
  - `top_p`: top_p参数
  - `system_prompt`: 系统提示词
  - `user_prompt`: 用户提示词
- **输出参数**:
  - `reasoning_content`: 思考过程
  - `answer`: 最终答案
  - `tokens_usage`: API用量信息

### 2. Siliconflow LLM API节点 ⭐ 新增
- **文件**: `siliconflow_llm_api_node.py`
- **功能**: 文本对话推理
- **输入参数**: 
  - `model`: 模型选择
  - `max_tokens`: 最大token数
  - `temperature`: 温度参数
  - `top_p`: top_p参数
  - `system_prompt`: 系统提示词
  - `user_prompt`: 用户提示词
- **输出参数**:
  - `reasoning_content`: 思考过程
  - `answer`: 最终答案
  - `tokens_usage`: API用量信息

## 配置说明

节点会自动从根目录的`config.json`文件中读取配置：

```json
{
  "LLM": {
    "siliconflow_llm": {
      "base_url": "https://api.siliconflow.cn/v1",
      "api_key": "your_api_key_here",
      "model": [
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-V3",
        "moonshotai/Kimi-K2-Instruct",
        "baidu/ERNIE-4.5-300B-A47B",
        "tencent/Hunyuan-A13B-Instruct",
        "MiniMaxAI/MiniMax-M1-80k",
        "THUDM/GLM-4-9B-0414"
      ]
    }
  },
  "VLM": {
    "siliconflow_vlm": {
      "base_url": "https://api.siliconflow.cn/v1",
      "api_key": "your_api_key_here",
      "model": [
        "THUDM/GLM-4.1V-9B-Thinking",
        "Pro/THUDM/GLM-4.1V-9B-Thinking",
        "Qwen/Qwen2.5-VL-72B-Instruct",
        "Qwen/Qwen2.5-VL-32B-Instruct",
        "Qwen/Qwen2-VL-72B-Instruct",
        "Qwen/QVQ-72B-Preview",
        "deepseek-ai/deepseek-vl2"
      ]
    }
  }
}
```

## 使用方法

### 在ComfyUI中使用

1. 启动ComfyUI后，在节点选择器中找到`API/Siliconflow`分类
2. 选择相应的节点：
   - `Siliconflow VLM API节点` - 用于图片视觉推理
   - `Siliconflow LLM API节点` - 用于文本对话
3. 配置输入参数
4. 连接节点到工作流
5. 运行推理

### 测试节点

运行测试脚本验证节点是否正常工作：

```bash
cd Siliconflow_Node
python test_siliconflow_llm_node.py
```

## 特性

- **自动配置**: 从config.json自动读取API配置
- **多模型支持**: 支持多种Siliconflow模型
- **智能解析**: 自动解析reasoning_content和answer
- **错误处理**: 完善的错误处理和重试机制
- **Token统计**: 详细的token使用统计信息

## 注意事项

1. 确保在config.json中正确配置了Siliconflow API Key
2. 网络连接正常，能够访问Siliconflow API
3. API Key有足够的配额和权限
4. 选择的模型在当前API Key下可用

## 更新日志

### v1.0.0 (2024-01-XX)
- 新增Siliconflow LLM API节点
- 支持文本对话功能
- 完整的reasoning_content和tokens_usage输出
- 自动配置加载和错误处理 