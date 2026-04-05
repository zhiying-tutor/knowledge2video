import os
import sys
import subprocess
from typing import List
from manim import *
import multiprocessing
import re
import psutil
from pathlib import Path
import imageio_ffmpeg


def fix_json_common_errors(json_str: str) -> str:
    """
    尝试自动修复常见的 JSON 格式错误
    """
    import json
    
    # 先尝试直接解析，如果成功则无需修复
    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass
    
    fixed = json_str
    
    # 1. 移除 JavaScript 风格的注释 (// 和 /* */)
    fixed = re.sub(r'//.*?(?=\n|$)', '', fixed)
    fixed = re.sub(r'/\*.*?\*/', '', fixed, flags=re.DOTALL)
    
    # 2. 移除数组最后一个元素后的逗号 (trailing comma in arrays)
    # 例如: ["a", "b",] -> ["a", "b"]
    fixed = re.sub(r',(\s*)\]', r'\1]', fixed)
    
    # 3. 移除对象最后一个字段后的逗号 (trailing comma in objects)
    # 例如: {"a": 1,} -> {"a": 1}
    fixed = re.sub(r',(\s*)\}', r'\1}', fixed)
    
    # 4. 将单引号替换为双引号（JSON 标准要求双引号）
    # 注意：这是一个简单的替换，可能会误伤字符串内的单引号
    # 只在解析失败后尝试
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        pass
    
    # 5. 尝试修复未转义的引号问题
    # 这是一个复杂问题，这里只做简单处理
    
    # 6. 移除控制字符
    fixed = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', fixed)
    
    return fixed


def extract_json_from_markdown(text):
    """
    从 markdown 文本中提取 JSON，并尝试自动修复常见格式错误
    """
    import json
    
    # 优先尝试匹配标准的 markdown 代码块 (```json ... ```)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        json_str = match.group(1)
        # 尝试修复并返回
        return fix_json_common_errors(json_str)
    
    # 【回退机制】如果没找到代码块，尝试寻找字符串中第一个 '{' 和最后一个 '}'
    # 这能处理 LLM 忘记写 markdown 标记的情况，或者在代码块前有废话的情况
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        json_str = text[start : end + 1]
        # 尝试修复并返回
        return fix_json_common_errors(json_str)
    
    return text


def extract_answer_from_response(response):
    try:
        content = response.candidates[0].content.parts[0].text
    except Exception:
        try:
            content = response.choices[0].message.content
        except Exception:
            content = str(response)
    content = extract_json_from_markdown(content)
    return content


# [修改后] src/utils.py 中的 fix_png_path
def fix_png_path(code_str: str, assets_dir: Path) -> str:
    assets_dir = Path(assets_dir).resolve()
    # 假设 assets_dir 结尾是 "assets/icon"，我们需要知道父级结构来做更智能的判断
    # 这里主要防止 "icon" 目录重复
    assets_dir_name = assets_dir.name # 通常是 "icon"

    def replacer(match):
        original_path_str = match.group(1)  # 如 "icon/car.png" 或 "car.png"
        path_obj = Path(original_path_str)
        
        # 1. 如果已经是绝对路径，直接尝试保留文件名或检查是否在 assets_dir 下
        if path_obj.is_absolute():
            # 简单策略：仅提取文件名，重新拼接到正确的 assets_dir
            return f'"{assets_dir / path_obj.name}"'
            
        # 2. 处理相对路径
        # 检查原路径是否已经包含了 assets_dir 的名字 (例如 "icon/car.png")
        parts = path_obj.parts
        if parts[0] == assets_dir_name:
            # 如果路径以 "icon" 开头，去掉它，避免重复拼接
            # 例如 "icon/car.png" -> "car.png"
            stripped_path = Path(*parts[1:])
            return f'"{assets_dir / stripped_path}"'
        
        # 3. 默认情况：直接拼接
        # 例如 "car.png" -> ".../assets/icon/car.png"
        return f'"{assets_dir / path_obj}"'

    pattern = r'["\']([^"\']+\.png)["\']'
    return re.sub(pattern, replacer, code_str)


def get_optimal_workers():
    """根据 CPU 核心数和负载自适应计算最佳并行进程数"""
    try:
        cpu_count = multiprocessing.cpu_count()
    except NotImplementedError:
        cpu_count = 6  # default

    # Manim 渲染是 CPU 密集型的；通常将 worker 设置为 CPU 核心数或核心数减一
    # 预留 1 个核心给系统/其他进程
    optimal = max(1, cpu_count - 1)

    # 如果是高性能多核机器 (>16 核)，
    # 适当限制 worker 数量以避免内存溢出
    if optimal > 16:
        optimal = 16

    print(f"⚙️ 检测到 {cpu_count} 个核心，将使用 {optimal} 个并行进程")
    return optimal


