# InkFlow Agent Guide

指导 AI Agent 使用和维护 InkFlow 视频生成项目。

## 项目定位

InkFlow 根据项目目录下的脚本自动生成画面、配音、字幕，输出 `output/final.mp4`。

- 画面首帧：Seedream（火山方舟）
- 视频片段：Seedance（火山方舟）/ Remotion 动态信息图
- TTS：Edge TTS（免费，默认）/ 火山引擎 TTS（可选）
- 合成：FFmpeg
- 成本：每次运行写入 `logs/cost.json`

## 快速开始

```bash
# 1. 安装 Python 依赖
uv sync

# 2. 安装 Remotion 依赖（信息图工作流需要 Node.js）
cd remotion && pnpm install && cd ..

# 3. 生成视频
uv run inkflow projects/example-proj
```

## 目录结构

```text
inkflow/
├── packages/                # Python monorepo (uv workspace)
│   ├── inkflow-core/        # 模型、配置、脚本加载、公共类型
│   ├── inkflow-generators/  # Seedream / Seedance / TTS / 字幕 / 封面
│   ├── inkflow-workflows/   # 工作流编排器
│   │   ├── legacy.py        # Legacy 图片工作流
│   │   ├── shot.py          # Shot 级 Seedance 视频工作流
│   │   └── infographic.py   # Remotion 信息图工作流
│   ├── inkflow-assembly/    # FFmpeg 合成
│   ├── inkflow-remotion/    # Python ↔ Remotion 桥接
│   └── inkflow-cli/         # CLI 入口
├── remotion/                # Node.js Remotion 子项目
│   ├── src/
│   │   ├── compositions/    # Infographic、Chart、Map、ShaderTransition 等
│   │   └── lib/             # types、easing、transitions
│   └── public/              # 运行期资源（由 Python 准备）
├── projects/                # 视频项目目录
│   ├── example-proj/        # 唯一被 git 跟踪的模板
│   │   ├── visual-reference.png
│   │   ├── scripts/
│   │   │   ├── script.md    # 默认脚本（推荐，声明式 Markdown 格式）
│   │   │   └── script.json  # JSON 格式脚本（与 script.md 等价）
│   │   ├── assets/
│   │   ├── output/
│   │   └── logs/
│   └── ...                  # 其他项目（被 .gitignore 忽略）
├── pyproject.toml
├── .env.example
└── AGENTS.md
```

每个视频一个 `projects/<name>/` 目录，各项目为同级目录。其余项目被 `.gitignore` 忽略。

每个项目根目录下必须放置 `visual-reference.png`，作为该项目全局画风参考图。所有首帧图生成都会以该图为参考，确保全片画风统一。

## 核心包

| 包                   | 文件                  | 职责                        |
| -------------------- | --------------------- | --------------------------- |
| `inkflow-core`       | `config.py`           | 环境变量与项目路径          |
| `inkflow-core`       | `models.py`           | 脚本数据模型                |
| `inkflow-core`       | `script_loader.py`    | 加载/保存 `script.json` / `script.md` |
| `inkflow-core`       | `types.py`            | `WorkflowOutput` 等公共类型 |
| `inkflow-generators` | `image/seedream.py`   | Seedream 图片生成           |
| `inkflow-generators` | `image/shot_frame.py` | Seedream 首帧图生成         |
| `inkflow-generators` | `video/seedance.py`   | Seedance 视频片段生成       |
| `inkflow-generators` | `tts/generator.py`    | TTS 生成（Edge / 火山）     |
| `inkflow-generators` | `subtitle.py`         | SRT 字幕                    |
| `inkflow-generators` | `cover.py`            | 封面图                      |
| `inkflow-generators` | `cost.py`             | 成本追踪                    |
| `inkflow-workflows`  | `base.py`             | `Workflow` 抽象与注册表     |
| `inkflow-workflows`  | `legacy.py`           | Legacy 图片工作流           |
| `inkflow-workflows`  | `shot.py`             | Shot 级视频工作流           |
| `inkflow-workflows`  | `infographic.py`      | Remotion 信息图工作流       |
| `inkflow-workflows`  | `pipeline.py`         | 流程编排                    |
| `inkflow-assembly`   | `assembler.py`        | FFmpeg 合成                 |
| `inkflow-remotion`   | `composition.py`      | 生成 composition.json       |
| `inkflow-remotion`   | `assets.py`           | 准备 Remotion public/ 资源  |
| `inkflow-remotion`   | `planner.py`          | 声明式 visual 转 composition |
| `inkflow-remotion`   | `renderer.py`         | 调用 Remotion CLI 渲染      |
| `inkflow-cli`        | `main.py`             | CLI 入口                    |

