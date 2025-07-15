# ComfyUI Free API Plugin

A plugin for ComfyUI that provides multiple free AI API services, supporting text conversation, image generation, and image analysis.

## 🚀 Features

### 📝 Text Conversation (LLM)
- **Gemini LLM**: Google Gemini large language models
- **GLM LLM**: Zhipu AI GLM series models
- **Qwen LLM**: Alibaba Tongyi Qianwen series models
- **Siliconflow LLM**: Various models from Siliconflow platform

### 🖼️ Image Generation (IMAGE)
- **GLM Image**: Zhipu AI image generation models
- **Qwen Image**: Alibaba Tongyi Qianwen image generation models
- **Qwen ImageEdit**: Alibaba Tongyi Qianwen image editing models

### 👁️ Image Analysis (VLM)
- **Gemini VLM**: Google Gemini vision language models
- **GLM VLM**: Zhipu AI vision language models
- **Qwen VLM**: Alibaba Tongyi Qianwen vision language models
- **Siliconflow VLM**: Siliconflow platform vision language models

## 📦 Installation

1. Copy the entire `Comfyui_Free_API` folder to ComfyUI's `custom_nodes` directory
2. Restart ComfyUI
3. Find the relevant nodes under the `API` category in the node selector

## ⚙️ Configuration

### 1. Get API Keys

- **Gemini**: Visit [Google AI Studio](https://makersuite.google.com/app/apikey) to get API key
- **GLM**: Visit [Zhipu AI Open Platform](https://open.bigmodel.cn/) to get API key
- **Qwen**: Visit [Alibaba Cloud Tongyi Qianwen](https://dashscope.console.aliyun.com/) to get API key
- **Siliconflow**: Visit [Siliconflow Platform](https://www.siliconflow.cn/) to get API key

### 2. Modify Configuration File

Edit the `config.json` file and fill in your API keys in the corresponding positions:

```json
{
  "LLM": {
    "gemini_llm": {
      "api_key": "Your Gemini API Key"
    },
    "glm_llm": {
      "api_key": "Your GLM API Key"
    }
  }
}
```

## 🎯 Usage

### Text Conversation Example

1. Add `Gemini LLM API` node in ComfyUI
2. Set parameters:
   - `model`: Select model
   - `max_tokens`: Maximum output length
   - `temperature`: Creativity level
   - `user_prompt`: Enter your question
3. Connect `Text Display` node to view results

### Image Generation Example

1. Add `GLM Image API` node
2. Set parameters:
   - `model`: Select image generation model
   - `quality`: Image quality
   - `size`: Image size
   - `prompt`: Describe the image to generate
3. Connect `Preview Image` node to view results

### Image Analysis Example

1. Add `Gemini VLM API` node
2. Connect input image
3. Set analysis prompt
4. Connect `Text Display` node to view analysis results

## 📁 Node Categories

In ComfyUI node selector, all nodes are under the `API` category:

- `API/Gemini` - Gemini related nodes
- `API/GLM` - GLM related nodes
- `API/Qwen` - Qwen related nodes
- `API/Siliconflow` - Siliconflow related nodes

## 🔧 FAQ

### Q: What if API call fails?
A: Check the following:
- Is the API key correctly configured?
- Is the network connection normal?
- Is there sufficient API quota?

### Q: Image processing error?
A: Ensure:
- Input image format is correct
- Image size is within reasonable range
- Network connection is stable

### Q: How to improve generation quality?
A: Try:
- Adjust temperature parameter
- Use more detailed prompts
- Select more advanced models

## 📖 Example Workflows

Check the example images in the `Examples` folder to understand workflow configurations for various usage scenarios.

## 🤝 Contributing

Welcome to submit Issues and Pull Requests to improve this plugin!

## 📄 License

This project is licensed under the MIT License.

---

**Note**: Please ensure you have valid accounts and sufficient quota for the corresponding API services before use. 