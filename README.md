# ComfyUI Free API 插件

> 一个为ComfyUI提供多种免费AI API服务的插件，支持文本对话、图像生成、图像分析、视频分析等功能。

> 精选Gemini、GLM、Qwen、Siliconflow四个官方平台的API接口，针对新用户均有免费使用额度，新手友好。

> 通过在插件目录下的config.json文件中添加`model`名称，然后重启ComfyUI即可添加以上平台的更多模型。

> 新增OpenAI兼容Chat API和Image API节点，任何兼容OpenAI通用接口格式的文本、视觉和画图API节点均可使用。

## 📖 示例工作流

#### LLM API工作流
<img width="1046" height="1129" alt="LLM-API示例" src="https://github.com/user-attachments/assets/e499e5a0-0850-47aa-ab1d-8de62cfb2f75" />

#### VLM API工作流
<img width="1893" height="1195" alt="VLM-API示例" src="https://github.com/user-attachments/assets/c81ed02a-94ed-44f5-a9ad-a7add17467f1" />

#### GLM API视频分析工作流
<img width="1925" height="940" alt="GLM视频推理示例" src="https://github.com/user-attachments/assets/3fc4734f-e53c-4558-b019-6d0eee96aadf" />

#### GLM API文生图工作流
<img width="1269" height="935" alt="GLM图片生成示例" src="https://github.com/user-attachments/assets/eb13e098-1a28-48a7-8a7a-b71d397a0f22" />

#### Qwen API图像编辑工作流
<img width="1383" height="958" alt="Qwen-ImageEdit示例" src="https://github.com/user-attachments/assets/c9d65c6f-9662-4af3-849a-989b44e889f5" />

#### Wan2.1图像编辑工作流
<img width="1383" height="958" alt="Qwen-ImageEdit示例" src="https://github.com/user-attachments/assets/c9d65c6f-9662-4af3-849a-989b44e889f5" />

#### Wan2.2文生图工作流
<img width="1569" height="1150" alt="Wan2 2文生图示例-1" src="https://github.com/user-attachments/assets/6f3527f3-b388-4c11-88f5-6a5044ab2fbc" />

#### Wan2.2文生视频工作流
<img width="1101" height="1055" alt="Wan2 2文生视频示例" src="https://github.com/user-attachments/assets/139b4157-2d5a-4da5-8ec9-320a1ca2e029" />

#### Wan2.2图生视频工作流
<img width="1616" height="1059" alt="Wan2 2图生视频示例" src="https://github.com/user-attachments/assets/2c5edd80-8451-400b-8cdf-4e2645176623" />

## 🚀 功能特性 

### 📝 文本对话 (LLM)
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

### 方法1:手动安装

1. 将整个`Comfyui_Free_API`文件夹复制到ComfyUI的`custom_nodes`目录
2. 重启ComfyUI
3. 在节点选择器中找到`API`分类下的相关节点

### 方法2: Git克隆

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Lingyuzhou111/Comfyui_Free_API.git
```

## ⚙️ 配置

### 1. 获取API密钥

- **Gemini**: 访问 [Google AI Studio](https://makersuite.google.com/app/apikey) 获取API密钥
- **GLM**: 访问 [智谱AI开放平台](https://www.bigmodel.cn/invite?icode=X2DxJtbSTtZrPmDGSjIgW%2Bnfet45IvM%2BqDogImfeLyI%3D) 获取API密钥
- **Qwen**: 访问 [阿里云通义千问](https://dashscope.console.aliyun.com/) 获取API密钥
- **Siliconflow**: 访问 [Siliconflow平台](https://cloud.siliconflow.cn/i/IvfkhvET) 获取API密钥

### 2. 修改配置文件

编辑`config.json`文件，将你的API密钥填入对应位置：

```json
{
  "LLM": {
    "glm_llm": {
      "api_key": "你的GLM API密钥"
    },
    "qwen_llm": {
      "api_key": "你的Qwen API密钥"
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

- `API/OpenAI` - OpenAI兼容格式相关节点
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

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个插件！

## 📄 许可证

本项目采用MIT许可证。

---

**注意**: 使用前请确保你有相应API服务的有效账户和足够的配额。 
