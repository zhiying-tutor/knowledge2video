import os
from typing import Optional
from .user_profile import UserProfile, get_default_profile


def get_prompt3_code(
    regenerate_note: str,
    section,
    section_steps,
    base_class: str,
    user_profile: Optional[UserProfile] = None,
    estimated_duration: Optional[int] = None
):
    """
    生成Manim代码的提示词
    
    Args:
        regenerate_note: 重新生成的注意事项
        section: 章节信息对象
        section_steps: 音频步骤侧车数据
        base_class: 基类代码
        user_profile: 用户配置，可选
        estimated_duration: 该章节的预计时长（秒），可选
    
    Returns:
        完整的提示词字符串
    """
    # 如果没有提供用户配置，使用默认配置
    if user_profile is None:
        user_profile = get_default_profile()
    
    # 获取 AI 智能生成的用户画像提示词
    profile_prompt = user_profile.get_stage3_prompt()
    target_language = user_profile.get_language()
    total_audio_duration = sum(step.get("audio_duration", 0) for step in section_steps)
    
    # 生成时长指导说明
    duration_guidance = ""
    if estimated_duration:
        duration_guidance = f"""
    ### 时长控制要求
    - **目标时长**: 本章节预计时长为 **{estimated_duration} 秒**
    - **节奏分配建议**:
        - 已给定音频真值总时长约 **{total_audio_duration:.2f} 秒**
        - 每条 narration 的持续时间必须严格等于对应 step 的 `audio_duration`
        - 剩余 {max(0, estimated_duration - total_audio_duration):.2f} 秒才允许用于 narration 之间的额外停顿或章节收尾
    - **wait() 使用指南**:
        - narration 段内部严禁用 `self.wait()` 代替 `audio_duration`
        - narration 之间允许极短停顿：`self.wait(0.2)` 到 `self.wait(0.8)`
        - 章节结束前允许 `self.wait(1)` 到 `self.wait(2)`
    - **⚠️ 必须严格遵守**: narration 时间轴以 `audio_duration` 为唯一真理，严禁自行压缩！
"""
    
    return f"""
    你是一位精通 Manim 的 Python 专家。请编写代码生成一个**解释复杂算法执行逻辑**的视频片段。

    {regenerate_note}
    {duration_guidance}

    {profile_prompt}

    ## 🔴🔴🔴 关键规则摘要（必须首先阅读！）🔴🔴🔴
    
    **在生成任何代码之前，请确保理解并遵守以下最重要的规则：**
    
    ### 规则 1：数学公式和特殊符号必须用 MathTex
    
    **🔴 以下内容必须使用 MathTex，严禁使用 Text()：**
    - 所有数学公式（如 `O(log n)`, `n²`, `2^7`等）
    - 比较表达式（如 `5 > 3`, `mid = 5`等）
    - **勾号 ✓ 和叉号 ✗ / ×**（Text 无法显示！）
    
    ```python
    # ✅ 正确：数学表达式用 MathTex
    MathTex(r"O(\log_2 n)", color="#9B6D0B").scale(0.8)
    MathTex(r"2^7 = 128", color="#9B6D0B").scale(0.8)
    
    # ✅ 正确：勾和叉必须用 MathTex
    correct_mark = MathTex(r"\checkmark", color="#478211").scale(1.2)  # 绿色勾 ✓
    wrong_mark = MathTex(r"\times", color="#C84A2B").scale(1.2)        # 红色叉 ✗
    
    # ❌ 错误：用 Text 显示会变成方框！
    Text("O(log₂n)")  # ❌ 会显示方框
    Text("✓")         # ❌ 会显示方框
    Text("✗")         # ❌ 会显示方框
    Text("×")         # ❌ 会显示方框
    ```
    
    ### 🔴🔴🔴 规则 1.1：勾号和叉号的唯一正确写法（违反此规则 = 代码无法渲染 = 生成失败）🔴🔴🔴
    
    **这是最容易犯错的地方！AI 经常错误地使用 Text("✓") 或 Text("✗")！**
    
    **✅ 唯一正确的写法（必须完全按照这个格式）：**
    ```python
    # 绿色勾号 ✓ - 表示正确
    correct_mark = MathTex(r"\\checkmark", color="#478211").scale(1.2)
    
    # 红色叉号 ✗ - 表示错误 
    wrong_mark = MathTex(r"\\times", color="#C84A2B").scale(1.2)
    ```
    
    **❌ 以下写法全部是错误的（会显示方框或乱码）：**
    ```python
    # ❌ 错误写法 1：直接在 Text 中使用 Unicode 符号
    Text("✗")           # ❌ 显示方框
    Text("×")           # ❌ 显示方框
    
    # ❌ 错误写法 2：在注释中写"勾"或"叉"然后用 Text
    # 红叉表示不需要交换
    wrong_mark = Text("✗", font="Noto Sans SC", font_size=28, color="#C84A2B")  # ❌ 错误！
    ```
    
    **🔍 自检：如果你的代码中出现以下任何内容，必须改为 MathTex：**
    - `Text("✓"` → 改为 `MathTex(r"\\checkmark"`
    - `Text("✗"` → 改为 `MathTex(r"\\times"`
    - `Text("×"` → 改为 `MathTex(r"\\times"`
    - `Text("√"` → 改为 `MathTex(r"\\checkmark"`

    ### 🔴🔴🔴 规则 1.2：严禁以任何理由将 MathTex 替换为 Text！🔴🔴🔴

    **运行环境已完整配置 LaTeX（texlive-full），MathTex 绝对不会出问题！**

    **以下借口全部无效，严禁使用：**
    - ❌ "使用 Text 代替 MathTex 来避免 LaTeX 文件锁定问题" — **环境没有锁定问题！**
    - ❌ "为了兼容性改用 Text" — **MathTex 完全兼容！**
    - ❌ "简化代码，用 Text 替代 MathTex" — **这会导致方框！**

    **无论是首次生成代码还是修复错误时，都必须使用 MathTex 渲染数学符号和特殊符号。**
    **如果修复代码时遇到 LaTeX 相关错误，应该修复 LaTeX 语法本身，而不是把 MathTex 改成 Text！**

    ### 🔴🔴🔴 规则 1.3：讲解文字中出现数学片段时，禁止整句 Text(line) 直出！🔴🔴🔴

    **这是 `log₂n` 最常见渲染失败来源。**
    左侧讲解行如果包含数学/符号片段（如 `O(`、`log`、`²`、`ₙ`、`₂`、`^`、`=`、`≤`、`≥`、`✓`、`✗`），
    **必须拆成 Text + MathTex 混排**，不能直接 `Text(line, ...)`。

    ```python
    # ❌ 错误：整句 Text 会导致 log₂n / O(log n) 等符号渲染异常
    Text("递归版本是O(log n)，递归深度最大为log₂n", font="Noto Sans SC", font_size=20, color="#2C1608")

    # ✅ 正确：中文用 Text，数学片段用 MathTex，再组合
    lecture_line = VGroup(
        Text("递归版本是", font="Noto Sans SC", font_size=20, color="#2C1608"),
        MathTex(r"O(\\log n)", color="#2C1608").scale(0.65),
        Text("，递归深度最大为", font="Noto Sans SC", font_size=20, color="#2C1608"),
        MathTex(r"\\log_2 n", color="#2C1608").scale(0.65)
    ).arrange(RIGHT, buff=0.06, aligned_edge=DOWN)
    ```

    ### 🔴🔴🔴 规则 1.4：`setup_layout()` 首批讲解行严禁包含数学符号！🔴🔴🔴

    `setup_layout(title_text, lecture_lines)` 内部会把 `lecture_lines` 逐行直接做成 `Text(...)`。
    因此首批讲解行如果写 `log₂n` / `O(log n)` / `n/2^k` 会出现渲染异常（如方框、缺字）。

    **硬性要求：传入 `setup_layout()` 的首批 `lecture_lines` 必须是纯中文自然语言，不得包含数学记号。**

    ```python
    # ❌ 错误：首批讲解行直接放数学符号（会被 Text 渲染）
    self.setup_layout("复杂度分析", [
        "当剩余1个元素时停止，解得 k=log₂n"
    ])

    # ✅ 正确：首批改写为纯中文描述
    self.setup_layout("复杂度分析", [
        "当剩余一个元素时停止，k=logn（以2为底）"  # 这里虽然有 logn，但没有数学符号
    ])
    ```

    **若必须展示公式，请放到右侧动画区用 `MathTex`，不要写进 `setup_layout()` 的 lecture_lines。**
    
    ### 规则 2：代码块必须使用 self.create_code_block()
    
    **🔴 严禁手动创建 Code 对象！必须使用基类提供的 `self.create_code_block()` 方法！**
    
    ```python
    # ✅ 正确：使用 self.create_code_block() 创建代码块
    code_obj = self.create_code_block(code_text, language="{target_language.lower()}")
    code_obj.to_edge(DOWN, buff=0.3).to_edge(LEFT, buff=0.3)
    
    # ❌ 错误：手动创建 Code 对象（容易遗漏参数导致深色背景）
    Code(code_string=code_text, language="python")  # ❌ 会是深色背景
    ```
    
    **`create_code_block()` 已经内置了正确的配置：**
    - `formatter_style="tango"` - tango 语法高亮主题
    - `background="rectangle"` - 矩形背景
    - `background_config` - 浅金色背景 + 金色边框
    
    ### 规则 3：元素位置边界限制（严禁出框！）

    **屏幕安全区域（Manim 坐标系）：**
    - **X 轴范围**: [-7.0, 7.0]（左右边界）
    - **Y 轴范围**: [-4.0, 4.0]（上下边界）

    **左侧区域（代码+讲解）：**
    - X ∈ [-7.0, 0]
    - 代码块：`to_edge(DOWN, buff=0.3).to_edge(LEFT, buff=0.3)`
    - 讲解文字：`to_edge(LEFT, buff=0.3)`，高度限制 2.5

    **右侧区域（动画演示）：**
    - X ∈ [0.3, 6.5]，Y ∈ [-3.5, 3.0]
    - 中心点：`RIGHT_CENTER = [3.5, -0.5, 0]`
    - 最大尺寸：宽 6.0，高 5.5

    ```python
    # ✅ 正确：创建元素后检查边界
    obj.move_to(RIGHT_CENTER)
    if obj.width > 6.0: obj.scale_to_fit_width(6.0)
    if obj.height > 5.5: obj.scale_to_fit_height(5.5)

    # 检查是否超出边界
    if obj.get_right()[0] > 6.5:
        obj.shift(LEFT * (obj.get_right()[0] - 6.5 + 0.2))
    if obj.get_bottom()[1] < -3.5:
        obj.shift(UP * (-3.5 - obj.get_bottom()[1] + 0.2))
    if obj.get_top()[1] > 3.0:
        obj.shift(DOWN * (obj.get_top()[1] - 3.0 + 0.2))
    ```

    **❌ 常见错误：**
    - 数组/表格太长超出右边界
    - 文字/代码块太多超出下边界
    - 动画元素与标题重叠（超出上边界 Y=3.0）

    **📐 右侧元素尺寸速查表（设计时直接参照，避免出框！）：**
    | 元素类型 | 最大数量/尺寸 | 推荐参数 | 占用宽度估算 |
    |---------|-------------|---------|------------|
    | 横排 Square 数组 | ≤8 个 | side_length=0.6, buff=0.1 | 8×0.7≈5.6 ✅ |
    | 横排 Square 数组 | ≤10 个 | side_length=0.5, buff=0.08 | 10×0.58≈5.8 ✅ |
    | 横排 Square 数组 | >10 个 | ❌ 必须分两行或缩小 | 超出6.0 ❌ |
    | 纵排文字标签 | ≤6 行 | font_size=18 | 高度≈4.2 ✅ |
    | 二维表格/矩阵 | ≤6×6 | cell_size=0.6 | 3.6×3.6 ✅ |
    | 二叉树 | ≤4 层 | 节点 radius=0.25 | 高度≈4.0 ✅ |
    | 右侧文字标注 | - | font_size=16~18 | 单行≤5.0 宽 |

    **🔴 右侧大图专用硬性规则（必须遵守）：**
    - 当右侧正在展示**大型图案**（如：横排数组、二维矩阵、二叉树、调用栈、大表格）时，
        **该大图案的右侧****禁止出现**额外文字标注/解释文本/标题动画、（如 `Text(...)`、`MathTex(...)` 标签、对比说明）。

    **⚠️ 超出上表限制时的处理方式：**
    - 数组超过 10 个元素 → 分两行显示，或用 `side_length=0.4`
    - 表格超过 6 列 → 缩小 cell_size 或只展示关键部分
    - 文字标注太长 → 换行或缩小 font_size
    
    ### 规则 4：讲解文字必须使用 font_size=20
    
    **🔴 左侧讲解文字的字体大小必须固定为 20！**
    
    ```python
    # ✅ 正确：讲解文字必须使用 font_size=20
    new_lecture_texts = [
        Text(line, font="Noto Sans SC", font_size=20, color="#2C1608") 
        for line in new_lecture_lines
    ]
    new_lecture = VGroup(*new_lecture_texts).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
    new_lecture.align_to(lecture_pos, UL)          
    ```

    **字体大小规范：**
    | 元素类型 | font_size | 说明 |
    |---------|-----------|------|
    | 大标题 | 28 | 顶部标题，加粗 |
    | **讲解文字** | **20** | **左侧讲解区域，必须固定** |
    
    ### 规则 5：construct() 开头必须调用 setup_layout()
    
    **🔴🔴🔴 严禁跳过 setup_layout()！这是设置背景色的关键！🔴🔴🔴**
    
    `setup_layout()` 方法会设置奶油白背景色 `#FFFDF4`，如果不调用，背景会是黑色！
    
    ```python
    # ✅ 正确：construct() 第一行必须调用 setup_layout()
    class MyScene(TeachingScene):
        def construct(self):
            # 🔴 第一行必须调用 setup_layout()！
            self.setup_layout("标题文字", ["讲解文字1", "讲解文字2"])
            
            # 然后再创建其他元素...
    
    # ❌ 错误：不调用 setup_layout() 会导致黑色背景！
    class MyScene(TeachingScene):
        def construct(self):
            # ❌ 直接创建元素，没有调用 setup_layout()
            title = Text("标题", ...)  # 背景是黑色！
    ```

    ### 规则 6：旁白步骤必须使用 play_synced_step()

    **每一条 narration 都必须调用 `self.play_synced_step(...)`。**
    它内部会播放音频、保持对应短句高亮，并让右侧动画与音频并行运行。

    ```python
    # ✅ 正确：使用音频真实时长作为 narration 唯一时间真值
    self.play_synced_step(
        0,
        steps[0]["audio_path"],
        steps[0]["audio_duration"],
        Create(array_group)
    )

    # ❌ 错误：手动 add_sound + wait，或自行编写 narration 时长
    self.add_sound(steps[0]["audio_path"])
    self.wait(3)  # ❌ 严禁手写 narration 时长
    ```

    **注意：**
    - `steps[i]["spoken_script"]` 只用于离线 TTS，不允许显示在画面上
    - 画面上只能显示 `steps[i]["screen_text"]`
    - narration 段内部如需右侧动画，必须作为 `play_synced_step(..., *animations)` 的并行动画传入
    - narration 段内部严禁为了对齐语音而额外写 `self.wait(x)`
    - 如果当前 batch 的 `screen_texts` 不够覆盖后续 narration，必须先调用 `self.replace_lecture_lines(next_batch_lines)` 再继续

    ---

    ### 核心任务：通用算法可视化
    不要硬编码特定的形状，而是根据算法逻辑选择最合适的 Manim 对象。

    ### 1. 动态布局系统
    **【重要】左侧三层垂直布局，严禁重叠：**
    ```python
    # 左侧垂直布局 (从上到下):
    # Layer 1: 标题 title -> to_edge(UP, buff=0.2)
    # Layer 2: 讲解文字 lecture -> 标题下方, 高度限制 2.5 单位
    # Layer 3: 代码 code_obj -> to_edge(DOWN, buff=0.2), 高度限制 3.5 单位
    # 左侧区域: X ∈ [-7.0, 0], 右侧区域: X ∈ [0.3, 6.5]

    # === 布局模板 ===
    LEFT_MAX_WIDTH = 6.5  # 左侧元素最大宽度，防止与右侧重叠
    
    title.to_edge(UP, buff=0.2)
    # ⚠️ 讲解文字从左上角开始，严禁Y轴居中
    self.lecture.next_to(title, DOWN, buff=1.0).to_edge(LEFT, buff=0.3)
    
    if self.lecture.height > 2.5:
        self.lecture.scale_to_fit_height(2.5)
    if self.lecture.width > LEFT_MAX_WIDTH:
        self.lecture.scale_to_fit_width(LEFT_MAX_WIDTH)
    
    code_obj.to_edge(DOWN, buff=0.2).to_edge(LEFT, buff=0.3)
    if code_obj.height > 3.5:
        code_obj.scale_to_fit_height(3.5)
    if code_obj.width > LEFT_MAX_WIDTH:
        code_obj.scale_to_fit_width(LEFT_MAX_WIDTH)
    
    # 确保讲解与代码不重叠
    if self.lecture.get_bottom()[1] < code_obj.get_top()[1] + 0.3:
        code_obj.scale(0.85)
        code_obj.to_edge(DOWN, buff=0.3)
    ```

     **【⚠️ 讲解文字分批显示 - 硬性规则】**
     - **🔴 每行字数限制**：每行讲解文字不超过 **20个中文字符**（含标点、英文字母、数字）即可放一行，无需刻意拆短。只有超过20字时才按语义拆成多行。**不要把一句完整的短句强行拆成两行！一句话能在20字以内说完就放一行。** 超过20字的文字会侵入右侧动画区域导致重叠！

     ### 🔴🔴🔴 分批核心规则（最容易犯错！必须严格遵守！）🔴🔴🔴

     **AI 最常犯的错误：不管有没有代码块，都机械地每批4行。这是错误的！**

     **执行顺序（必须按顺序执行，不能跳步）：**
     1. **先判断当前章节有没有代码块**
         - **有代码块**（左下有 `create_code_block`）→ 每批最多 **4行**
         - **无代码块**（纯讲解+右侧动画，如思路分析、题目解读、总结等）→ 每批最多 **8行**
         - **🔴 大部分思路分析章节都没有代码块，应该用8行上限，不是4行！**
     2. **再按语义完整性分批（比行数限制更重要！）**
         - **同一知识点可跨多批**（建议 2-4 批，按时长自适应），但不能与下一个知识点拼到同一批
         - **不同知识点不能硬凑到同一批**
         - 如果一个知识点只有2行，就只显示2行；如果有6行，就显示6行
         - **严禁机械地每批都凑满4行！**
         - **特别强调：必须按语义完整性分批，不能按固定行数模板化切分。**
     3. **最后检查是否超过该场景上限（4行或8行）**
         - 若未超过：保持该知识点完整，不做额外拆分
         - 若超过：只在该知识点内部按自然语义断点拆分，**禁止跨知识点拼接凑行数**

    - **左上对齐**：讲解文字必须 `.next_to(title, DOWN, buff=0.5).to_edge(LEFT, buff=0.3)`，从**左上角**开始，**严禁Y轴居中**
    - **位置固定**：首批出现时记录 `lecture_pos = self.lecture.get_corner(UL)`，后续批次用 `.align_to(lecture_pos, UL)` 保持左上对齐
    - **切换方式**：当前批次讲完 → `FadeOut` + `self.remove()` → 新批次在**原位置左上对齐**显示

    **【关键】右侧动画区域（严禁出框，必须在标题下方）：**
    ```python
    # 右侧区域: 中心(3.5, -0.5), 最大宽6.0/高5.5
    # ⚠️ Y范围: [-3.5, 3.0]，上边界必须在标题下方（标题在 Y≈3.5）
    RIGHT_CENTER = np.array([3.5, -0.5, 0])  # 中心点下移，避免与标题重叠
    RIGHT_TOP_Y = 3.0    # 右侧区域上边界（在标题下方）
    RIGHT_BOTTOM_Y = -3.5  # 右侧区域下边界

    # 所有右侧元素：先 move_to(RIGHT_CENTER)，再检查尺寸和边界
    if obj.width > 6.0: obj.scale_to_fit_width(6.0)
    if obj.height > 5.5: obj.scale_to_fit_height(5.5)

    # ⚠️ 检查上下边界
    if obj.get_top()[1] > RIGHT_TOP_Y:
        obj.shift(DOWN * (obj.get_top()[1] - RIGHT_TOP_Y + 0.2))
    if obj.get_bottom()[1] < RIGHT_BOTTOM_Y:
        obj.shift(UP * (RIGHT_BOTTOM_Y - obj.get_bottom()[1] + 0.2))
    ```

    **【🚨🚨🚨 代码展示 - 必须使用 self.create_code_block() 🚨🚨🚨】**
    
    ⚠️ **严禁用 Text() 显示代码！必须使用基类的 `self.create_code_block()` 方法！**
    
    ```python
    # ✅✅✅ 唯一正确的写法 ✅✅✅
    code_text = \"\"\"# {target_language} 示例
def algo(data):
    # 核心逻辑
    pass\"\"\"
    code_obj = self.create_code_block(code_text, language="{target_language.lower()}")
    code_obj.to_edge(DOWN, buff=0.3).to_edge(LEFT, buff=0.3)
    self.play(Create(code_obj))
    
    # ❌ 错误：手动创建 Code 对象
    Code(code_string=code_text, language="python")  # ❌ 容易遗漏参数
    ```
    
    **`create_code_block()` 已内置正确配置：**
    - `formatter_style="tango"` - tango 语法高亮
    - `background="rectangle"` - 矩形背景
    - `background_config` - 浅金色背景 #fff7e8 + 金色边框 #e4c8a6
    
    **【代码注释规则 - 必须使用中文】**
    - **代码注释必须全部使用中文**，方便观众理解

    **【代码高亮框精确定位】使用 code_obj[2] 访问代码行 VGroup：**
    ```python
    code_lines = code_obj[2]
    highlight = SurroundingRectangle(code_lines[0], color=YELLOW, buff=0.05)
    self.play(Create(highlight))
    
    # ✅ 移动高亮框 (使用 Transform)
    new_highlight = SurroundingRectangle(code_lines[2], color=YELLOW, buff=0.05)
    self.play(Transform(highlight, new_highlight))
    ```

    ### 2. 交互与逻辑表现
    - **代码高亮**: 使用 `SurroundingRectangle` 精确框选，禁止用 `Indicate` 高亮代码块
    - **呼吸感时序**: 文字高亮结束后必须 `self.wait(0.5)`，先左上文字→停顿→再右侧动画
    - **逻辑外显化**: 条件判断显示 `MathTex("5 > 3")`，成立变绿/不成立变红
    - **递归**: 在屏幕一角维护 Stack VGroup，每层递归 add 矩形，返回时 remove

    ### 🔴 规则 6.1：讲解文字必须通过音频步骤自动高亮 🔴
    
    **每一句讲解文字都必须通过 `play_synced_step()` 完成：**
    - 音频开始播放时，对应短句开始高亮
    - 高亮持续整个 `audio_duration`
    - narration 结束后恢复原色 `#2C1608`
    - 严禁跳过任何一句

    ```python
    self.play_synced_step(
        0,
        steps[0]["audio_path"],
        steps[0]["audio_duration"],
        FadeIn(some_right_side_obj)
    )
    ```

    ### 🔴 规则 7：方块+文字标签的正确组合方式（严禁 arrange 分离！）🔴

    **创建带文字标签的方块数组时，必须先把每个方块和文字组合成一个单元，再整体排列。**
    **严禁先 move_to 叠放文字，再对包含方块和文字的 VGroup 调用 arrange()，这会把文字挤到方块右边！**

    ```python
    # ✅ 正确：每个方块和文字组成一个单元，再排列
    chars = ["a", "b", "c", "d"]
    cells = VGroup()
    for c in chars:
        sq = Square(side_length=0.5, color="#e4c8a6", fill_color="#fff7e8", fill_opacity=0.8)
        txt = Text(c, font="Noto Sans SC", font_size=18, color="#2C1608")
        txt.move_to(sq)  # 文字叠在方块中心
        cells.add(VGroup(sq, txt))  # 组合成一个单元
    cells.arrange(RIGHT, buff=0.05)  # 整体排列

    label = Text("s = ", font="Noto Sans SC", font_size=20, color="#2C1608")
    row = VGroup(label, cells).arrange(RIGHT, buff=0.2)

    # ❌ 错误：方块和文字分开放入 VGroup 再 arrange（文字会被挤到右边！）
    squares = VGroup(*[Square(side_length=0.5) for _ in range(4)]).arrange(RIGHT, buff=0.05)
    texts = VGroup(*[Text(c, ...) for c in chars])
    for i, t in enumerate(texts):
        t.move_to(squares[i])  # 先叠放
    row = VGroup(label, squares, texts).arrange(RIGHT, buff=0.2)  # ❌ arrange 会把 texts 整体挤到 squares 右边！
    ```

    ### 3. 数据结构映射
    - **Array/DP Table**: `VGroup` of `Square`，必须标 Index
    - **Tree/Graph**: `Graph` 类或 `Circle` + `Line`
    - **Pointer**: `Arrow` 指向当前操作对象
    - 禁止 3D 场景，保持 2D 清晰图解

    ### 任务输入
    - 标题: {section.title}
    - 屏幕短句: {[step["screen_text"] for step in section_steps]}
    - 音频步骤数据: {section_steps}
    - 动画指令: {section.animations}

    ### 代码规范
    - 继承 `TeachingScene`，变量先定义后使用
    - 节奏：`self.wait(1)` 给观众思考时间
    - 代码语言: **{target_language}**

    ### 参考代码结构
    ```python
    from manim import *
    {base_class}

    class {section.id.title().replace('_', '')}Scene(TeachingScene):
        def construct(self):
            steps = {section_steps}
            current_batch = steps[:4]
            screen_texts = [step["screen_text"] for step in current_batch]

            # 🔴🔴🔴 第一行必须调用 setup_layout()！设置背景色和基础布局 🔴🔴🔴
            self.setup_layout("{section.title}", screen_texts)

            # 1. 创建代码块 - 🔴 必须使用 self.create_code_block()！
            code_raw = \"\"\"# {target_language} 示例
def algo(data):
    # 核心逻辑
    pass\"\"\"
            code = self.create_code_block(code_raw, language="{target_language.lower()}")
            code.to_edge(DOWN, buff=0.3).to_edge(LEFT, buff=0.3)

            # 2. Data Structures
            array_group = VGroup(*[Square() for _ in range(5)]).arrange(RIGHT)
            
            # 3. 勾叉标记 - 🔴 必须用 MathTex，严禁用 Text！
            correct_mark = MathTex(r"\\checkmark", color="#478211").scale(1.2)  # 绿色勾 ✓
            wrong_mark = MathTex(r"\\times", color="#C84A2B").scale(1.2)        # 红色叉 ✗

            # 🔴 narration 必须使用 play_synced_step，以音频真实时长为准
            self.play_synced_step(
                0,
                steps[0]["audio_path"],
                steps[0]["audio_duration"],
                Create(code)
            )

            self.play_synced_step(
                1,
                steps[1]["audio_path"],
                steps[1]["audio_duration"],
                Create(array_group)
            )
            
            # 4. Execution Trace
            code_lines = code[2]
            highlight = SurroundingRectangle(code_lines[0], color=YELLOW, buff=0.05)
            self.play_synced_step(
                2,
                steps[2]["audio_path"],
                steps[2]["audio_duration"],
                Create(highlight)
            )
            
            # 移动高亮
            new_hl = SurroundingRectangle(code_lines[1], color=YELLOW, buff=0.05)
            self.play_synced_step(
                3,
                steps[3]["audio_path"],
                steps[3]["audio_duration"],
                Transform(highlight, new_hl)
            )

            # 如果 narration 超过当前批次，必须先切换左侧讲解文字，再继续高亮
            if len(steps) > 4:
                next_batch = steps[4:8]
                self.replace_lecture_lines([step["screen_text"] for step in next_batch])
                self.play_synced_step(
                    0,
                    next_batch[0]["audio_path"],
                    next_batch[0]["audio_duration"]
                )
            
            self.wait(2)
    ```

    ### 强制约束 - 字体与配色
    **【字体规则】** 所有 `Text()` 必须使用 `font="Noto Sans SC"`（跨平台中文字体）
    ```python
    # ✅ 正确示例
    Text("标题文字", font="Noto Sans SC", font_size=28, color="#BE8944", weight="BOLD")
    Text("讲解文字", font="Noto Sans SC", font_size=20, color="#2C1608")  # 讲解文字必须 font_size=20
    ```
    
    **【🚨🚨🚨 数学表达式与特殊符号 - 必须用 MathTex！🚨🚨🚨】**
    
    **完整规则详见上方规则 1 和规则 1.1，以下是快速参考：**
    
    **核心原则：** Text() 无法渲染数学符号和特殊符号（会变方框），必须用 MathTex。
    
    ```python
    # ✅ 正确示例
    MathTex(r"O(\log_2 n)", color="#9B6D0B").scale(0.8)        # 复杂度
    MathTex(r"2^7 = 128 > 100", color="#9B6D0B").scale(0.8)    # 数学表达式
    MathTex(r"\\checkmark", color="#478211").scale(1.2)          # 绿色勾 ✓
    MathTex(r"\\times", color="#C84A2B").scale(1.2)              # 红色叉 ✗
    
    # ✅ 中文+数学混排
    VGroup(
        Text("因为：", font="Noto Sans SC", font_size=20, color="#2C1608"),
        MathTex(r"2^7 = 128 > 100", color="#9B6D0B").scale(0.8)
    ).arrange(RIGHT, buff=0.2)
    
    # ❌ 错误：以下写法全部会显示方框！
    # Text("✓")  Text("✗")  Text("×")  Text("O(n²)")  Text("log₂n")
    ```
    
    **【需要用 MathTex 的符号速查表】**
    | 符号类型 | 常见符号 | MathTex 写法 |
    |---------|---------|-------------|
    | 上标/下标 | ², ³, ₂, ₙ | `r"^2"`, `r"^3"`, `r"_2"`, `r"_n"` |
    | 运算符 | ×, ÷, ≤, ≥, ≠ | `r"\\times"`, `r"\\div"`, `r"\\leq"`, `r"\\geq"`, `r"\\neq"` |
    | 对数/无穷 | log₂, ∞ | `r"\\log_2"`, `r"\\infty"` |
    | **勾/叉** | **✓, ✗** | **`r"\\checkmark"`（绿勾）, `r"\\times"`（红叉）** |
    
    **⚠️ 违反此规则 = 显示方框 = 生成失败**
    
    **【配色表】** `背景颜色: #FFFDF4` 【奶油白色背景，严禁使用纯黑背景】
    | 语义 | 文字色 | 背景色 | 边框色 | 样式 |
    |------|--------|--------|--------|------|
    | 普通文字 | #2C1608 | - | - | 普通 |
    | 大标题 | #BE8944 | - | - | **加粗 weight="BOLD"** |
    | 重要概念 | #9B6D0B | #FAECD2 | #f2cf7f | - |
    | 警告/错误 | #C84A2B | #FBDDD6 | #f4b1a1 | - |
    | 强调/高亮 | #C35101 | #FDDFCA | #f7bc93 | - |
    | 提示/信息 | #1A7F99 | #ecf6fa | #bde0ee | - |
    | 成功/正确 | #478211 | #effce3 | #c7e7aa | - |
    | 代码块 | - | #fff7e8 | #e4c8a6 | **必须用 tango + background_config** |
    
    **【配色原则】**
    - 每个场景最多 3-4 种强调色，确保整体和谐
    - 讲解文字讲到对应句子时只改变颜色，不改位置大小
    - 小框标题用语义色（成功框用绿、错误框用红），不允许使用大标题色
    - 顶部的大标题颜色必须为 #BE8944，且必须加粗
    - 边框色与标题色配套
    - 代码块必须使用指定的浅色背景和 tango 语法高亮主题，不能使用默认的深色主题和其余语法高亮主题
    - 禁止使用纯白/纯黑的文字，禁止调色板外颜色


    ### 防遮挡规则
    - **宽度安全**: Text/MathTex 设置 `max_width=5` 或 `.scale_to_fit_width()`
    - **⚠️ 右边界硬性限制（必须遵守）**：
        - 右侧区域 X ∈ [0.3, 6.5]，宽度最大 6.2
        - 创建元素后检查并缩放：
          ```python
          if obj.get_right()[0] > 6.5 or obj.get_left()[0] < 0.3:
              obj.scale_to_fit_width(6.2).move_to([3.4, obj.get_center()[1], 0])
          ```
        - VGroup 的 arrange() 后必须检查并缩放
    - **背景保护**: 叠加标签加 `.add_background_rectangle(color=BLACK, opacity=0.8)`
    - **间距预留**: VGroup 使用 `.arrange(DOWN, buff=0.5)`

    **🔴 放新元素前的清理检查（必须遵守！防止右侧元素堆叠重叠）：**

    每次在右侧放置新的主要元素（数组、表格、图、大文字块等）前，必须执行以下 3 步：
    1. **盘点**：列出当前右侧还存在哪些元素
    2. **判断**：哪些元素在后续动画中不再被引用？（不再 Transform、不再 move_to、不再读取位置）
    3. **清理**：对不再需要的元素执行 `FadeOut` + `self.remove()`，然后再添加新元素

    ```python
    # ✅ 正确：放新数组前，先清理旧的不再使用的元素
    self.play(FadeOut(old_array), FadeOut(old_labels), FadeOut(old_pointer))
    self.remove(old_array, old_labels, old_pointer)
    # 清理完毕后，再创建和添加新元素
    new_array = VGroup(*[Square(side_length=0.6) for _ in range(8)]).arrange(RIGHT, buff=0.1)
    new_array.move_to([3.5, -0.5, 0])
    self.play(FadeIn(new_array))

    # ✅ 正确：保留还在用的元素，只清理不用的
    # old_pointer 后面还要用，所以只清理 old_labels
    self.play(FadeOut(old_labels))
    self.remove(old_labels)
    new_labels = VGroup(...)
    self.play(FadeIn(new_labels))

    # ❌ 错误：不清理旧元素就直接添加新元素（导致重叠！）
    new_array = VGroup(...)  # ❌ 旧数组还在原位，新旧重叠！
    self.play(FadeIn(new_array))
    ```

    ### 🔴🔴🔴 生成代码后必须执行的自检（Final Check）🔴🔴🔴

    **🚨 FATAL ERROR 检查 — 包含以下任何一行 = 代码作废，渲染必定失败！🚨**

    在输出代码前，对你的代码执行以下搜索。如果命中任何一条，必须立即修正，否则代码无法运行：

    | 🚨 搜索这个模式 | ⚠️ 问题 | ✅ 必须改为 |
    |----------------|---------|-----------|
    | `Text("✓"` | 会显示方框 | `MathTex(r"\\checkmark", color=...).scale(1.2)` |
    | `Text("✔"` | 会显示方框 | `MathTex(r"\\checkmark", color=...).scale(1.2)` |
    | `Text("√"` | 会显示方框 | `MathTex(r"\\checkmark", color=...).scale(1.2)` |
    | `Text("✗"` | 会显示方框 | `MathTex(r"\\times", color=...).scale(1.2)` |
    | `Text("✘"` | 会显示方框 | `MathTex(r"\\times", color=...).scale(1.2)` |
    | `Text("×"` | 会显示方框 | `MathTex(r"\\times", color=...).scale(1.2)` |
    | `Text("O(` | 数学符号方框 | 拆分为 Text + MathTex 的 VGroup |
    | `Text("log` | 数学符号方框 | 拆分为 Text + MathTex 的 VGroup |
    | `Text(".*log₂.*")` | 下标渲染不稳定/方框 | 拆分为 Text + `MathTex(r"\\log_2 n")` |
    | `Code(code_string=` | 样式错误 | `self.create_code_block(` |
    | `self.add_to_right(` | ❌ 该方法已删除！ | 手动 `move_to` + 边界检查 + `self.play(FadeIn(...))` |
    | `self.remove_from_right(` | ❌ 该方法已删除！ | `self.play(FadeOut(...))` + `self.remove(...)` |
    | `self.clear_right_area(` | ❌ 该方法已删除！ | 逐个 `FadeOut` + `self.remove()` |
    | `# 使用 Text 代替 MathTex` | ❌ 严禁替换！环境已配置 LaTeX | 保持 MathTex，修复 LaTeX 语法 |
    | `# 避免 LaTeX` | ❌ 严禁以此为借口 | 保持 MathTex，环境没有 LaTeX 问题 |

    **🔴🔴🔴 严禁使用 `self.add_to_right()` — 该方法不存在！🔴🔴🔴**
    基类 `TeachingScene` 中没有 `add_to_right`、`remove_from_right`、`clear_right_area` 方法。
    如果你的代码中出现这些调用，运行时会直接报 `AttributeError` 崩溃！
    正确做法：手动 `move_to()` 定位 → 检查边界 → `self.play(FadeIn(obj))` 添加。

    **完整自检步骤（必须全部执行）：**
    1. 搜索所有 `Text(` 调用，检查内容是否包含 ✓✗×√ 或数学符号 → 必须改为 MathTex，否则运行必定失败！
    2. 专项检查所有讲解行：若行文本含 `O(`/`log`/`²`/`₂`/`ₙ`/`^`/`=`/`≤`/`≥`/`✓`/`✗`，禁止整句 `Text(line, ...)`，必须改为 Text + MathTex 混排（重点检查 `log₂n`）
    3. 检查每一条 narration 是否都调用了 `play_synced_step`
    4. 检查 narration 段内部是否错误地写了手动 `self.wait(x)` 来代替 `audio_duration`
    5. 检查每行讲解文字是否超过20个中文字符，超过则拆行（不超过20字的短句不要强行拆开）
    6. 检查讲解文字分批是否按语义切分，不同知识点不能混在同一批
    7. 检查右侧是否出现“**大型图案 + 右侧文字标注并存**”的情况；若出现，必须删除右侧文字或先切换场景后再显示
    8. 专项检查 `self.setup_layout(..., lecture_lines)` 的首批行：若包含 `O(` / `log` / `²` / `₂` / `ₙ` / `^` / `=` / `≤` / `≥`，必须改写为纯中文描述，并将公式改到右侧 `MathTex`
"""