## 常用命令

```bash
# 生成视频（默认使用 script.md，不存在则回退到 script.json）
uv run inkflow projects/example-proj

# 指定脚本
uv run inkflow projects/example-proj --script scripts/script.json

# 分步调试
uv run inkflow projects/example-proj --step images|audio|subtitles|video

# Python 检查
uv run ruff check packages/
uv run mypy packages/

# Remotion 检查
cd remotion && pnpm run lint
```

## 工作流

InkFlow 支持三种工作流，按 `metadata.workflow` 或脚本结构自动选择：

### 1. Legacy 图片工作流

当 `metadata.workflow == "legacy"`，或脚本没有 `shots` 数组时启用：

1. 为每条 `subtitles` 生成一张 Seedream 图片。
2. TTS 生成音频。
3. 按字幕拼接图片与音频，生成最终视频。

### 2. Shot 级视频工作流

当 `metadata.workflow == "shot"`，或脚本包含 `shots` 数组且 shot 带有 `start_frame_prompt` / `video_motion_prompt` 时启用：

1. TTS 生成音频。
2. 计算 shot 真实时长。
3. Seedream 生成首帧图。
4. Seedance 生成无声视频片段。
5. 裁剪/循环拼接视频，合并音频，输出最终视频。

### 3. Infographic 信息图工作流

当 `metadata.workflow == "infographic"` 时启用：

1. TTS 生成音频。
2. `AssetFetcher` 解析 shot 的 `visual.assets`，生成/下载所需图片或视频，并复制到 `remotion/public/`。
3. `VisualPlanner` 根据 `visual.description` + `assets` 自动生成 `composition.json`。
4. Remotion 按 `composition.json` 渲染每个 shot 的 MP4。
5. FFmpeg 拼接所有 shot 视频与音频，输出最终视频。

信息图工作流大幅减少 Seedance 使用，适合数据展示、图表、文字动效、地图等场景。

## 脚本格式

脚本是**声明式**的，只描述“要什么”，不描述“怎么实现”。

顶层结构只有三块：

```json
{
  "metadata": { ... },
  "subtitles": ["..."],
  "shots": [ ... ]
}
```

- `subtitles`: 旁白/字幕文本列表，每条一行。
- `shots`: 连续视觉镜头，每个 shot 通过 `subtitle_indices` 引用字幕行。
- `shots[n].visual`: 用自然语言 `description` 和声明式 `assets` 描述画面。
- Remotion composition、元素布局、动画由 `VisualPlanner` 自动生成，**不由用户手写**。

### Markdown 脚本（推荐）

`script.md` 使用 YAML frontmatter 写 `metadata`，用 `# Shot` 标题划分镜头：

```markdown
---
title: "数据增长故事"
resolution: "1080x1920"
aspect_ratio: "9:16"
fps: 30
style_prompt: "扁平化信息图风格，深蓝背景"
workflow: "infographic"
remotion:
  fps: 30
  concurrency: 1
default_transition:
  type: "fade"
  duration: 0.5
voice:
  voice_id: "zh-CN-YunxiNeural"
  speed: 1.2
burn_subtitles: false
---

# 1
2023 年，我们的用户只有一千人

到了 2024 年，暴涨到一万人

画面：深蓝科技信息图，展示两年用户增长的柱状图，数据标签醒目

素材：
- seedream_image: 深蓝科技感背景，数据增长主题

# 2
2025 年，预计突破十万人

画面：向上箭头与增长曲线，金色预测数据高亮

素材：
- seedream_image: 深蓝色科技感背景，一个向上箭头和增长曲线
```

解析规则：

- `# 1`、`# 2` ... 表示新 shot。
- shot 标题下方到 `画面：` 之前的段落是字幕文本，每段一行字幕。
- `画面：` 段落到 `素材：` 之前是 `visual.description`。
- `素材：` 下方每条 `- type: description` 是一个 `Asset`。

### JSON 脚本

与 Markdown 等价：

