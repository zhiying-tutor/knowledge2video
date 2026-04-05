"""
用户个性化配置模块
支持通过自然语言描述生成定制化的视频内容
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable


# ============ AI 解析用户画像的提示词 ============

def get_profile_analysis_prompt(user_profile_text: str) -> str:
    """
    生成让 AI 解析用户画像文本的提示词
    
    Args:
        user_profile_text: 用户输入的自然语言描述
        
    Returns:
        让 AI 分析用户画像的提示词
    """
    return f"""
你是一位教育视频制作专家。请分析以下用户画像描述，并提取关键信息，生成针对教学视频制作的详细指导。

## 用户输入的画像描述
{user_profile_text}

## 重要规则
- **难度级别必须严格遵循用户的明确指定**。如果用户描述中包含明确的难度要求（如"入门"、"中等"、"进阶"、"简单"、"难"等），你必须原样采用，不得根据用户背景或学习目标自行调整。
- 难度映射参考：
  - "简单"/"入门"/"偏简单入门" → "入门"
  - "中等"/"内容难度为中等" → "中等"
  - "进阶"/"高级"/"偏高级进阶"/"难" → "进阶"
- 只有在用户完全未提及难度时，才根据用户背景合理推断。

## 请从以下维度分析并输出 JSON 格式

请严格按照以下 JSON 格式输出，不要添加任何其他文字：

{{
    "user_summary": {{
        "age_group": "从描述中推断的年龄段（如：高中生/大学生/研究生/职场人士）",
        "background": "推断的知识背景和已有储备",
        "learning_goal": "用户的学习目标",
        "target_language": "用户选择的编程语言（如未指定则默认Python）",
        "difficulty_preference": "用户期望的难度（入门/进阶/专家）"
    }},
    "stage1_outline_guidance": {{
        "audience_description": "一句话描述目标受众，用于大纲生成",
        "content_depth": "内容深度要求（应该讲多深、跳过什么）",
        "example_style": "举例风格（用什么样的例子更容易让该用户理解）",
        "pacing_requirement": "节奏要求（快/中/慢，是否需要详细解释每个概念）",
        "motivation_hook": "开场引入建议（什么样的场景能吸引该用户）"
    }},
    "stage2_storyboard_guidance": {{
        "visual_complexity": "视觉复杂度要求（简洁明了/适中/详尽复杂）",
        "animation_pace": "动画节奏（每步停顿时间、是否需要重复演示）",
        "code_display_style": "代码展示风格（注释多少、是否逐行讲解）",
        "lecture_tone": "讲解语气风格（轻松活泼/专业严谨/循循善诱）",
        "emphasis_points": "该用户特别需要强调的内容"
    }},
    "stage3_code_guidance": {{
        "code_language": "代码语言",
        "code_style": "代码风格要求（简洁/详细注释/展示多种写法）",
        "variable_naming": "变量命名风格建议",
        "comment_density": "注释密度（高/中/低）",
        "complexity_handling": "复杂度讲解深度（是否需要数学证明）"
    }}
}}
"""


def get_stage1_profile_prompt(parsed_profile: Dict[str, Any]) -> str:
    """
    根据解析后的用户画像，生成 Stage1（大纲生成）的用户画像提示词片段
    
    Args:
        parsed_profile: AI 解析后的用户画像字典
        
    Returns:
        用于 Stage1 的用户画像提示词
    """
    summary = parsed_profile.get("user_summary", {})
    guidance = parsed_profile.get("stage1_outline_guidance", {})
    
    return f"""
## 用户画像 (AI 智能解析)

### 目标受众
- **人群**: {summary.get('age_group', '未指定')}
- **知识背景**: {summary.get('background', '未指定')}
- **学习目标**: {summary.get('learning_goal', '未指定')}
- **期望难度**: {summary.get('difficulty_preference', '中等')}
- **编程语言**: {summary.get('target_language', 'Python')}

### 大纲设计指导
- **内容深度**: {guidance.get('content_depth', '适中')}
- **举例风格**: {guidance.get('example_style', '贴近生活的例子')}
- **节奏要求**: {guidance.get('pacing_requirement', '中等节奏')}
- **开场引入**: {guidance.get('motivation_hook', '使用生活化场景引入')}
"""


def get_stage2_profile_prompt(parsed_profile: Dict[str, Any]) -> str:
    """
    根据解析后的用户画像，生成 Stage2（分镜脚本）的用户画像提示词片段
    
    Args:
        parsed_profile: AI 解析后的用户画像字典
        
    Returns:
        用于 Stage2 的用户画像提示词
    """
    summary = parsed_profile.get("user_summary", {})
    guidance = parsed_profile.get("stage2_storyboard_guidance", {})
    
    return f"""
