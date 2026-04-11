import sys
import os
import imageio_ffmpeg

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 安全地设置编码（兼容 Celery Worker 环境）
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass  # 在 Celery Worker 中可能会失败，忽略即可

# Ensure ffmpeg is in PATH for Manim and other subprocesses
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
FFMPEG_DIR = os.path.dirname(FFMPEG_PATH)
if FFMPEG_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ["PATH"]

import re
import ast
import argparse
import json
import time
import random
import subprocess
import shutil
import pathlib
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor

from src.gpt_request import *
from prompts import *
from prompts.user_profile import UserProfile, get_default_profile, create_profile_from_text, parse_profile_with_ai_sync
from src.utils import *
from src.scope_refine import *
from src.external_assets import process_storyboard_with_assets
from src.audio_steps import (
    build_section_steps,
    save_section_steps,
    build_section_narration_track,
    remux_video_with_audio,
)
from src.overview_scene import (
    build_overview_lecture_lines,
    generate_overview_manim_code,
    _merge_section_titles_with_ai,
    OVERVIEW_INTRO_LINE,
    OVERVIEW_ENDING_LINE,
)
from src.cover_scene import generate_cover_manim_code


@dataclass
class Section:
    id: str
    title: str
    lecture_lines: List[str]
    animations: List[str]
    estimated_duration: Optional[int] = None  # 预计时长（秒）


@dataclass
class TeachingOutline:
    topic: str
    target_audience: str
    sections: List[Dict[str, Any]]


@dataclass
class VideoFeedback:
    section_id: str
    video_path: str
    has_issues: bool
    suggested_improvements: List[str]
    raw_response: Optional[str] = None


@dataclass
class RunConfig:
    use_feedback: bool = True
    use_assets: bool = True
    api: Callable = None
    feedback_rounds: int = 2
    iconfinder_api_key: str = ""
    max_code_token_length: int = 10000
    max_fix_bug_tries: int = 10
    max_regenerate_tries: int = 10
    max_feedback_gen_code_tries: int = 3
    max_mllm_fix_bugs_tries: int = 3
    duration: int = 5
    # 用户个性化配置
    user_profile: Optional[UserProfile] = None
    # 强制大纲难度（入门/中等/进阶），若为空则由画像推断
    forced_difficulty_level: Optional[str] = None