def get_regenerate_note(attempt, MAX_REGENERATE_TRIES, error_message: str = None):
    """
    生成重试提示词（仅用于运行失败的情况）
    
    Args:
        attempt: 当前尝试次数
        MAX_REGENERATE_TRIES: 最大尝试次数
        error_message: 运行失败的错误信息（可选）
    """
    base_note = f"""⚠️ 注意：这是第 {attempt}/{MAX_REGENERATE_TRIES} 次尝试生成代码。

"""
    
    if error_message:
        # 运行失败的情况 - 提供错误信息，要求修复但保持动画效果
        return base_note + f"""**上次代码运行失败，错误信息如下：**
```
{error_message}
```

## 🔴🔴🔴 修复要求（必须严格遵守！）🔴🔴🔴

**1. 只修复错误，不删除内容！**
- 仅针对错误信息中指出的具体问题进行修复
- **严禁删除任何讲解文字、动画步骤或 wait() 调用**
- **严禁缩短视频时长或减少内容**
- **严禁将复杂动画简化为只显示标题和文字**

**2. 保持完整性检查清单：**
- [ ] 所有原有的讲解文字是否都保留了？
- [ ] 所有原有的动画步骤是否都保留了？
- [ ] wait() 调用的总时长是否与原来相近？
- [ ] 数据结构可视化（数组、指针、高亮等）是否完整？
- [ ] 代码块和代码高亮是否保留？

**3. 常见错误的正确修复方式：**
| 错误类型 | ✅ 正确做法 | ❌ 错误做法 |
|---------|-----------|-----------|
| 变量未定义 | 添加变量定义 | 删除使用该变量的代码 |
| 索引越界 | 修复索引计算或添加边界检查 | 减少数组元素数量 |
| 对象属性错误 | 修正属性名或方法调用 | 删除该对象 |
| 动画冲突 | 调整动画顺序或使用 AnimationGroup | 删除动画 |
| LaTeX 错误 | 修复 LaTeX 语法 | 改用纯文本（会显示方框） |
| **MathTex 报错** | **修复 LaTeX 语法本身** | **把 MathTex 改成 Text（严禁！）** |
| **引号嵌套错误** | 内层用单引号 `'` | 内层用中文双引号 `"` |

**🔴 引号嵌套规则（非常重要！）：**
- 如果 Text() 外层使用双引号 `"`，内层必须使用**英文单引号** `'`
- ❌ 错误：`Text("最大的数"浮"到最后！")` - 中文双引号会导致语法错误
- ✅ 正确：`Text("最大的数'浮'到最后！")` - 使用英文单引号

**4. 如果实在无法修复某个复杂动画：**
- 用等效的简单动画替代，而不是直接删除
- 保持相同的讲解内容和时长
- 例如：复杂的数组交换动画 → 简单的 FadeOut + FadeIn，但保留数值变化的展示

**5. 绝对禁止的行为：**
- ❌ 删除整个动画演示部分，只保留标题和讲解文字
- ❌ 将 30 秒的视频缩短为 5 秒
- ❌ 删除代码块展示
- ❌ 删除数据结构可视化
"""
    
    else:
        # 无具体信息时的通用提示
        return base_note + """请检查并改进代码：
- 确保所有变量在使用前已定义
- 检查 `self.wait()` 是否充足
- **保持动画效果完整，不要过度简化**
- **严禁删除任何讲解文字、动画步骤或数据结构可视化**
"""
