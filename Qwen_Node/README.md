# Qwen API节点

本目录包含用于在ComfyUI中调用阿里云Qwen API的节点，包括视觉推理和图像编辑功能。

## 节点列表

### 1. Qwen VLM API节点 (qwen_vlm_api_node.py)

用于调用阿里云Qwen视觉推理API，实现图片识别、推理等功能。

#### 功能简介
- 专门针对阿里云Qwen视觉大模型API
- 输入图片和自定义提示词，返回AI推理结果文本
- 所有API参数和模型选项自动读取config.json中的VLM.qwen_vlm配置
- 支持流式输出

#### 输入参数说明
- **image**：输入图片（ComfyUI标准image类型）
- **model**：选择推理模型（自动读取VLM.qwen_vlm.model配置）
- **max_tokens**：最大返回token数，默认512
- **temperature**：采样温度，默认0.8
- **top_p**：采样top_p，默认0.6
- **system_prompt**：系统提示词（可选）
- **user_prompt**：用户问题或描述（必填）
- **stream**：是否启用流式输出（可选）

#### 输出
- **reasoning_content**：STRING类型，AI的思考过程
- **answer**：STRING类型，AI返回的最终答案
- **tokens_usage**：STRING类型，API用量统计信息

### 2. Qwen Image Edit API节点 (qwen_imageedit_api_node.py)

用于调用阿里云Qwen图像编辑API，实现多种图像编辑功能。

#### 功能简介
- 支持多种图像编辑功能：风格化、局部重绘、去水印、扩图等
- 支持异步任务处理，自动轮询结果
- 所有API参数自动读取config.json中的IMAGE.qwen_imageedit配置

#### 输入参数说明
- **prompt**：编辑指令（必填，文本框形式）
- **function**：编辑功能类型（必填，下拉框形式）
- **image**：输入图像（必填）
- **mask**：蒙版图像（可选，仅局部重绘功能需要）

#### 支持的编辑功能
- **指令编辑**：通过指令编辑图像，简单编辑任务优先推荐
- **局部重绘**：需要指定编辑区域，适合对编辑范围有精确控制的场景
- **全局风格化**：对整个图像应用统一的风格，支持2种风格
- **局部风格化**：对图像的特定区域应用风格，支持8种风格
- **去文字水印**：自动识别并去除图像中的文字水印
- **扩图**：扩展图像的尺寸，智能填充边缘内容
- **图像超分**：提高图像的分辨率和清晰度
- **图像上色**：为黑白图像添加颜色
- **线稿生图**：将线稿转换为彩色图像
- **参考卡通形象生图**：参考卡通形象生成图像

#### 输出
- **image**：IMAGE类型，编辑后的图像

## 配置文件

### VLM配置 (config.json中的VLM.qwen_vlm)
```json
{
  "VLM": {
    "qwen_vlm": {
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "你的API密钥",
      "model": ["qwen2.5-vl-72b-instruct", "qwen-vl-max-2025-04-08", ...]
    }
  }
}
```

### IMAGE配置 (config.json中的IMAGE.qwen_imageedit)
```json
{
  "IMAGE": {
    "qwen_imageedit": {
      "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2image/image-synthesis",
      "api_key": "你的API密钥",
      "model": "wanx2.1-imageedit"
    }
  }
}
```

## 使用方法

### VLM节点使用
1. 在ComfyUI工作流中添加"Qwen VLM API节点"
2. 选择模型，上传图片，填写问题描述
3. 运行节点，输出即为AI推理结果

### 图像编辑节点使用
1. 在ComfyUI工作流中添加"Qwen Image Edit API节点"
2. 选择编辑功能类型，上传图像，填写编辑指令
3. 如需局部重绘，还需上传蒙版图像
4. 运行节点，等待处理完成，输出编辑后的图像

## 支持的模型

### VLM模型
- qwen2.5-vl-72b-instruct
- qwen2.5-vl-32b-instruct
- qwen-vl-max-2025-04-08
- qwen-vl-max-2025-04-02
- qwen-vl-max-2025-01-25
- qwen-vl-plus-2025-05-07
- qwen-vl-plus-2025-01-25
- qvq-max-2025-05-15
- qvq-max-2025-03-25
- qvq-max-latest
- qvq-max
- qwen-vl-ocr-2025-04-13

### 图像编辑模型
- wanx2.1-imageedit

## 注意事项

1. **API密钥配置**：确保config.json中正确配置了对应的api_key
2. **图像格式**：支持常见图片格式（jpg/png），建议使用JPEG格式
3. **异步处理**：图像编辑功能使用异步API，需要等待处理完成
4. **蒙版要求**：局部重绘功能需要提供蒙版图像，蒙版应为黑白图像
5. **网络连接**：确保网络连接稳定，API调用需要访问阿里云服务

## 常见问题

- 图片过大或格式不支持会报错，请使用常见图片格式
- API key失效或配额不足会导致API请求失败
- 图像编辑任务可能需要较长时间，请耐心等待
- 确保config.json中正确配置了对应的配置项

如有疑问请联系开发者或查阅详细文档。 