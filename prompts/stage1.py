from typing import Optional
from .user_profile import UserProfile, get_default_profile


def get_prompt1_outline(
    knowledge_point: str,
    duration: int = 5,
    reference_image_path: Optional[str] = None,
    user_profile: Optional[UserProfile] = None,
    forced_difficulty_level: Optional[str] = None
):
    """
    生成教学大纲的提示词
    
    Args:
        knowledge_point: 要讲解的知识点/算法
        duration: 视频时长（分钟）
        reference_image_path: 参考图片路径（可选）
        user_profile: 用户配置，可选，默认使用默认配置
    
    Returns:
        完整的提示词字符串
    """
    # 如果没有提供用户配置，使用默认配置
    if user_profile is None:
        user_profile = get_default_profile()
    
    # 获取 AI 智能生成的用户画像提示词
    profile_prompt = user_profile.get_stage1_prompt()
    target_language = user_profile.get_language()
    
    difficulty_field_instruction = (
        forced_difficulty_level
        if forced_difficulty_level
        else "根据用户画像确定的难度级别"
    )

    force_difficulty_prompt = ""
    if forced_difficulty_level:
        force_difficulty_prompt = f"""
    ## 🔴 难度硬约束（必须严格遵守）
    - 本次请求指定难度：**{forced_difficulty_level}**
    - 输出 JSON 时，`difficulty_level` 字段必须且只能等于 **\"{forced_difficulty_level}\"**
    - 严禁根据用户画像、额外信息或模型偏好改写该值
"""

    base_prompt = f""" 
    你是一位**计算机科学教育架构师**。你需要设计一个**基于执行追踪（Execution Trace）**的深度算法教学大纲。

    目标算法: "{knowledge_point}"
    要求视频总时长：至少 {duration} 分钟。
    
    {profile_prompt}
    {force_difficulty_prompt}
    
    这意味着你需要：
    1. 设计足够多的小节（Sections），通常需要 8-12 个小节。
    2. 每个小节的内容必须详尽，涵盖初始化、每一步迭代、边界条件处理、复杂度分析以及总结。
    3. 特别是对于二分搜索，不能只讲一次成功的查找，必须包含：
       - 场景引入（查字典/猜数字）。
       - 算法核心思想（分而治之）。
       - 详细的代码初始化（low, high, mid 指针）。
       - 多次迭代过程（左侧查找、右侧查找）。
       - 查找失败的情况（找不到元素时指针如何交错）。
       - 边界情况（数组为空、只有一个元素、目标在开头/结尾）。
       - 复杂度分析（为什么是 O(log n)）。
       - 实际应用场景。

    # 核心指令 (Universal Analysis Protocol)
    
    0.  **场景引入与直觉构建 (Conceptual Hook - MANDATORY)**:
        - 在进入代码细节前，必须设计一个现实生活的类比场景（Analogy）。
        - 具体要求：
          - 场景化：例如讲二分搜索，必须先描述"在图书馆按编号找书"或"查字典"的场景。
          - **重要**：场景选择必须符合目标受众的生活经验和认知水平。
          - 对比痛点：必须展示"朴素做法"（如一本本翻，线性查找）的低效，以此引出"优化做法"（二分查找）的必要性。
          - 零代码：此阶段禁止出现任何代码或复杂变量，仅讨论逻辑和直觉。
        - 输出结构调整：在 JSON 的 sections 列表中，第一个 section 的 id 必须是 section_0_intro，内容必须是上述类比。

    1.  **算法解构 (Decomposition)**:
        - 如果这是基础算法（如排序），直接展示过程。
        - 如果这是**复杂/组合算法**（如 A*搜索、红黑树插入、带有记忆化的DP）：
          - 必须将视频分为：**"基础状态" -> "遇到的问题/瓶颈" -> "优化策略/核心操作" -> "最终状态"**。
          - 或者是：**"数据结构A的维护" + "数据结构B的配合"**（例如 LRU Cache = HashMap + DoubleLinkedList）。
        - **根据用户画像调整内容深度和讲解风格**。

    2.  **用例设计 (Case Engineering)**:
        - 设计一个**"最小完备集" (Minimal Complete Case)**。
        - 这个用例不能太简单（导致看不出优化点），也不能太复杂（导致视频冗长）。
        - **根据用户画像调整示例复杂度**。
        - *关键*：如果是优化算法，用例必须能触发那个"优化逻辑"（例如：讲剪枝算法，必须构造一个能被剪枝的分支）。

    3.  **变量追踪清单**:
        - 列出所有核心变量（Trace Variables）。对于复杂算法，可能包含：递归栈深度、当前 Cost、Hash表内容、PQ 队列状态等。

    4.  **代码展示要求**:
        - 所有代码必须使用 **{target_language}** 编写
        - 代码风格和注释详细程度根据用户画像调整

    5.  **结尾结构要求 (Strict Ending Structure)**:
        - **倒数第二节 (Summary)**: 仅包含文字总结、复杂度回顾、优缺点分析。**禁止出现代码**。
        - **最后一节 (Full Source Code)**: 仅展示完整的、可运行的 {target_language} 源代码。**禁止出现大段讲解文字**。此部分专门用于让观众暂停截图或阅读完整逻辑。

    # 输出格式 (JSON)
    
    ## ⚠️⚠️⚠️ JSON 输出格式要求（必须严格遵守）⚠️⚠️⚠️
    
    **🚨 关键规则：**
    1. **只输出纯 JSON**，不要添加任何解释文字、markdown 标记或注释
    2. **字符串中的引号必须转义**：如果字符串内容包含双引号 `"`，必须写成 `\\"`
    3. **字符串中的换行必须转义**：使用 `\\n` 而不是实际换行
    4. **数组最后一个元素后不要加逗号**
    5. **所有字符串必须用双引号**，不能用单引号
    6. **确保 JSON 可以被 Python 的 json.loads() 正确解析**
    7. **请直接输出 JSON，不要用 ```json ``` 包裹**
    
    请严格按照以下格式输出：
    {{
        "topic": "视频标题（体现深度和硬核，如'从零实现：XXX算法的内存级演示'）",
        "target_audience": "根据用户画像描述目标受众",
        "programming_language": "{target_language}",
        "difficulty_level": "{difficulty_field_instruction}",
        "data_case_definition": "详细定义输入数据。例如：'图G：节点A-E，边权如下...；启发式函数 h(n)=...'",
        "algorithm_components": ["列出涉及的数据结构，如 'Min-Heap', 'Adjacency List', 'Visited Set'"],
        "sections": [
            {{
                "id": "section_0_intro",
                "title": "场景引入",
                "content": "描述现实生活的类比场景，如查字典，引出算法必要性。",
                "code_mapping": "None"
            }},
            {{
                "id": "section_1",
                "title": "结构定义与初始化",
                "content": "展示由哪些基础数据结构组合而成，初始化状态。",
                "code_mapping": "Class Definition / Init function"
            }},
            {{
                "id": "section_2",
                "title": "核心逻辑/优化点演示",
                "content": "演示算法最精髓的部分（如旋转、松弛、剪枝）。必须展示数据变化。",
                "code_mapping": "Core Loop / Recursion / State Transition"
            }}
        ]
    }}
    
    **❌ 常见错误（会导致解析失败）：**
    - 数组最后一个元素后面有逗号：`["a", "b",]` ❌
    - 字符串内的引号没有转义：`"说"你好""` ❌ 应该是 `"说\\"你好\\""`
    - 使用单引号：`'title'` ❌ JSON 必须用双引号
    - 对象最后一个字段后有逗号：`{{"id": "1",}}` ❌
    """
    
    if reference_image_path:
        base_prompt += f"\n注：请参考提供的图片来决定数据结构的视觉风格（如树是画成圆圈还是方块）。\n"

    return base_prompt
