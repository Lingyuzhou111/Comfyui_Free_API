# ComfyUI Free API 插件

> 一个为ComfyUI提供多种免费AI API服务的插件，支持文本对话、图像生成、图像分析、视频分析、视频生成等功能。

> 精选Gemini、GLM、Qwen、Siliconflow四个官方平台的API接口，针对新用户均有免费使用额度，新手友好。

> **250715** ：通过在插件目录下的config.json文件中添加`model`名称，然后重启ComfyUI即可添加以上平台的更多模型。

> **250717** ：新增OpenAI兼容Chat API和Image API节点，任何兼容OpenAI通用接口格式的文本、视觉和画图API节点均可使用。

> **250717** ：新增Qwen Image API和Qwen Video API节点，支持最新的Wan2.2文生图、Wan2.2文生视频、Wan2.2图生视频和Wan2.1首尾帧生视频。

> **250729** ：GLM LLM API节点支持最新的glm-4.5、glm-4.5-air和glm-4.5-flash推理模型。

> **250805** ：新增支持硅基流动、火山方舟、魔搭等API平台的图像生成，支持调用第三方gpt-image-1的API进行多图编辑

> **250817** ：新增支持Qwen-TTS的语音合成，Siliconflow-TTS的语音合成和语音识别节点

> **250818** ：Qwen Image API(阿里云百炼)和OpenAI Image API(支持魔搭API)节点支持最新的qwen-image文生图功能

> **250819** ：新增Qwen Image Edit API节点支持最新的qwen-image-edit图生图功能

> **250909** ：新增LLM Prompt Enhance和VLM Prompt Enhance节点支持预设提示增强功能

> **250912** ：新增Free Translate节点支持免费的多语种翻译

> **251001** ：新增OpenAI Sora API节点支持调用302平台的sora-2生成视频

> **251008** ：将OpenAI Sora API节点拆分为Chat(同步)模式和Async(异步)模式，支持302和T8star双平台一键切换

> **251014** ：新增Grok imagine i2v图生视频节点(需要特殊网络环境)

> **251027** ：新增Haiyi AI生图和AI生视频节点

## 📖 示例工作流
####  新增Haiyi AI生图和AI生视频节点
<img width="445" height="580" alt="wechat_2025-10-26_231947_777" src="https://github.com/user-attachments/assets/61acf51c-7482-40ab-a92e-4c2ec5c22427" />
<img width="545" height="580" alt="wechat_2025-10-26_222817_408" src="https://github.com/user-attachments/assets/ba9421db-d7db-4d31-92c0-540ee7bf6de6" />
<img width="1020" height="725" alt="wechat_2025-10-26_210116_071" src="https://github.com/user-attachments/assets/17a3eb7e-01ab-438a-a79d-7f4aa7cfb420" />
-海艺平台注册地址: https://www.haiyi.art 

####  新增Grok imagine i2v图生视频节点
<img width="1025" height="1099" alt="55950dfa87bcaecef8e08e1cf4da7c02" src="https://github.com/user-attachments/assets/d2c3937a-2bd2-42e0-8dee-84ab05d7b51f" />
示例工作流 https://github.com/Lingyuzhou111/Comfyui_Free_API/blob/main/Examples/LYZ_GROK_I2V%E5%B7%A5%E4%BD%9C%E6%B5%81.json

####  将OpenAI Sora API节点拆分为Chat(同步)模式和Async(异步)模式，支持双平台一键切换
<img width="1201" height="1099" alt="wechat_2025-10-08_231405_662" src="https://github.com/user-attachments/assets/c2f1c634-91b0-438e-9422-b130dda461c4" />
<img width="1473" height="1095" alt="wechat_2025-10-08_222903_939" src="https://github.com/user-attachments/assets/90a55031-b849-4621-a15e-5273208ec39f" />
示例工作流 https://github.com/Lingyuzhou111/Comfyui_Free_API/blob/main/Examples/LYZ-Sora-API%E5%B7%A5%E4%BD%9C%E6%B5%81.json

-302.ai平台 https://share.302.ai/U6TUev
-T8star平台 https://ai.t8star.cn/register?aff=lUL848049

####  新增OpenAI Sora API节点支持调用302平台的sora-2生成视频
<img width="1730" height="994" alt="00e37c9fdf869fda83b88e90674b30e7" src="https://github.com/user-attachments/assets/70fbacc5-6388-4d10-a8eb-e32f1576873f" />
-支持文生和图生，在提示词末尾加入"使用横屏/竖屏"或"比例16:9/9:16"可指定生成结果的比例

