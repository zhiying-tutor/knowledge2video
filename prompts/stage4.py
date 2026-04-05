# prompts/stage4.py

def get_prompt4_layout_feedback(section, position_table):
    return f"""
1. 分析要求 (ANALYSIS REQUIREMENTS):
- 请仅从**布局(Layout)**和**空间位置(Spatial Positioning)**的角度分析这个 Manim 教育视频。
- 参考提供的网格图进行精确的空间分析。
- 核心目标：消除遮挡、重叠，并优化网格空间的利用率。

2. 内容上下文 (Content Context):
- 标题: {section.title}
- 讲解词: {'; '.join(section.lecture_lines)}
- 当前网格占用情况: {position_table}

3. 视觉锚点系统 (6*6 grid, 仅右侧区域):
lecture | A1 A2 A3 A4 A5 A6 | B1 B2 B3 B4 B5 B6 | C1 C2 C3 C4 C5 C6 | D1 D2 D3 D4 D5 D6 | E1 E2 E3 E4 E5 E6 | F1 F2 F3 F4 F5 F6

- 点定位 (point): self.place_at_grid(obj, 'B2', scale_factor=0.8)
- 区域定位 (area): self.place_in_area(obj, 'A1', 'C3', scale_factor=0.7)

4. 布局评估 (检查所有项):
- **遮挡 (Obstruction)**: 动画元素是否遮挡了左侧的讲解文字？[严重]
- **重叠 (Overlap)**: 动画元素之间（公式、标签、图形）是否发生重叠？
- **出界 (Off-screen)**: 元素是否被切掉或超出了屏幕可视范围？[特别是长文本标签]
- **网格违规**: 空间利用是否不合理（太挤或太散）？
- **未消失**: 检查是否有应该淡出但未淡出的元素。

5. 强制约束:
- 颜色: 指出颜色不清晰的地方。
- 字体/比例: 针对网格位置调整字体大小和素材缩放。
- 一致性: **不要**对左侧讲解词做任何位置或大小动画，只改变颜色。
- 邻近性: 确保标签文字与其对应的物体在 1 个网格单位以内。

6. 讲解文字分批规则核查（硬性）:
- 每行讲解文字不超过 **20个中文字符**（含标点、英文字母、数字）即可放一行；只有超过 20 字时才按语义拆分。
- 禁止把 20 字以内的完整短句强行拆成两行。
- 先判断是否有代码块：
    - 有代码块（左下有 `create_code_block`）→ 每批最多 **4行**
    - 无代码块（纯讲解 + 右侧动画）→ 每批最多 **8行**
- 分批必须优先按语义完整性：
    - 同一知识点可跨多批（建议 2-4 批，按时长自适应），但不能与下一个知识点拼到同一批
    - 不同知识点不能硬凑同一批
    - 严禁机械地每批凑满 4 行或 8 行
- 若发现违反以上规则，必须在 `improvements` 中给出可执行修复建议（包含对象与代码修改方向）。

7. 渲染失败检测（硬性，新增）:
- 必须检查是否出现“字符渲染失败”现象：画面中出现小方块/空心框/乱码占位符。
- 重点检查对象：数学公式、上下标、比较符号（如 ≤ ≥ ≠）、以及勾叉符号（✓ ✗ × √）。
- 若发现以上问题，`layout.has_issues` 必须为 true，并在 `improvements` 中明确指出：
    - 问题对象（例如某个标题、标签、讲解行、公式）
    - 触发原因（例如错误使用 `Text("✓")`、整句 `Text` 混入数学片段）
    - 修复方案（改为 `MathTex`，或 Text+MathTex 混排）
- 对勾叉符号必须给出唯一推荐修复：
    - 勾号：`MathTex(r"\\checkmark", color="#478211")`
    - 叉号：`MathTex(r"\\times", color="#C84A2B")`

8. 重要：必须严格按照以下 JSON 结构输出:
{{
    "layout": {{
        "has_issues": true,  // 如果有明显布局问题则为 true
        "improvements": [
            {{
                "problem": "具体问题描述 (中文)",
                "solution": "建议修改的代码逻辑，例如：将圆形从 C3 移到 E3",
                "line_number": X, // 估算代码行号
                "object_affected": "受影响的对象名"
            }},
            ...
        ]
    }}
}}

9. 解决方案要求:
- 在解决方案中提供具体的网格坐标建议。
- 仅列出最影响视觉体验的 3 个布局问题！
- 不要给出视频时间戳。
- 问题描述要简洁，解决方案要具体可执行。
"""


def get_feedback_list_prefix(feedback_improvements):
    """
    生成反馈列表的前缀说明
    """
    return f"""       
MLLM 视觉反馈建议：基于对生成视频的分析，请解决以下布局问题：
{chr(10).join([f"- {improvement}" for improvement in feedback_improvements])}
"""


def get_feedback_improve_code(feedback, code):
    return f"""
你是一位 Manim v0.19.0 教育动画专家。

**必须遵守 (MANDATORY)**:
- 基于以下反馈，修改当前的 Manim 代码。
- 动画和标签请使用明亮、高对比度的颜色！
- **严禁**对左侧讲解词（lecture lines）应用任何位置或大小动画，只允许改变颜色（highlight）。
- 讲解文字分批必须与上游规则一致：
    - 每行不超过 20 字（超过才按语义拆分）
    - 有代码块每批 ≤4 行；无代码块每批 ≤8 行
    - 分批优先语义完整性，严禁机械凑满行数
- 若存在字符渲染失败（小方块/乱码占位符）：
    - 数学与符号内容必须改用 `MathTex`
    - 含数学片段的整句文本改为 Text+MathTex 混排
    - 勾叉符号必须使用：
        - `MathTex(r"\\checkmark", color="#478211")`
        - `MathTex(r"\\times", color="#C84A2B")`
- 仅输出更新后的完整 Python 代码。不需要任何解释。

反馈意见 (Feedback):
{feedback}

---

当前代码 (Current Code):
```python
{code}
"""