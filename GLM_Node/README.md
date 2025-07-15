# GLM Node 模块

本模块包含基于智谱AI GLM API的ComfyUI自定义节点，支持视觉推理、文本对话和图像生成功能。

## 节点列表

### 1. GLM VLM API节点
- **文件**: `glm_vlm_api_node.py`
- **功能**: 图片和视频视觉推理
- **输入参数**: 
  - `image`: 本地图片输入
  - `image_url`: 图片URL输入
  - `video_url`: 视频URL输入
  - `model`: 模型选择
  - `max_tokens`: 最大token数
  - `temperature`: 温度参数
  - `top_p`: top_p参数
  - `system_prompt`: 系统提示词
  - `user_prompt`: 用户提示词
- **输出参数**:
  - `reasoning_content`: 思考过程
  - `answer`: 最终答案

### 2. GLM LLM API节点
- **文件**: `glm_llm_api_node.py`
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

### 3. GLM Image API节点 ⭐ 新增
- **文件**: `glm_image_api_node.py`
- **功能**: 文本到图像生成
- **输入参数**: 
  - `model`: 模型选择（下拉框）
  - `quality`: 图像质量（下拉框：standard/hd）
  - `size`: 图像尺寸（下拉框：1024x1024等）
  - `prompt`: 文本描述（文本框）
- **输出参数**:
  - `image`: 生成的图片（IMAGE类型）

### 4. GLM视频推理节点
- **文件**: `glm_vlm_api_video_node.py`
- **功能**: 专门用于视频理解的节点
- **输入参数**: 与VLM API节点类似
- **输出参数**: 与VLM API节点类似

## 功能简介

### GLM VLM API节点
- 支持智谱GLM系列视觉大模型API（如GLM-4V、GLM-4.1V等）
- **支持三种输入方式**：本地图片、图片URL、视频URL
- 输入图片/视频和自定义提示词，返回AI推理结果文本
- 智能解析reasoning_content和answer，支持两种格式
- 所有API参数和模型选项自动读取config.json
- **简洁高效**：直接使用API字段，无需复杂的流式解析

### GLM LLM API节点
- 支持智谱GLM系列大语言模型API（如GLM-4、GLM-Z1等）
- 输入文本提示词，返回AI对话结果
- 支持reasoning_content和tokens_usage输出
- 自动从配置文件读取API参数和模型选项

### GLM Image API节点 ⭐ 新增
- 支持智谱AI的图像生成模型（如CogView-4等）
- 输入文本描述，生成高质量图片
- 支持多种图像质量和尺寸选项
- 自动下载和转换图片为ComfyUI格式
- 完整的错误处理和重试机制

## 输入参数说明

### GLM VLM API节点参数

#### 必需参数
- **model**：选择推理模型（自动读取配置，如glm-4v-flash、glm-4.1v等）
- **max_tokens**：最大返回token数，默认512，范围1-8192
- **temperature**：采样温度，默认0.8，范围0.0-2.0
- **top_p**：采样top_p，默认0.6，范围0.0-1.0
- **system_prompt**：系统提示词（可选，用于设定AI角色和行为）
- **user_prompt**：用户问题或描述（必填，如"请描述这张图片"）

#### 可选输入参数（三选一，通过连线接入）
- **image**：本地图片输入（ComfyUI标准image类型）
- **image_url**：图片URL地址（STRING类型，通过连线接入）
- **video_url**：视频URL地址（STRING类型，通过连线接入）

**注意**：三种输入方式互斥，优先使用video_url > image_url > image

### GLM LLM API节点参数
- **model**：选择对话模型（自动读取配置）
- **max_tokens**：最大返回token数，默认2048，范围1-8192
- **temperature**：采样温度，默认0.8，范围0.0-2.0
- **top_p**：采样top_p，默认0.6，范围0.0-1.0
- **system_prompt**：系统提示词（可选）
- **user_prompt**：用户提示词（必填）

### GLM Image API节点参数 ⭐ 新增
- **model**：选择图像生成模型（下拉框，如cogview-4-250304）
- **quality**：图像质量（下拉框）
  - `standard`：标准质量，生成速度快（5-10秒）
  - `hd`：高清质量，细节更丰富（约20秒）
- **size**：图像尺寸（下拉框）
  - 推荐尺寸：1024x1024, 768x1344, 864x1152, 1344x768, 1152x864, 1440x720, 720x1440
  - 自定义尺寸：长宽512px-2048px，需被16整除，最大像素数不超过2^21
- **prompt**：图像描述文本（文本框，必填）

## 输出

### GLM VLM API节点输出
- **reasoning_content**：STRING类型，AI的思考过程
- **answer**：STRING类型，AI返回的最终答案

### GLM LLM API节点输出
- **reasoning_content**：STRING类型，AI的思考过程
- **answer**：STRING类型，AI返回的最终答案
- **tokens_usage**：STRING类型，API用量统计信息

### GLM Image API节点输出 ⭐ 新增
- **image**：IMAGE类型，生成的图片（ComfyUI标准格式）

## 使用方法

### GLM VLM API节点

#### 方式一：本地图片
1. 在ComfyUI工作流中添加"GLM VLM API节点"
2. 连接图片节点到image输入
3. 选择模型，填写问题描述
4. 运行节点

