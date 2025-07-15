# ComfyUI Free API 插件

一个为ComfyUI提供多种免费AI API服务的插件，支持文本对话、图像生成、图像分析等功能。

## 🚀 功能特性

### 📝 文本对话 (LLM)
- **Gemini LLM**: Google Gemini大语言模型
- **GLM LLM**: 智谱AI GLM系列模型
- **Qwen LLM**: 阿里通义千问系列模型
- **Siliconflow LLM**: Siliconflow平台多种模型

### 🖼️ 图像生成 (IMAGE)
- **GLM Image**: 智谱AI图像生成模型
- **Qwen Image**: 阿里通义千问图像生成模型
- **Qwen ImageEdit**: 阿里通义千问图像编辑模型

### 👁️ 图像分析 (VLM)
- **Gemini VLM**: Google Gemini视觉语言模型
- **GLM VLM**: 智谱AI视觉语言模型
- **Qwen VLM**: 阿里通义千问视觉语言模型
- **Siliconflow VLM**: Siliconflow平台视觉语言模型

## 📦 安装

1. 将整个`Comfyui_Free_API`文件夹复制到ComfyUI的`custom_nodes`目录
2. 重启ComfyUI
3. 在节点选择器中找到`API`分类下的相关节点

## ⚙️ 配置

### 1. 获取API密钥

- **Gemini**: 访问 [Google AI Studio](https://makersuite.google.com/app/apikey) 获取API密钥
- **GLM**: 访问 [智谱AI开放平台](https://open.bigmodel.cn/) 获取API密钥
- **Qwen**: 访问 [阿里云通义千问](https://dashscope.console.aliyun.com/) 获取API密钥
- **Siliconflow**: 访问 [Siliconflow平台](https://www.siliconflow.cn/) 获取API密钥

### 2. 修改配置文件

编辑`config.json`文件，将你的API密钥填入对应位置：

```json
{
  "LLM": {
    "gemini_llm": {
      "api_key": "你的Gemini API密钥"
    },
    "glm_llm": {
      "api_key": "你的GLM API密钥"
    }
  }
}
```

## 🎯 使用方法

### 文本对话示例

1. 在ComfyUI中添加`Gemini LLM API`节点
2. 设置参数：
   - `model`: 选择模型
   - `max_tokens`: 最大输出长度
   - `temperature`: 创造性程度
   - `user_prompt`: 输入你的问题
3. 连接`Text Display`节点查看结果

### 图像生成示例

1. 添加`GLM Image API`节点
2. 设置参数：
   - `model`: 选择图像生成模型
   - `quality`: 图像质量
   - `size`: 图像尺寸
   - `prompt`: 描述要生成的图像
3. 连接`Preview Image`节点查看结果

### 图像分析示例

1. 添加`Gemini VLM API`节点
2. 连接输入图像
3. 设置分析提示词
4. 连接`Text Display`节点查看分析结果

## 📁 节点分类

在ComfyUI节点选择器中，所有节点都在`API`分类下：

- `API/Gemini` - Gemini相关节点
- `API/GLM` - GLM相关节点  
- `API/Qwen` - Qwen相关节点
- `API/Siliconflow` - Siliconflow相关节点

## 🔧 常见问题

### Q: API调用失败怎么办？
A: 检查以下几点：
- API密钥是否正确配置
- 网络连接是否正常
- API配额是否充足

### Q: 图像处理出错？
A: 确保：
- 输入图像格式正确
- 图像大小在合理范围内
- 网络连接稳定

### Q: 如何提高生成质量？
A: 尝试：
- 调整temperature参数
- 使用更详细的提示词
- 选择更高级的模型

## 📖 示例工作流

查看`Examples`文件夹中的示例图片，了解各种使用场景的工作流配置。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个插件！

## 📄 许可证

本项目采用MIT许可证。

---

**注意**: 使用前请确保你有相应API服务的有效账户和足够的配额。 