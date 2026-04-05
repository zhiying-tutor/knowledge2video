# AGENTS

## 全自动项目开发规范

### 绝对执行隔离 (Absolute Execution Isolation)

本项目的核心渲染业务、E2E 测试及长视频生成，必须且只能在 Docker 容器内运行。

严禁 AI 代理在宿主机本地使用 `uv run`、`pip` 或裸 `python` 强行拉取依赖或运行核心业务脚本。

所有物理穿透执行必须挂载系统级依赖并走 Docker 隔离舱，例如：

```bash
docker-compose run --rm --no-deps -v "$PWD:/workspace" -w /workspace -e PYTHONPATH=/workspace ... api bash -c "..."
```

## 路径与环境安全铁律

- 所有核心渲染、E2E、长视频生成命令默认在容器内执行。
- 如果仓库内已有容器标准命令，优先复用现成命令，不得退回宿主机本地执行。
- 执行前必须保留项目工作目录挂载、`PYTHONPATH`、网络穿透变量以及系统级依赖安装步骤。

## 音视频真值铁律

- 任何音视频对齐、旁白时长、成片时长相关判断，严禁使用模型估算值或接口元数据，必须且只能依赖物理文件落盘后的本地测时结果（如 `ffprobe`、`wave`、`pydub`）。
- 涉及 TTS 与大体积音频流的容器命令，必须确保 `NO_PROXY` / `no_proxy` 包含 `vip.dmxapi.com`，防止代理/VPN 在物理链路层劫持音频请求。
- 端到端重跑、E2E 或音频链路测试前，必须销毁旧的音频、代码生成物、渲染产物与合并视频，禁止让脏缓存伪装成“成功结果”。
- “文件带音轨”不等于“旁白完整发声”。验收有声视频时，必须同时做局部静音分析（如 `ffmpeg silencedetect`、分段抽样、AST 对位分析），禁止只看 AAC 流存在与平均音量。