```json
{
  "metadata": {
    "title": "数据增长故事",
    "resolution": "1080x1920",
    "aspect_ratio": "9:16",
    "fps": 30,
    "style_prompt": "扁平化信息图风格，深蓝背景",
    "workflow": "infographic",
    "remotion": { "fps": 30, "concurrency": 1 },
    "default_transition": { "type": "fade", "duration": 0.5 },
    "voice": { "voice_id": "zh-CN-YunxiNeural", "speed": 1.2 },
    "burn_subtitles": false
  },
  "subtitles": [
    "2023 年，我们的用户只有一千人",
    "到了 2024 年，暴涨到一万人",
    "2025 年，预计突破十万人"
  ],
  "shots": [
    {
      "shot_id": 1,
      "subtitle_indices": [0, 1],
      "visual": {
        "description": "深蓝科技信息图，展示两年用户增长的柱状图，数据标签醒目",
        "assets": [
          { "id": "bg", "type": "seedream_image", "description": "深蓝科技感背景，数据增长主题" }
        ]
      }
    },
    {
      "shot_id": 2,
      "subtitle_indices": [2],
      "visual": {
        "description": "向上箭头与增长曲线，金色预测数据高亮",
        "assets": [
          { "id": "bg2", "type": "seedream_image", "description": "深蓝色科技感背景，一个向上箭头和增长曲线" }
        ]
      }
    }
  ]
}
```

### 字段说明

#### Subtitle

`subtitles` 数组中的每一项就是一行字幕/旁白文本。

#### Shot

| 字段                | 说明                                                         |
| ------------------- | ------------------------------------------------------------ |
| `shot_id`           | 全局唯一序号                                                 |
| `subtitle_indices`  | 该 shot 对应的字幕行索引列表                                 |
| `visual`            | 视觉描述                                                     |
| `visual.description`| 自然语言画面描述，不写风格词                                 |
| `visual.style`      | 视觉风格提示，默认 `infographic`                             |
| `visual.background` | 可选背景色/背景值                                            |
| `visual.assets`     | 所需素材列表                                                 |
| `transition`        | shot 结束时的转场配置                                        |

#### Asset

| 类型             | 说明                                                         |
| ---------------- | ------------------------------------------------------------ |
| `seedream_image` | 用 Seedream 生成一张图片，基于 `description`                 |
| `image_url`      | 下载网络图片，`url` 必填                                     |
| `video_url`      | 下载网络视频，`url` 必填                                     |
| `local_image`    | 复制本地图片到 Remotion public/，`url` 为相对/绝对路径       |
| `local_video`    | 复制本地视频到 Remotion public/，`url` 为相对/绝对路径       |
| `seedance_video` | 用 Seedance 生成一小段视频（当前未实现）                     |

#### Metadata

| 字段                  | 说明                                |
| --------------------- | ----------------------------------- |
| `title`               | 视频标题                            |
| `resolution`          | 输出分辨率，如 `1920x1080`          |
| `aspect_ratio`        | Seedance 比例参数                   |
| `fps`                 | 输出帧率                            |
| `workflow`            | 工作流：legacy / shot / infographic |
| `remotion`            | Remotion 渲染配置                   |
| `default_transition`  | 默认 shot 转场                      |
| `style_prompt`        | 全局画风提示词                      |
| `video_system_prompt` | 系统级风格提示词                    |
| `burn_subtitles`      | 是否烧录字幕                        |
| `voice`               | 全局 TTS 配置                       |
| `video_model`         | Seedance 模型名（shot 工作流）      |
| `video_resolution`    | 固定 `720p`（shot 工作流）          |

## 视频脚本编写准则

核心原则与详细范本见 [`docs/script-instruction.md`](docs/script-instruction.md)。下面是快速要点：

### 1. 时长与钩子

- 目标时长：≥2 分钟，信息密度高。
- **黄金 3 秒**：第一句必须抛钩子。

### 2. 字幕与台词

- 每句不要太长，一口气读完。
- 一屏一句，不要堆长段落。
- 口语化。
- **字幕结尾不要加句号**。

### 2.1 字幕输出方式

- **默认不将字幕烧录进视频**。
- 字幕以独立 `assets/subtitles/caption.srt` 文件形式输出。
- 只有用户明确要求硬字幕时，才将 `metadata.burn_subtitles` 设为 `true`。

### 3. 画面节奏

- 每个 shot 尽量控制在 5 秒以内。
- shot 总时长不要超过 12 秒（Seedance 单段上限；Remotion 无此限制，但仍建议保持快节奏）。
- 同一空间、同一主体、同一情绪弧的连续台词放进一个 shot。

### 4. 画幅

- 知识/叙事类：横屏 `1920x1080`（16:9）。
- 短平快/强情绪类：竖屏 `1080x1920`（9:16）。