####  新增Free Translate节点支持免费的多语种翻译
<img width="875" height="916" alt="7d05c199efb0a0daaebbcc840b181848" src="https://github.com/user-attachments/assets/8a758798-5b7e-409d-9abf-c35651d82028" />

####  新增LLM Prompt Enhance和VLM Prompt Enhance节点支持预设提示增强功能
<img width="1825" height="1128" alt="b566b6f819bf68a377ac0fb2519f78d0" src="https://github.com/user-attachments/assets/5d77442d-a308-4dc0-8489-9c52d575a45a" />
<img width="1836" height="1205" alt="2df8b526c32ecdd4d20bacd7454a4c05" src="https://github.com/user-attachments/assets/3d97deeb-2406-4e6f-8e4b-b3c6d6aa119b" />

####  新增Qwen Image Edit API节点支持最新的qwen-image-edit图生图功能
<img width="2165" height="888" alt="wechat_2025-08-19_172109_520" src="https://github.com/user-attachments/assets/d205a80a-2d42-4062-a8ce-b09b4435cb2d" />

####  Qwen Image API(阿里云百炼)和OpenAI Image API(支持魔搭API)节点支持最新的qwen-image文生图功能
<img width="2173" height="886" alt="wechat_2025-08-19_172042_625" src="https://github.com/user-attachments/assets/a857e7b2-234a-4c17-b0c9-eb91683a61e6" />

#### 新增支持Qwen-TTS的语言合成，Siliconflow-TTS的语音合成和语音识别节点
<img width="2330" height="979" alt="wechat_2025-08-18_060009_885" src="https://github.com/user-attachments/assets/ec6614d1-20e1-42b5-a003-73f93b8cec58" />
<img width="2130" height="910" alt="wechat_2025-08-18_060849_384" src="https://github.com/user-attachments/assets/690a2083-534f-45ec-abba-410c7cc19c41" />

#### 新增支持硅基流动、火山方舟、魔搭等API平台的图像生成和调用第三方gpt-image-1的API进行多图编辑
<img width="1650" height="1149" alt="OpenAI兼容格式文生图-1" src="https://github.com/user-attachments/assets/65d81826-91a5-42c1-bf7e-5febed60d51f" />
<img width="1995" height="718" alt="OpenAI兼容格式文生图-2" src="https://github.com/user-attachments/assets/c73ce3d3-fcd1-4e35-a4d8-53e5f1537a77" />

#### Wan2.1首尾帧生视频工作流
<img width="1458" height="1168" alt="Wan2 1首尾帧生视频示例" src="https://github.com/user-attachments/assets/e1541ca4-c1a5-4617-a9b7-baee9eb51499" />

#### Wan2.2图生视频工作流
<img width="1616" height="1059" alt="Wan2 2图生视频示例" src="https://github.com/user-attachments/assets/2c5edd80-8451-400b-8cdf-4e2645176623" />

#### Wan2.2文生视频工作流
<img width="1101" height="1055" alt="Wan2 2文生视频示例" src="https://github.com/user-attachments/assets/139b4157-2d5a-4da5-8ec9-320a1ca2e029" />

#### Wan2.2文生图工作流
<img width="1569" height="1150" alt="Wan2 2文生图示例-1" src="https://github.com/user-attachments/assets/6f3527f3-b388-4c11-88f5-6a5044ab2fbc" />

#### Wan2.1图像编辑工作流(该节点已更名为Wanx2.1 Image Edit API节点，与最新的QwenImageEdit节点以示区分)
<img width="1383" height="958" alt="Qwen-ImageEdit示例" src="https://github.com/user-attachments/assets/c9d65c6f-9662-4af3-849a-989b44e889f5" />

#### GLM API文生图工作流
<img width="1269" height="935" alt="GLM图片生成示例" src="https://github.com/user-attachments/assets/eb13e098-1a28-48a7-8a7a-b71d397a0f22" />

#### GLM API视频分析工作流
<img width="1925" height="940" alt="GLM视频推理示例" src="https://github.com/user-attachments/assets/3fc4734f-e53c-4558-b019-6d0eee96aadf" />

#### VLM API工作流
<img width="1893" height="1195" alt="VLM-API示例" src="https://github.com/user-attachments/assets/c81ed02a-94ed-44f5-a9ad-a7add17467f1" />

#### LLM API工作流
<img width="1046" height="1129" alt="LLM-API示例" src="https://github.com/user-attachments/assets/e499e5a0-0850-47aa-ab1d-8de62cfb2f75" />

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
    },
    "siliconflow_llm": {
      "api_key": "你的Siliconflow API密钥"
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






