## 用户画像 (AI 智能解析)

### 受众特征
- **目标观众**: {summary.get('age_group', '未指定')}
- **知识背景**: {summary.get('background', '未指定')}
- **编程语言**: {summary.get('target_language', 'Python')}

### 分镜设计指导
- **视觉复杂度**: {guidance.get('visual_complexity', '适中')}
- **动画节奏**: {guidance.get('animation_pace', '中等节奏，关键步骤停顿')}
- **代码展示风格**: {guidance.get('code_display_style', '适量注释，逐步讲解')}
- **讲解语气**: {guidance.get('lecture_tone', '清晰专业')}
- **特别强调**: {guidance.get('emphasis_points', '核心概念和实际应用')}
"""


def get_stage3_profile_prompt(parsed_profile: Dict[str, Any]) -> str:
    """
    根据解析后的用户画像，生成 Stage3（Manim代码生成）的用户画像提示词片段
    
    Args:
        parsed_profile: AI 解析后的用户画像字典
        
    Returns:
        用于 Stage3 的用户画像提示词
    """
    summary = parsed_profile.get("user_summary", {})
    guidance = parsed_profile.get("stage3_code_guidance", {})
    
    return f"""
## 用户画像 (AI 智能解析)

### 受众特征
- **目标观众**: {summary.get('age_group', '未指定')}
- **知识背景**: {summary.get('background', '未指定')}
- **期望难度**: {summary.get('difficulty_preference', '中等')}

