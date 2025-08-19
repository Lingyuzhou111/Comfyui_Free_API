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

# Siliconflow TTS API 节点

## 功能描述

这是一个 ComfyUI 自定义节点，用于调用 Siliconflow TTS（文本转语音）API，将文本转换为语音。

## 主要特性

- 🎯 **文本转语音**: 支持中文、英文、中英混合输入
- 🎭 **多种音色**: 提供8种不同风格的音色选择
- 🔄 **流式支持**: 支持流式和非流式两种输出模式
- 📊 **智能解析**: 自动解析API响应，提供详细的生成信息
- 🎵 **音频输出**: 直接输出ComfyUI兼容的AUDIO格式
- ⚙️ **高级控制**: 支持采样率、播放速度、音频增益等参数调节

## 输入参数

### 必需参数
- **text**: 要转换的文本内容（支持多行输入）
- **voice**: 音色选择（下拉框）
- **model**: TTS模型选择（从config.json动态读取）
- **response_format**: 音频输出格式选择

### 可选参数
- **sample_rate**: 音频采样率（8000-48000 Hz）
- **speed**: 音频播放速度（0.25-4.0倍速）
- **gain**: 音频增益（-10到+10 dB）
- **stream**: 是否启用流式输出（默认：False）

## 音色选项

| 音色名称 | 描述 |
|---------|------|
| alex | 男性音色，清晰自然 |
| anna | 女性音色，温柔甜美 |
| bella | 女性音色，活泼开朗 |
| benjamin | 男性音色，成熟稳重 |
| charles | 男性音色，年轻活力 |
| claire | 女性音色，知性优雅 |
| david | 男性音色，磁性魅力 |
| diana | 女性音色，高贵典雅 |

## 音频格式选项

| 格式 | 描述 | 支持的采样率 |
|------|------|-------------|
| mp3 | MP3压缩格式 | 32000, 44100 Hz |
| wav | WAV无损格式 | 8000, 16000, 24000, 32000, 44100 Hz |
| pcm | PCM原始格式 | 8000, 16000, 24000, 32000, 44100 Hz |
| opus | Opus压缩格式 | 48000 Hz |

## 输出结果

1. **audio**: ComfyUI兼容的音频格式，可直接连接到其他音频处理节点
2. **audio_url**: 音频文件URL（Siliconflow TTS直接返回二进制数据，此字段为空）
3. **generation_info**: 详细的生成信息（包含音频大小、内容类型、生成时间等）

## 使用方法

1. 在 ComfyUI 中添加 "Siliconflow TTS API节点"
2. 输入要转换的文本内容
3. 选择合适的音色
4. 选择TTS模型
5. 选择音频输出格式
6. 调整可选参数（采样率、速度、增益等）
7. 运行后获得音频数据，可直接连接到保存节点或其他处理节点

## 配置要求

确保在 `config.json` 中正确配置了 `TTS.siliconflow_tts` 部分：

```json
{
  "TTS": {
    "siliconflow_tts": {
      "base_url": "https://api.siliconflow.cn/v1",
      "api_key": "your_api_key_here",
      "model": ["FunAudioLLM/CosyVoice2-0.5B", "fnlp/MOSS-TTSD-v0.5"]
    }
  }
}
```

## 技术特点

- **二进制音频处理**: 直接处理API返回的二进制音频数据
- **智能音频转换**: 自动转换为ComfyUI标准音频格式
- **参数验证**: 完善的参数范围检查和验证
- **错误处理**: 完善的异常处理和fallback机制
- **音频优化**: 自动音频归一化和重采样

## 注意事项

- 文本长度建议控制在4000字符以内
- 不同音频格式支持不同的采样率范围
- 播放速度范围：0.25x 到 4.0x
- 音频增益范围：-10 dB 到 +10 dB
- 错误情况下会返回静音音频作为fallback

## 节点分类

在 ComfyUI 中，该节点位于 `API/Siliconflow` 分类下，显示名称为 "Siliconflow TTS API节点"。

## API 特点

Siliconflow TTS API 相比其他TTS服务具有以下优势：
- 支持多种高质量音色
- 提供丰富的音频参数控制
- 支持多种音频格式输出
- 响应速度快，音频质量高
- 支持流式输出，适合长文本处理

# Siliconflow 音频上传节点

## 功能描述

