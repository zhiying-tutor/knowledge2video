# PROJECT.md

## 1. 项目定位
K2V (Knowledge to Video) 是一个将知识点自动转换为教学视频的系统。系统的基本流水线是：

1. Stage 1 生成教学大纲
2. Stage 2 生成分镜脚本
3. Stage 3 生成 Manim 业务代码
4. 渲染 section 视频
5. 合并 section 视频得到最终成片

V5.0 的主题不是“加一个 TTS 接口”，而是建立一条**可计算、可验证、可回灌**的旁白真值链。最终目标是：

- 画面短句仍由原有 storyboard 驱动
- 旁白文本与画面文本彻底解耦
- 每条 narration 时长只服从物理音频真值
- 即便 Manim 内部混音不稳定，最终 section 视频仍能通过 Python + FFmpeg 获得稳定音轨

---

## 2. V5.0 的系统结论
V5.0 架构已经把“讲什么、画什么、响什么”拆成三条不同职责链：

- `lecture_lines`
  负责画面左侧短句与视觉提示
- `section_steps`
  负责旁白 sidecar 数据与音频真值
- Stage 3 业务代码
  负责动画调度与视觉时间轴表达

这三条链路在最终成片阶段重新汇合，但汇合点不再是 Manim 内部的黑盒混音，而是 Python 侧的**时间轴重建 + 音轨回灌**。

当前代码基线下，系统已经具备如下能力：

- 真实 `tts-pro` TTS 调用
- TTS 返回格式自动识别
- 统一音频规范化为持久 `.wav`
- 本地物理测时
- `play_synced_step(...)` 可视化调度原语
- AST 覆盖校验
- section 级 narration track 重建
- FFmpeg 回灌 section 音轨
- 合并后音轨保留校验

---

## 3. 架构核心原则

### 3.1 视觉与旁白解耦
V5.0 明确拒绝让一份文案同时承担“屏幕文本”和“TTS 旁白”双重职责。

原因很简单：
- 屏幕短句要求短、稳、易扫读
- TTS 旁白要求口语化、自然、可听

因此：
- `Section.lecture_lines` 继续表示画面短句
- `spoken_script` 专门表示旁白扩写
- `spoken_script` 绝不进入画面

### 3.2 时间真值来自物理文件
模型估时、接口 metadata 时长、经验值时长都不是可信真值。

V5.0 的时间真值定义为：
- 音频先落盘
- 再用本地库测时
- 再把测得的 `audio_duration` 写入 sidecar 数据

只有这一层测时，才允许参与后续：
- Prompt 注入
- 视觉调度
- narration track 重建
- 音视频对齐验收

### 3.3 最终音轨不押注 Manim
V5.0 早期确实尝试过依赖 Manim 的 `add_sound()` 链路，但实弹验证暴露出一个关键事实：

- 宏观上 mp4 有音轨
- 局部上会出现大面积 narration 丢失

因此最终架构选择是：
- **允许 Manim 在渲染期参与临时音频调度**
- **但绝不把最终音轨正确性押在 Manim 内部混音上**

最终成片音轨以 Python 侧重建结果为准。

---

## 4. 数据模型：`section_steps`

### 4.1 背景
Stage 2 输出的 `Section` 结构仍然是：

```python
Section(
    id: str,
    title: str,
    lecture_lines: List[str],
    animations: List[str],
    estimated_duration: Optional[int]
)
```

V5.0 不覆盖这个结构，而是在 Stage 2.5 派生出旁车数据 `section_steps`。

### 4.2 `section_steps` 结构
每个 `lecture_line` 会裂变成一个 step：

```python
{
    "screen_text": "画面上的短句",
    "spoken_script": "供 TTS 使用的最小增量口语旁白",
    "audio_path": "/abs/path/to/step_00.wav",
    "audio_duration": 4.655979166666667
}
```

字段语义：

- `screen_text`
  视觉短句真值。只用于屏幕显示。

- `spoken_script`
  最小增量扩写后的旁白真值。只用于 TTS。

- `audio_path`
  容器内可直接访问的绝对路径。后续既会被 Prompt 注入，也会被 Python 侧重建 narration track 使用。

- `audio_duration`
  音频物理时长，单位秒，浮点数。

### 4.3 存储位置
`section_steps` 会持久化到：

`<output_dir>/<section_id>_steps.json`