class TeachingVideoAgent:
    def __init__(
        self,
        idx,
        knowledge_point,
        folder="CASES",
        cfg: Optional[RunConfig] = None,
    ):
        """1. Global parameter"""
        self.learning_topic = knowledge_point
        self.idx = idx
        self.cfg = cfg or RunConfig()
        self.folder = folder  # 修复：保存 folder 路径，供 get_serializable_state 使用

        if not self.cfg.api:
            raise ValueError(f"❌ 错误: TeachingVideoAgent 初始化失败。必须在 RunConfig 中提供有效的 'api' 回调函数。")

        self.use_feedback = cfg.use_feedback
        self.use_assets = cfg.use_assets
        self.API = cfg.api
        self.feedback_rounds = cfg.feedback_rounds
        self.iconfinder_api_key = cfg.iconfinder_api_key
        self.max_code_token_length = cfg.max_code_token_length
        self.max_fix_bug_tries = cfg.max_fix_bug_tries
        self.max_regenerate_tries = cfg.max_regenerate_tries
        self.max_feedback_gen_code_tries = cfg.max_feedback_gen_code_tries
        self.max_mllm_fix_bugs_tries = cfg.max_mllm_fix_bugs_tries
        self.forced_difficulty_level = cfg.forced_difficulty_level
        self.duration = cfg.duration
        self.use_assets = cfg.use_assets
        self.API = cfg.api
        self.feedback_rounds = cfg.feedback_rounds
        self.iconfinder_api_key = cfg.iconfinder_api_key
        self.max_code_token_length = cfg.max_code_token_length
        self.max_fix_bug_tries = cfg.max_fix_bug_tries
        self.max_regenerate_tries = cfg.max_regenerate_tries
        self.max_feedback_gen_code_tries = cfg.max_feedback_gen_code_tries
        self.max_mllm_fix_bugs_tries = cfg.max_mllm_fix_bugs_tries
        
        # 用户个性化配置
        self.user_profile = cfg.user_profile or get_default_profile()

        """2. Path for output"""
        self.output_dir = get_output_dir(idx=idx, knowledge_point=self.learning_topic, base_dir=folder)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.assets_dir = Path(*self.output_dir.parts[: self.output_dir.parts.index("CASES")]) / "assets" / "icon"
        self.assets_dir.mkdir(exist_ok=True)

        """3. ScopeRefine & Anchor Visual"""
        self.scope_refine_fixer = ScopeRefineFixer(self.API, self.max_code_token_length)
        self.extractor = GridPositionExtractor()

        """4. External Database"""
        knowledge_ref_mapping_path = (
            Path(*self.output_dir.parts[: self.output_dir.parts.index("CASES")]) / "json_files" / "long_video_ref_mapping.json"
        )
        with open(knowledge_ref_mapping_path) as f:
            self.KNOWLEDGE2PATH = json.load(f)
        self.knowledge_ref_img_folder = (
            Path(*self.output_dir.parts[: self.output_dir.parts.index("CASES")]) / "assets" / "reference"
        )
        self.GRID_IMG_PATH = self.knowledge_ref_img_folder / "GRID.png"

        """5. Data structure"""
        self.outline = None
        self.enhanced_storyboard = None
        self.sections = []
        self.section_codes = {}
        self.section_steps = {}
        self.section_videos = {}
        self.video_feedbacks = {}

        """6. For Efficiency"""
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _request_api_and_track_tokens(self, prompt, max_tokens=10000):
        """packages API requests and automatically accumulates token usage"""
        response, usage = self.API(prompt, max_tokens=max_tokens)
        if usage:
            self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self.token_usage["total_tokens"] += usage.get("total_tokens", 0)
        return response

    def _request_video_api_and_track_tokens(self, prompt, video_path):
        """Wraps video API requests and accumulates token usage automatically"""
        response, usage = request_gemini_video_img_token(prompt=prompt, video_path=video_path, image_path=self.GRID_IMG_PATH)

        if usage:
            self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self.token_usage["total_tokens"] += usage.get("total_tokens", 0)
        return response

    def _video_has_audio_stream(self, video_path: Path) -> bool:
        video_path = Path(video_path)
        ffprobe_path = shutil.which("ffprobe")
        if not ffprobe_path or not video_path.exists():
            return False

        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return False

        return bool(payload.get("streams"))

    def _remux_section_audio(self, section_id: str, video_path: Path) -> Path:
        steps_file = self.output_dir / f"{section_id}_steps.json"
        code_file = self.output_dir / f"{section_id}.py"
        if not steps_file.exists() or not code_file.exists():
            raise FileNotFoundError(f"Missing steps/code file for remux: {section_id}")

        if section_id in self.section_steps:
            section_steps = self.section_steps[section_id]
        else:
            with open(steps_file, "r", encoding="utf-8") as f:
                section_steps = json.load(f)
            self.section_steps[section_id] = section_steps

        remux_dir = self.output_dir / "audio_remux"
        remux_dir.mkdir(exist_ok=True)
        narration_path = remux_dir / f"{section_id}_track.wav"
        fixed_video_path = remux_dir / f"{section_id}_with_audio.mp4"

        build_section_narration_track(section_steps, code_file, narration_path)
        remux_video_with_audio(video_path, narration_path, fixed_video_path)
        return fixed_video_path

    def get_serializable_state(self):
        """返回可以序列化保存的Agent状态"""
        return {"idx": self.idx, "knowledge_point": self.learning_topic, "folder": self.folder, "cfg": self.cfg}

    def _validate_synced_step_coverage(self, code: str, expected_steps: int) -> Tuple[bool, str]:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return False, f"SyntaxError during AST validation: {exc}"

        construct_func = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name != "TeachingScene":
                for child in node.body:
                    if isinstance(child, ast.FunctionDef) and child.name == "construct":
                        construct_func = child
                        break
            if construct_func:
                break

        if construct_func is None:
            return False, "No construct() method found in generated scene code"

        synced_calls = 0
        raw_add_sound_calls = 0
        for node in ast.walk(construct_func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "play_synced_step":
                    synced_calls += 1
                elif node.func.attr == "add_sound":
                    raw_add_sound_calls += 1

        if raw_add_sound_calls > 0:
            return False, "construct() contains raw add_sound() calls instead of play_synced_step()"
        if synced_calls < expected_steps:
            return False, f"construct() only calls play_synced_step() {synced_calls} times, expected {expected_steps}"

        return True, ""

    def generate_outline(self) -> TeachingOutline:
        outline_file = self.output_dir / "outline.json"

        if outline_file.exists():
            print("📂 正在读取大纲...")
            with open(outline_file, "r", encoding="utf-8") as f:
                outline_data = json.load(f)
        else:
            """Step 1: Generate teaching outline from topic"""
            refer_img_path = (
                self.knowledge_ref_img_folder / img_name
                if (img_name := self.KNOWLEDGE2PATH.get(self.learning_topic)) is not None
                else None
            )
            prompt1 = get_prompt1_outline(
                knowledge_point=self.learning_topic, 
                duration=self.duration, 
                reference_image_path=refer_img_path,
                user_profile=self.user_profile,
                forced_difficulty_level=self.forced_difficulty_level,
            )

            print(f"📝 正在生成大纲...")

            for attempt in range(1, self.max_regenerate_tries + 1):
                api_func = self._request_api_and_track_tokens if refer_img_path else self._request_api_and_track_tokens
                response = api_func(prompt1, max_tokens=self.max_code_token_length)
                if response is None:
                    print(f"⚠️ 第 {attempt} 次尝试失败，正在重试...")
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("API 请求多次失败")
                    continue
                try:
                    content = response.candidates[0].content.parts[0].text
                except Exception:
                    try:
                        content = response.choices[0].message.content
                    except Exception:
                        content = str(response)
                content = extract_json_from_markdown(content)
                try:
                    outline_data = json.loads(content)
                    with open(self.output_dir / "outline.json", "w", encoding="utf-8") as f:
                        json.dump(outline_data, f, ensure_ascii=False, indent=2)
                    break
                except json.JSONDecodeError:
                    print(f"⚠️ 第 {attempt} 次尝试大纲格式无效，正在重试...")
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("大纲格式多次无效，请检查提示词或 API 响应")

        self.outline = TeachingOutline(
            topic=outline_data["topic"],
            target_audience=outline_data["target_audience"],
            sections=outline_data["sections"],
        )
        print(f"== 大纲已生成: {self.outline.topic}")
        return self.outline

    def generate_storyboard(self) -> List[Section]:
        """Step 2: Generate teaching storyboard from outline (optionally with asset enhancement)"""
        if not self.outline:
            raise ValueError("大纲未生成，请先生成大纲")

        storyboard_file = self.output_dir / "storyboard.json"
        enhanced_storyboard_file = self.output_dir / "storyboard_with_assets.json"

        if enhanced_storyboard_file.exists():
            print("📂 发现已增强的分镜脚本，正在加载...")
            with open(enhanced_storyboard_file, "r", encoding="utf-8") as f:
                self.enhanced_storyboard = json.load(f)
        elif storyboard_file.exists():
            print("📂 发现分镜脚本，正在加载...")
            with open(storyboard_file, "r", encoding="utf-8") as f:
                storyboard_data = json.load(f)
            if self.use_assets:
                self.enhanced_storyboard = self._enhance_storyboard_with_assets(storyboard_data)
            else:
                self.enhanced_storyboard = storyboard_data
        else:
            print("🎬 正在生成分镜脚本...")
            refer_img_path = (
                self.knowledge_ref_img_folder / img_name
                if (img_name := self.KNOWLEDGE2PATH.get(self.learning_topic)) is not None
                else None
            )

            prompt2 = get_prompt2_storyboard(
                outline=json.dumps(self.outline.__dict__, ensure_ascii=False, indent=2),
                reference_image_path=refer_img_path,
                user_profile=self.user_profile
            )

            for attempt in range(1, self.max_regenerate_tries + 1):
                api_func = self._request_api_and_track_tokens
                response = api_func(prompt2, max_tokens=self.max_code_token_length)
                if response is None:
                    print(f"⚠️ 第 {attempt} 次尝试 API 请求失败，正在重试...")
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("API 请求多次失败")
                    continue

                try:
                    content = response.candidates[0].content.parts[0].text
                except Exception:
                    try:
                        content = response.choices[0].message.content
                    except Exception:
                        content = str(response)

                try:
                    json_str = extract_json_from_markdown(content)
                    storyboard_data = json.loads(json_str)

                    # Save original storyboard
                    with open(storyboard_file, "w", encoding="utf-8") as f:
                        json.dump(storyboard_data, f, ensure_ascii=False, indent=2)

                    # Enhance storyboard (add assets)
                    if self.use_assets:
                        self.enhanced_storyboard = self._enhance_storyboard_with_assets(storyboard_data)
                    else:
                        self.enhanced_storyboard = storyboard_data
                    break

                except json.JSONDecodeError as e:
                    print(f"⚠️ 第 {attempt} 次尝试分镜格式无效，正在重试...")
                    print(f"❌ JSON Error: {e}")
                    print(f"❌ Content snippet: {content[:1000]}...") 
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("分镜格式多次无效，请检查提示词或 API 响应")

        # Parse into Section objects (using enhanced storyboard)
        self.sections = []
        for section_data in self.enhanced_storyboard["sections"]:
            section = Section(
                id=section_data["id"],
                title=section_data["title"],
                lecture_lines=section_data.get("lecture_lines", []),
                animations=section_data["animations"],
                estimated_duration=section_data.get("estimated_duration"),  # 解析预计时长
            )
            self.sections.append(section)

        print(f"== 分镜处理完成，共生成 {len(self.sections)} 个小节")
        return self.sections

    def _enhance_storyboard_with_assets(self, storyboard_data: dict) -> dict:
        """Enhance storyboard: smart analysis and download assets"""
        print("🤖 正在增强分镜：智能分析并下载素材...")

        try:
            enhanced_storyboard = process_storyboard_with_assets(
                storyboard=storyboard_data,
                api_function=self.API,
                assets_dir=str(self.assets_dir),
                iconfinder_api_key=self.iconfinder_api_key,
            )
            enhanced_storyboard_file = self.output_dir / "storyboard_with_assets.json"
            with open(enhanced_storyboard_file, "w", encoding="utf-8") as f:
                json.dump(enhanced_storyboard, f, ensure_ascii=False, indent=2)
            print("✅ 分镜已增强素材")
            return enhanced_storyboard

        except Exception as e:
            print(f"⚠️ 素材下载失败，使用原始分镜: {e}")
            return storyboard_data

    def inject_cover_section(self) -> None:
        """
        在 sections 列表最前面注入一个「封面」section。

        封面展示大标题（短名称）+ 副标题（完整 topic），并播放介绍旁白。
        使用确定性模板生成 Manim 代码，保证 100% 成功率。
        """
        if not self.outline:
            print("⚠️ 大纲尚未生成，跳过封面注入")
            return

        # 如果已经注入过，不重复注入
        if self.sections and self.sections[0].id == "section_cover":
            print("🎬 封面 section 已存在，跳过注入")
            return

        # 封面旁白：介绍语（会走 TTS 管线）
        intro_text = f"本视频将带你学习：{self.outline.topic}"

        cover_section = Section(
            id="section_cover",
            title=self.outline.topic,
            lecture_lines=[intro_text],
            animations=["Gradient background", "Create decoration lines", "FadeIn title", "FadeIn subtitle", "Play intro audio"],
            estimated_duration=10,  # 封面约 8-12 秒（含旁白）
        )

        # 插入到 sections 最前面
        self.sections.insert(0, cover_section)
        print(f"🎬 已注入封面 section（知识点：{self.outline.topic}）")

    def _generate_cover_code(self, section: Section) -> str:
        """
        为封面 section 使用确定性模板生成 Manim 代码。

        封面现在有旁白（介绍语），需要先生成 TTS 音频，再生成代码。

        Returns:
            完整的 Manim 代码字符串
        """
        # 先生成 TTS 音频（封面有旁白了）
        section_steps = self.prepare_section_steps(section)

        code = generate_cover_manim_code(
            topic=self.outline.topic,
            short_title=self.learning_topic,
            section_steps=section_steps,
        )

        # 保存代码文件
        code_file = self.output_dir / f"{section.id}.py"
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)

        self.section_codes[section.id] = code
        print(f"🎬 封面 section 代码已生成（模板化，含 TTS 旁白）")
        return code

    def inject_overview_section(self) -> None:
        """
        在 sections 列表最前面注入一个「课程导览」概述 section。

        该方法使用 AI 合并精简 section titles，然后生成 lecture_lines。
        概述 section 后续会正常走 TTS 管线（Stage 2.5）和模板化代码生成（跳过 LLM Stage 3）。
        """
        if not self.outline or not self.sections:
            print("⚠️ 大纲或分节尚未生成，跳过概述注入")
            return

        # 如果已经注入过，不重复注入
        if self.sections and self.sections[0].id == "section_overview":
            print("📋 概述 section 已存在，跳过注入")
            return

        # 从大纲提取 section titles（排除 overview 和 cover）
        section_titles = [
            s.title for s in self.sections
            if s.id not in ("section_overview", "section_cover")
        ]

        # 使用 AI 合并精简 section titles（5-12 条）
        print("🤖 正在使用 AI 合并精简章节标题...")
        merged_titles = _merge_section_titles_with_ai(
            section_titles=section_titles,
            topic=self.outline.topic,
            api_func=self._request_api_and_track_tokens,
        )
        print(f"📋 合并后共 {len(merged_titles)} 条概要: {merged_titles}")

        # 生成概述的 lecture_lines（不含总起行，直接从 bullet 开始）
        overview_lines = build_overview_lecture_lines(
            section_titles=merged_titles,
        )

        overview_section = Section(
            id="section_overview",
            title="课程导览",
            lecture_lines=overview_lines,
            animations=["FadeIn title", "Sequential FadeIn bullet points", "FadeIn ending"],
            estimated_duration=20,  # 概述约 15-25 秒
        )

        # 插入到 sections 最前面
        self.sections.insert(0, overview_section)
        print(f"📋 已注入概述 section（{len(overview_lines)} 条讲解行）")

    def _generate_overview_code(self, section: Section) -> str:
        """
        为概述 section 使用确定性模板生成 Manim 代码（跳过 LLM）。

        Returns:
            完整的 Manim 代码字符串
        """
        import re as _re

        # 确保 section_steps 已构建
        section_steps = self.prepare_section_steps(section)

        # 从 lecture_lines 中提取合并后的 section titles
        # 新格式：起始语 + "第X部分，标题" + 结束语
        # 旧格式（兼容）：圈号格式 "① 标题" + 收尾行
        merged_titles = []
        for line in section.lecture_lines:
            # 跳过起始语
            if line == OVERVIEW_INTRO_LINE:
                continue
            # 跳过结束语（新格式）
            if line == OVERVIEW_ENDING_LINE:
                continue
            # 跳过旧格式收尾行（兼容旧数据）
            if line == "让我们开始吧！":
                continue

            # 新格式：提取 "第X部分，标题" 中的标题部分
            match = _re.match(r"^第[一二三四五六七八九十\d]+部分，(.+)$", line)
            if match:
                merged_titles.append(match.group(1).strip())
                continue

            # 旧格式兼容：去掉圈号前缀（如 "① "）
            cleaned = _re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*", "", line)
            if cleaned and cleaned != line:
                merged_titles.append(cleaned)

        code = generate_overview_manim_code(
            section_titles=merged_titles,
            section_steps=section_steps,
        )

        # 注入 base_class（与其他 section 统一处理）
        code = replace_base_class(code, base_class)

        # 保存代码文件
        code_file = self.output_dir / f"{section.id}.py"
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)

        self.section_codes[section.id] = code
        print(f"📋 概述 section 代码已生成（模板化，无需 LLM）")
        return code

    def generate_section_code(self, section: Section, attempt: int = 1, feedback_improvements=None, error_message: str = None) -> str:
        """Generate Manim code for a single section
        
        Args:
            section: 章节对象
            attempt: 当前尝试次数
            feedback_improvements: MLLM 反馈的改进建议（效果不佳时）
            error_message: 上次运行失败的错误信息（运行失败时）
        """
        # ── 封面 section 使用确定性模板，跳过 LLM ──
        if section.id == "section_cover" and not feedback_improvements:
            code_file = self.output_dir / f"{section.id}.py"
            steps_file = self.output_dir / f"{section.id}_steps.json"
            audio_dir = self.output_dir / "audio" / section.id
            audio_files_exist = audio_dir.exists() and any(
                fp.is_file() for p in ("*.wav",) for fp in audio_dir.glob(p)
            )
            if (
                attempt == 1
                and code_file.exists()
                and steps_file.exists()
                and audio_files_exist
            ):
                print(f"📂 发现 {section.id} 的现有代码，正在读取...")
                with open(steps_file, "r", encoding="utf-8") as f:
                    self.section_steps[section.id] = json.load(f)
                with open(code_file, "r", encoding="utf-8") as f:
                    code = f.read()
                    self.section_codes[section.id] = code
                    return code
            return self._generate_cover_code(section)

        # ── 概述 section 使用确定性模板，跳过 LLM ──
        if section.id == "section_overview" and not feedback_improvements:
            code_file = self.output_dir / f"{section.id}.py"
            steps_file = self.output_dir / f"{section.id}_steps.json"
            audio_dir = self.output_dir / "audio" / section.id
            audio_files_exist = audio_dir.exists() and any(
                fp.is_file() for p in ("*.wav",) for fp in audio_dir.glob(p)
            )
            if (
                attempt == 1
                and code_file.exists()
                and steps_file.exists()
                and audio_files_exist
            ):
                print(f"📂 发现 {section.id} 的现有代码，正在读取...")
                with open(steps_file, "r", encoding="utf-8") as f:
                    self.section_steps[section.id] = json.load(f)
                with open(code_file, "r", encoding="utf-8") as f:
                    code = f.read()
                    self.section_codes[section.id] = code
                    return code
            return self._generate_overview_code(section)

        code_file = self.output_dir / f"{section.id}.py"
        steps_file = self.output_dir / f"{section.id}_steps.json"
        audio_dir = self.output_dir / "audio" / section.id
        audio_files_exist = audio_dir.exists() and any(
            file_path.is_file()
            for pattern in ("*.wav", "*.mp3", "*.ogg")
            for file_path in audio_dir.glob(pattern)
        )

        if (
            attempt == 1
            and code_file.exists()
            and not feedback_improvements
            and steps_file.exists()
            and audio_files_exist
        ):
            print(f"📂 发现 {section.id} 的现有代码，正在读取...")
            with open(steps_file, "r", encoding="utf-8") as f:
                self.section_steps[section.id] = json.load(f)
            with open(code_file, "r", encoding="utf-8") as f:
                code = f.read()
                self.section_codes[section.id] = code
                return code
        # print(f"💻 正在为 {section.id} 生成 Manim 代码 (尝试 {attempt}/{self.max_regenerate_tries})...")
        regenerate_note = ""
        if attempt > 1:
            # 仅用于运行失败的情况
            regenerate_note = get_regenerate_note(
                attempt, 
                MAX_REGENERATE_TRIES=self.max_regenerate_tries,
                error_message=error_message
            )

        # Add MLLM feedback and improvement suggestions
        if feedback_improvements:
            current_code = self.section_codes.get(section.id, "")
            try:
                modifier = GridCodeModifier(current_code)
                modified_code = modifier.parse_feedback_and_modify(feedback_improvements)
                modified_code = fix_png_path(modified_code, self.assets_dir)
                with open(code_file, "w", encoding="utf-8") as f:
                    f.write(modified_code)

                self.section_codes[section.id] = modified_code
                return modified_code
            except Exception as e:
                print(f"⚠️ GridCodeModifier 失败，回退到原始代码: {e}")
                code_gen_prompt = get_feedback_improve_code(
                    feedback=get_feedback_list_prefix(feedback_improvements), code=current_code
                )

        else:
            section_steps = self.prepare_section_steps(section)
            code_gen_prompt = get_prompt3_code(
                regenerate_note=regenerate_note, 
                section=section, 
                section_steps=section_steps,
                base_class=base_class,
                user_profile=self.user_profile,
                estimated_duration=section.estimated_duration  # 传递预计时长
            )

        response = self._request_api_and_track_tokens(code_gen_prompt, max_tokens=self.max_code_token_length)
        if response is None:
            print(f"❌ 通过 API 生成 {section.id} 代码失败。")
            return ""

        try:
            code = response.candidates[0].content.parts[0].text
        except Exception:
            try:
                code = response.choices[0].message.content
            except Exception:
                code = str(response)
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].strip()

        # Replace base class
        code = replace_base_class(code, base_class)
        code = fix_png_path(code, self.assets_dir)

        if not feedback_improvements:
            is_valid, validation_error = self._validate_synced_step_coverage(code, len(section_steps))
            if not is_valid:
                if attempt < self.max_regenerate_tries:
                    print(f"⚠️ {section.id} 代码未覆盖全部音频步骤，重新生成: {validation_error}")
                    return self.generate_section_code(
                        section=section,
                        attempt=attempt + 1,
                        error_message=validation_error,
                    )
                raise ValueError(validation_error)

        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)

        self.section_codes[section.id] = code
        return code

    def prepare_section_steps(self, section: Section) -> List[dict]:
        steps_file = self.output_dir / f"{section.id}_steps.json"
        audio_dir = self.output_dir / "audio" / section.id
        if (
            steps_file.exists()
            and audio_dir.exists()
            and any(file_path.is_file() for file_path in audio_dir.glob("*.wav"))
        ):
            with open(steps_file, "r", encoding="utf-8") as f:
                section_steps = json.load(f)
            self.section_steps[section.id] = section_steps
            return section_steps

        section_steps = build_section_steps(
            section=section,
            output_root=self.output_dir,
            api_func=self._request_api_and_track_tokens,
        )
        save_section_steps(section_steps, steps_file)
        self.section_steps[section.id] = section_steps
        return section_steps

    def debug_and_fix_code(self, section_id: str, max_fix_attempts: int = 3) -> Tuple[bool, Optional[str]]:
        """Enhanced debug and fix code method
        
        Returns:
            Tuple[bool, Optional[str]]: (成功与否, 最后一次错误信息)
        """
        if section_id not in self.section_codes:
            code_file = self.output_dir / f"{section_id}.py"
            if code_file.exists():
                print(f"📂 [Worker] 从文件重新加载代码: {section_id}")
                with open(code_file, "r", encoding="utf-8") as f:
                    self.section_codes[section_id] = f.read()
            else:
                return False, "代码文件不存在"
        
        last_error = None  # 保存最后一次错误信息

        # 动态解析 Scene 名称，避免类名与默认推断不一致
        code_content_for_scene = self.section_codes.get(section_id, "")
        scene_candidates = re.findall(r"class\s+(\w+)\s*\([^)]*\):", code_content_for_scene)
        # 过滤掉没有 construct 方法的类
        preferred_scene = None
        if scene_candidates:
            for cname in scene_candidates:
                # 简单检查, 该类后出现 'def construct' 字样
                pattern = rf"class\s+{cname}\s*\([^)]*\):[\s\S]*?def\s+construct\s*\("""
                if re.search(pattern, code_content_for_scene):
                    # 排除纯基类名称，如 TeachingScene/BaseScene 等
                    if cname.lower() not in ("teachingscene", "basescene"):
                        preferred_scene = cname
                        break
            if not preferred_scene:
                preferred_scene = scene_candidates[-1]

        # 封面 section 现在有旁白（介绍语），与其他 section 走同样的音频回灌流程
        is_cover = False  # 封面不再特殊处理

        # [Optimized] Check if video already exists to skip rendering
        scene_name_check = preferred_scene if preferred_scene else f"{section_id.title().replace('_', '')}Scene"
        code_file_check = f"{section_id}.py"
        video_patterns_check = [
            self.output_dir / "media" / "videos" / f"{code_file_check.replace('.py', '')}" / "480p15" / f"{scene_name_check}.mp4",
            self.output_dir / "media" / "videos" / "480p15" / f"{scene_name_check}.mp4",
            self.output_dir / "media" / "videos" / f"{code_file_check.replace('.py', '')}" / "1080p60" / f"{scene_name_check}.mp4",
            self.output_dir / "media" / "videos" / "1080p60" / f"{scene_name_check}.mp4",
        ]
        for video_path in video_patterns_check:
            if video_path.exists():
                # 封面无旁白，直接使用已有视频，跳过回灌
                if is_cover:
                    self.section_videos[section_id] = str(video_path)
                    print(f"✅ {self.learning_topic} {section_id} 发现已有封面视频，跳过渲染: {video_path}")
                    return True, None

                if self._video_has_audio_stream(video_path):
                    try:
                        fixed_video_path = self._remux_section_audio(section_id, video_path)
                    except Exception as remux_error:
                        print(f"⚠️ {self.learning_topic} {section_id} 已有视频回灌失败，将重新渲染: {remux_error}")
                        break

                    if self._video_has_audio_stream(fixed_video_path):
                        self.section_videos[section_id] = str(fixed_video_path)
                        print(f"✅ {self.learning_topic} {section_id} 发现已有视频，回灌后跳过渲染: {fixed_video_path}")
                        return True, None  # 成功，无错误
                    print(f"⚠️ {self.learning_topic} {section_id} 已有视频回灌后仍无音轨，重新渲染: {fixed_video_path}")
                    break
                print(f"⚠️ {self.learning_topic} {section_id} 已有视频缺少音轨，重新渲染: {video_path}")

        for fix_attempt in range(max_fix_attempts):
            print(f"🔧 {self.learning_topic} 正在调试 {section_id} (尝试 {fix_attempt + 1}/{max_fix_attempts})")

            try:
                # 首先尝试使用代码中真实存在的 Scene 名称，否则退回到默认推断
                scene_name = preferred_scene if preferred_scene else f"{section_id.title().replace('_', '')}Scene"
                code_file = f"{section_id}.py"
                cmd = [sys.executable, "-m", "manim", "-ql", str(code_file), scene_name]

                result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.output_dir, timeout=2000)

                if result.returncode == 0:
                    video_patterns = [
                        self.output_dir / "media" / "videos" / f"{code_file.replace('.py', '')}" / "480p15" / f"{scene_name}.mp4",
                        self.output_dir / "media" / "videos" / "480p15" / f"{scene_name}.mp4",
                        self.output_dir / "media" / "videos" / f"{code_file.replace('.py', '')}" / "1080p60" / f"{scene_name}.mp4",
                        self.output_dir / "media" / "videos" / "1080p60" / f"{scene_name}.mp4",
                    ]

                    for video_path in video_patterns:
                        if video_path.exists():
                            # 封面无旁白，渲染成功后直接使用，跳过回灌
                            if is_cover:
                                self.section_videos[section_id] = str(video_path)
                                print(f"✅ {self.learning_topic} {section_id} 封面渲染完成")
                                return True, None

                            try:
                                fixed_video_path = self._remux_section_audio(section_id, video_path)
                            except Exception as remux_error:
                                last_error = f"Audio remux failed: {remux_error}"
                                print(f"❌ {self.learning_topic} {section_id} 音频回灌失败: {remux_error}")
                                break

                            if not self._video_has_audio_stream(fixed_video_path):
                                last_error = f"Rendered video has no audio stream after remux: {fixed_video_path}"
                                print(f"❌ {self.learning_topic} {section_id} 回灌后仍无音轨: {fixed_video_path}")
                                break

                            self.section_videos[section_id] = str(fixed_video_path)
                            print(f"✅ {self.learning_topic} {section_id} 完成")
                            return True, None  # 成功，无错误
                
                # 保存错误信息
                last_error = result.stderr

                current_code = self.section_codes[section_id]
                fixed_code = self.scope_refine_fixer.fix_code_smart(section_id, current_code, result.stderr, self.output_dir)

                if fixed_code:
                    self.section_codes[section_id] = fixed_code
                    with open(self.output_dir / code_file, "w", encoding="utf-8") as f:
                        f.write(fixed_code)
                else:
                    break

            except subprocess.TimeoutExpired:
                last_error = "Manim 渲染超时 (超过 300 秒)"
                print(f"❌ {self.learning_topic} {section_id} 超时")
                break
            except Exception as e:
                last_error = str(e)
                print(f"❌ {self.learning_topic} {section_id} 失败，异常: {e}")
                break

        return False, last_error

    def get_mllm_feedback(self, section: Section, video_path: str, round_number: int = 1) -> VideoFeedback:
        print(f"🤖 {self.learning_topic} 使用 MLLM 分析视频 ({round_number}/{self.feedback_rounds}): {section.id}")

        current_code = self.section_codes[section.id]
        positions = self.extractor.extract_grid_positions(current_code)
        position_table = self.extractor.generate_position_table(positions)
        analysis_prompt = get_prompt4_layout_feedback(section=section, position_table=position_table)

        def _parse_layout(feedback_content):
            has_layout_issues, suggested_improvements = False, []
            try:
                data = json.loads(feedback_content)
                lay = data.get("layout", {})
                has_layout_issues = bool(lay.get("has_issues", False))
                for it in lay.get("improvements", []) or []:
                    if isinstance(it, dict):
                        prob = str(it.get("problem", "")).strip()
                        sol = str(it.get("solution", "")).strip()
                        if prob or sol:
                            suggested_improvements.append(f"[LAYOUT] Problem: {prob}; Solution: {sol}")

            except json.JSONDecodeError:
                print(f"⚠️ {self.learning_topic} JSON 解析失败，回退到关键词分析")

                for m in re.finditer(
                    r"Problem:\s*(.*?);\s*Solution:\s*(.*?)(?=\n|$)", feedback_content, flags=re.IGNORECASE | re.DOTALL
                ):
                    suggested_improvements.append(f"[LAYOUT] Problem: {m.group(1).strip()}; Solution: {m.group(2).strip()}")

                if not suggested_improvements:
                    for sol in re.findall(r"Solution\s*:\s*(.+)", feedback_content, flags=re.IGNORECASE):
                        suggested_improvements.append(f"[LAYOUT] Problem: ; Solution: {sol.strip()}")

            return has_layout_issues, suggested_improvements

        try:
            response = request_gemini_video_img(prompt=analysis_prompt, video_path=video_path, image_path=self.GRID_IMG_PATH)
            feedback_content = extract_answer_from_response(response)
            has_layout_issues, suggested_improvements = _parse_layout(feedback_content)
            feedback = VideoFeedback(
                section_id=section.id,
                video_path=video_path,
                has_issues=has_layout_issues,
                suggested_improvements=suggested_improvements,
                raw_response=feedback_content,
            )
            self.video_feedbacks[f"{section.id}_round{round_number}"] = feedback
            return feedback

        except Exception as e:
            print(f"❌ {self.learning_topic} MLLM 分析失败: {str(e)}")
            return VideoFeedback(
                section_id=section.id,
                video_path=video_path,
                has_issues=False,
                suggested_improvements=[],
                raw_response=f"Error: {str(e)}",
            )

    def optimize_with_feedback(self, section: Section, feedback: VideoFeedback) -> bool:
        """Optimize the code based on feedback from the MLLM"""
        if not feedback.has_issues or not feedback.suggested_improvements:
            print(f"✅ {self.learning_topic} {section.id} 无需优化")
            return True

        # === Step 1: back up original code AND video ===
        original_code_content = self.section_codes[section.id]
        
        # [新增] 备份原始视频文件
        original_video_path = self.section_videos.get(section.id)
        video_backup_path = None
        if original_video_path and os.path.exists(original_video_path):
            try:
                video_path_obj = Path(original_video_path)
                # 创建备份文件名，例如: Section01_backup.mp4
                video_backup_path = video_path_obj.with_name(f"{video_path_obj.stem}_backup{video_path_obj.suffix}")
                shutil.copy2(original_video_path, video_backup_path)
                print(f"📦 已备份原始视频: {video_backup_path}")
            except Exception as e:
                print(f"⚠️ 视频备份失败: {e}")

        for attempt in range(self.max_feedback_gen_code_tries):
            print(
                f"🎯 {self.learning_topic} MLLM 反馈优化 {section.id} 代码，尝试 {attempt + 1}/{self.max_feedback_gen_code_tries}"
            )

            # === Step 2: back up original code and apply improvements ===
            if attempt > 0:
                self.section_codes[section.id] = original_code_content

            # === Step 3: re-generate code with feedback ===
            self.generate_section_code(
                section=section, attempt=attempt + 1, feedback_improvements=feedback.suggested_improvements
            )
            success, _ = self.debug_and_fix_code(section.id, max_fix_attempts=self.max_mllm_fix_bugs_tries)
            
            if success:
                optimized_output_dir = self.output_dir / "optimized_videos"
                optimized_output_dir.mkdir(exist_ok=True)
                optimized_video_path = optimized_output_dir / f"{section.id}_optimized.mp4"

                if section.id in self.section_videos:
                    current_video_path = Path(self.section_videos[section.id])
                    if current_video_path.exists():
                        current_video_path.replace(optimized_video_path)
                        self.section_videos[section.id] = str(optimized_video_path)
                        print(f"✨ {self.learning_topic} {section.id} 优化后的视频已保存: {optimized_video_path}")
                        
                        # [新增] 优化成功，删除不再需要的备份文件
                        if video_backup_path and video_backup_path.exists():
                            try:
                                video_backup_path.unlink()
                            except:
                                pass
                    else:
                        print(f"⚠️ {self.learning_topic} {section.id} 未找到生成的视频文件: {current_video_path}")
                else:
                    print(f"⚠️ {self.learning_topic} {section.id} 未找到优化后的视频路径")
                return True
            else:
                print(
                    f"❌ {self.learning_topic} {section.id} MLLM 优化失败，尝试 {attempt + 1}/{self.max_feedback_gen_code_tries}"
                )
        
        print(f"❌ {self.learning_topic} {section.id} 所有优化尝试均失败，回滚到原始版本")
        
        # 回滚代码
        self.section_codes[section.id] = original_code_content
        with open(self.output_dir / f"{section.id}.py", "w", encoding="utf-8") as f:
            f.write(original_code_content)

        # [新增] 回滚视频文件
        if video_backup_path and video_backup_path.exists():
            try:
                target_path = Path(original_video_path)
                # 将备份文件移动回原路径（覆盖可能存在的失败产物）
                video_backup_path.replace(target_path)
                self.section_videos[section.id] = str(target_path)
                print(f"♻️ 已从备份恢复原始视频: {target_path}")
            except Exception as e:
                print(f"⚠️ 视频恢复失败: {e}")
        else:
            print(f"⚠️ 无法恢复视频：未找到备份文件")

        return False

    def generate_codes(self) -> Dict[str, str]:
        if not self.sections:
            raise ValueError(f"{self.learning_topic} 请先生成教学小节")

        def task(section):
            try:
                self.generate_section_code(section, attempt=1)
                return section.id, None
            except Exception as e:
                return section.id, e

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(task, section): section for section in self.sections}
            for future in as_completed(futures):
                section_id, err = future.result()
                if err:
                    print(f"❌ {self.learning_topic} {section_id} 代码生成失败: {err}")

        return self.section_codes

    def render_section(self, section: Section) -> bool:
        section_id = section.id

        try:
            success = False
            last_error = None  # 保存最后一次错误信息用于重试
            for regenerate_attempt in range(self.max_regenerate_tries):
                # print(f"🎯 Processing {section_id} (regenerate attempt {regenerate_attempt + 1}/{self.max_regenerate_tries})")
                try:
                    if regenerate_attempt > 0:
                        # 将上次的错误信息传递给代码生成，帮助 LLM 修复问题
                        self.generate_section_code(section, attempt=regenerate_attempt + 1, error_message=last_error)
                    success, last_error = self.debug_and_fix_code(section_id, max_fix_attempts=self.max_fix_bug_tries)
                    if success:
                        break
                    # last_error 已经在 debug_and_fix_code 中更新
                except Exception as e:
                    last_error = str(e)
                    print(f"⚠️ {section_id} 第 {regenerate_attempt + 1} 次尝试抛出异常: {str(e)}")
                    continue
            if not success:
                print(f"❌ {self.learning_topic} {section_id} 全部失败，跳过该小节")
                return False

            # MLLM feedback
            if self.use_feedback:
                try:
                    for round in range(self.feedback_rounds):
                        current_video = self.section_videos.get(section_id)
                        if not current_video:
                            print(f"❌ {self.learning_topic} {section_id} 没有可用视频进行 MLLM 反馈")
                            return success
                        try:
                            feedback = self.get_mllm_feedback(section, current_video, round_number=round + 1)

                            optimization_success = self.optimize_with_feedback(section, feedback)
                            if optimization_success:
                                pass
                            else:
                                print(
                                    f"⚠️ {self.learning_topic} {section_id} 第 {round+1} 轮 MLLM 反馈优化失败，使用当前版本"
                                )
                        except Exception as e:
                            print(
                                f"⚠️ {self.learning_topic} {section_id} 第 {round+1} 轮 MLLM 反馈处理异常: {str(e)}"
                            )
                            continue

                except Exception as e:
                    print(f"⚠️ {self.learning_topic} {section_id} MLLM 反馈处理异常: {str(e)}")

            return success

        except Exception as e:
            print(f"❌ {self.learning_topic} {section_id} 渲染过程异常: {str(e)}")
            return False

    def render_section_worker(self, section_data) -> Tuple[str, bool, Optional[str]]:
        section_id = "unknown"
        try:
            section, agent_class, kwargs = section_data
            section_id = section.id
            agent = agent_class(**kwargs)
            success = agent.render_section(section)
            video_path = agent.section_videos.get(section.id) if success else None
            return section_id, success, video_path

        except Exception as e:
            print(f"❌ {self.learning_topic} {section_id} 渲染过程异常: {str(e)}")
            return section_id, False, None

    def render_all_sections(self, max_workers: int = 6) -> Dict[str, str]:
        print(f"🎥 开始并行渲染所有分节视频 (最多 {max_workers} 个进程)...")

        tasks = []
        for section in self.sections:
            try:
                task_data = (section, self.__class__, self.get_serializable_state())
                tasks.append(task_data)
            except Exception as e:
                print(f"⚠️ 为 {section.id} 准备任务数据时出错: {str(e)}")
                continue

        if not tasks:
            print("❌ 没有有效任务可执行")
            return {}

        results = {}
        successful_count = 0
        failed_count = 0

        try:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_section = {}
                for task in tasks:
                    try:
                        future = executor.submit(self.render_section_worker, task)
                        future_to_section[future] = task[0].id
                    except Exception as e:
                        section_id = task[0].id if task and len(task) > 0 else "unknown"
                        print(f"⚠️ 提交 {section_id} 任务时出错: {str(e)}")
                        failed_count += 1

                for future in as_completed(future_to_section):
                    section_id = future_to_section[future]
                    try:
                        sid, success, video_path = future.result(timeout=1200)

                        if success and video_path:
                            results[sid] = video_path
                            successful_count += 1
                            print(f"✅ {sid} 视频渲染成功: {video_path}")
                        else:
                            failed_count += 1
                            print(f"⚠️ {sid} 视频渲染失败")

                    except Exception as e:
                        failed_count += 1
                        print(f"❌ {section_id} 视频渲染过程错误: {str(e)}")

        except Exception as e:
            print(f"❌ 并行渲染过程中出现严重错误: {str(e)}")

        # 更新结果并输出统计信息
        self.section_videos.update(results)

        total_sections = len(self.sections)
        print(f"\n📊 渲染统计:")
        print(f"   总小节数: {total_sections}")
        print(f"   成功率: {successful_count/total_sections*100:.1f}%" if total_sections > 0 else "   成功率: 0%")

        if successful_count == 0:
            print("❌ 所有分节视频渲染失败")
        elif failed_count > 0:
            print(
                f"⚠️ {failed_count} 个分节视频渲染失败，但 {successful_count} 个分节视频渲染成功"
            )
        else:
            print("🎉 所有分节视频渲染成功！")

        return results

    def merge_videos(self, output_filename: str = None) -> str:
        """Step 5: Merge all section videos"""
        if not self.section_videos:
            raise ValueError("没有可用视频进行合并")

        if output_filename is None:
            safe_name = topic_to_safe_name(self.learning_topic)
            output_filename = f"{safe_name}.mp4"

        output_path = self.output_dir / output_filename

        print(f"🔗 开始合并分节视频...")

        video_list_file = self.output_dir / "video_list.txt"
        ordered_ids = []
        if self.sections:
            ordered_ids = [s.id for s in self.sections]
        else:
            # 备选方案：如果缺失 sections 对象，使用自然排序 (Natural Sort)
            # 这里简单实现一个 key function 处理 trailing numbers
            def natural_keys(text):
                return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
            ordered_ids = sorted(self.section_videos.keys(), key=natural_keys)
        
        with open(video_list_file, "w", encoding="utf-8") as f:
            # 优先使用 ordered_ids (来自大纲 self.sections)
            target_ids = ordered_ids if ordered_ids else sorted(self.section_videos.keys())
    
            for section_id in target_ids:
            # 确保只处理不仅在大纲中、且实际生成了视频的 ID
                if section_id in self.section_videos:
                    video_path = self.section_videos[section_id].replace(f"{self.output_dir}/", "")
                    f.write(f"file '{video_path}'\n")

        # ffmpeg
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            result = subprocess.run(
                [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(video_list_file), "-c", "copy", str(output_path)],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                if self._video_has_audio_stream(output_path):
                    return str(output_path)
                print(f"❌ 合并结果缺少音轨: {output_path}")
                return None
            else:
                print(f"❌ 合并分节视频失败: {result.stderr}")
                return None
        except Exception as e:
            print(f"❌ 合并分节视频失败: {e}")
            return None

    def GENERATE_VIDEO(self) -> str:
        """Generate complete video with MLLM feedback optimization"""
        try:
            self.generate_outline()
            self.generate_storyboard()
            self.inject_overview_section()
            self.inject_cover_section()
            self.generate_codes()
            self.render_all_sections()
            final_video = self.merge_videos()
            if final_video:
                print(f"🎉 视频生成成功: {final_video}")
                return final_video
            else:
                print(f"❌ {self.learning_topic} 失败")
                return None
        except Exception as e:
            print(f"❌ 视频生成失败: {e}")
            return None


def process_knowledge_point(idx, kp, folder_path: Path, cfg: RunConfig):
    print(f"\n🚀 正在处理知识点: {kp}")
    start_time = time.time()

    agent = TeachingVideoAgent(
        idx=idx,
        knowledge_point=kp,
        folder=folder_path,
        cfg=cfg,
    )
    video_path = agent.GENERATE_VIDEO()

    duration_minutes = (time.time() - start_time) / 60
    total_tokens = agent.token_usage["total_tokens"]

    print(f"✅ 知识点 '{kp}' 处理完成。耗时: {duration_minutes:.2f} 分钟, Token 使用: {total_tokens}")
    return kp, video_path, duration_minutes, total_tokens


def process_batch(batch_data, cfg: RunConfig):
    """Process a batch of knowledge points (serial within a batch)"""
    batch_idx, kp_batch, folder_path = batch_data
    results = []
    print(f"第 {batch_idx + 1} 批次开始处理 {len(kp_batch)} 个知识点")

    for local_idx, (idx, kp) in enumerate(kp_batch):
        try:
            if local_idx > 0:
                delay = random.uniform(3, 6)
                print(f"⏳ 第 {batch_idx + 1} 批次在处理 {kp} 前等待 {delay:.1f} 秒...")
                time.sleep(delay)
            results.append(process_knowledge_point(idx, kp, folder_path, cfg))
        except Exception as e:
            print(f"❌ 第 {batch_idx + 1} 批次处理 {kp} 失败: {e}")
            results.append((kp, None, 0, 0))
    return batch_idx, results


def run_Code2Video(
    knowledge_points: List[str], folder_path: Path, parallel=True, batch_size=3, max_workers=8, cfg: RunConfig = RunConfig()
):
    all_results = []

    if parallel:
        batches = []
        for i in range(0, len(knowledge_points), batch_size):
            batch = [(i + j, kp) for j, kp in enumerate(knowledge_points[i : i + batch_size])]
            batches.append((i // batch_size, batch, folder_path))

        print(
            f"🔄 并行批处理模式: {len(batches)} 个批次，每批 {batch_size} 个知识点，{max_workers} 个并发批次"
        )
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_batch, batch, cfg): batch for batch in batches}
            for future in as_completed(futures):
                try:
                    batch_idx, batch_results = future.result()
                    all_results.extend(batch_results)
                    print(f"✅ 第 {batch_idx + 1} 批次完成")
                except Exception as e:
                    print(f"❌ 第 {batch_idx + 1} 批次处理失败: {e}")
    else:
        print("🔄 串行处理模式")
        for idx, kp in enumerate(knowledge_points):
            try:
                all_results.append(process_knowledge_point(idx, kp, folder_path, cfg))
            except Exception as e:
                print(f"❌ 串行处理 {kp} 失败: {e}")
                all_results.append((kp, None, 0, 0))

    successful_runs = [r for r in all_results if r[1] is not None]
    total_runs = len(all_results)
    if not successful_runs:
        print("\n所有知识点处理失败，无法计算平均值。")
        return

    total_duration = sum(r[2] for r in successful_runs)
    total_tokens_consumed = sum(r[3] for r in successful_runs)
    num_successful = len(successful_runs)

    print("\n" + "=" * 50)
    print(f"   总知识点数: {total_runs}")
    print(f"   成功处理: {num_successful} ({num_successful/total_runs*100:.1f}%)")
    print(f"   平均耗时 [分]: {total_duration/num_successful:.2f} 分钟/知识点")
    print(f"   平均 Token 消耗: {total_tokens_consumed/num_successful:,.0f} tokens/知识点")
    print("=" * 50)


def get_api_and_output(API_name):
    mapping = {
        "gpt-41": (request_gpt41_token, "Chatgpt41"),
        "claude": (request_claude_token, "CLAUDE"),
        "gpt-5": (request_gpt5_token, "Chatgpt5"),
        "gpt-4o": (request_gpt4o_token, "Chatgpt4o"),
        "gpt-o4mini": (request_o4mini_token, "Chatgpto4mini"),
        "Gemini": (request_gemini_token, "Gemini"),
    }
    try:
        return mapping[API_name]
    except KeyError:
        raise ValueError("无效的 API 模型名称")


def build_and_parse_args():
    parser = argparse.ArgumentParser()
    # TODO: Core hyperparameters
    parser.add_argument(
        "--API",
        type=str,
        choices=["gpt-41", "claude", "gpt-5", "gpt-4o", "gpt-o4mini", "Gemini"],
        default="gpt-4o",
    )
    parser.add_argument(
        "--folder_prefix",
        type=str,
        default="TEST",
    )
    parser.add_argument("--knowledge_file", type=str, default="long_video_topics_list.json")
    parser.add_argument("--iconfinder_api_key", type=str, default="")

    # Basically invariant parameters
    parser.add_argument("--use_feedback", action="store_true", default=False)
    parser.add_argument("--no_feedback", action="store_false", dest="use_feedback")
    parser.add_argument("--use_assets", action="store_true", default=False)
    parser.add_argument("--no_assets", action="store_false", dest="use_assets")

    parser.add_argument("--max_code_token_length", type=int, help="max # token for generating code", default=10000)
    parser.add_argument("--max_fix_bug_tries", type=int, help="max # tries for SR to fix bug", default=10)
    parser.add_argument("--max_regenerate_tries", type=int, help="max # tries to regenerate", default=10)
    parser.add_argument("--max_feedback_gen_code_tries", type=int, help="max # tries for Critic", default=3)
    parser.add_argument("--max_mllm_fix_bugs_tries", type=int, help="max # tries for Critic to fix bug", default=3)
    parser.add_argument("--feedback_rounds", type=int, default=2)
    parser.add_argument("--duration", type=int, default=5, help="Estimated video duration in minutes")

    parser.add_argument("--parallel", action="store_true", default=False)
    parser.add_argument("--no_parallel", action="store_false", dest="parallel")
    parser.add_argument("--parallel_group_num", type=int, default=3)
    parser.add_argument("--max_concepts", type=int, help="Limit # concepts for a quick run, -1 for all", default=-1)
    parser.add_argument("--knowledge_point", type=str, help="if knowledge_file not given, can ignore", default=None)
    
    # 新增参数：最大并行工作进程数
    parser.add_argument("--max_workers", type=int, default=None, help="Force specific number of workers, overriding auto-detection")

    # 用户个性化配置参数 - 新的自然语言描述方式
    parser.add_argument(
        "--user_profile",
        type=str,
        default="",
        help="用户画像的自然语言描述，例如：'我是17岁的高中生，想要的学习难度是入门级，选择的编程语言是Python，目标是利用暑假成功入门Python'"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = build_and_parse_args()

    api, folder_name = get_api_and_output(args.API)
    folder = Path(__file__).resolve().parent / "CASES" / f"{args.folder_prefix}_{folder_name}"

    _CFG_PATH = pathlib.Path(__file__).with_name("api_config.json")
    with _CFG_PATH.open("r", encoding="utf-8") as _f:
        _CFG = json.load(_f)
    iconfinder_cfg = _CFG.get("iconfinder", {})
    args.iconfinder_api_key = iconfinder_cfg.get("api_key")
    if args.iconfinder_api_key:
        print(f"Iconfinder API 密钥: {args.iconfinder_api_key}")
    else:
        print("警告: 配置文件中未找到 Iconfinder API 密钥。使用默认值 (None)。")

    if args.knowledge_point:
        print(f"🔄 单知识点模式: {args.knowledge_point}")
        knowledge_points = [args.knowledge_point]
        args.parallel_group_num = 1
    elif args.knowledge_file:
        with open(Path(__file__).resolve().parent / "json_files" / args.knowledge_file, "r", encoding="utf-8") as f:
            knowledge_points = json.load(f)
            if args.max_concepts is not None:
                knowledge_points = knowledge_points[: args.max_concepts]
    else:
        raise ValueError("必须提供 --knowledge_point 或 --knowledge_file")

    # 创建用户个性化配置
    if args.user_profile:
        print(f"🧠 正在使用 AI 解析用户画像...")
        print(f"📝 用户输入: {args.user_profile}")
        
        # 先创建基础的用户配置
        user_profile = create_profile_from_text(args.user_profile)
        
        # 使用 AI 解析用户画像
        parsed_profile = parse_profile_with_ai_sync(args.user_profile, api)
        
        if parsed_profile:
            user_profile.update_with_parsed_profile(parsed_profile)
            print(f"✅ AI 解析成功！")
            
            # 打印解析结果摘要
            summary = parsed_profile.get("user_summary", {})
            print(f"📋 解析结果:")
            print(f"   - 年龄段: {summary.get('age_group', '未知')}")
            print(f"   - 知识背景: {summary.get('background', '未知')}")
            print(f"   - 学习目标: {summary.get('learning_goal', '未知')}")
            print(f"   - 编程语言: {summary.get('target_language', 'Python')}")
            print(f"   - 难度偏好: {summary.get('difficulty_preference', '中等')}")
        else:
            print(f"⚠️ AI 解析失败，使用默认解析结果")
    else:
        print(f"📋 未提供用户画像，使用默认配置")
        user_profile = get_default_profile()

    cfg = RunConfig(
        api=api,
        iconfinder_api_key=args.iconfinder_api_key,
        use_feedback=args.use_feedback,
        use_assets=args.use_assets,
        max_code_token_length=args.max_code_token_length,
        max_fix_bug_tries=args.max_fix_bug_tries,
        max_regenerate_tries=args.max_regenerate_tries,
        max_feedback_gen_code_tries=args.max_feedback_gen_code_tries,
        max_mllm_fix_bugs_tries=args.max_mllm_fix_bugs_tries,
        feedback_rounds=args.feedback_rounds,
        duration=args.duration,
        user_profile=user_profile,
    )
    
    # 优先使用命令行参数指定的 workers，否则自动计算
    real_workers = args.max_workers if args.max_workers is not None else get_optimal_workers()

    run_Code2Video(
        knowledge_points,
        folder,
        parallel=args.parallel,
        batch_size=max(1, int(len(knowledge_points) / args.parallel_group_num)),
        max_workers=real_workers,
        cfg=cfg,
    )