这是一个 ComfyUI 自定义节点，用于向 Siliconflow TTS API 上传参考音频，并获取自定义音色的 URI。通过这个节点，用户可以创建自己的专属音色，用于后续的文本转语音生成。

## 主要特性

- 🎵 **音频上传**: 支持上传 ComfyUI 兼容的 AUDIO 格式音频
- 🔄 **格式转换**: 自动将音频转换为 base64 编码格式
- 🎭 **自定义音色**: 创建用户专属的音色模型
- 📝 **文本关联**: 为音频关联对应的文字内容
- 🚀 **API集成**: 直接调用 Siliconflow 音频上传 API
- ⚙️ **参数复用**: 复用 TTS 节点的模型配置

## 输入参数

### 必需参数
- **audio**: 要上传的参考音频（ComfyUI AUDIO 格式）
- **model**: TTS模型选择（从config.json动态读取，与TTS节点保持一致）
- **custom_name**: 用户自定义的音色名称（建议使用有意义的名称）
- **text**: 参考音频对应的文字内容（用于训练音色模型）

## 输出结果

- **uri**: 自定义音色的唯一标识符，格式为 `speech:custom-name:unique-id:hash`

## 使用方法

### 1. 基本工作流程
1. 在 ComfyUI 中添加 "Siliconflow 音频上传节点"
2. 连接音频源（可以是其他音频处理节点的输出）
3. 选择合适的 TTS 模型
4. 输入自定义音色名称
5. 输入参考音频对应的文字内容
6. 运行后获得自定义音色的 URI

### 2. 与 TTS 节点配合使用
```
音频源 → 音频上传节点 → 获得URI → TTS节点（使用自定义音色）
```

### 3. 音色名称建议
- 使用描述性的名称，如："温柔女声"、"磁性男声"、"童声"等
- 避免使用特殊字符和空格
- 建议使用中文名称，便于识别

## 技术实现

### 音频格式转换
1. **输入**: ComfyUI AUDIO 格式 `{"waveform": torch.Tensor, "sample_rate": int}`
2. **处理**: 转换为 WAV 格式的字节流
3. **编码**: 转换为 base64 编码
4. **输出**: `data:audio/wav;base64,{base64_string}`

### API 请求结构
```json
{
    "model": "FunAudioLLM/CosyVoice2-0.5B",
    "customName": "用户自定义音色名称",
    "audio": "data:audio/wav;base64,{base64编码的音频数据}",
    "text": "参考音频对应的文字内容"
}
```

### 响应处理
- 成功时返回 URI 字段
- 失败时返回错误信息
- 支持详细的日志记录

## 配置要求

### 1. API 配置
确保在 `config.json` 中正确配置了 `TTS.siliconflow_tts` 部分：

```json
{
  "TTS": {
    "siliconflow_tts": {
      "base_url": "https://api.siliconflow.cn/v1",
      "api_key": "your_api_key_here",
      "model": ["FunAudioLLM/CosyVoice2-0.5B", "fnlp/MOSS-TTSD-v0.5"]
    }
  }
}
```

### 2. 日志配置
**默认配置**（推荐）：
- 日志级别：INFO
- 详细日志：false（始终使用简化模式，避免base64字符串刷屏）

如需调试，可通过环境变量启用详细日志：

```bash
# 设置日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
export SILICONFLOW_LOG_LEVEL=INFO

# 启用详细日志（包括base64数据，仅用于调试）
export SILICONFLOW_VERBOSE_LOGS=true

# 禁用详细日志（默认，推荐）
export SILICONFLOW_VERBOSE_LOGS=false
```

**注意**：默认情况下，系统始终使用简化模式，不会记录完整的base64数据，确保日志清晰易读。

## 使用场景

### 1. 个性化音色创建
- 上传自己的声音样本
- 创建专属的音色模型
- 用于个人项目或商业应用

### 2. 音色定制服务
- 为客户定制专属音色
- 品牌音色开发
- 角色音色设计

### 3. 音色优化
- 上传高质量音频样本
- 改进现有音色质量
- 多语言音色支持

## 注意事项

### 音频质量要求
- **时长**: 建议 10-60 秒的清晰音频
- **质量**: 高采样率（建议 44.1kHz 或以上）
- **清晰度**: 避免背景噪音和回声
- **格式**: 支持 WAV、MP3 等常见格式