### Manim 代码生成指导
- **代码语言**: {guidance.get('code_language', 'Python')}
- **代码风格**: {guidance.get('code_style', '清晰易读，适量注释')}
- **变量命名**: {guidance.get('variable_naming', '语义化命名')}
- **注释密度**: {guidance.get('comment_density', '中等')}
- **复杂度讲解**: {guidance.get('complexity_handling', '简要说明，不深入数学证明')}
"""


@dataclass
class UserProfile:
    """用户配置文件 - 基于自然语言描述"""
    
    # 原始用户输入
    raw_profile_text: str = ""
    
    # AI 解析后的结构化数据
    parsed_profile: Optional[Dict[str, Any]] = None
    
    # 各阶段的用户画像提示词（由 AI 生成）
    stage1_prompt: str = ""
    stage2_prompt: str = ""
    stage3_prompt: str = ""
    
    # 提取的关键信息（便于直接访问）
    target_language: str = "Python"
    
    def __post_init__(self):
        """如果有原始文本但没有解析结果，设置默认值"""
        if self.raw_profile_text and not self.parsed_profile:
            # 设置默认的解析结果
            self.parsed_profile = self._get_default_parsed_profile()
            self._generate_stage_prompts()
    
    def _get_default_parsed_profile(self) -> Dict[str, Any]:
        """返回默认的解析结果结构"""
        return {
            "user_summary": {
                "age_group": "大学生/研究生",
                "background": "有一定编程基础",
                "learning_goal": "学习算法与数据结构",
                "target_language": "Python",
                "difficulty_preference": "进阶"
            },
            "stage1_outline_guidance": {
                "audience_description": "有编程基础的大学生",
                "content_depth": "理论与实践结合，包含复杂度分析",
                "example_style": "使用课程项目和面试题场景",
                "pacing_requirement": "中等节奏，适当跳过基础概念",
                "motivation_hook": "从实际问题引入，展示算法的实用价值"
            },
            "stage2_storyboard_guidance": {
                "visual_complexity": "适中，关键步骤详细展示",
                "animation_pace": "中等节奏，关键步骤停顿讲解",
                "code_display_style": "包含必要注释，展示标准实现",
                "lecture_tone": "专业但易懂",
                "emphasis_points": "算法核心思想和实现技巧"
            },
            "stage3_code_guidance": {
                "code_language": "Python",
                "code_style": "Pythonic风格，清晰易读",
                "variable_naming": "语义化命名，遵循PEP8",
                "comment_density": "中等，关键步骤有注释",
                "complexity_handling": "简要说明时间空间复杂度"
            }
        }
    
    def _generate_stage_prompts(self):
        """根据解析结果生成各阶段的提示词"""
        if self.parsed_profile:
            self.stage1_prompt = get_stage1_profile_prompt(self.parsed_profile)
            self.stage2_prompt = get_stage2_profile_prompt(self.parsed_profile)
            self.stage3_prompt = get_stage3_profile_prompt(self.parsed_profile)
            
            # 提取目标语言
            summary = self.parsed_profile.get("user_summary", {})
            self.target_language = summary.get("target_language", "Python")
    
    def update_with_parsed_profile(self, parsed_profile: Dict[str, Any]):
        """使用 AI 解析的结果更新用户画像"""
        self.parsed_profile = parsed_profile
        self._generate_stage_prompts()
        
        # 更新目标语言
        summary = parsed_profile.get("user_summary", {})
        self.target_language = summary.get("target_language", "Python")
    
    def get_stage1_prompt(self) -> str:
        """获取 Stage1（大纲生成）的用户画像提示词"""
        return self.stage1_prompt
    
    def get_stage2_prompt(self) -> str:
        """获取 Stage2（分镜脚本）的用户画像提示词"""
        return self.stage2_prompt
    
    def get_stage3_prompt(self) -> str:
        """获取 Stage3（Manim代码）的用户画像提示词"""
        return self.stage3_prompt
    
    def get_language(self) -> str:
        """获取目标编程语言"""
        return self.target_language
    
    def to_dict(self) -> dict:
        """转换为字典格式，便于序列化"""
        return {
            "raw_profile_text": self.raw_profile_text,
            "parsed_profile": self.parsed_profile,
            "target_language": self.target_language
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        """从字典创建 UserProfile 实例"""
        profile = cls(
            raw_profile_text=data.get("raw_profile_text", ""),
            parsed_profile=data.get("parsed_profile"),
            target_language=data.get("target_language", "Python")
        )
        if profile.parsed_profile:
            profile._generate_stage_prompts()
        return profile


def get_default_profile() -> UserProfile:
    """获取默认用户配置"""
    default_text = "我是大学生，有一定编程基础，想学习算法与数据结构，使用Python，难度为中等级别。"
    profile = UserProfile(raw_profile_text=default_text)
    return profile


def create_profile_from_text(profile_text: str) -> UserProfile:
    """
    根据自然语言描述创建用户配置（不调用 AI，使用默认结构）
    实际的 AI 解析需要在 agent.py 中调用
    
    Args:
        profile_text: 用户输入的自然语言描述
    
    Returns:
        UserProfile 实例（带有默认解析结果，需要后续调用 AI 更新）
    """
    return UserProfile(raw_profile_text=profile_text)


def parse_profile_with_ai_sync(
    profile_text: str, 
    api_function: Callable,
    max_retries: int = 5
) -> Dict[str, Any]:
    """
    使用 AI 解析用户画像文本（同步版本，带重试机制）
    
    Args:
        profile_text: 用户输入的自然语言描述
        api_function: API 调用函数
        max_retries: 最大重试次数，默认5次
        
    Returns:
        解析后的用户画像字典
    """
    import json
    import time
    
    prompt = get_profile_analysis_prompt(profile_text)
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔄 正在解析用户画像 (尝试 {attempt}/{max_retries})...")
            
            response, _ = api_function(prompt, max_tokens=2000)
            
            if response is None:
                print(f"⚠️ 第 {attempt} 次尝试：API 返回空响应")
                if attempt < max_retries:
                    time.sleep(1)  # 等待1秒后重试
                continue
            
            # 尝试从响应中提取文本
            try:
                content = response.candidates[0].content.parts[0].text
            except Exception:
                try:
                    content = response.choices[0].message.content
                except Exception:
                    content = str(response)
            
            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # 尝试解析 JSON
            parsed = json.loads(content)
            
            # 验证解析结果包含必要的字段
            if "user_summary" in parsed and "stage1_outline_guidance" in parsed:
                return parsed
            else:
                print(f"⚠️ 第 {attempt} 次尝试：解析结果缺少必要字段")
                if attempt < max_retries:
                    time.sleep(1)
                continue
            
        except json.JSONDecodeError as e:
            print(f"⚠️ 第 {attempt} 次尝试：JSON 解析错误 - {e}")
            if attempt < max_retries:
                time.sleep(1)
            continue
        except Exception as e:
            print(f"⚠️ 第 {attempt} 次尝试：解析失败 - {e}")
            if attempt < max_retries:
                time.sleep(1)
            continue
    
    print(f"❌ AI 解析用户画像失败，已尝试 {max_retries} 次")
    return None
