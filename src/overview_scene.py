"""
Overview Scene Generator — 视频概述/课程导览模板

在视频最开始生成一个确定性的概述 Section，快速预览本节课将讲些什么。

设计理念参考：
- MIT OCW / 大学课堂：开头展示 Agenda
- 3Blue1Brown：简要预览旅程
- 教育心理学「先行组织者 (Advance Organizer)」理论

本模块不依赖 LLM 生成 Manim 代码，而是用确定性模板保证 100% 成功率。
旁白文本仍走正常 TTS 管线（expand → TTS → 物理测时）。

Section titles 合并精简由 AI 完成（_merge_section_titles_with_ai），
保证 overview 简洁有效，每页最多 6 条。
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Callable, List, Optional


# ── 常量 ─────────────────────────────────────────────────────
BULLETS_PER_PAGE = 6  # 每页最多显示的章节数

# ── 圈号字符映射 ────────────────────────────────────────────
_CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# ── 中文序数词映射 ──────────────────────────────────────────
_ORDINAL_WORDS = [
    "第一", "第二", "第三", "第四", "第五",
    "第六", "第七", "第八", "第九", "第十",
    "第十一", "第十二", "第十三", "第十四", "第十五",
    "第十六", "第十七", "第十八", "第十九", "第二十",
]

# ── 概述起始语 / 结束语常量 ─────────────────────────────────
OVERVIEW_INTRO_LINE = "本视频将分为以下几个部分进行讲解"
OVERVIEW_ENDING_LINE = "好的，接下来让我们正式开始具体内容的学习吧"


def _circled(n: int) -> str:
    """返回 ①②③… 格式的编号，超出范围用 (n) 兜底。"""
    if 1 <= n <= len(_CIRCLED_NUMBERS):
        return _CIRCLED_NUMBERS[n - 1]
    return f"({n})"


def _ordinal(n: int) -> str:
    """返回 '第一'、'第二'… 格式的序数词，超出范围用 '第N' 兜底。"""
    if 1 <= n <= len(_ORDINAL_WORDS):
        return _ORDINAL_WORDS[n - 1]
    return f"第{n}"


# ── AI 合并 section titles ──────────────────────────────────


def _merge_section_titles_with_ai(
    section_titles: List[str],
    topic: str,
    api_func: Callable,
    max_retries: int = 3,
) -> List[str]:
    """
    用 AI 将详细的 section titles 合并精简为适合 overview 展示的概要列表。

    Args:
        section_titles: 原始的全部 section 标题列表
        topic: 视频主题（用于过滤与 topic 重复的条目）
        api_func: API 调用函数
        max_retries: 最大重试次数

    Returns:
        合并后的标题列表（5-12 条）
    """
    titles_json = json.dumps(section_titles, ensure_ascii=False)

    prompt = f"""你是教学视频大纲精简器。

任务：将以下章节标题列表合并精简为适合"课程导览"页面的概要列表。

规则：
1. 将内容相似或连续的章节合并为一条高层概要
   例如："执行追踪（一）：xxx"和"执行追踪（二）：yyy"合并为"执行追踪"
   例如："完整源代码（第1部分）"、"完整源代码（第2部分）"、"完整源代码（第3部分）"合并为"完整源代码"
2. 如果原标题是“前缀 - 后缀”或“前缀：后缀”结构，优先保留“前缀 ： 关键限定后缀”
   例如："场景引入：从游戏排行榜说起，为什么线性查找让人崩溃？" 应保留为 "场景引入：线性查找的困境"
   例如："算法核心思想 - 搜索空间收缩" 应保留为 "算法核心思想：搜索空间收缩"
   例如："复杂度分析：为什么是 O(log n)？" 应保留为 "复杂度分析： O(log n)"
3. 但如果后缀只是收尾性质或泛化概括，不要强行保留后缀
   例如："完整源代码"、"完整代码回顾"、"进阶思考与总结回顾" 这类标题应简化为更自然的高层标题
4. 最终条目数控制在 5-12 条
5. 每条尽量控制在 15 个中文字符以内
6. 不引入新内容，只能合并/简化原标题
7. 如果某条标题与视频主题"{topic}"完全相同或高度重复，则删除该条
8. 去掉原始编号，直接输出标题文本
9. 输出格式：JSON 字符串数组，例如 ["标题1", "标题2", ...]

章节标题列表：
{titles_json}