### 文本内容要求
- **准确性**: 文字内容必须与音频完全匹配
- **长度**: 建议控制在 1000 字符以内
- **语言**: 支持中文、英文等多种语言
- **标点**: 避免使用特殊标点符号

### 使用限制
- **API 配额**: 注意 API 调用次数限制
- **文件大小**: 音频文件不宜过大
- **处理时间**: 上传和处理需要一定时间
- **存储期限**: 自定义音色可能有存储期限

## 错误处理

### 常见错误及解决方案

1. **API Key 错误**
   - 检查 config.json 中的 api_key 配置
   - 确认 API Key 的有效性

2. **音频转换失败**
   - 检查音频数据格式是否正确
   - 确认音频数据完整性

3. **网络请求超时**
   - 检查网络连接
   - 适当增加超时时间

4. **参数验证失败**
   - 检查必填参数是否完整
   - 确认参数格式是否正确

## 节点分类

在 ComfyUI 中，该节点位于 `API/Siliconflow` 分类下，显示名称为 "Siliconflow 音频上传节点"。

## 最佳实践

### 1. 音频准备
- 使用高质量录音设备
- 选择安静的环境录制
- 保持语速和语调一致
- 避免背景音乐和噪音

### 2. 文本准备
- 确保文字与音频完全对应
- 使用标准标点符号
- 避免缩写和特殊符号
- 保持语言风格一致

### 3. 工作流程
- 先测试音频质量
- 准备准确的文字内容
- 选择合适的模型
- 记录生成的 URI

## 扩展功能

### 1. 批量上传
- 支持多个音频文件上传
- 批量创建音色模型
- 批量管理音色资源

### 2. 音色管理
- 查看已创建的音色列表
- 删除不需要的音色
- 更新音色信息

### 3. 质量评估
- 音频质量自动检测
- 音色效果预览
- 质量评分和建议

这个节点为用户提供了创建个性化音色的强大工具，通过与 TTS 节点的配合使用，可以实现更加丰富和个性化的语音合成体验。

# Siliconflow 自定义音色列表节点

## 功能描述

这是一个 ComfyUI 自定义节点，用于获取 Siliconflow TTS API 中所有已创建的自定义音色列表。通过这个节点，用户可以查看和管理已创建的自定义音色，获取它们的URI以便在TTS节点中使用。

## 主要特性

- 🔍 **音色列表获取**: 自动获取所有已创建的自定义音色
- 🔑 **API Key管理**: 支持从config.json读取或手动输入API Key
- 📋 **格式化输出**: 生成易读的音色列表格式
- 🔄 **强制刷新**: 支持强制刷新音色列表
- 📝 **详细信息**: 显示音色名称、模型、URI和文本内容
- 🎯 **使用指导**: 提供清晰的使用说明

## 输入参数

### 必需参数
- **api_key**: Siliconflow API Key（留空则从config.json读取）

### 可选参数
- **force_refresh**: 是否强制刷新音色列表（默认：false）

## 输出结果

- **uri_list**: 格式化的自定义音色列表，包含所有音色的详细信息

## 使用方法

### 1. 基本工作流程
1. 在 ComfyUI 中添加 "Siliconflow 自定义音色列表" 节点
2. 输入API Key（或留空使用config.json中的配置）
3. 选择是否强制刷新
4. 运行后获得完整的音色列表

### 2. 与TTS节点配合使用
```
音色列表节点 → 获取URI → TTS节点（使用自定义音色）
```

### 3. 工作流示例
```
Siliconflow 自定义音色列表 → 展示文本
                    ↓
            复制URI到TTS节点
                    ↓
            Siliconflow TTS API节点
```

## 技术实现

### API调用
- **端点**: `GET /v1/audio/voice/list`
- **认证**: Bearer Token
- **超时**: 60秒

### 响应处理
- 解析JSON响应中的`results`数组
- 提取每个音色的关键信息
- 格式化生成易读的文本输出

### 错误处理
- API请求失败处理
- JSON解析错误处理
- 网络异常处理
- 配置缺失处理

## 配置要求

### 1. API配置
确保在 `config.json` 中正确配置了 `TTS.siliconflow_tts` 部分：

