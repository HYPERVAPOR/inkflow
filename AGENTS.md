# InkFlow Agent Guide

指导 AI Agent 使用和维护 InkFlow 视频生成项目。

## 项目定位

InkFlow 根据 `script.json` 自动生成画面、配音、字幕，输出 `output/final.mp4`。

- 画面首帧：Seedream（火山方舟）
- 视频片段：Seedance（火山方舟）
- TTS：Edge TTS（免费，默认）/ 火山引擎 TTS（可选）
- 合成：FFmpeg
- 成本：每次运行写入 `logs/cost.json`

## 快速开始

```bash
uv sync
uv run python main.py projects/example-proj
```

## 目录结构

```text
inkflow/
├── main.py                 # CLI 入口
├── src/                    # 核心代码
├── projects/               # 视频项目目录
│   ├── example-proj/       # 唯一被 git 跟踪的模板
│   │   ├── visual-reference.png   # 该项目的画风参考图
│   │   ├── scripts/
│   │   ├── assets/
│   │   │   ├── images/     # Seedream 生成的首帧图
│   │   │   ├── videos/     # Seedance 生成的视频片段
│   │   │   ├── audio/      # TTS 生成的配音
│   │   │   ├── subtitles/  # SRT 字幕文件
│   │   │   └── music/      # BGM
│   │   ├── output/
│   │   └── logs/
│   └── lobotomy/           # 其他视频项目（被 .gitignore 忽略）
│       ├── visual-reference.png   # 该项目的画风参考图
│       ├── scripts/
│       ├── assets/
│       ├── output/
│       └── logs/
├── pyproject.toml
├── .env.example
└── AGENTS.md
```

每个视频一个 `projects/<name>/` 目录，各项目为同级目录。其余项目被 `.gitignore` 忽略。

每个项目根目录下必须放置 `visual-reference.png`，作为该项目全局画风参考图。所有首帧图生成都会以该图为参考，确保全片画风统一。

## 核心文件

| 文件                          | 职责                             |
| ----------------------------- | -------------------------------- |
| `src/config.py`               | 环境变量与项目路径               |
| `src/models.py`               | `script.json` 数据模型           |
| `src/image_generator.py`      | Seedream 图片生成（legacy 流程） |
| `src/shot_frame_generator.py` | Seedream 首帧图生成（shot 流程） |
| `src/video_generator.py`      | Seedance 视频片段生成            |
| `src/tts_generator.py`        | TTS 生成（Edge TTS / 火山 TTS）              |
| `src/subtitle_generator.py`   | SRT 字幕                         |
| `src/video_assembler.py`      | FFmpeg 合成                      |
| `src/pipeline.py`             | 流程编排                         |
| `src/cost_tracker.py`         | 成本追踪                         |

## 常用命令

```bash
# 生成视频
uv run python main.py projects/example-proj

# 分步调试
uv run python main.py projects/example-proj --step images|audio|subtitles|video

# 指定 BGM
uv run python main.py projects/example-proj --bgm /path/to/music.mp3
```

## 工作流

InkFlow 支持两种工作流，按 `script.json` 自动选择：

### Shot 级视频工作流（推荐）

当 `script.json` 同时包含 `shots` 数组且 `scenes` 中的 `shot_id` 被赋值时启用：

1. **写剧本**：先写纯文本旁白，再划分 shot。
2. **TTS 生成**：为每句台词生成音频，得到实际时长。
3. **计算 shot 时长**：把属于同一 shot 的台词时长相加，向上取整，作为 Seedance 生成该段视频的目标时长（单段上限 12 秒）。
4. **生成首帧图**：用 Seedream 为每个 shot 生成首帧，参考全局 `visual-reference.png`。
5. **生成视频**：用 Seedance 以首帧图为输入，生成无声视频片段。
6. **合成**：把各 shot 视频按 shot 总时长裁剪/循环，拼接画面，再拼接 scene 音频，合并后加字幕与 BGM。

### Legacy 图片工作流

当 `script.json` 没有 `shots` 数组或 scene 没有 `shot_id` 时启用：

1. 为每个 scene 生成一张 Seedream 图片。
2. TTS 生成音频。
3. 按 scene 拼接图片与音频，生成最终视频。

## script.json 格式