请直接输出 JSON 数组，不要添加任何其他文字："""

    for attempt in range(1, max_retries + 1):
        try:
            response = api_func(prompt, max_tokens=500)
            # 提取文本
            try:
                content = response.candidates[0].content.parts[0].text
            except Exception:
                try:
                    content = response.choices[0].message.content
                except Exception:
                    content = str(response)

            content = content.strip()
            # 移除可能的 markdown 代码块包装
            if content.startswith("```"):
                content = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            content = content.strip()

            merged = json.loads(content)
            if isinstance(merged, list) and len(merged) >= 3:
                return [str(t) for t in merged]
        except Exception as e:
            print(f"⚠️ AI 合并 section titles 第 {attempt} 次失败: {e}")
            if attempt >= max_retries:
                break

    # 兜底：简单规则合并
    return _merge_section_titles_fallback(section_titles, topic)


def _merge_section_titles_fallback(
    section_titles: List[str],
    topic: str,
) -> List[str]:
    """
    规则兜底：将连续相同前缀的标题合并。

    合并逻辑：
    - 取冒号/括号前的前缀，连续相同前缀的条目合并为一条
    - 跳过与 topic 重复的条目
    """
    import re as _re

    def _get_prefix(title: str) -> str:
        # 取冒号前的部分作为前缀
        for sep in ["：", ":"]:
            if sep in title:
                prefix = title.split(sep)[0]
                # 去掉括号内容
                prefix = _re.sub(r"[（(][^）)]*[）)]", "", prefix).strip()
                return prefix
        return title.strip()

    merged = []
    prev_prefix = None

    for title in section_titles:
        # 跳过与 topic 重复的
        if title.strip() == topic.strip():
            continue

        prefix = _get_prefix(title)
        if prefix == prev_prefix and merged:
            # 相同前缀，跳过（已经有了）
            continue
        else:
            # 使用精简的前缀作为标题
            if prefix != title:
                merged.append(prefix)
            else:
                merged.append(title)
            prev_prefix = prefix

    return merged if merged else section_titles


# ── 从大纲提取概述数据 ──────────────────────────────────────


def build_overview_lecture_lines(
    section_titles: List[str],
) -> List[str]:
    """
    从合并后的 section titles 生成概述 lecture_lines（旁白文本短句）。

    策略：
    - 第一行：起始语（如"本视频将分为以下几个部分进行讲解"）
    - 中间行：每个 section title 一行，使用"第X部分，标题"格式
      （给 TTS 用，让 AI 扩写出自然的"第一部分..."、"第二部分..."表述）
    - 最后一行：结束语（如"好的，接下来让我们正式开始具体内容的学习吧"）

    注意：画面上仍然使用 ① ② ③ 圈号格式显示，这里的格式仅影响旁白。

    Args:
        section_titles: 合并精简后的标题列表

    Returns:
        List[str] — 适合传入 Section.lecture_lines 的短句列表
    """
    lines: List[str] = []

    # 起始语
    lines.append(OVERVIEW_INTRO_LINE)

    # Section 列表 — 使用"第X部分，标题"格式（给 TTS 扩写用）
    for idx, title in enumerate(section_titles, start=1):
        lines.append(f"{_ordinal(idx)}部分，{title}")

    # 结束语
    lines.append(OVERVIEW_ENDING_LINE)

    return lines


# ── 生成确定性 Manim 代码 ───────────────────────────────────


def generate_overview_manim_code(
    section_titles: List[str],
    section_steps: List[dict],
) -> str:
    """
    生成概述 section 的完整 Manim 代码（确定性模板，不依赖 LLM）。

    视觉设计：
    1. 显示"课程导览"标题 + "本节内容"副标题，同时播放起始语旁白（step_0）
    2. 逐条 FadeIn 各章节标题（配合 play_synced_step 旁白）
       - 画面上使用 ① ② ③ 圈号格式
       - step_1 ~ step_N 对应各 bullet
       - 如果章节超过 BULLETS_PER_PAGE 个，自动分页
    3. 播放结束语旁白（最后一个 step），不显示文字

    Args:
        section_titles: 合并后的章节标题列表
        section_steps: 已构建的 section_steps（含 audio_path, audio_duration 等）
                       step_0 = 起始语, step_1~N = bullets, step_N+1 = 结束语

    Returns:
        完整的 Python/Manim 代码字符串
    """
    # 构建全部 bullet 文本列表（画面上用圈号格式）
    all_bullet_texts = []
    for idx, title in enumerate(section_titles, start=1):
        all_bullet_texts.append(f"{_circled(idx)} {title}")

    num_steps = len(section_steps)
    num_bullets = len(all_bullet_texts)

    # 分页：每页 BULLETS_PER_PAGE 个
    pages: List[List[int]] = []
    for start in range(0, num_bullets, BULLETS_PER_PAGE):
        end = min(start + BULLETS_PER_PAGE, num_bullets)
        pages.append(list(range(start, end)))

    num_pages = len(pages)

    # 生成全部 bullet 的 Text 创建代码
    bullet_creation_lines = []
    for i, bt in enumerate(all_bullet_texts):
        safe_bt = bt.replace('"', '\\"').replace("'", "\\'")
        bullet_creation_lines.append(
            f'        bullet_{i} = Text("{safe_bt}", font="Noto Sans CJK SC", font_size=22, color="#2C1608")'
        )
    bullet_creation_code = "\n".join(bullet_creation_lines)

    # 生成分页动画代码
    # step 索引：step_0 = 起始语, step_1 ~ step_N = bullets, step_N+1 = 结束语
    page_animation_blocks = []
    for page_idx, page_bullet_indices in enumerate(pages):
        block_lines = []

        if page_idx == 0:
            page_bullet_names = [f"bullet_{i}" for i in page_bullet_indices]
            block_lines.append(
                f"        # ── 第 {page_idx + 1} 页（共 {num_pages} 页）──"
            )
            block_lines.append(
                f"        bullets = VGroup({', '.join(page_bullet_names)}).arrange(DOWN, center=True, buff=0.35)"
            )
            block_lines.append(
                f"        bullets.next_to(underline, DOWN, buff=0.5)"
            )
            block_lines.append(
                f"        if bullets.get_bottom()[1] < -3.5:"
            )
            block_lines.append(
                f"            bullets.scale_to_fit_height(5.0)"
            )
            block_lines.append(
                f"            bullets.next_to(underline, DOWN, buff=0.5)"
            )
            block_lines.append(
                f"        self.lecture = bullets"
            )
        else:
            page_bullet_names = [f"bullet_{i}" for i in page_bullet_indices]
            block_lines.append(
                f"\n        # ── 第 {page_idx + 1} 页（共 {num_pages} 页）──"
            )
            block_lines.append(
                f"        self.play(FadeOut(bullets))"
            )
            block_lines.append(
                f"        self.remove(bullets)"
            )
            block_lines.append(
                f"        bullets = VGroup({', '.join(page_bullet_names)}).arrange(DOWN, center=True, buff=0.35)"
            )
            block_lines.append(
                f"        bullets.next_to(underline, DOWN, buff=0.5)"
            )
            block_lines.append(
                f"        if bullets.get_bottom()[1] < -3.5:"
            )
            block_lines.append(
                f"            bullets.scale_to_fit_height(5.0)"
            )
            block_lines.append(
                f"            bullets.next_to(underline, DOWN, buff=0.5)"
            )
            block_lines.append(
                f"        self.lecture = bullets"
            )

        # 逐条 FadeIn + play_synced_step
        # step 索引 = bullet 全局索引 + 1（因为 step_0 是起始语）
        for local_idx, bullet_global_idx in enumerate(page_bullet_indices):
            step_idx = bullet_global_idx + 1  # +1 因为 step_0 是起始语
            block_lines.append(
                f"\n        # 第 {bullet_global_idx + 1} 个要点"
            )
            block_lines.append(
                f"        self.play_synced_step("
            )
            block_lines.append(
                f"            {local_idx},"
            )
            block_lines.append(
                f"            steps[{step_idx}][\"audio_path\"],"
            )
            block_lines.append(
                f"            steps[{step_idx}][\"audio_duration\"],"
            )
            block_lines.append(
                f"            FadeIn(bullet_{bullet_global_idx}, shift=RIGHT * 0.3),"
            )
            block_lines.append(
                f"        )"
            )

        page_animation_blocks.append("\n".join(block_lines))

    page_animation_code = "\n".join(page_animation_blocks)

    # 最后一步的 step index（结束语）
    last_step_idx = num_steps - 1

    code = f'''from manim import *
import numpy as np

{_get_base_class_import()}

class SectionOverviewScene(TeachingScene):
    def construct(self):
        steps = {json.dumps(section_steps, ensure_ascii=False)}

        # ── 背景色 ──
        self.camera.background_color = "#FFFDF4"

        # ── 标题 ──
        page_title = Text("课程导览", font="Noto Sans CJK SC", font_size=28, color="#BE8944", weight="BOLD")
        page_title.to_edge(UP, buff=0.5)

        # ── 副标题 "本节内容" ──
        subtitle = Text("本节内容", font="Noto Sans CJK SC", font_size=24, color="#7B4B2A", weight="BOLD")
        subtitle.move_to([0, 2.0, 0])

        # 下划线装饰
        underline = Line(
            start=subtitle.get_left() + DOWN * 0.2,
            end=subtitle.get_right() + DOWN * 0.2,
            color="#e4c8a6",
            stroke_width=2,
        )

        # 创建全部 bullet Text 对象
{bullet_creation_code}

        # 显示标题 + 副标题，同时播放起始语旁白（step_0）
        self.add_sound(steps[0]["audio_path"])
        self.play(FadeIn(page_title), FadeIn(subtitle), FadeIn(underline), run_time=min(steps[0]["audio_duration"], 2.0))
        remaining_intro = steps[0]["audio_duration"] - min(steps[0]["audio_duration"], 2.0)
        if remaining_intro > 0:
            self.wait(remaining_intro)

        # ── 分页展示全部章节 ──
{page_animation_code}

        # ── 结束语旁白（不显示文字，只播放声音）──
        self.add_sound(steps[{last_step_idx}]["audio_path"])
        self.wait(steps[{last_step_idx}]["audio_duration"])

        self.play(FadeOut(bullets))
        self.wait(0.5)
'''

    return code


def _get_base_class_import() -> str:
    """返回 base_class 的内联定义（与 prompts/base_class.py 保持一致）。"""
    return ""