```json
{
  "TTS": {
    "siliconflow_tts": {
      "base_url": "https://api.siliconflow.cn/v1",
      "api_key": "your_api_key_here",
      "model": ["FunAudioLLM/CosyVoice2-0.5B", "fnlp/MOSS-TTSD-v0.5"]
    }
  }
}
```

### 2. 日志配置
支持通过环境变量控制日志输出：

```bash
# 设置日志级别
export SILICONFLOW_LOG_LEVEL=INFO

# 启用详细日志
export SILICONFLOW_VERBOSE_LOGS=true
```

## 输出格式示例

### 成功输出
```
🎵 Siliconflow 自定义音色列表
==================================================
总计: 2 个音色

🎭 音色 1:
   名称: 温柔女声
   模型: FunAudioLLM/CosyVoice2-0.5B
   URI: speech:温柔女声:cm06fwxp000068q4ogttrpwj5:kaxgzbtrmbhupklkvqqj
   文本: 在一无所知中, 梦里的一天结束了，一个新的轮回便会开始

🎭 音色 2:
   名称: 磁性男声
   模型: fnlp/MOSS-TTSD-v0.5
   URI: speech:磁性男声:cm06fwxp000068q4ogttrpwj5:kaxgzbtrmbhupklkvqqj
   文本: 今天天气真好，适合出去走走

📝 使用说明:
• 复制上述URI到TTS节点的voice参数中
• 支持在TTS节点中使用自定义音色
• 音色名称建议使用有意义的描述
```

### 错误输出
```
错误：未配置Siliconflow TTS API Key，请在config.json中设置siliconflow_tts.api_key或在节点中输入
```

## 使用场景

### 1. 音色管理
- 查看已创建的所有自定义音色
- 管理音色资源
- 备份音色信息

### 2. 工作流集成
- 在TTS工作流中获取可用音色
- 动态选择音色
- 批量处理不同音色

### 3. 调试和测试
- 验证音色创建是否成功
- 检查API连接状态
- 排查音色相关问题

## 注意事项

### API限制
- 注意API调用频率限制
- 大型音色列表可能需要较长处理时间
- 建议合理使用强制刷新功能

### 数据安全
- API Key信息敏感，注意保护
- 音色列表可能包含个人信息
- 生产环境请谨慎使用

### 性能考虑
- 音色列表较大时可能影响性能
- 建议缓存音色列表，避免频繁请求
- 使用强制刷新功能时要考虑网络延迟

## 错误处理

### 常见错误及解决方案

1. **API Key错误**
   - 检查config.json中的api_key配置
   - 确认API Key的有效性
   - 尝试在节点中手动输入API Key

2. **网络连接失败**
   - 检查网络连接
   - 确认API端点可访问
   - 适当增加超时时间

3. **权限不足**
   - 确认API Key有足够的权限
   - 检查账户状态
   - 联系Siliconflow支持

4. **响应格式错误**
   - 检查API版本兼容性
   - 查看API文档更新
   - 启用详细日志进行调试

## 节点分类

在 ComfyUI 中，该节点位于 `API/Siliconflow` 分类下，显示名称为 "Siliconflow 自定义音色列表"。

## 最佳实践

### 1. 工作流设计
- 将音色列表节点放在工作流开始位置
- 使用展示文本节点查看结果
- 合理设置刷新频率

### 2. 音色管理
- 使用有意义的音色名称
- 定期清理不需要的音色
- 记录音色的用途和特点

### 3. 性能优化
- 避免频繁调用音色列表
- 使用缓存机制
- 合理设置超时时间

## 扩展功能

### 1. 音色筛选
- 按模型筛选音色
- 按名称搜索音色
- 按创建时间排序

### 2. 批量操作
- 批量删除音色
- 批量更新音色信息
- 批量导出音色配置

### 3. 音色预览
- 音色效果试听
- 音色质量评估
- 音色对比分析

这个节点为用户提供了管理Siliconflow自定义音色的强大工具，通过与TTS节点的配合使用，可以实现更加灵活和个性化的语音合成工作流。

# Siliconflow 音频转文字节点

## 功能描述

`Siliconflow_Audio_To_Text` 节点是一个 ComfyUI 自定义节点，用于将音频文件转换为文字内容。该节点集成了 Siliconflow 平台的音频转录 API，支持多种音频格式和模型。

## 主要特性