### 5. 脚本创作流程

脚本分步完成，关键步骤完成后向用户报告并等待批准：

1. 写纯文本旁白（Markdown 或 txt）。
2. 划分 shot，确定每句字幕归属。
3. 跑 TTS 拿到真实时长，必要时调整 shot 分组。
4. 成本审计。
5. 补全每个 shot 的 `visual.description` 与 `assets`。

### 6. 画面描述语言

- `visual.description` 只描述画面内容、主体、动作、构图、情绪。
- **禁止**在描述里写风格词，例如“涂鸦风格”“手绘”“线条画”“油画”“写实”“卡通”“白色背景”“电影感镜头”等。
- 画风、笔触、色调、背景质感由 `metadata.style_prompt` 和 `visual-reference.png` 统一控制。

## Remotion 信息图工作流

### VisualPlanner 自动识别

`VisualPlanner` 根据 `visual.description` 关键词自动插入元素：

| 关键词                | 生成的元素    |
| --------------------- | ------------- |
| 柱状图 / bar chart    | `chart_bar`   |
| 折线图 / line chart   | `chart_line`  |
| 饼图 / pie chart      | `chart_pie`   |
| 地图 / map            | `map`         |
| `seedream_image` 素材 | `seedream_image` |
| `video_url` 素材      | `video`       |

字幕文本会自动渲染为底部文字元素。

### 转场

| 类型       | 说明                                                                                 |
| ---------- | ------------------------------------------------------------------------------------ |
| `fade`     | 淡入淡出                                                                             |
| `slide`    | 滑入滑出，可指定 direction                                                           |
| `shader`   | WebGL2 shader 特效（mix、cross_zoom、pixelate），默认 swiftshader 保证 headless 稳定 |
| `seedance` | 占位：当前 fallback 到 fade                                                          |

### 配置

环境变量：

```bash
REMOTION_DIR=/path/to/remotion          # 默认自动探测
REMOTION_MAX_WORKERS=1                  # 渲染并发
REMOTION_GL=swiftshader                 # headless WebGL 后端
```

## TTS 配置

InkFlow 支持两种 TTS 后端，通过环境变量或 `metadata.voice` 切换。

| Provider   | 说明                       | 配置项                   |
| ---------- | -------------------------- | ------------------------ |
| `edge_tts` | 免费、无需密钥，默认       | `TTS_VOICE`、`TTS_SPEED` |
| `volcano`  | 火山引擎豆包/Seed 语音合成 | `VOLCANO_TTS_API_KEY` 等 |

详见 `.env.example`。

## 成本

### Seedream 首帧图

| 分辨率       | 价格       |
| ------------ | ---------- |
| ≤ 236 万像素 | 0.30 元/张 |
| > 236 万像素 | 0.60 元/张 |

### Seedance 视频（无声）

当前 shot 工作流**只使用 720p**。约 0.172 元/秒。

### Remotion 信息图

- Seedream 图片：按张计费
- Remotion 渲染：本地算力，基本无 API 成本
- 适合替代大量 Seedance 片段，显著降低总成本

Edge TTS 免费。成本写入 `logs/cost.json`。

## 代码规范

- Python ≥3.10
- `uv run ruff check packages/`
- `uv run mypy packages/`
- Remotion: `cd remotion && pnpm run lint`

## 注意事项

1. 所有路径通过 `Config(project_dir)` 获取，不要写死。
2. 新增 Python 模块放 `packages/inkflow-<name>/src/inkflow_<name>/`。
3. 新增 Remotion 组件放 `remotion/src/compositions/`。
4. 不要硬编码 API Key。
5. 产物必须写入项目目录的 `assets/`、`output/`、`logs/`，禁止写根目录。
6. 不要提交 `.env`。
7. 不要提交 `projects/` 下除 `example-proj` 外的目录。
8. 不要擅自执行 `git commit` / `git push`。

## 验证改动

```bash
uv run python -m py_compile packages/inkflow-cli/src/inkflow_cli/main.py \
  packages/inkflow-workflows/src/inkflow_workflows/pipeline.py \
  packages/inkflow-assembly/src/inkflow_assembly/assembler.py \
  packages/inkflow-remotion/src/inkflow_remotion/*.py \
  packages/inkflow-generators/src/inkflow_generators/**/*.py \
  packages/inkflow-core/src/inkflow_core/*.py
uv run ruff check packages/
uv run mypy packages/
cd remotion && pnpm run lint
```
