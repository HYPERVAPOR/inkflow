# InkFlow

AI 视频生成 Workflow。

根据项目目录下的 `script.json` 自动生成画面、配音、字幕，并合成最终视频。

每个视频对应一个独立的项目目录，方便同时管理多个视频。

## 快速开始

### 1. 安装依赖

本项目使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

```bash
# 创建虚拟环境并安装依赖
uv sync

# 进入虚拟环境
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

同时需要安装 [FFmpeg](https://ffmpeg.org/download.html) 并确保在 PATH 中。

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的火山方舟 API Key 和图片单价：

```bash
ARK_API_KEY=your_api_key_here
SEEDREAM_PRICE_PER_IMAGE=0.002
```

TTS 使用 Edge TTS，完全免费，无需额外配置。

### 3. 准备项目

每个视频是一个独立的项目目录，结构如下：

```text
projects/example-proj/
├── scripts/
│   └── script.json         # 视频脚本
├── assets/
│   ├── images/             # 生成的画面
│   ├── audio/              # 生成的配音
│   ├── music/              # 背景音乐（可选）
│   └── subtitles/          # 生成的字幕
├── output/                 # 最终视频
└── logs/                   # 运行日志
```

示例项目已放在 `projects/example-proj/`，可直接使用或复制一份改名字：

```bash
cp -r projects/example-proj projects/my_video
```

每个 scene 包含：
- `subtitle`: 旁白/字幕文本
- `image_prompt`: 画面内容提示词
- `use_reference_image`: 是否参考上一张图保持连续性
- `voice`: TTS 音色配置

全局风格词写在 `metadata.style_prompt` 中，会自动注入到每个画面的生成提示词里。

### 4. 生成视频

```bash
uv run python main.py projects/example-proj
```

运行结束后会生成成本报告：`projects/example-proj/logs/cost.json`。

> 提示：连续几句描述同一画面时，可在 scene 中设置 `"hold_image": true` 复用上一张图，节省成本并避免画面切换过快。详见 `AGENTS.md`。

#### 添加背景音乐

把背景音乐放到 `projects/example-proj/assets/music/bgm.mp3`，会自动使用。

或手动指定：

```bash
uv run python main.py projects/example-proj --bgm projects/example-proj/assets/music/background.mp3
```

#### 分步调试

```bash
uv run python main.py projects/example-proj --step images
uv run python main.py projects/example-proj --step audio
uv run python main.py projects/example-proj --step subtitles
uv run python main.py projects/example-proj --step video
```

#### 使用已安装的 CLI

```bash
uv run inkflow projects/example-proj
```

## 项目结构

```text
.
├── main.py                 # CLI 入口
├── src/                    # 核心代码
│   ├── config.py           # 项目目录与全局配置
│   ├── models.py           # script.json 数据模型
│   ├── script_loader.py    # 脚本加载/保存
│   ├── image_generator.py  # Seedream 图片生成
│   ├── tts_generator.py    # Edge TTS 语音生成
│   ├── subtitle_generator.py  # SRT 字幕生成
│   ├── video_assembler.py  # FFmpeg 视频合成
│   ├── pipeline.py         # 流程编排
│   └── cost_tracker.py     # API 成本追踪
├── projects/               # 视频项目目录
│   └── example-proj/
│       ├── scripts/script.json
│       ├── assets/
│       ├── output/
│       └── logs/
├── pyproject.toml
├── .env.example
└── plan.md                 # 完整 workflow 设计文档
```

## 成本追踪

每次运行会自动记录 API 调用成本，输出到 `projects/<name>/logs/cost.json`。

Seedream 图片生成按分辨率计费：

| 分辨率 | 单张价格 |
|--------|----------|
| ≤ 236 万像素 | 0.30 元 |
| > 236 万像素 | 0.60 元 |

例如 `1080x1920`（约 207 万像素）为 **0.30 元/张**。

Edge TTS 免费，成本记为 0。

若 Seedream API 响应中包含 `usage.cost` 或 `usage.total_cost`，会优先使用响应中的实际费用；否则按上述分辨率档位估算。

## 注意事项

- 图片生成调用 Seedream API，需要确保 `SEEDREAM_MODEL` 和 `SEEDREAM_BASE_URL` 与你的火山方舟账号一致。
- `src/image_generator.py` 默认按 OpenAI-compatible 格式解析响应，如 Seedream 实际返回格式不同，请调整 `_call_api` 方法。
- 参考图当前按 scene 顺序串行生成；如要并行化复杂依赖，可扩展 `generate` 中的依赖图逻辑。
- 新增视频项目时，复制 `projects/example-proj/` 目录并重命名即可，所有中间产物相互隔离。