### Shot 级视频工作流示例

```json
{
  "scenes": [
    {
      "scene_id": 1,
      "subtitle": "旁白文本",
      "shot_id": 1,
      "duration_hint": 3
    }
  ],
  "shots": [
    {
      "shot_id": 1,
      "start_frame_prompt": "首帧画面内容描述，中文，不写风格",
      "video_motion_prompt": "视频运动与变化描述，中文，不写风格",
      "use_reference_image": false,
      "reference_from": null,
      "hold_video": false
    }
  ],
  "metadata": {
    "title": "标题",
    "resolution": "1920x1080",
    "aspect_ratio": "16:9",
    "fps": 24,
    "style_prompt": "手绘简约漫画风格，白色背景",
    "music_mood": "tense",
    "music_source": "stock",
    "tags": ["标签1", "标签2"],
    "cover_image": {
      "prompt": "封面画面内容描述，与视频主题呼应，不写风格",
      "text": "一句吸引点击的文案，不要和标题重复"
    },
    "voice": { "voice_id": "zh-CN-YunxiNeural", "speed": 1.0, "emotion": "neutral" },
    "subtitle_style": {
      "FontName": "Noto Sans CJK SC",
      "FontSize": 32,
      "PrimaryColour": "&HFFFFFF&",
      "OutlineColour": "&H000000&",
      "Outline": 2,
      "Alignment": 2,
      "MarginV": 40
    },
    "burn_subtitles": true,
    "video_model": "doubao-seedance-1-0-pro-250528",
    "video_resolution": "720p",
    "video_watermark": false,
    "video_system_prompt": "传统手绘动画风格，拍二动画，低帧率，断奏动作，可见的铅笔纹理，粗线条艺术，逐帧美感"
  }
}
```

### 字段说明

#### Scene

| 字段            | 说明                                        |
| --------------- | ------------------------------------------- |
| `scene_id`      | 全局唯一序号                                |
| `subtitle`      | 旁白/字幕文本                               |
| `shot_id`       | 所属 shot，启用 shot 工作流时必填           |
| `duration_hint` | 预估时长，TTS 失败时回退使用                |
| `voice`         | 可选，单独覆盖 `metadata.voice` 的 TTS 配置（`voice_id`、`speed`、`emotion`、`provider`） |

#### Shot

| 字段                  | 说明                                                |
| --------------------- | --------------------------------------------------- |
| `shot_id`             | 全局唯一序号                                        |
| `start_frame_prompt`  | Seedream 首帧图内容描述，只描述画面内容，不写风格   |
| `video_motion_prompt` | Seedance 视频运动描述，描述镜头/主体/环境如何动起来 |
| `use_reference_image` | 是否参考上一 shot 的首帧                            |
| `reference_from`      | 参考来源， `"prev"` 或具体 `shot_id`                |
| `hold_video`          | 复用上一 shot 的视频片段                            |

#### Metadata

| 字段               | 说明                                                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| `title`            | 视频标题                                                                                                     |
| `resolution`       | 输出分辨率，如 `1920x1080`                                                                                   |
| `aspect_ratio`     | Seedance 比例参数，如 `16:9`、`9:16`                                                                         |
| `tags`             | 视频标签数组，用于分类、检索和平台发布，如 `["自我提升", "习惯"]`                                            |
| `cover_image`      | 封面图配置，`prompt` 用于生成 4:3 横封面，`text` 为叠加在封面上的文案（需与标题有差异）                      |
| `voice`            | 全局 TTS 配音配置；默认 provider 为 `edge_tts`，可在 `.env` 切换为 `volcano` |
| `video_model`      | Seedance 模型名，默认 `doubao-seedance-1-0-pro-250528`；可在 `.env` 通过 `SEEDANCE_MODEL` 改新建脚本的默认值 |
| `video_resolution` | **固定为 `720p`**，当前工作流不支持更高分辨率，用于控制成本                                                  |
| `video_watermark`  | 是否带水印，默认 `false`                                                                                     |
| `video_system_prompt` | 系统级视频风格提示词，自动追加到每条 `start_frame_prompt`、`video_motion_prompt`、封面图和 legacy `image_prompt` 前面，用于统一全片动画风格 |

#### 封面图 `cover_image`

