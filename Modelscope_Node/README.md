# ModelScope Image API 节点

## 概述

ModelScope Image API 节点是一个适配 ComfyUI 的自定义节点，用于调用魔搭（ModelScope）的图像生成服务。该节点支持多种模型和 Lora，可以生成高质量的图像。

## 功能特性

- **多模型支持**：支持 Qwen Image、FLUX、FLUX Kontext、FLUX Krea、麦橘超然、写实风、动漫风、水墨画等多种模型
- **多Lora串联**：支持最多三个Lora模型串联使用，实现更丰富的图像生成效果
- **多种比例**：支持 1:1、1:2、3:4、4:3、16:9、9:16 等多种图片比例
- **实时状态**：提供任务状态监控和剩余次数查询
- **完整信息**：返回图片和详细的生成信息

## 安装配置

### 1. 配置文件

在 `Modelscope_Node` 目录下需要 `ms_config.json` 配置文件，包含以下内容：

```json
{
  "cookies": "你的魔搭网站cookie字符串",
  "csrf_token": "你的CSRF令牌",
  "api_config": {
    "base_url": "https://www.modelscope.cn/api/v1/muse/predict",
    "timeout": 30,
    "max_wait_time": 300,
    "check_interval": 3
  },
  "models": {
    "qwen": {
      "name": "Qwen Image",
      "styleType": "QWEN_IMAGE"
    },
    "flux": {
      "name": "FLUX",
      "styleType": "FLUX"
    }
  },
  "lora_map": {
    "QWEN_麦橘美人": {
      "modelName": "merjic/majicbeauty-qwen1",
      "modelVersionId": "282253",
      "triggerWord": "",
      "weight": 1.0
    },
    "QWEN_极致写实": {
      "modelName": "Lingyuzhou/Qwen_Lenovo_UltraReal",
      "modelVersionId": "314073",
      "triggerWord": "",
      "weight": 1.0
    }
  },
  "ratios": ["1:1", "1:2", "3:4", "4:3", "16:9", "9:16"],
  "ratio_map": {
    "1:1": {"width": 1328, "height": 1328},
    "1:2": {"width": 832, "height": 1664},
    "3:4": {"width": 1140, "height": 1482},
    "4:3": {"width": 1482, "height": 1140},
    "9:16": {"width": 928, "height": 1664},
    "16:9": {"width": 1664, "height": 928}
  }
}
```

### 2. 获取配置信息

1. **登录魔搭网站**：访问 https://www.modelscope.cn 并登录
2. **获取 Cookie**：在浏览器开发者工具中复制所有 cookie
3. **获取 CSRF Token**：在开发者工具中找到 `csrf_token` 的值
```
#快捷模式
1.点进AIGC专区➡️图片生成➡️ctrl+shift+i(相当于F12)进入开发者模式➡️随便画一张图，找到右边的quicksubmit标签右键复制为cRUL(bash)
2.然后把上面的ms_config.json和curl信息打包扔给AI，让它帮你自动填好
```

## 使用方法

### 节点参数

#### 必需参数
- **prompt** (STRING): 图片描述词，支持多行文本
- **model** (SELECT): 选择使用的模型
- **ratio** (SELECT): 选择图片比例

#### 可选参数
- **lora_name_1** (SELECT): 选择第一个 Lora 模型，默认为 "none"
- **lora_weight_1** (FLOAT): 第一个 Lora 权重，范围 0.1-2.0，默认 1.0
- **lora_name_2** (SELECT): 选择第二个 Lora 模型，默认为 "none"
- **lora_weight_2** (FLOAT): 第二个 Lora 权重，范围 0.1-2.0，默认 1.0
- **lora_name_3** (SELECT): 选择第三个 Lora 模型，默认为 "none"
- **lora_weight_3** (FLOAT): 第三个 Lora 权重，范围 0.1-2.0，默认 1.0

### 输出结果

