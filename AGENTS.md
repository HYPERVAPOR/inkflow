# InkFlow Agent Guide

InkFlow 根据 `script.json` 生成画面、配音、字幕，输出 `output/final.mp4`。

- 首帧图：Seedream（火山方舟）
- 视频片段：Seedance（火山方舟）
- 配音：Edge TTS（默认）/ 火山 TTS
- 合成：FFmpeg

## 目录结构

```
projects/<name>/
  visual-reference.png      # 全局画风参考，必需
  scripts/script.json       # 剧本
  scripts/script_text.md    # 纯文本台词（审阅用）
  assets/{images,videos,audio,subtitles,music}/
  output/                   # 最终视频
  logs/                     # cost.json / subtitles_with_duration.json
```

## script.json 结构

`script.json` 只有三个顶层对象：`metadata`、`subtitles`、`shots`。

```json
{
  "metadata": {
    "title": "标题",
    "width": 1920,
    "height": 1080,
    "aspect_ratio": "16:9",
    "fps": 30,
    "style_prompt": "全局画风描述",
    "video_system_prompt": "追加到所有画面/视频提示词前的系统风格词",
    "burn_subtitles": false,
    "cover_image": { "prompt": "", "text": "封面文案" },
    "tags": ["情感", "心理学"]
  },
  "subtitles": [
    { "subtitle_id": 1, "text": "第一句台词", "duration": 2.1 }
  ],
  "shots": [
    {
      "shot_id": 1,
      "subtitle_ids": [1, 2, 3],
      "start_frame_prompt": "首帧画面内容，不写风格",
      "video_motion_prompt": "镜头/主体/环境运动",
      "reference_from": null
    }
  ]
}
```

## 脚本流程

1. 写 `scripts/script_text.md`（纯台词，每句一行），用户确认。
2. 跑 TTS：`uv run python main.py projects/<name> --step audio`，生成 `logs/subtitles_with_duration.json`。
3. 根据真实时长划分 shot，每个 shot 对应一个或多个 subtitle，总时长 2–5s，超过 5s 需说明理由，超过 12s 视为节奏失败。
4. 写 `script.json`：`metadata` + `subtitles`（含 `actual_duration`）+ `shots`（含 `subtitle_ids`）。
5. **成本审计**：首帧 `shot数×0.3` + 视频 `总时长×0.172` + TTS。>50 CNY 需用户确认。
6. 补全 `shots` 提示词，用户确认。
7. 生成首帧、视频、字幕，合成最终视频。

## 提示词规范

- 用中文。
- `start_frame_prompt` 只描述首帧内容；`video_motion_prompt` 只描述运动。
- 禁止写风格词（手绘、写实、电影感、白色背景等）。
- 画风由 `metadata.style_prompt` + `visual-reference.png` 统一控制。
- 参考上一 shot 时只写变化，不写风格。

## TTS

默认从 `.env` 读取语音配置（`TTS_PROVIDER` / `TTS_VOICE` / `TTS_SPEED`）。
`script.json` 里可以省略 `voice`，如需单独覆盖再写：

```json
"voice": { "provider": "volcano", "voice_id": "zh_male_dayi_uranus_bigtts", "speed": 1.2 }
```

## 成本

- Seedream 首帧：0.3 元/张（≤236 万像素）
- Seedance 720p：0.172 元/秒
- Edge TTS：免费

## 常用命令

```bash
uv run python main.py projects/<name>              # 完整流程
uv run python main.py projects/<name> --step audio # 仅 TTS
uv run ruff check src main.py
```
