# InkFlow Agent Guide

指导 AI Agent 使用和维护 InkFlow 视频生成项目。

## 项目定位

InkFlow 根据 `script.json` 自动生成画面、配音、字幕，输出 `output/final.mp4`。

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
cd remotion && npm install && cd ..

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
│   │   ├── assets/
│   │   ├── output/
│   │   └── logs/
│   └── ...                  # 其他项目（被 .gitignore 忽略）
├── pyproject.toml           # uv workspace 根配置
├── .env.example
└── AGENTS.md
```

每个视频一个 `projects/<name>/` 目录，各项目为同级目录。其余项目被 `.gitignore` 忽略。

每个项目根目录下必须放置 `visual-reference.png`，作为该项目全局画风参考图。所有首帧图生成都会以该图为参考，确保全片画风统一。

## 核心包

| 包 | 文件 | 职责 |
| --- | --- | --- |
| `inkflow-core` | `config.py` | 环境变量与项目路径 |
| `inkflow-core` | `models.py` | `script.json` 数据模型 |
| `inkflow-core` | `script_loader.py` | 加载/保存 script.json |
| `inkflow-core` | `types.py` | `WorkflowOutput` 等公共类型 |
| `inkflow-generators` | `image/seedream.py` | Seedream 图片生成 |
| `inkflow-generators` | `image/shot_frame.py` | Seedream 首帧图生成 |
| `inkflow-generators` | `video/seedance.py` | Seedance 视频片段生成 |
| `inkflow-generators` | `tts/generator.py` | TTS 生成（Edge / 火山） |
| `inkflow-generators` | `subtitle.py` | SRT 字幕 |
| `inkflow-generators` | `cover.py` | 封面图 |
| `inkflow-generators` | `cost.py` | 成本追踪 |
| `inkflow-workflows` | `base.py` | `Workflow` 抽象与注册表 |
| `inkflow-workflows` | `legacy.py` | Legacy 图片工作流 |
| `inkflow-workflows` | `shot.py` | Shot 级视频工作流 |
| `inkflow-workflows` | `infographic.py` | Remotion 信息图工作流 |
| `inkflow-workflows` | `pipeline.py` | 流程编排 |
| `inkflow-assembly` | `assembler.py` | FFmpeg 合成 |
| `inkflow-remotion` | `composition.py` | 生成 composition.json |
| `inkflow-remotion` | `assets.py` | 准备 Remotion public/ 资源 |
| `inkflow-remotion` | `renderer.py` | 调用 Remotion CLI 渲染 |
| `inkflow-cli` | `main.py` | CLI 入口 |

## 常用命令

```bash
# 生成视频
uv run inkflow projects/example-proj

# 指定脚本
uv run inkflow projects/example-proj --script scripts/script_infographic.json

# 分步调试
uv run inkflow projects/example-proj --step images|audio|subtitles|video

# Python 检查
uv run ruff check packages/
uv run mypy packages/