例如：

`src/CASES/E2E_REAL/0-二分搜索/section_0_intro_steps.json`

其设计目的包括：
- Prompt 注入
- 调试与复盘
- section 回灌
- 缓存复用

---

## 5. `src/audio_steps.py`：音频引擎

`src/audio_steps.py` 是 V5.0 的音频主引擎。它承担了从文本扩写到后期回灌的整条音频链路。

### 5.1 主要职责

1. 短句扩写为 `spoken_script`
2. 调用真实 TTS
3. 自动识别返回音频格式
4. 规范化音频到 `.wav`
5. 物理测时
6. 构建 `section_steps`
7. 解析生成代码的时间轴
8. 重建 narration track
9. 回灌到 section 视频

### 5.2 关键函数

- `expand_screen_text_to_spoken_script(...)`
- `get_tts_endpoint_config()`
- `synthesize_tts_audio(...)`
- `resolve_audio_output_path(...)`
- `normalize_audio_for_manim(...)`
- `measure_audio_duration(...)`
- `build_section_steps(...)`
- `build_section_narration_track(...)`
- `remux_video_with_audio(...)`

---

## 6. TTS 物理管线

### 6.1 默认配置
当前代码默认：

- `DEFAULT_TTS_MODEL = "tts-pro"`
- `DEFAULT_TTS_BASE_URL = "https://vip.dmxapi.com/v1"`
- `DEFAULT_TTS_VOICE = "alloy"`

优先级是：

1. `TTS_API_KEY` / `TTS_BASE_URL` / `TTS_MODEL` / `TTS_VOICE`
2. `OPENAI_API_KEY`
3. 配置文件中的全局 `api_key` 与 `gpt5.base_url`

### 6.2 扩写策略
扩写函数 `expand_screen_text_to_spoken_script(...)` 的约束是：

- 保持原意
- 不引入新知识点
- 最小增量扩写
- 输出一条适合 TTS 的单句口语文本

这不是自由改写，而是“视觉短句 -> 可朗读单句”的轻量转换。

### 6.3 TTS 请求兼容
真实服务在兼容 OpenAI 协议时，参数兼容性并不完全稳定。因此 `synthesize_tts_audio(...)` 会依次尝试多个 payload 版本，例如：

- 带 `voice` + `response_format`
- 带 `voice` 不带 `response_format`
- 不带 `voice` 仅带 `response_format`
- 仅保留最小字段

遇到 `400` 时会降级 payload，遇到 `401/403/404` 则视为硬阻断。

### 6.4 返回格式处理
真实联调中，`tts-pro` 返回的并不是假定的 `.wav`，而是 `.mp3`。因此当前实现不会假设返回格式，而是通过：

- 文件魔数
- `Content-Type`

来判断实际格式。

支持分流为：
- `.wav`
- `.mp3`
- `.ogg`

### 6.5 音频规范化
无论原始返回格式是什么，V5.0 都会执行规范化：

```python
audio = AudioSegment.from_file(source_path)
normalized = audio.set_frame_rate(48000).set_channels(2).set_sample_width(2)
normalized.export(target_path, format="wav")
```

规范化目的：
- 统一后续测时行为
- 统一 Manim 输入格式
- 统一 FFmpeg 回灌输入格式

### 6.6 哑弹防线
音频文件落盘后，会做最基础的合法性检查：

- 时长不得短于阈值
- `rms` 不能为 0
- 无法识别的音频格式直接报错

这能防止“请求成功但内容无效”的假成功。

### 6.7 物理测时
当前测时逻辑：

- `.wav` 使用 `wave`
- 非 `.wav` 使用 `pydub`

注意：虽然代码保留了非 `.wav` 分支，但在当前 V5.0 正式链路中，返回音频最终都会被统一导出成 `.wav`，因此正常路径下实际走的是 `.wav + wave`。

---

## 7. `prompts/base_class.py`：视觉调度原语

### 7.1 保留的基础职责
基类仍负责：

- `setup_layout(...)`
- `create_code_block(...)`
- `highlight_lecture_line(...)`
- `unhighlight_lecture_line(...)`
- `replace_lecture_lines(...)`

这些能力继续服务于 Stage 3 的视觉表达。

### 7.2 `play_synced_step(...)`
V5.0 新增了：

