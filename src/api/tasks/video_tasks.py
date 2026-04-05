"""
视频生成 Celery 任务
"""

import sys
import os
import json
import traceback
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

import redis

# 添加项目根目录到 sys.path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent.parent  # code2video/src
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from .celery_app import celery_app
from ..config import settings
from ..utils.file_utils import save_video_with_hash
from ..utils.sse import SyncTaskProgressCallback


@celery_app.task(bind=True, name="src.api.tasks.video_tasks.generate_video_task")
def generate_video_task(
    self,
    request_data: Dict[str, Any],
    channel_name: str
) -> Dict[str, Any]:
    """
    视频生成 Celery 任务
    
    Args:
        request_data: 请求数据
        channel_name: Redis 发布频道名称
        
    Returns:
        任务结果
    """
    # 创建 Redis 客户端用于发布进度
    redis_client = redis.from_url(settings.redis_url)
    callback = SyncTaskProgressCallback(redis_client, channel_name)
    
    result = {
        "success": False,
        "video_file": None,
        "error": None,
        "token_usage": None,
    }
    
    try:
        # 导入必要的模块（延迟导入，避免循环依赖）
        from src.agent import TeachingVideoAgent, RunConfig
        from src.gpt_request import (
            request_claude_token,
            request_gpt4o_token,
            request_gpt5_token,
            request_gemini_token,
            request_o4mini_token,
            request_gpt41_token,
        )
        from prompts.user_profile import (
            UserProfile,
            create_profile_from_text,
            parse_profile_with_ai_sync,
        )
        from src.utils import get_optimal_workers
        
        # 解析请求参数
        knowledge_point = request_data["knowledge_point"]
        age = request_data.get("age")
        gender = request_data.get("gender")
        language = request_data.get("language", "Python")
        duration = request_data.get("duration", 5)
        difficulty = request_data.get("difficulty", "medium")
        # 规范化难度值（兼容枚举/大小写）
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).lower()
        extra_info = request_data.get("extra_info", "")
        use_feedback = request_data.get("use_feedback", True)
        use_assets = request_data.get("use_assets", True)
        api_model = request_data.get("api_model", settings.default_api)
        
        # 获取 API 函数（键名与 api_config.json 一致）
        api_mapping = {
            "claude": request_claude_token,
            "gpt4o": request_gpt4o_token,
            "gpt5": request_gpt5_token,
            "gpt-41": request_gpt41_token,
            "gpt-o4mini": request_o4mini_token,
            "gemini": request_gemini_token,
        }
        api_func = api_mapping.get(api_model, request_claude_token)
        
        # ========== 阶段 1: 解析用户画像 ==========
        task_id = callback.on_stage_start("parse_profile", "正在解析用户画像。")
        
        try:
            # 难度映射（请求值 -> 中文等级）
            difficulty_level_map = {
                "simple": "入门",
                "medium": "中等",
                "hard": "进阶",
            }
            forced_difficulty_level = difficulty_level_map.get(difficulty, "中等")

            # 难度映射为自然语言描述
            difficulty_desc_map = {
                "simple": "内容难度偏简单入门",
                "medium": "内容难度为中等",
                "hard": "内容难度偏高级进阶",
            }
            difficulty_desc = difficulty_desc_map.get(difficulty, "内容难度为中等")
            
            # 构建用户画像文本
            profile_parts = []
            if age:
                profile_parts.append(f"我是{age}岁")
            if gender:
                profile_parts.append(f"性别{gender}")
            profile_parts.append(f"选择的编程语言是{language}")
            profile_parts.append(difficulty_desc)
            if extra_info:
                profile_parts.append(extra_info)
            
            profile_text = "，".join(profile_parts)
            
            user_profile = create_profile_from_text(profile_text)
            # 使用 AI 解析用户画像
            parsed_profile = parse_profile_with_ai_sync(profile_text, api_func)
            if parsed_profile:
                # 强制覆盖难度偏好，确保严格与请求 difficulty 一致
                parsed_profile.setdefault("user_summary", {})
                parsed_profile["user_summary"]["difficulty_preference"] = forced_difficulty_level
                user_profile.update_with_parsed_profile(parsed_profile)
            
            callback.on_stage_finish(task_id, "用户画像解析成功。")
        except Exception as e:
            callback.on_stage_failed(task_id, f"用户画像解析失败: {str(e)}")
            raise
        
        # ========== 阶段 2: 创建 Agent 并生成视频 ==========
        # 配置
        cfg = RunConfig(
            api=api_func,
            use_feedback=use_feedback,
            use_assets=use_assets,
            duration=duration,
            user_profile=user_profile,
            forced_difficulty_level=forced_difficulty_level,
            max_code_token_length=50000,  # 提高 token 上限，避免分镜脚本被截断
            max_fix_bug_tries=10,
            max_regenerate_tries=10,
            max_feedback_gen_code_tries=5,
            max_mllm_fix_bugs_tries=5,
            feedback_rounds=2,
        )
        
        # 创建输出目录
        folder_path = src_dir / "CASES" / f"API_{api_model}"
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # 创建 Agent
        agent = TeachingVideoAgent(
            idx=0,
            knowledge_point=knowledge_point,
            folder=str(folder_path),
            cfg=cfg,
        )
        
        # ========== 阶段 3: 生成大纲 ==========
        task_id = callback.on_stage_start("generate_outline", "正在生成教学大纲。")
        try:
            agent.generate_outline()

            # 强制覆盖大纲中的 difficulty_level，确保与请求参数完全一致
            outline_file = Path(agent.output_dir) / "outline.json"
            if outline_file.exists():
                with open(outline_file, "r", encoding="utf-8") as f:
                    outline_data = json.load(f)
                outline_data["difficulty_level"] = forced_difficulty_level
                with open(outline_file, "w", encoding="utf-8") as f:
                    json.dump(outline_data, f, ensure_ascii=False, indent=2)

            callback.on_stage_finish(task_id, "教学大纲生成成功。")
        except Exception as e:
            callback.on_stage_failed(task_id, f"教学大纲生成失败: {str(e)}")
            raise
        
        # ========== 阶段 4: 生成分镜 ==========
        task_id = callback.on_stage_start("generate_storyboard", "正在生成分镜脚本。")
        try:
            agent.generate_storyboard()
            callback.on_stage_finish(task_id, "分镜脚本生成成功。")
        except Exception as e:
            callback.on_stage_failed(task_id, f"分镜脚本生成失败: {str(e)}")
            raise
        
        # ========== 阶段 5: 生成代码 ==========
        task_id = callback.on_stage_start("generate_codes", "正在生成 Manim 代码。")
        try:
            agent.generate_codes()
            callback.on_stage_finish(task_id, "Manim 代码生成成功。")
        except Exception as e:
            callback.on_stage_failed(task_id, f"Manim 代码生成失败: {str(e)}")
            raise
        
        # ========== 阶段 6: 渲染视频 ==========
        task_id = callback.on_stage_start("render_videos", "正在渲染视频片段。")
        try:
            agent.render_all_sections()
            callback.on_stage_finish(task_id, "视频片段渲染成功。")
        except Exception as e:
            callback.on_stage_failed(task_id, f"视频片段渲染失败: {str(e)}")
            raise
        
        # ========== 阶段 7: 合并视频 ==========
        task_id = callback.on_stage_start("merge_videos", "正在合并视频。")
        try:
            final_video_path = agent.merge_videos()
            if not final_video_path:
                raise Exception("视频合并失败，未生成最终视频")
            callback.on_stage_finish(task_id, "视频合并成功。")
        except Exception as e:
            callback.on_stage_failed(task_id, f"视频合并失败: {str(e)}")
            raise
        
        # ========== 阶段 8: 保存视频 ==========
        task_id = callback.on_stage_start("save_video", "正在保存视频文件。")
        try:
            # 准备元信息
            metadata = {
                "knowledge_point": knowledge_point,
                "language": language,
                "duration": duration,
                "difficulty": difficulty,
                "age": age,
                "gender": gender,
                "extra_info": extra_info,
                "api_model": api_model,
                "outline": agent.outline.__dict__ if agent.outline else None,
                "token_usage": agent.token_usage,
                "created_at": datetime.now().isoformat(),
            }
            
            # 保存视频并获取哈希文件名
            video_filename = save_video_with_hash(final_video_path, metadata)
            
            callback.on_stage_finish(task_id, "视频文件保存成功。")
            
            result["success"] = True
            result["video_file"] = video_filename
            result["token_usage"] = agent.token_usage
            
        except Exception as e:
            callback.on_stage_failed(task_id, f"视频文件保存失败: {str(e)}")
            raise
        
        # ========== 发送最终结果 ==========
        callback.on_result("视频生成成功。", {
            "video_file": video_filename,
            "token_usage": agent.token_usage,
        })
        
    except Exception as e:
        error_msg = f"视频生成失败: {str(e)}"
        result["error"] = error_msg
        result["traceback"] = traceback.format_exc()
        
        # 发送失败结果
        callback.on_result(error_msg, {"error": str(e)})
    
    finally:
        redis_client.close()
    
    return result