#### 方式二：图片URL（连线方式）
1. 在ComfyUI工作流中添加"GLM VLM API节点"
2. 添加一个文本节点（如PrimitiveNode），输入图片URL
3. 将文本节点的输出连接到GLM节点的image_url输入
4. 选择模型，填写问题描述
5. 运行节点

#### 方式三：视频URL（连线方式）
1. 在ComfyUI工作流中添加"GLM VLM API节点"
2. 添加一个文本节点（如PrimitiveNode），输入视频URL
3. 将文本节点的输出连接到GLM节点的video_url输入
4. 选择模型，填写问题描述（如"请仔细描述这个视频"）
5. 运行节点

### GLM LLM API节点
1. 在ComfyUI工作流中添加"GLM LLM API节点"
2. 配置模型、参数和提示词
3. 连接节点到工作流
4. 运行推理

### GLM Image API节点 ⭐ 新增
1. 在ComfyUI工作流中添加"GLM Image API节点"
2. 配置参数：
   - **model**: 选择图像生成模型（如cogview-4-250304）
   - **quality**: 选择图像质量（standard或hd）
   - **size**: 选择图像尺寸（如1024x1024）
   - **prompt**: 输入图像描述文本
3. 连接节点的image输出到预览或保存节点
4. 运行生成

## 配置文件

### GLM VLM API节点
- 节点会自动读取`Comfyui_Free_API/config.json`中的`glm_vlm`配置
- 需要配置`api_key`（智谱API密钥）和`base_url`（API地址）
- 模型列表会自动从配置中读取

### GLM LLM API节点
- 节点会自动读取`Comfyui_Free_API/config.json`中的`glm_llm`配置
- 需要配置`api_key`（智谱API密钥）和`base_url`（API地址）
- 模型列表会自动从配置中读取

### GLM Image API节点 ⭐ 新增
- 节点会自动读取`Comfyui_Free_API/config.json`中的`glm_image`配置
- 需要配置`api_key`（智谱API密钥）和`base_url`（API地址）
- 模型列表会自动从配置中读取

#### GLM Image配置示例
```json
{
  "IMAGE": {
    "glm_image": {
      "base_url": "https://open.bigmodel.cn/api/paas/v4/images/generations",
      "api_key": "your_api_key_here",
      "model": ["cogview-4-250304", "cogview-4", "cogview-3-flash"]
    }
  }
}
```

## 解析逻辑
- **主要方式**：直接使用API返回的`reasoning_content`字段（如glm-4.1v-thinking-flash）
- **备用方式**：解析content中的`<think>...</think>`标签（兼容其他模型）
- **智能降级**：自动选择最佳解析方式，确保兼容性

## 支持的模型类型

### 支持reasoning_content字段的模型
- `glm-4.1v-thinking-flash` ✅
- `glm-4.1v-thinking` ✅
- `glm-4.1v-thinking-flashx` ✅（支持视频理解）
- 其他支持思考过程的GLM模型

### 需要标签解析的模型
- `glm-4v-flash` ⚠️
- `glm-4v-plus` ⚠️
- `glm-4v` ⚠️
- 其他基础GLM模型

## 常见问题
- **reasoning_content为空**：检查模型是否支持思考过程输出（如glm-4.1v-thinking-flash），或调整system_prompt引导模型输出思考过程
- **图片处理失败**：请使用常见图片格式（jpg/png），确保图片大小适中
- **视频处理失败**：确保视频URL可访问，支持常见视频格式（mp4等）
- **URL格式错误**：确保URL以http://或https://开头
- **连线输入为空**：确保文本节点正确输出URL字符串
- **API请求失败**：检查API key是否有效，网络连接是否正常
- **解析失败**：如果API返回格式异常，节点会返回原始内容作为answer

## 技术说明
- **多输入支持**：智能识别输入类型，自动构造相应的API请求
- **连线接入**：image_url和video_url支持通过其他节点连线输入
- **URL验证**：基本的URL格式验证，确保输入正确
- **简洁高效**：直接使用API字段，避免复杂的流式解析
- **智能兼容**：自动适配不同模型的响应格式
- **错误处理**：完善的错误处理机制，确保节点稳定运行

## API兼容性
- **GLM API**：完全兼容，支持JWT认证
- **响应格式**：支持reasoning_content字段和标签解析两种格式
- **思考过程**：适用于支持思考过程的模型
- **视频理解**：支持视频URL输入，适用于支持视频的模型

## 使用示例

### 图片URL连线示例
```
文本节点输出: https://example.com/test.jpg
连接到: GLM节点的image_url输入
user_prompt: 请描述这张图片中的内容
```

### 视频URL连线示例
```
文本节点输出: https://example.com/test.mp4
连接到: GLM节点的video_url输入
user_prompt: 请仔细描述这个视频中发生了什么
```

## 工作流示例

### 图片URL工作流
1. PrimitiveNode（文本节点）→ 输出图片URL
2. GLM VLM API节点 ← 连接image_url
3. 设置其他参数并运行

### 视频URL工作流
1. PrimitiveNode（文本节点）→ 输出视频URL
2. GLM VLM API节点 ← 连接video_url
3. 设置其他参数并运行

如有疑问请联系开发者或查阅详细文档。 