```python
def play_synced_step(
    self,
    line_index,
    audio_path,
    audio_duration,
    *animations,
    highlight_color="#C35101",
    reset_color="#2C1608",
)
```

这个原语的职责是：
- 在 narration 段开始时高亮左侧对应短句
- 调用 `add_sound(audio_path)`
- 用 `audio_duration` 约束并行动画窗口
- 在 narration 段结束时恢复短句颜色

### 7.3 设计哲学
`play_synced_step(...)` 的真正价值不是“最终混音”，而是：

- 给大模型一个稳定的 narration 调度心智模型
- 让视觉表达继续自由
- 把“讲一句话持续多久”固定到 `audio_duration`

也就是说，它是**视觉时间轴原语**，不是最终音轨真值层。

---

## 8. `prompts/stage3.py`：代码生成模板

### 8.1 输入契约
Stage 3 现在显式消费：

- `section`
- `section_steps`
- `base_class`
- `estimated_duration`

Prompt 会注入：

- `screen_texts`
- 完整 `section_steps`
- 原始 `section.animations`

### 8.2 Prompt 目标
Prompt 不再只要求“大模型写动画”，而是要求它：

- 仅在画面中使用 `screen_text`
- 把 `spoken_script` 视为离线 TTS 数据，不得显示
- narration 段必须通过 `play_synced_step(...)` 调度
- narration 行数过多时必须分批切换 `screen_text`

### 8.3 Few-shot 骨架
few-shot 已经从旧版 `highlight + wait` 改为：

```python
steps = [...]
screen_texts = [step["screen_text"] for step in steps[:4]]
self.setup_layout("标题", screen_texts)
self.play_synced_step(...)
```

这保证大模型的默认心智是：
- narration 用 `play_synced_step`
- 画面文本来自 `screen_text`
- 动画仍可自由构造

---

## 9. `src/agent.py`：运行时总调度

### 9.1 Stage 2.5 注入
`prepare_section_steps(...)` 在 Stage 3 之前运行，构建并缓存 `section_steps`。

如果本地已经存在：
- `section_steps.json`
- section 音频目录
- 目录中有可用 `.wav`

则会复用已生成的音频侧车数据。

### 9.2 AST 覆盖校验
`_validate_synced_step_coverage(...)` 会对生成代码执行本地 AST 校验：

- 找到 `construct()`
- 统计 `play_synced_step(...)` 调用数
- 拒绝 `construct()` 里直接写 `add_sound()`
- 若 `play_synced_step` 调用数小于 `len(section_steps)`，直接判失败并重生

这一步是防止 Stage 3 业务代码只对前几句挂旁白、后面偷工减料的重要硬闸门。

### 9.3 音轨存在校验
`_video_has_audio_stream(...)` 使用 `ffprobe` 检查视频是否带音轨。

使用位置包括：
- 渲染缓存命中时的复用判断
- section 回灌后的视频校验
- 最终合并视频的音轨校验

### 9.4 section 回灌入口
`_remux_section_audio(...)` 是 section 级收口函数。它会：

1. 读取 `<section_id>_steps.json`
2. 读取 `<section_id>.py`
3. 调用 `build_section_narration_track(...)`
4. 调用 `remux_video_with_audio(...)`
5. 输出 `<output_dir>/audio_remux/<section_id>_with_audio.mp4`

因此从 V5.0 开始，`section_videos` 的最终权威结果应该理解为：

- **不是原始 Manim 直出视频**
- **而是回灌后的 section 视频**

### 9.5 缓存策略
当前缓存命中策略已经升级为：

- 若已有视频存在，也先做回灌修正
- 只有“回灌后仍带音轨”的 section 视频才允许跳过渲染
- 旧的“虽然带音轨但局部 narration 丢失”的 section 视频不会直接被无脑复用

---

## 10. 终极防线：时间轴重建与音频回灌

### 10.1 为什么需要回灌
真实实弹验证表明，以下事实同时成立：

- TTS 单段音频是正常的
- Stage 3 的 `play_synced_step` 覆盖也完整
- 但复杂 scene 的最终音轨会出现大面积局部静音

也就是说，问题并不在：
- TTS 哑弹
- Prompt 漏调用

而在：
- **复杂业务场景下，Manim 内部的逐句 `add_sound()` 混音不稳定**

### 10.2 当前实现思路
V5.0 的正式方案是放弃对 Manim 最终混音结果的信任，转而：