- 用 Seedream 单独生成一张 **4:3 横封面**（1440x1080），风格和参考图与正片保持一致。
- 从横封面中心裁剪出一张 **3:4 竖封面**。
- 程序会在两张封面上居中叠加 `cover_image.text`，白字黑边，自动换行。
- `text` 不要与 `title` 重复，建议写成引发好奇的短句。
- 产物保存在项目 `assets/images/`：`cover_horizontal_text.png`、`cover_vertical_text.png`。

## 视频脚本编写准则

核心原则与详细范本见 [`docs/script-instruction.md`](docs/script-instruction.md)。下面是快速要点：

### 1. 时长与钩子

- 目标时长：≥2 分钟，信息密度高。
- **黄金 3 秒**：第一句必须抛钩子，激发好奇心，吊胃口。
- 常用钩子方向：反常识冲突、反直觉提问、第二人称假设、悖论式答案、痛点共鸣、悬念预告。
- 详细范本（含《一面镜子》《火车撞你》《变成霸王龙》《老一辈怕笑话》四个案例）见 `docs/script-instruction.md` 第 2 章。

### 2. 字幕与台词

- 每句不要太长，一口气读完。
- 一屏一句，不要堆长段落。
- 口语化，像对朋友讲故事。
- **字幕结尾不要加句号**，保持干净、利落，符合短视频平台习惯。

### 3. 画面节奏

- 每个 scene 停留 2.5-4 秒。
- 每个 shot 总时长不要超过 12 秒（Seedance 单段上限）。
- 可以把 2-4 句相关台词合并到一个 shot，避免 PPT 式切换。
- 每句台词对应具体视觉意象。

### 4. 画幅

- 知识/叙事类：横屏 `1920x1080`（16:9）。
- 短平快/强情绪类：竖屏 `1080x1920`（9:16）。

### 5. 脚本创作流程（分四步 + 用户审阅）

脚本不是一次性写成最终 `script.json`，而是分步完成，确保画面、运动与叙事上下文一致。完整流程与 shot 策略见 `docs/script-instruction.md` 第 6 章。

**第零步：输出纯文本脚本供用户审阅（新增）**

在写 `script.json` 之前，先交付一份只有台词文本的纯文本脚本：

- 文件路径：`projects/<name>/scripts/script_text.md`
- 内容只包含旁白/字幕文本，每句一行，不标注时间戳，不写 `start_frame_prompt` 或 `video_motion_prompt`。
- 目标时长 2 分钟以上，信息密度高，钩子前置。
- **必须等用户确认文本后，再继续下一步。**

> **为什么这样做**：画面和运动提示词生成成本高、修改麻烦。如果台词本身方向不对，越早返工成本越低。纯文本审阅是防止"生成完才发现故事不对"的关键防线。

**第一步：纯文本剧本**

用户确认 `script_text.md` 后，将其转换为 `script.json` 的 `scenes` 数组：

- 每一句台词对应一个 `scene`。
- 只填 `scene_id`、`subtitle`、`duration_hint`，**不写 `start_frame_prompt` 或 `video_motion_prompt`**。
- 暂时不决定 shot 划分。

**第二步：划分 shot**

根据画面连续性与节奏，把 scene 分组为 shot。原则：

- 同一空间、同一主体、同一情绪弧的连续台词放进一个 shot。
- 每个 shot 总时长按 `duration_hint` 估算，控制在 12 秒以内。
- 转场、换主体、换情绪时切新 shot。

**第三步：跑 TTS 拿到真实时间序列**

写完 shot 分组和台词后，先跑音频：

```bash
uv run python main.py projects/<name> --step audio
```

跑完后查看 `logs/script_with_duration.json`，得到每句台词的真实秒数。然后：

- 把同一 shot 下所有 scene 的 `actual_duration` 相加，得到真实 shot 时长。
- 如果某个 shot **超过 12 秒**，必须拆 shot 或精简台词。
- 把真实时长写回 `script.json` 的 `duration_hint`，方便下次直接读取。

> **必须做这一步**：`duration_hint` 只是估算，TTS 真实时长可能更长。如果不先验证，Seedance 生成 12 秒视频后，后面合成时只能靠循环/裁剪硬对齐，效果会变差。

