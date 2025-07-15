# Comfyui_Free_API 插件包初始化
# 导入所有子模块的节点，确保ComfyUI能正确加载

import os
import sys

# 添加当前目录到Python路径，确保子模块能正确导入
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 导入GLM LLM API节点
try:
    from GLM_Node.glm_llm_api_node import NODE_CLASS_MAPPINGS as GLM_LLM_NODE_MAPPINGS
    from GLM_Node.glm_llm_api_node import NODE_DISPLAY_NAME_MAPPINGS as GLM_LLM_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import GLM_Node.glm_llm_api_node: {e}")
    GLM_LLM_NODE_MAPPINGS = {}
    GLM_LLM_DISPLAY_MAPPINGS = {}

# 导入GLM VLM API节点
try:
    from GLM_Node.glm_vlm_api_node import NODE_CLASS_MAPPINGS as GLM_NODE_MAPPINGS
    from GLM_Node.glm_vlm_api_node import NODE_DISPLAY_NAME_MAPPINGS as GLM_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import GLM_Node: {e}")
    GLM_NODE_MAPPINGS = {}
    GLM_DISPLAY_MAPPINGS = {}

# 导入GLM视频推理节点
try:
    from GLM_Node.glm_vlm_api_video_node import NODE_CLASS_MAPPINGS as GLM_VIDEO_NODE_MAPPINGS
    from GLM_Node.glm_vlm_api_video_node import NODE_DISPLAY_NAME_MAPPINGS as GLM_VIDEO_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import GLM_Node.glm_vlm_api_video_node: {e}")
    GLM_VIDEO_NODE_MAPPINGS = {}
    GLM_VIDEO_DISPLAY_MAPPINGS = {}

# 导入GLM Image API节点
try:
    from GLM_Node.glm_image_api_node import NODE_CLASS_MAPPINGS as GLM_IMAGE_NODE_MAPPINGS
    from GLM_Node.glm_image_api_node import NODE_DISPLAY_NAME_MAPPINGS as GLM_IMAGE_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import GLM_Node.glm_image_api_node: {e}")
    GLM_IMAGE_NODE_MAPPINGS = {}
    GLM_IMAGE_DISPLAY_MAPPINGS = {}

# 导入Qwen LLM API节点
try:
    from Qwen_Node.qwen_llm_api_node import NODE_CLASS_MAPPINGS as QWEN_LLM_NODE_MAPPINGS
    from Qwen_Node.qwen_llm_api_node import NODE_DISPLAY_NAME_MAPPINGS as QWEN_LLM_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import Qwen_Node.qwen_llm_api_node: {e}")
    QWEN_LLM_NODE_MAPPINGS = {}
    QWEN_LLM_DISPLAY_MAPPINGS = {}

# 导入Qwen VLM API节点
try:
    from Qwen_Node.qwen_vlm_api_node import NODE_CLASS_MAPPINGS as QWEN_NODE_MAPPINGS
    from Qwen_Node.qwen_vlm_api_node import NODE_DISPLAY_NAME_MAPPINGS as QWEN_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import Qwen_Node: {e}")
    QWEN_NODE_MAPPINGS = {}
    QWEN_DISPLAY_MAPPINGS = {}

# 导入Qwen图像编辑节点
try:
    from Qwen_Node.qwen_imageedit_api_node import NODE_CLASS_MAPPINGS as QWEN_IMAGEEDIT_NODE_MAPPINGS
    from Qwen_Node.qwen_imageedit_api_node import NODE_DISPLAY_NAME_MAPPINGS as QWEN_IMAGEEDIT_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import Qwen_Node.qwen_imageedit_api_node: {e}")
    QWEN_IMAGEEDIT_NODE_MAPPINGS = {}
    QWEN_IMAGEEDIT_DISPLAY_MAPPINGS = {}

# 导入Siliconflow LLM API节点
try:
    from Siliconflow_Node.siliconflow_llm_api_node import NODE_CLASS_MAPPINGS as SILICONFLOW_LLM_NODE_MAPPINGS
    from Siliconflow_Node.siliconflow_llm_api_node import NODE_DISPLAY_NAME_MAPPINGS as SILICONFLOW_LLM_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import Siliconflow_Node.siliconflow_llm_api_node: {e}")
    SILICONFLOW_LLM_NODE_MAPPINGS = {}
    SILICONFLOW_LLM_DISPLAY_MAPPINGS = {}

# 导入Siliconflow VLM API节点
try:
    from Siliconflow_Node.siliconflow_vlm_api_node import NODE_CLASS_MAPPINGS as SILICONFLOW_NODE_MAPPINGS
    from Siliconflow_Node.siliconflow_vlm_api_node import NODE_DISPLAY_NAME_MAPPINGS as SILICONFLOW_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import Siliconflow_Node: {e}")
    SILICONFLOW_NODE_MAPPINGS = {}
    SILICONFLOW_DISPLAY_MAPPINGS = {}

# 导入Gemini VLM API节点
try:
    from Gemini_Node.gemini_vlm_api_node import NODE_CLASS_MAPPINGS as GEMINI_VLM_NODE_MAPPINGS
    from Gemini_Node.gemini_vlm_api_node import NODE_DISPLAY_NAME_MAPPINGS as GEMINI_VLM_DISPLAY_MAPPINGS
except ImportError as e:
    print(f"Warning: Failed to import Gemini_Node.gemini_vlm_api_node: {e}")
    GEMINI_VLM_NODE_MAPPINGS = {}
    GEMINI_VLM_DISPLAY_MAPPINGS = {}    


# 合并所有节点的映射
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# 添加GLM节点
NODE_CLASS_MAPPINGS.update(GLM_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(GLM_DISPLAY_MAPPINGS)

# 添加GLM视频URL节点
NODE_CLASS_MAPPINGS.update(GLM_VIDEO_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(GLM_VIDEO_DISPLAY_MAPPINGS)

# 添加GLM LLM API节点
NODE_CLASS_MAPPINGS.update(GLM_LLM_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(GLM_LLM_DISPLAY_MAPPINGS)

# 添加GLM Image API节点
NODE_CLASS_MAPPINGS.update(GLM_IMAGE_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(GLM_IMAGE_DISPLAY_MAPPINGS)

# 添加Qwen节点
NODE_CLASS_MAPPINGS.update(QWEN_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(QWEN_DISPLAY_MAPPINGS)

# 添加Qwen图像编辑节点
NODE_CLASS_MAPPINGS.update(QWEN_IMAGEEDIT_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(QWEN_IMAGEEDIT_DISPLAY_MAPPINGS)

# 添加Qwen LLM API节点
NODE_CLASS_MAPPINGS.update(QWEN_LLM_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(QWEN_LLM_DISPLAY_MAPPINGS)

# 添加Siliconflow节点
NODE_CLASS_MAPPINGS.update(SILICONFLOW_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(SILICONFLOW_DISPLAY_MAPPINGS)

# 添加Siliconflow LLM API节点
NODE_CLASS_MAPPINGS.update(SILICONFLOW_LLM_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(SILICONFLOW_LLM_DISPLAY_MAPPINGS)

# 添加Gemini VLM API节点
NODE_CLASS_MAPPINGS.update(GEMINI_VLM_NODE_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(GEMINI_VLM_DISPLAY_MAPPINGS)

# 导出节点映射，供ComfyUI使用
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS'] 