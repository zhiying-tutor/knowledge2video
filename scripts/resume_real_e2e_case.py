import json
import os
import re
import sys
from pathlib import Path

from pydub import AudioSegment

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def configure_openai_env() -> None:
    config_path = ROOT_DIR / "src" / "api_config.json"
    with config_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    default_base_url = cfg.get("gpt5", {}).get("base_url") or cfg.get("gpt4o", {}).get("base_url")
    default_api_key = cfg.get("gpt5", {}).get("api_key") or cfg.get("gpt4o", {}).get("api_key")

    if default_base_url and not os.getenv("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = default_base_url
    if default_api_key and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = default_api_key


configure_openai_env()

from prompts.user_profile import create_profile_from_text
from src.agent import TeachingVideoAgent, RunConfig
from src.api.tasks.video_tasks import _post_validate_and_normalize_sections
from src.gpt_request import request_gpt5_token


PAYLOAD = {
    "knowledge_point": "二叉树的各种遍历",
    "language": "Python",
    "duration": 5,
    "difficulty": "simple",
    "extra_info": "面向初学者，尽量直观，多用图示，我的计算机能力比较薄弱，我比较擅长生物，可以用生物的例子来解释",
}


def build_agent() -> TeachingVideoAgent:
    difficulty_level_map = {
        "simple": "入门",
        "medium": "中等",
        "hard": "进阶",
    }
    difficulty_desc_map = {
        "simple": "内容难度偏简单入门",
        "medium": "内容难度为中等",
        "hard": "内容难度偏高级进阶",
    }

    profile_parts = [
        f"选择的编程语言是{PAYLOAD['language']}",
        difficulty_desc_map.get(PAYLOAD["difficulty"], "内容难度为中等"),
    ]
    if PAYLOAD.get("extra_info"):
        profile_parts.append(PAYLOAD["extra_info"])
    profile_text = "，".join(profile_parts)
    user_profile = create_profile_from_text(profile_text)

    cfg = RunConfig(
        api=request_gpt5_token,
        use_feedback=True,
        use_assets=True,
        duration=PAYLOAD["duration"],
        user_profile=user_profile,
        forced_difficulty_level=difficulty_level_map.get(PAYLOAD["difficulty"], "中等"),
        max_code_token_length=50000,
        max_fix_bug_tries=10,
        max_regenerate_tries=10,
        max_feedback_gen_code_tries=5,
        max_mllm_fix_bugs_tries=5,
        feedback_rounds=2,
    )

    cases_root = ROOT_DIR / "src" / "CASES" / "E2E_REAL"
    return TeachingVideoAgent(
        idx=0,
        knowledge_point=PAYLOAD["knowledge_point"],
        folder=str(cases_root),
        cfg=cfg,
    )


def hydrate_audio(section, output_dir: Path) -> None:
    audio_dir = output_dir / "audio"
    section.line_durations = []
    section.line_audio_files = []
    section.section_audio_file = None

    for line_idx in range(len(section.lecture_lines)):
        line_audio_path = audio_dir / f"sec_{section.id}_line_{line_idx}.wav"
        if line_audio_path.exists():
            line_audio = AudioSegment.from_file(line_audio_path)
            section.line_durations.append(len(line_audio) / 1000.0)
            section.line_audio_files.append(str(line_audio_path.relative_to(output_dir)))

    section_audio_path = audio_dir / f"sec_{section.id}_full.wav"
    if section_audio_path.exists():
        section.section_audio_file = str(section_audio_path.relative_to(output_dir))


def parse_scene_name(code: str, section_id: str) -> str:
    scene_candidates = re.findall(r"class\s+(\w+)\s*\([^)]*\):", code)
    if scene_candidates:
        for cname in scene_candidates:
            pattern = rf"class\s+{cname}\s*\([^)]*\):[\s\S]*?def\s+construct\s*\("
            if re.search(pattern, code) and cname.lower() not in ("teachingscene", "basescene"):
                return cname
        return scene_candidates[-1]
    return f"{section_id.title().replace('_', '')}Scene"


def locate_existing_video(agent: TeachingVideoAgent, section_id: str) -> str | None:
    optimized_path = agent.output_dir / "optimized_videos" / f"{section_id}_optimized.mp4"
    if optimized_path.exists():
        return str(optimized_path.resolve())

    code = agent.section_codes.get(section_id, "")
    if not code:
        code_file = agent.output_dir / f"{section_id}.py"
        if code_file.exists():
            code = code_file.read_text(encoding="utf-8")
            agent.section_codes[section_id] = code

    scene_name = parse_scene_name(code, section_id)
    code_file_name = f"{section_id}.py"
    candidates = [
        agent.output_dir / "media" / "videos" / code_file_name.replace(".py", "") / "480p15" / f"{scene_name}.mp4",
        agent.output_dir / "media" / "videos" / "480p15" / f"{scene_name}.mp4",
        agent.output_dir / "media" / "videos" / code_file_name.replace(".py", "") / "1080p60" / f"{scene_name}.mp4",
        agent.output_dir / "media" / "videos" / "1080p60" / f"{scene_name}.mp4",
    ]
    for path in candidates:
        if path.exists():
            return str(path.resolve())
    return None


def main() -> int:
    agent = build_agent()
    print(f"Output dir: {agent.output_dir}")

    agent.generate_outline()
    agent.generate_storyboard()

    for section in agent.sections:
        hydrate_audio(section, agent.output_dir)
        code_file = agent.output_dir / f"{section.id}.py"
        if code_file.exists():
            agent.section_codes[section.id] = code_file.read_text(encoding="utf-8")

    missing_optimized = []
    for section in agent.sections:
        existing = locate_existing_video(agent, section.id)
        if existing:
            agent.section_videos[section.id] = existing
        optimized_path = agent.output_dir / "optimized_videos" / f"{section.id}_optimized.mp4"
        if not optimized_path.exists():
            missing_optimized.append(section)

    print("Missing optimized sections:")
    for section in missing_optimized:
        print(f"  - {section.id}")

    failures = []
    for section in missing_optimized:
        print(f"=== RESUME SECTION: {section.id} ===")
        try:
            success = agent.render_section(section)
            latest = locate_existing_video(agent, section.id)
            if latest:
                agent.section_videos[section.id] = latest
            optimized_path = agent.output_dir / "optimized_videos" / f"{section.id}_optimized.mp4"
            if not success or not optimized_path.exists():
                failures.append(section.id)
        except Exception as exc:
            print(f"❌ Resume failed for {section.id}: {exc}")
            failures.append(section.id)

    for section in agent.sections:
        latest = locate_existing_video(agent, section.id)
        if latest:
            agent.section_videos[section.id] = latest

    optimized_status = {
        section.id: (agent.output_dir / "optimized_videos" / f"{section.id}_optimized.mp4").exists()
        for section in agent.sections
    }
    print("Optimized status:")
    for section_id, status in optimized_status.items():
        print(f"  {section_id}: {status}")

    if failures:
        print("❌ Some sections still failed to optimize:")
        for section_id in failures:
            print(f"  - {section_id}")
        return 1

    if not all(optimized_status.values()):
        print("❌ Not all sections have optimized videos, aborting merge.")
        return 1

    _post_validate_and_normalize_sections(agent)
    final_video = agent.merge_videos(output_filename="real_e2e_output.mp4")
    print(f"Final merged video: {final_video}")
    return 0 if final_video else 1


if __name__ == "__main__":
    raise SystemExit(main())
