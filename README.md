# Short Video AI Studio

一个面向短视频创作者的 AI Web MVP：输入文字、图片或视频素材，系统会进行素材理解、引导式追问、生成短视频选题，并输出可直接拍摄的分镜脚本。

当前 UI 是黑橙色 Creator OS 风格，适合做内测演示、开源原型和后续 SaaS 产品迭代。

## Features

- 文字、图片、视频素材输入
- 素材分析和创作机会提取
- 引导式追问，补全目标用户、平台、风格和拍摄限制
- 生成 3-10 个短视频选题
- 根据选题生成拍摄脚本、口播、画面建议和封面方向
- 生成过程带分阶段进度条，避免结果突然出现
- SQLite 本地项目存储和事件日志
- OpenAI / Gemini 模型接入，本地规则兜底
- 可复制或下载 Markdown 脚本
- 附带本地字幕视频生成脚手架

## Quick Start

```bash
git clone <your-repo-url>
cd short-video-ai-studio

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app:app --reload --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

也可以使用 Makefile：

```bash
make install
make dev
```

## Model Setup

没有 API Key 时，项目会使用本地规则兜底，方便先跑通流程。

配置模型：

```bash
cp .env.example .env
```

编辑 `.env`：

```text
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

MAX_UPLOAD_MB=100
```

模型优先级：

1. 配置 `OPENAI_API_KEY` 时优先使用 OpenAI。
2. 没有 OpenAI，但配置了 `GEMINI_API_KEY` 时使用 Gemini。
3. 都没有配置时使用本地规则。

查看当前模型状态：

```bash
curl http://127.0.0.1:8000/api/model-status
```

## Docker

```bash
docker build -t short-video-ai-studio .
docker run --rm -p 8000:8000 --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/uploads:/app/uploads" \
  -v "$(pwd)/output:/app/output" \
  short-video-ai-studio
```

或：

```bash
make docker-build
make docker-run
```

## Data Storage

本地运行时会自动创建：

```text
data/projects.db          项目、问答、选题、脚本和事件日志
uploads/                  用户上传的图片或视频
output/web_projects/      生成出的脚本、视频配置和封面 brief
```

内测时可以备份这三个目录。正式部署时建议升级为：

- 数据库：Postgres / Supabase / Neon
- 文件存储：S3 / Cloudflare R2 / 阿里云 OSS / 腾讯云 COS

## API

常用接口：

```text
GET  /api/health
GET  /api/model-status
POST /api/projects
GET  /api/projects
GET  /api/projects/{project_id}
POST /api/projects/{project_id}/assets
POST /api/projects/{project_id}/analyze
GET  /api/projects/{project_id}/questions/next
POST /api/projects/{project_id}/answers
POST /api/projects/{project_id}/topics
POST /api/projects/{project_id}/scripts
GET  /api/projects/{project_id}/events
```

FastAPI 文档：

```text
http://127.0.0.1:8000/docs
```

## Local Video Pipeline

仓库还包含一个本地短视频自动化生成脚手架：

- `pipeline.py`：从选题生成文案、视频 YAML、即梦任务 YAML 和封面 brief
- `generate_video.py`：用 YAML 渲染 9:16 竖屏 MP4
- `dreamina_batch.py`：调用即梦 Dreamina CLI 批量提交文生视频/图生视频任务

示例：

```bash
python pipeline.py examples/pipeline.yaml
python generate_video.py examples/project.yaml
```

## Development

检查语法：

```bash
make check
```

清理缓存：

```bash
make clean
```

## GitHub Checklist

开源前确认：

- `.env` 没有提交
- `data/`、`uploads/`、`output/` 没有提交
- README 中的仓库地址已替换
- 已选择许可证，当前为 MIT

## License

MIT