def monitor_system_resources():
    """监控系统资源使用情况"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        print(f"📊 资源使用情况: CPU {cpu_percent:.1f}% | 内存 {memory.percent:.1f}%")

        if cpu_percent > 95:
            print("⚠️ CPU 使用率过高")
        if memory.percent > 90:
            print("⚠️ 内存使用率过高")

        return True
    except Exception:
        return False


def replace_base_class(code: str, new_class_def: str) -> str:
    lines = code.splitlines(keepends=True)
    class_start = None
    class_end = None

    # 查找 class TeachingScene(Scene): 的起始行
    for i, line in enumerate(lines):
        # 放宽正则，只要是以 "class TeachingScene" 开头即可，忽略继承参数和冒号后的空格/注释
        if re.match(r"^\s*class\s+TeachingScene", line):
            class_start = i
            break

    if class_start is not None:
        # 查找类定义的结束行
        # 类结束于缩进相同或更少的行出现时
        base_indent = len(lines[class_start]) - len(lines[class_start].lstrip())
        class_end = class_start + 1
        while class_end < len(lines):
            line = lines[class_end]
            # 如果发现空行以外且缩进小于等于基准缩进的行，说明类定义结束
            if line.strip() != "" and (len(line) - len(line.lstrip()) <= base_indent):
                break
            class_end += 1

        # 用新的定义替换原始的 TeachingScene
        new_block = new_class_def.strip() + "\n\n"
        return "".join(lines[:class_start]) + new_block + "".join(lines[class_end:])
    else:
        # 如果 TeachingScene 不存在，插入到第一个类定义之前
        for i, line in enumerate(lines):
            if re.match(r"^\s*class\s+\w+", line):
                insert_pos = i
                break
        else:
            insert_pos = 0

        new_block = new_class_def.strip() + "\n\n"
        return "".join(lines[:insert_pos]) + new_block + "".join(lines[insert_pos:])


# 将程序保存到 .py 文件
def save_code_to_file(code: str, filename: str = "scene.py"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"代码已保存至 {filename}")


# 运行 manim 代码生成视频
def run_manim_script(filename: str, scene_name: str, output_dir: str = "videos") -> str:
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{scene_name}.mp4")

    cmd = [
        sys.executable, "-m", "manim",
        "-pqh",  # 修改为 -pqh (play + high quality 1080p)，原版为 -pql
        str(filename),  # 脚本路径
        scene_name,  # 类名
        "--output_file",
        f"{scene_name}.mp4",
        "--media_dir",
        str(output_dir),  # 媒体输出目录
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("Manim 错误:", result.stderr.decode())
        raise RuntimeError(f"渲染场景 {scene_name} 失败。")

    print(f"视频已保存至 {output_path}")
    return output_path


# 使用 ffmpeg 拼接多个 mp4 文件
def stitch_videos(video_files: List[str], output_path: str = "final_output.mp4"):
    list_file = "video_list.txt"
    with open(list_file, "w") as f:
        for vf in video_files:
            f.write(f"file '{os.path.abspath(vf)}'\n")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output_path]
    print("正在拼接视频:", cmd)
    subprocess.run(cmd, check=True)
    print(f"最终拼接视频已保存至 {output_path}")


def topic_to_safe_name(knowledge_point):
    # 允许：中文、字母、数字、空格、_ - { } [ ] . , + & ' =
    # 【修复】在正则中添加了 \. \, \' 以匹配注释描述
    SAFE_PATTERN = r"[^A-Za-z0-9\u4e00-\u9fa5 _\-\{\}\[\]\+&=\u03C0\.\,\']"
    safe_name = re.sub(SAFE_PATTERN, "", knowledge_point)
    # 将连续空格替换为单个下划线
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    return safe_name


def get_output_dir(idx, knowledge_point, base_dir, get_safe_name=False):
    safe_name = topic_to_safe_name(knowledge_point)
    # 前缀 idx-
    folder_name = f"{idx}-{safe_name}"
    if get_safe_name:
        return Path(base_dir) / folder_name, safe_name

    return Path(base_dir) / folder_name


def eva_video_list(knowledge_points, base_dir):

    video_list = []
    for idx, kp in enumerate(knowledge_points):
        folder, safe_name = get_output_dir(idx, kp, base_dir, get_safe_name=True)

        # mp4 文件名必须安全且一致
        mp4_name = f"{safe_name}.mp4"
        mp4_path = folder / mp4_name
        video_list.append({"path": str(mp4_path), "knowledge_point": kp})
    return video_list


if __name__ == "__main__":
    print(get_optimal_workers())