# Remotion 检查
cd remotion && npm run lint
```

## 工作流

InkFlow 支持三种工作流，按 `metadata.workflow` 或脚本结构自动选择：

### 1. Legacy 图片工作流

当 `metadata.workflow == "legacy"`，或脚本没有 `shots` 数组/scene 没有 `shot_id` 时启用：

1. 为每个 scene 生成一张 Seedream 图片。
2. TTS 生成音频。
3. 按 scene 拼接图片与音频，生成最终视频。

### 2. Shot 级视频工作流（推荐）

当 `metadata.workflow == "shot"`，或脚本同时包含 `shots` 数组且 `scenes` 中的 `shot_id` 被赋值时启用：

1. TTS 生成音频。
2. 计算 shot 真实时长。
3. Seedream 生成首帧图。
4. Seedance 生成无声视频片段。
5. 裁剪/循环拼接视频，合并音频，输出最终视频。

### 3. Infographic 信息图工作流

当 `metadata.workflow == "infographic"` 时启用：

1. TTS 生成音频。
2. Seedream 生成 shot 背景图。
3. Python 生成 `composition.json`，准备 `remotion/public/` 资源。
4. Remotion 按 `composition.json` 渲染每个 shot 的 MP4。
5. FFmpeg 拼接所有 shot 视频与音频，输出最终视频。

信息图工作流大幅减少 Seedance 使用，适合数据展示、图表、文字动效、地图等场景。

## script.json 格式

### 工作流选择

```json
{
  "metadata": {
    "workflow": "infographic"
  }
}
```

`workflow` 可选 `"legacy"`、`"shot"`、`"infographic"`。省略时自动推断。

### Infographic 工作流示例

```json
{
  "metadata": {
    "title": "数据增长故事",
    "resolution": "1080x1920",
    "aspect_ratio": "9:16",
    "fps": 30,
    "style_prompt": "扁平化信息图风格，深蓝背景",
    "workflow": "infographic",
    "remotion": {
      "fps": 30,
      "scale": 1.0,
      "concurrency": 1
    },
    "default_transition": {
      "type": "fade",
      "duration": 0.5
    },
    "voice": { "voice_id": "zh-CN-YunxiNeural", "speed": 1.2 },
    "burn_subtitles": false
  },
  "scenes": [
    { "scene_id": 1, "subtitle": "2023 年用户一千人", "shot_id": 1, "duration_hint": 3 },
    { "scene_id": 2, "subtitle": "2024 年暴涨到一万人", "shot_id": 1, "duration_hint": 3 }
  ],
  "shots": [
    {
      "shot_id": 1,
      "start_frame_prompt": "深蓝背景信息图，数据增长主题",
      "composition": {
        "background": "#0f172a",
        "elements": [
          {
            "id": "title",
            "type": "text",
            "props": { "text": "用户增长", "fontSize": 72, "color": "#ffffff" },
            "layout": { "x": 0, "y": 200, "width": "100%", "height": 120 },
            "animation": { "type": "fade_in", "duration": 0.6 }
          },
          {
            "id": "chart",
            "type": "chart_bar",
            "props": { "data": [1000, 10000], "options": { "colors": ["#60a5fa", "#3b82f6"] } },
            "layout": { "x": 140, "y": 500, "width": 800, "height": 600 },
            "animation": { "type": "draw", "duration": 1.2, "delay": 0.5 }
          }
        ],
        "transition": { "type": "fade", "duration": 0.5 }
      }
    }
  ]
}
```

### 字段说明

#### Scene

| 字段 | 说明 |
| --- | --- |
| `scene_id` | 全局唯一序号 |
| `subtitle` | 旁白/字幕文本 |
| `shot_id` | 所属 shot |
| `duration_hint` | 预估时长，TTS 失败时回退使用 |
| `voice` | 可选，单独覆盖 `metadata.voice` |

#### Shot

| 字段 | 说明 |
| --- | --- |
| `shot_id` | 全局唯一序号 |
| `start_frame_prompt` | Seedream 首帧图内容描述（信息图工作流也需要） |
| `video_motion_prompt` | Seedance 运动描述（仅 shot 工作流） |
| `use_reference_image` | 是否参考上一 shot 的首帧 |
| `reference_from` | 参考来源，`"prev"` 或具体 `shot_id` |
| `hold_video` | 复用上一 shot 的视频片段 |
| `transition_to_next` | 使用下一张首帧作为尾帧（仅 shot 工作流） |
| `composition` | 信息图工作流：Remotion composition 定义 |

#### Shot.composition

| 字段 | 说明 |
| --- | --- |
| `elements` | 元素数组：text、chart_line、chart_bar、chart_pie、map、shape、seedream_image |
| `transition` | shot 结束时的转场：fade / slide / shader / seedance |
| `background` | 背景色或 CSS 背景值 |

#### CompositionElement

| 字段 | 说明 |
| --- | --- |
| `id` | 元素唯一 id |
| `type` | 元素类型 |
| `props` | 元素特定属性 |
| `layout` | 位置/尺寸：`x`、`y`、`width`、`height` |
| `animation` | 动画：`fade_in`、`slide_in`、`scale_in`、`draw`、`grow` |

#### Metadata

| 字段 | 说明 |
| --- | --- |
| `title` | 视频标题 |
| `resolution` | 输出分辨率，如 `1920x1080` |
| `aspect_ratio` | Seedance 比例参数 |
| `workflow` | 工作流：legacy / shot / infographic |
| `remotion` | Remotion 渲染配置 |
| `default_transition` | 默认 shot 转场 |
| `style_prompt` | 全局画风提示词 |
| `video_system_prompt` | 系统级风格提示词 |
| `burn_subtitles` | 是否烧录字幕 |

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

- 每个 scene 停留 2.5-4 秒。
- **每个 shot 尽量控制在 5 秒以内**。
- 每个 shot 总时长不要超过 12 秒（Seedance 单段上限；Remotion 无此限制，但仍建议保持快节奏）。

### 4. 画幅

- 知识/叙事类：横屏 `1920x1080`（16:9）。
- 短平快/强情绪类：竖屏 `1080x1920`（9:16）。

### 5. 脚本创作流程

脚本分步完成，关键步骤完成后向用户报告并等待批准。完整流程见 `docs/script-instruction.md` 第 6 章。

### 6. 画面提示词语言与内容

- `start_frame_prompt` 只描述首帧画面内容，不写风格词。
- 画风由 `metadata.style_prompt` 和 `visual-reference.png` 统一控制。

### 7. 画面复用与参考

- `visual-reference.png` 作为全局画风参考。
- `hold_video` 复用上一 shot 视频。
- `use_reference_image` + `reference_from: "prev"` 保持视觉连续性。

## Remotion 信息图工作流

### 支持的元素

| 类型 | 说明 |
| --- | --- |
| `seedream_image` | 嵌入 Seedream 生成的图片 |
| `text` | 文字，支持淡入/滑入动画 |
| `chart_line` | 折线图 |
| `chart_bar` | 柱状图 |
| `chart_pie` | 饼图 |
| `map` | 地图图片 + 缩放动画 |
| `shape` | 矩形形状 |

### 转场

| 类型 | 说明 |
| --- | --- |
| `fade` | 淡入淡出 |
| `slide` | 滑入滑出，可指定 direction |
| `shader` | WebGL2 shader 特效（mix、cross_zoom、pixelate），默认 swiftshader 保证 headless 稳定 |
| `seedance` | 占位：当前 fallback 到 fade |

### 配置

环境变量：

```bash
REMOTION_DIR=/path/to/remotion          # 默认自动探测
REMOTION_MAX_WORKERS=1                  # 渲染并发
REMOTION_GL=swiftshader                 # headless WebGL 后端
```

## TTS 配置

InkFlow 支持两种 TTS 后端，通过环境变量或 `script.json` 中的 `voice.provider` 切换。

| Provider | 说明 | 配置项 |
| --- | --- | --- |
| `edge_tts` | 免费、无需密钥，默认 | `TTS_VOICE`、`TTS_SPEED` |
| `volcano` | 火山引擎豆包/Seed 语音合成 | `VOLCANO_TTS_API_KEY` 等 |

详见 `.env.example`。

## 成本

### Seedream 首帧图

| 分辨率 | 价格 |
| --- | --- |
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
- Remotion: `cd remotion && npm run lint`

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
uv run python -m py_compile packages/*/src/**/*.py packages/*/*/**/*.py
uv run ruff check packages/
uv run mypy packages/
cd remotion && npm run lint
uv run inkflow projects/example-proj --script scripts/script_infographic.json --step images
```