- **image** (IMAGE): 生成的图片，ComfyUI 标准格式
- **generation_info** (STRING): 生成信息，包含以下内容：
  - `image_url`: 图片下载链接
  - `remaining_count`: 剩余次数信息
  - `model`: 使用的模型
  - `ratio`: 图片比例
  - `lora_names`: 使用的 Lora 名称列表（如果有）
  - `lora_weights`: Lora 权重列表（如果有）

### 使用示例

#### 基础使用
```
prompt: "一只可爱的小猫咪"
model: "qwen"
ratio: "1:1"
```

#### 使用单个 Lora
```
prompt: "一个美丽的女孩"
model: "qwen"
ratio: "9:16"
lora_name_1: "麦橘美人"
lora_weight_1: 0.8
```

#### 使用多个 Lora 串联
```
prompt: "一个美丽的女孩，节日风格"
model: "qwen"
ratio: "9:16"
lora_name_1: "麦橘美人"
lora_weight_1: 0.8
lora_name_2: "极致写实"
lora_weight_2: 0.6
```

#### 不同风格
```
prompt: "一幅水墨山水画"
model: "ink"
ratio: "16:9"
```

## 支持的模型

| 模型名称 | 描述 | 是否支持 Lora |
|---------|------|---------------|
| qwen | Qwen Image 模型 | ✅ |
| flux | FLUX 模型 | ⚠️ 需要配置checkpointModelVersionId |
| kontext | FLUX Kontext 模型 | ⚠️ 需要配置checkpointModelVersionId |
| krea | FLUX Krea 模型 | ⚠️ 需要配置checkpointModelVersionId |
| majic | 麦橘超然模型 | ⚠️ 需要配置checkpointModelVersionId |
| realistic | 写实风模型 | ⚠️ 需要配置checkpointModelVersionId |
| anime | 动漫风模型 | ⚠️ 需要配置checkpointModelVersionId |
| ink | 水墨画模型 | ⚠️ 需要配置checkpointModelVersionId |

**注意**: 理论上所有模型都支持Lora，但需要在配置文件中为每个模型添加`checkpointModelVersionId`配置。目前只有Qwen模型已配置此参数。

## 支持的比例

| 比例 | 分辨率 | 适用场景 |
|------|--------|----------|
| 1:1 | 1328×1328 | 头像、图标 |
| 1:2 | 832×1664 | 手机壁纸 |
| 3:4 | 1140×1482 | 竖版海报 |
| 4:3 | 1482×1140 | 横版海报 |
| 9:16 | 928×1664 | 手机屏幕 |
| 16:9 | 1664×928 | 电脑屏幕 |

## 注意事项

1. **Cookie 配置**：必须正确配置魔搭网站的 cookie 才能正常使用
2. **使用限制**：魔搭有每日使用次数限制，请合理使用
3. **网络要求**：需要稳定的网络连接访问魔搭服务
4. **等待时间**：图片生成需要时间，请耐心等待
5. **Lora 支持**：理论上所有模型都支持Lora，但需要在配置文件中为每个模型添加`checkpointModelVersionId`配置。目前只有Qwen模型已配置此参数，最多支持三个 Lora 串联使用

## 错误处理

节点会处理以下常见错误：
- 配置错误：检查 cookie 和 csrf_token 是否正确
- 网络错误：检查网络连接
- 模型错误：检查模型名称是否正确
- 比例错误：自动回退到默认比例
- 超时错误：任务超时会自动终止

## 调试信息

节点会输出详细的调试信息，包括：
- 任务提交状态
- 图片生成进度
- 剩余次数信息
- 错误详情

## 更新日志

### v1.1.0
- 支持最多三个 Lora 串联使用
- 优化 Lora 参数结构，支持 lora_name_1/lora_weight_1, lora_name_2/lora_weight_2, lora_name_3/lora_weight_3
- 更新生成信息输出格式，支持多个 Lora 信息
- 修正Lora支持说明：理论上所有模型都支持Lora，需要配置checkpointModelVersionId

### v1.0.0
- 初始版本
- 支持多种模型和比例
- 支持单个 Lora 功能
- 完整的错误处理
- 详细的调试信息