**第四步：补全画面与运动提示词**

确认 shot 分组和时长都 OK 后，再补全 `start_frame_prompt` 和 `video_motion_prompt`：

| 策略             | 字段                                                  | 说明                                                                                                                                                                                             |
| ---------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **复用视频片段** | `hold_video: true`                                    | 当前 shot 与上一 shot 画面几乎不变，只换台词，复用同一段视频。                                                                                                                                   |
| **全新 shot**    | `use_reference_image: false`, `hold_video: false`     | 需要全新的视觉意象。                                                                                                                                                                             |
| **图生图参考**   | `use_reference_image: true`, `reference_from: "prev"` | 当前 shot 与上一 shot 在视觉上有**关联性或连续性**，例如同一人物换表情、同一场景加物件、同一空间换机位。参考指令要明确写出变化，如"给这张图片增加一个穿白大褂的男人"、"让这个人露出开心的表情"。 |

判断 shot 策略时要考虑前后 2-3 句的上下文，避免同一人物或场景被反复切镜头。

### 6. 画面提示词语言与内容

完整规范见 `docs/script-instruction.md` 第 7 章。

#### 语言

- 所有 `start_frame_prompt` 和 `video_motion_prompt` 默认**用中文撰写**，如果用户要求，则使用英文。

#### 内容

- `start_frame_prompt` 只描述**首帧画面内容**：主体、动作、场景、构图、情绪。
- `video_motion_prompt` 只描述**运动**：镜头怎么动、主体怎么动、环境如何变化。
- **禁止**在提示词里写风格词，例如“涂鸦风格”“手绘”“线条画”“油画”“写实”“卡通”“白色背景”“电影感镜头”等。
- 画风、笔触、色调、背景质感由 `metadata.style_prompt` 和项目根目录的 `visual-reference.png` 统一控制，避免单句提示词覆盖全局画风。
- 参考上一张图时，提示词只需说明“发生了什么变化”，同样不写风格。

### 7. 画面复用与参考

#### 全局画风参考图 `visual-reference.png`

- 每个项目根目录下必须放置 `visual-reference.png`。
- **所有首帧图默认都是图生图**：生成任何 shot 的首帧时，都会把 `visual-reference.png` 作为参考图传入 Seedream，确保全片画风统一。
- 如果项目目录下没有 `visual-reference.png`，会 fallback 为不带参考图生成，并打印 warning。

#### `hold_video` 与 `use_reference_image`

- `hold_video: true`：当前 shot 复用上一 shot 的视频片段，不再调用 Seedance。
- `use_reference_image: true` + `reference_from: "prev"`：当前 shot 的首帧需要与上一张图保持**视觉连续性**（如人物换表情、同场景加物件）。此时会用上一张图覆盖全局画风参考图，优先保证画面连续性。
- 不依赖上一张图的 shot 会并发生成，提升效率；依赖 `prev` 的 shot 按顺序串行生成。
- 并发数通过环境变量 `SEEDREAM_MAX_WORKERS` 配置，默认 `32`。Seedream 文档标注的限流为 **500 IPM（张 / 分钟）**，可根据网络情况和账号配额调整，但不要超过该上限。
- 画面规划完成后，再生成最终 `script.json`。

### 8. Seedance 视频并发

根据 Seedance 官方文档：

| 限制项     | 上限 |
| ---------- | ---- |
| 最大并发数 | 10   |
| 最大 RPM   | 600  |

- 并发数通过环境变量 `SEEDANCE_MAX_WORKERS` 配置，默认 `10`。
- 超过 10 个任务会进入排队状态，不会失败。
- 如果账号配额更高，可以调大；否则保持默认。

### 8. 去水印

- `src/shot_frame_generator.py` 调用 Seedream API 时已传入 `"watermark": false`。
- `src/video_generator.py` 调用 Seedance API 时已传入 `"watermark": false`。
- 无需后处理，生成即无水印。
- 若某些模型仍返回水印，再考虑增加后处理。

## TTS 配置

InkFlow 支持两种 TTS 后端，通过环境变量或 `script.json` 中的 `voice.provider` 切换。