1. 使用 Stage 3 代码作为“视觉时间轴脚本”
2. 本地 AST 解析 `construct()`
3. 抽取 narration/停顿事件
4. 重新构造 section narration track
5. 用 FFmpeg 把 narration track 回灌到渲染视频中

### 10.3 时间轴解释规则
当前 `build_section_narration_track(...)` 的解释规则是明确且有限的：

- 遇到 `play_synced_step(...)`
  - 追加对应 step 的旁白音频

- 遇到 `wait(x)`
  - 追加 `x` 秒静音

- 遇到 `play(..., run_time=t)`
  - 追加 `t` 秒静音

- 遇到 `play(...)` 且未显式给出 `run_time`
  - 视为 `1.0s` 静音窗口

- 遇到 `replace_lecture_lines(...)`
  - 视为 `1.0s` 静音窗口

- 支持简单的 `if len(steps) > N:` 分支模式

这套规则的目标不是完美还原所有业务语义，而是：
- 用确定性、可复盘的方式重建 narration 时间表
- 确保每个 `play_synced_step` 对应的旁白绝不会丢

### 10.4 这套方案当前能解决什么
它已经能解决此前最严重的问题：

- 不再出现 `60s+` 的大面积 narration 消失
- 每个 step 的旁白都被明确纳入最终 track
- section 与最终成片都能被 `ffprobe` / `silencedetect` 直接审计

### 10.5 这套方案当前仍保留什么
它会保留业务代码里显式存在的视觉-only 停顿。

因此如果生成代码中存在：
- `self.wait(0.3)`
- `self.wait(1.5)`
- `self.play(...)` 但没有 narration
- `replace_lecture_lines(...)`

则最终回灌 track 中会保留对应静音窗口。

这意味着：
- “局部完全掉音”问题已经被回灌机制根治
- “视觉-only 过渡停顿过长”则属于 Prompt 与业务代码层面的节奏问题

这两者必须严格区分。

---

## 11. 验证体系

### 11.1 离线链路验证
`test_audio_pipeline.py` 用 mock 方式验证：

- `lecture_lines -> spoken_script`
- `spoken_script -> 音频文件`
- 音频文件 -> 物理时长
- `section_steps -> Prompt 注入`

### 11.2 真实 E2E
`test_real_e2e.py` 负责 smoke 级真实联调：

- 真实大纲
- 真实分镜
- 真实 TTS
- 真实 Stage 3 代码生成
- 真实渲染
- 真实 section 回灌
- 真实最终合并

### 11.3 局部静音验尸
V5.0 最重要的验尸工具是：

- `ffprobe`
- `ffmpeg volumedetect`
- `ffmpeg silencedetect`
- 代码 AST 覆盖分析

重要结论：

- “mp4 有 AAC 音轨” 不等于 “每一句 narration 都响了”
- “平均音量不为 0” 不等于 “中段没有大面积死寂”

因此 V5.0 的验收必须包含：

1. 原始 TTS 片段抽样非静音
2. section 视频带音轨
3. section 视频无大面积局部静音洞
4. 最终成片带音轨
5. 最终成片无大面积局部静音洞

---

## 12. 当前实现状态

V5.0 已经完整落地，当前正式链路是：

`lecture_lines`
-> `spoken_script`
-> `section_steps`
-> 真实 TTS 音频
-> 统一 `.wav`
-> 物理测时
-> Stage 3 `play_synced_step` 代码
-> AST 覆盖校验
-> 渲染 section 视频
-> AST 时间轴重建
-> narration track
-> FFmpeg 回灌 section 音轨
-> 最终合并成片

这条链已经把“宏观有音轨、局部大掉音”从不可控黑盒问题，降维成了可以静态分析、可验证、可回灌修复的问题。

---

## 13. 已知边界

当前代码仍有两个值得注意的边界：

1. narration track 的重建规则是 AST 启发式规则，不是全语义解释器
2. 视觉-only 的停顿仍会保留为静音窗口

这不是 V5.0 的失败，而是当前实现的明确边界。V5.0 已经解决的是“局部 narration 消失”的系统性故障；下一阶段若要继续优化，重点将转向：

- Prompt 节奏约束
- `play(...)` / `wait(...)` 的静音预算建模
- narration track 与视觉节奏的进一步压缩对齐
