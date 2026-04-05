# prompts/__init__.py
from .base_class import base_class
from .stage1 import get_prompt1_outline
from .stage2 import get_prompt2_storyboard, get_prompt_download_assets, get_prompt_place_assets
from .stage3 import get_prompt3_code, get_regenerate_note
from .stage4 import get_feedback_improve_code, get_feedback_list_prefix, get_prompt4_layout_feedback
from .stage5_eva import get_prompt_aes
from .stage5_unlearning import get_unlearning_prompt, get_unlearning_and_video_learning_prompt

# 用户个性化配置 - 新的 AI 智能解析方式
from .user_profile import (
    UserProfile,
    get_default_profile,
    create_profile_from_text,
    parse_profile_with_ai_sync,
    get_profile_analysis_prompt,
    get_stage1_profile_prompt,
    get_stage2_profile_prompt,
    get_stage3_profile_prompt,
)

__all__ = [
    # 基础类
    "base_class",
    
    # Stage 1: 大纲生成
    "get_prompt1_outline",
    
    # Stage 2: 分镜脚本
    "get_prompt2_storyboard",
    "get_prompt_download_assets",
    "get_prompt_place_assets",
    
    # Stage 3: 代码生成
    "get_prompt3_code",
    "get_regenerate_note",
    
    # Stage 4: 反馈优化
    "get_feedback_list_prefix",
    "get_feedback_improve_code",
    "get_prompt4_layout_feedback",
    
    # Stage 5: 评估
    "get_prompt_aes",
    "get_unlearning_prompt",
    "get_unlearning_and_video_learning_prompt",
    
    # 用户个性化配置 - AI 智能解析
    "UserProfile",
    "get_default_profile",
    "create_profile_from_text",
    "parse_profile_with_ai_sync",
    "get_profile_analysis_prompt",
    "get_stage1_profile_prompt",
    "get_stage2_profile_prompt",
    "get_stage3_profile_prompt",
]