| Provider | 说明 | 配置项 |
| -------- | ---- | ------ |
| `edge_tts` | 免费、无需密钥，默认 | `TTS_VOICE`、`TTS_SPEED` |
| `volcano` | 火山引擎豆包/Seed 语音合成 | `VOLCANO_TTS_API_KEY`（新版控制台，默认 v3）<br>或 `VOLCANO_TTS_APP_ID` + `VOLCANO_TTS_ACCESS_TOKEN` + `VOLCANO_TTS_CLUSTER`（旧版控制台，可切 v1）<br>`VOLCANO_TTS_BASE_URL`、`VOLCANO_TTS_VOICE`、`VOLCANO_TTS_RESOURCE_ID` |

切换全局 provider：

```bash
# .env
TTS_PROVIDER=volcano

# 新版 BytePlus Speech Console：默认 v3 接口
VOLCANO_TTS_API_KEY=your_api_key

# 旧版 Speech Console：切换到 v1 接口
# VOLCANO_TTS_BASE_URL=https://openspeech.bytedance.com/api/v1/tts
# VOLCANO_TTS_APP_ID=your_app_id
# VOLCANO_TTS_ACCESS_TOKEN=your_access_token
# VOLCANO_TTS_CLUSTER=volcano_tts

VOLCANO_TTS_VOICE=zh_male_aojiaobazong_moon_bigtts
```

也可以在 `metadata.voice` 或单条 `scene.voice` 中指定 `provider: "volcano"`，实现混合使用。

已验证的中文音色示例（v3 / `seed-tts-2.0`，后缀 `_uranus_bigtts`）：

- `zh_male_dayi_uranus_bigtts`（大壹 2.0）
- `zh_female_vv_uranus_bigtts`（Vivi 2.0）
- `zh_female_cancan_uranus_bigtts`（知性灿灿 2.0）
- `zh_female_sajiaoxuemei_uranus_bigtts`（撒娇学妹 2.0）
- `zh_female_wenroushunv_uranus_bigtts`（温柔淑女 2.0）
- `zh_female_gufengshaoyu_uranus_bigtts`（古风少御 2.0）
- `zh_male_zhuangzhou_uranus_bigtts`（庄周 2.0）
- `zh_male_kailangdidi_uranus_bigtts`（开朗弟弟 2.0）
- `zh_male_fanjuanqingnian_uranus_bigtts`（反卷青年 2.0）
- `zh_male_youyoujunzi_uranus_bigtts`（悠悠君子 2.0）
- `zh_male_sunwukong_uranus_bigtts`（猴哥 2.0）

若使用 v1（`volc.service_type.10029`），音色后缀需为 `_moon_bigtts`，例如 `zh_male_aojiaobazong_moon_bigtts`。

生成所有音色的试听样本：

```bash
PYTHONPATH=. uv run python scripts/generate_volcano_voice_samples.py
```

输出到 `output/volcano_voice_samples/`。

## 成本

### Seedream 首帧图

| 分辨率       | 价格       |
| ------------ | ---------- |
| ≤ 236 万像素 | 0.30 元/张 |
| > 236 万像素 | 0.60 元/张 |

### Seedance 视频（无声）

当前工作流**只使用 720p** 以控制成本。以 `doubao-seedance-1-0-pro-250528` 估算：

| 分辨率 | 约 5 秒价格 | 约每秒价格 |
| ------ | ----------- | ---------- |
| 720p   | 0.86 元     | 0.172 元   |

实际成本优先以 API 返回的 `completion_tokens` 为准；否则按 720p × 时长估算。

Edge TTS 免费。成本写入 `logs/cost.json`。

## 代码规范

- Python ≥3.10
- `uv run ruff check src main.py`
- `uv run mypy src main.py`

## 注意事项

1. 所有路径通过 `Config(project_dir)` 获取，不要写死。
2. 新增模块放 `src/`，使用相对导入。
3. 不要硬编码 API Key。
4. 产物必须写入项目目录的 `assets/`、`output/`、`logs/`，禁止写根目录。
5. 不要提交 `.env`。
6. 不要提交 `projects/` 下除 `example-proj` 外的目录。
7. 不要擅自执行 `git commit` / `git push`。

## 验证改动

```bash
uv run python -m py_compile main.py src/*.py
uv run ruff check src main.py
uv run python main.py projects/example-proj
```