- **音频输入支持**：接受 ComfyUI 的 AUDIO 格式输入
- **模型选择**：支持多种音频转录模型，默认使用 `FunAudioLLM/SenseVoiceSmall`
- **自动配置**：自动读取 `config.json` 中的 API 配置
- **临时文件管理**：自动创建和清理临时 WAV 文件
- **错误处理**：完善的错误处理和日志记录

## 输入参数

### 必需参数

| 参数名 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `audio` | AUDIO | 要转录的音频文件 | - |
| `model` | STRING | 音频转录模型选择 | FunAudioLLM/SenseVoiceSmall |

### 模型选项

节点会自动从 `config.json` 中读取可用的模型选项，并确保默认模型 `FunAudioLLM/SenseVoiceSmall` 在列表中。

## 输出参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `text` | STRING | 识别出的文字内容 |

## 使用方法

### 1. 基本使用

1. 在 ComfyUI 中添加 `Siliconflow_Audio_To_Text` 节点
2. 连接音频输入（可以是其他节点生成的音频或加载的音频文件）
3. 选择转录模型（可选）
4. 运行节点，获取转录结果

### 2. 工作流示例

```
音频文件 → Siliconflow_Audio_To_Text → 文字输出
    ↓
音频转录 → 文字内容
```

### 3. 配置要求

确保在 `config.json` 中配置了 Siliconflow API 参数：

```json
{
  "TTS": {
    "siliconflow_tts": {
      "base_url": "https://api.siliconflow.cn/v1",
      "api_key": "your-api-key-here",
      "model": [
        "FunAudioLLM/SenseVoiceSmall",
        "其他模型..."
      ]
    }
  }
}
```

## API 接口

### 请求端点

```
POST https://api.siliconflow.cn/v1/audio/transcriptions
```

### 请求参数

- **Authorization**: Bearer token（从 config.json 读取）
- **Content-Type**: multipart/form-data
- **model**: 转录模型名称
- **file**: 音频文件（WAV 格式）

### 响应格式

```json
{
  "text": "识别出的文字内容"
}
```

## 技术实现

### 音频处理流程

1. **输入验证**：检查音频数据是否有效
2. **格式转换**：将 ComfyUI AUDIO 格式转换为 WAV 文件
3. **临时文件**：创建临时 WAV 文件用于 API 请求
4. **API 调用**：发送 multipart/form-data 请求到 Siliconflow
5. **响应解析**：解析 API 响应，提取文字内容
6. **资源清理**：删除临时文件

### 错误处理

- API 配置缺失
- 音频数据无效
- 文件转换失败
- 网络请求异常
- 响应解析错误

## 日志信息

节点会记录详细的日志信息，包括：

- 音频转换状态
- API 请求详情
- 响应处理结果
- 错误信息和异常

### 日志级别控制

通过环境变量控制日志详细程度：

```bash
# 设置日志级别
export SILICONFLOW_LOG_LEVEL=DEBUG

# 启用详细日志
export SILICONFLOW_VERBOSE_LOGS=true
```

## 注意事项

1. **API 密钥**：确保在 `config.json` 中正确配置了 Siliconflow API Key
2. **音频格式**：节点会自动将音频转换为 WAV 格式
3. **临时文件**：临时文件会在处理完成后自动删除
4. **网络超时**：API 请求超时时间设置为 180 秒
5. **模型兼容性**：确保选择的模型支持音频转录功能

## 常见问题

### Q: 节点无法识别音频输入
A: 检查音频数据格式是否正确，确保输入的是 ComfyUI 的 AUDIO 格式

### Q: API 请求失败
A: 检查 `config.json` 中的 API 配置，确保 base_url 和 api_key 正确

### Q: 转录结果为空
A: 检查音频质量，确保音频清晰可听，尝试不同的转录模型

### Q: 处理速度慢
A: 音频转录需要时间，长音频文件处理时间会更长，请耐心等待

## 更新日志

- **v1.0.0**: 初始版本，支持基本的音频转文字功能
- 支持多种音频转录模型
- 自动配置管理
- 完善的错误处理
- 详细的日志记录

## 技术支持

如果遇到问题，请检查：

1. 日志输出中的错误信息
2. API 配置是否正确
3. 网络连接是否正常
4. 音频文件是否有效

---

*Siliconflow 音频转文字节点 - 让音频内容更易理解*


