# InkFlow

AI 视频生成 Workflow。

根据项目目录下的 `script.json` 自动生成画面、配音、字幕，并合成最终视频。

支持三种工作流：
- **Legacy**: 静态图片 + Ken Burns
- **Shot**: Seedance 视频片段
- **Infographic**: Remotion 动态信息图（数据、图表、文字动效、WebGL shader）

## 快速开始

### 1. 安装依赖

本项目使用 [uv](https://docs.astral.sh/uv/) 管理 Python 依赖，使用 npm 管理 Remotion 依赖。

```bash
# Python 依赖
uv sync

# Remotion 依赖（信息图工作流需要 Node.js）
cd remotion && npm install && cd ..
```

同时需要安装 [FFmpeg](https://ffmpeg.org/download.html) 并确保在 PATH 中。

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的火山方舟 API Key：

```bash
ARK_API_KEY=your_api_key_here
```

TTS 使用 Edge TTS，完全免费，无需额外配置。

### 3. 准备项目

每个视频是一个独立的项目目录，结构如下：

```text
projects/example-proj/
├── scripts/
│   ├── script.json              # 默认脚本
│   └── script_infographic.json  # 信息图示例脚本
├── assets/
│   ├── images/                  # 生成的画面
│   ├── videos/                  # 生成的视频片段
│   ├── audio/                   # 生成的配音
│   ├── music/                   # 背景音乐（可选）
│   └── subtitles/               # 生成的字幕
├── output/                      # 最终视频
└── logs/                        # 运行日志
```

示例项目已放在 `projects/example-proj/`，可直接使用或复制一份改名字：

```bash
cp -r projects/example-proj projects/my_video
```

### 4. 生成视频

```bash
# 默认脚本（legacy 或 shot）
uv run inkflow projects/example-proj

# 信息图示例
uv run inkflow projects/example-proj --script scripts/script_infographic.json
```

运行结束后会生成成本报告：`projects/example-proj/logs/cost.json`。

#### 添加背景音乐

把背景音乐放到 `projects/example-proj/assets/music/bgm.mp3`，会自动使用。

或手动指定：

```bash
uv run inkflow projects/example-proj --bgm projects/example-proj/assets/music/background.mp3
```

#### 分步调试

```bash
uv run inkflow projects/example-proj --step images
uv run inkflow projects/example-proj --step audio
uv run inkflow projects/example-proj --step subtitles
uv run inkflow projects/example-proj --step video
```

## 项目结构

```text
.
├── packages/                # Python monorepo (uv workspace)
│   ├── inkflow-core/        # 模型、配置、类型
│   ├── inkflow-generators/  # Seedream / Seedance / TTS / 字幕 / 封面
│   ├── inkflow-workflows/   # 工作流编排器
│   ├── inkflow-assembly/    # FFmpeg 合成
│   ├── inkflow-remotion/    # Python ↔ Remotion 桥接
│   └── inkflow-cli/         # CLI 入口
├── remotion/                # Node.js Remotion 子项目
├── projects/                # 视频项目目录
│   └── example-proj/
├── pyproject.toml
└── .env.example
```

## 工作流选择

在 `script.json` 的 `metadata` 中指定：

```json
{
  "metadata": {
    "workflow": "infographic"
  }
}
```

- `legacy`: 静态图片工作流
- `shot`: Seedance 视频工作流
- `infographic`: Remotion 动态信息图工作流

省略时按脚本结构自动推断。

## 成本追踪

每次运行会自动记录 API 调用成本，输出到 `projects/<name>/logs/cost.json`。

Seedream 图片生成按分辨率计费：

| 分辨率 | 单张价格 |
|--------|----------|
| ≤ 236 万像素 | 0.30 元 |
| > 236 万像素 | 0.60 元 |

Seedance 视频约 0.172 元/秒（720p）。

Remotion 信息图工作流主要成本为 Seedream 图片，渲染本身使用本地算力。

Edge TTS 免费，成本记为 0。

## 开发检查

```bash
uv run ruff check packages/
uv run mypy packages/
cd remotion && npm run lint
```

## 注意事项

- 图片生成调用 Seedream API，需要确保 `SEEDREAM_MODEL` 和 `SEEDREAM_BASE_URL` 与你的火山方舟账号一致。
- Remotion 信息图工作流需要 Node.js 环境。
- 新增视频项目时，复制 `projects/example-proj/` 目录并重命名即可，所有中间产物相互隔离。
