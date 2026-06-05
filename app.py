#!/usr/bin/env python3
"""Web MVP for guided short-video topic and script generation."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from pipeline import build_copy, build_video_project, slugify, write_copy_markdown, write_cover_brief, write_yaml


ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "projects.db"
UPLOAD_DIR = ROOT / "uploads"
PROJECT_DIR = ROOT / "output" / "web_projects"

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

QUESTION_FLOW_BY_LANGUAGE = {
    "zh": [
        {
            "id": "audience",
            "label": "目标用户",
            "question": "这条内容主要拍给谁看？",
            "placeholder": "例如：刚开始做小红书的职场新人 / 想转型的摄影师 / 本地餐饮老板",
        },
        {
            "id": "goal",
            "label": "内容目标",
            "question": "你希望这条视频达成什么结果？",
            "placeholder": "例如：涨粉、引导私信、卖课、种草产品、解释一个观点",
        },
        {
            "id": "platform",
            "label": "发布平台",
            "question": "你准备发到哪个平台？",
            "placeholder": "例如：抖音、小红书、视频号、B站、快手",
        },
        {
            "id": "style",
            "label": "表达风格",
            "question": "你希望视频是什么风格？",
            "placeholder": "例如：口播干货、剧情反转、探店种草、教程拆解、情绪共鸣",
        },
        {
            "id": "constraints",
            "label": "拍摄限制",
            "question": "拍摄时有什么限制或必须出现的元素？",
            "placeholder": "例如：只有手机拍摄、不能露脸、必须出现产品、时长 30 秒内",
        },
    ],
    "en": [
        {
            "id": "audience",
            "label": "Audience",
            "question": "Who is this video mainly for?",
            "placeholder": "Example: new creators on TikTok / local restaurant owners / freelancers changing careers",
        },
        {
            "id": "goal",
            "label": "Content goal",
            "question": "What should this video help you achieve?",
            "placeholder": "Example: gain followers, drive DMs, sell a course, explain a point, promote a product",
        },
        {
            "id": "platform",
            "label": "Platform",
            "question": "Where do you plan to publish it?",
            "placeholder": "Example: TikTok, Instagram Reels, YouTube Shorts, Xiaohongshu, WeChat Channels",
        },
        {
            "id": "style",
            "label": "Style",
            "question": "What kind of delivery style do you want?",
            "placeholder": "Example: talking-head tips, story-driven, product review, tutorial, emotional hook",
        },
        {
            "id": "constraints",
            "label": "Constraints",
            "question": "Any filming limits or must-have elements?",
            "placeholder": "Example: phone only, no face on camera, must show product, under 30 seconds",
        },
    ],
}


app = FastAPI(title="Short Video Studio")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectCreate(BaseModel):
    text: str = ""
    language: str = "zh"


class AnswerRequest(BaseModel):
    question_id: str
    answer: str


class TopicRequest(BaseModel):
    count: int = Field(default=6, ge=3, le=10)
    language: str = "zh"


class ScriptRequest(BaseModel):
    topic: Dict[str, Any]
    language: str = "zh"


class TrialOrderCreate(BaseModel):
    name: str = Field(default="", max_length=80)
    contact: str = Field(..., min_length=2, max_length=120)
    business: str = Field(default="", max_length=120)
    platform: str = Field(default="", max_length=80)
    material: str = Field(..., min_length=4, max_length=1200)
    language: str = "zh"


class TrialOrderUpdate(BaseModel):
    status: str


def normalize_language(language: Optional[str]) -> str:
    return "en" if language == "en" else "zh"


def is_english(project: Dict[str, Any]) -> bool:
    return normalize_language(project.get("language")) == "en"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)


def project_path(project_id: str) -> Path:
    return DATA_DIR / f"{project_id}.json"


def get_db() -> sqlite3.Connection:
    ensure_dirs()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS project_events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_project_id ON project_events(project_id)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trial_orders (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                business TEXT NOT NULL,
                platform TEXT NOT NULL,
                material TEXT NOT NULL,
                language TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                paid_at TEXT,
                delivered_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        for column, column_type in (("paid_at", "TEXT"), ("delivered_at", "TEXT")):
            try:
                connection.execute(f"ALTER TABLE trial_orders ADD COLUMN {column} {column_type}")
            except sqlite3.OperationalError:
                pass
        connection.execute("CREATE INDEX IF NOT EXISTS idx_trial_orders_created_at ON trial_orders(created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_trial_orders_paid_at ON trial_orders(paid_at)")


def migrate_json_projects() -> None:
    init_db()
    for path in DATA_DIR.glob("*.json"):
        project = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(project, dict) or not project.get("id"):
            continue
        with get_db() as connection:
            exists = connection.execute("SELECT 1 FROM projects WHERE id = ?", (project["id"],)).fetchone()
            if exists:
                continue
            connection.execute(
                """
                INSERT INTO projects (id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    project["id"],
                    json.dumps(project, ensure_ascii=False),
                    project.get("created_at") or now_iso(),
                    project.get("updated_at") or now_iso(),
                ),
            )


def log_project_event(project_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    with get_db() as connection:
        connection.execute(
            """
            INSERT INTO project_events (id, project_id, event_type, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                project_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
            ),
        )


def load_project(project_id: str) -> Dict[str, Any]:
    with get_db() as connection:
        row = connection.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row:
        return json.loads(row["data"])

    legacy_path = project_path(project_id)
    if legacy_path.exists():
        project = json.loads(legacy_path.read_text(encoding="utf-8"))
        save_project(project)
        return project
    raise HTTPException(status_code=404, detail="Project not found")


def save_project(project: Dict[str, Any]) -> None:
    project["updated_at"] = project.get("updated_at") or now_iso()
    created_at = project.get("created_at") or now_iso()
    with get_db() as connection:
        connection.execute(
            """
            INSERT INTO projects (id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (
                project["id"],
                json.dumps(project, ensure_ascii=False),
                created_at,
                project["updated_at"],
            ),
        )


def save_trial_order(payload: TrialOrderCreate) -> Dict[str, Any]:
    created_at = now_iso()
    order = {
        "id": uuid.uuid4().hex[:12],
        "name": payload.name.strip(),
        "contact": payload.contact.strip(),
        "business": payload.business.strip(),
        "platform": payload.platform.strip(),
        "material": payload.material.strip(),
        "language": normalize_language(payload.language),
        "amount_cents": 2000,
        "currency": "CNY",
        "status": "new",
        "paid_at": None,
        "delivered_at": None,
        "created_at": created_at,
        "updated_at": created_at,
    }
    with get_db() as connection:
        connection.execute(
            """
            INSERT INTO trial_orders (
                id, name, contact, business, platform, material, language,
                amount_cents, currency, status, paid_at, delivered_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["id"],
                order["name"],
                order["contact"],
                order["business"],
                order["platform"],
                order["material"],
                order["language"],
                order["amount_cents"],
                order["currency"],
                order["status"],
                order["paid_at"],
                order["delivered_at"],
                order["created_at"],
                order["updated_at"],
            ),
        )
    return order


def update_trial_order_status(order_id: str, status: str) -> Dict[str, Any]:
    allowed = {"new", "paid", "delivered", "cancelled"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid order status")
    updated_at = now_iso()
    paid_at_clause = ", paid_at = COALESCE(paid_at, ?)" if status in {"paid", "delivered"} else ""
    delivered_at_clause = ", delivered_at = COALESCE(delivered_at, ?)" if status == "delivered" else ""
    timestamp_params: List[str] = []
    if status in {"paid", "delivered"}:
        timestamp_params.append(updated_at)
    if status == "delivered":
        timestamp_params.append(updated_at)
    with get_db() as connection:
        connection.execute(
            f"""
            UPDATE trial_orders
            SET status = ?, updated_at = ?{paid_at_clause}{delivered_at_clause}
            WHERE id = ?
            """,
            (status, updated_at, *timestamp_params, order_id),
        )
        row = connection.execute(
            """
            SELECT id, name, contact, business, platform, material, language,
                   amount_cents, currency, status, paid_at, delivered_at, created_at, updated_at
            FROM trial_orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Trial order not found")
    return row_to_trial_order(row)


def row_to_trial_order(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "contact": row["contact"],
        "business": row["business"],
        "platform": row["platform"],
        "material": row["material"],
        "language": row["language"],
        "amount_cents": row["amount_cents"],
        "currency": row["currency"],
        "status": row["status"],
        "paid_at": row["paid_at"],
        "delivered_at": row["delivered_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def trial_revenue_summary() -> Dict[str, Any]:
    today = date.today().isoformat()
    with get_db() as connection:
        total_row = connection.execute(
            """
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(CASE WHEN paid_at IS NOT NULL THEN amount_cents ELSE 0 END), 0) AS revenue_cents,
                COALESCE(SUM(CASE WHEN status = 'delivered' THEN amount_cents ELSE 0 END), 0) AS delivered_cents
            FROM trial_orders
            """
        ).fetchone()
        today_row = connection.execute(
            """
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(CASE WHEN paid_at IS NOT NULL THEN amount_cents ELSE 0 END), 0) AS revenue_cents
            FROM trial_orders
            WHERE substr(COALESCE(paid_at, created_at), 1, 10) = ?
            """,
            (today,),
        ).fetchone()
        status_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM trial_orders
            GROUP BY status
            """
        ).fetchall()
    daily_goal_cents = 2000
    today_revenue_cents = int(today_row["revenue_cents"] or 0)
    return {
        "date": today,
        "daily_goal_cents": daily_goal_cents,
        "today_revenue_cents": today_revenue_cents,
        "today_goal_met": today_revenue_cents >= daily_goal_cents,
        "today_order_count": int(today_row["order_count"] or 0),
        "total_order_count": int(total_row["order_count"] or 0),
        "total_revenue_cents": int(total_row["revenue_cents"] or 0),
        "total_delivered_cents": int(total_row["delivered_cents"] or 0),
        "status_counts": {row["status"]: row["count"] for row in status_rows},
    }


def model_provider() -> str:
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "local"


def model_status() -> Dict[str, Any]:
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    return {
        "provider": model_provider(),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "openai_model": openai_model,
        "gemini_model": gemini_model,
    }


def business_config() -> Dict[str, Any]:
    contact = os.getenv("PUBLIC_CONTACT", "").strip()
    payment_note = os.getenv("PUBLIC_PAYMENT_NOTE", "").strip()
    return {
        "trial_price": 20,
        "trial_currency": "CNY",
        "contact": contact,
        "payment_note": payment_note,
        "has_contact": bool(contact),
        "has_payment_note": bool(payment_note),
    }


def safe_json(text: str) -> Optional[Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def call_openai_json(prompt: str, images: Optional[List[Path]] = None) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        content: List[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for image_path in images or []:
            if not image_path.exists():
                continue
            suffix = image_path.suffix.lower().replace(".", "") or "jpeg"
            encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/{suffix};base64,{encoded}",
                }
            )
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            store=False,
            input=[{"role": "user", "content": content}],
        )
        parsed = safe_json(response.output_text)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:  # noqa: BLE001 - model failure should not break local MVP
        return {"_error": str(exc)}


def call_gemini_json(prompt: str) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        parsed = safe_json(response.text or "")
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}


def project_brief(project: Dict[str, Any]) -> str:
    answers = project.get("answers", {})
    english = is_english(project)
    asset_lines = [
        f"- {asset['kind']}：{asset['filename']}（{round(asset['size'] / 1024 / 1024, 2)} MB）"
        for asset in project.get("assets", [])
    ]
    answer_lines = [f"- {key}: {value}" for key, value in answers.items() if value]
    if english:
        return "\n".join(
            [
                f"Original user input: {project.get('text') or 'None'}",
                "Assets:",
                *(asset_lines or ["- None"]),
                "Material summary:",
                project.get("analysis", {}).get("summary", "Not analyzed yet"),
                "User answers:",
                *(answer_lines or ["- None"]),
            ]
        )
    return "\n".join(
        [
            f"用户原始输入：{project.get('text') or '无'}",
            "素材：",
            *(asset_lines or ["- 无"]),
            "素材摘要：",
            project.get("analysis", {}).get("summary", "暂未分析"),
            "用户补充：",
            *(answer_lines or ["- 无"]),
        ]
    )


def fallback_analysis(project: Dict[str, Any]) -> Dict[str, Any]:
    text = project.get("text", "").strip()
    assets = project.get("assets", [])
    if is_english(project):
        kinds = ", ".join(sorted({asset["kind"] for asset in assets})) or "text"
        base = text or "the uploaded material"
        return {
            "summary": f"This short-video material is based on {kinds}. The core clue is: {base[:120]}",
            "opportunities": [
                "Open with the audience's strongest pain point and show the result in the first three seconds.",
                "Turn the material into one clear point instead of covering too much in one video.",
                "Prioritize shootable actions and shots, not only copywriting.",
            ],
            "model": "local",
        }
    kinds = "、".join(sorted({asset["kind"] for asset in assets})) or "文字"
    base = text or "用户上传的素材"
    return {
        "summary": f"这是一个基于{kinds}的短视频创作素材，核心线索是：{base[:120]}",
        "opportunities": [
            "从用户最关心的痛点切入，前三秒直接给结果。",
            "把素材拆成一个明确观点，避免一条视频讲太多。",
            "优先设计可拍的动作和镜头，而不是只生成文案。",
        ],
        "model": "local",
    }


def analyze_project(project: Dict[str, Any]) -> Dict[str, Any]:
    if is_english(project):
        prompt = f"""You are a short-video content strategist. Analyze the user's material and output strict JSON in English.
JSON fields:
summary: material summary under 80 words
opportunities: 3-5 shootable content opportunities
risks: 1-3 content or expression risks

{project_brief(project)}
"""
    else:
        prompt = f"""你是短视频选题策划。请分析下面的用户素材，输出严格 JSON。
JSON 字段：
summary: 80 字以内素材摘要
opportunities: 3-5 条可拍摄机会
risks: 1-3 条内容风险或表达风险

{project_brief(project)}
"""
    image_paths = [
        Path(asset["path"])
        for asset in project.get("assets", [])
        if asset.get("content_type") in IMAGE_TYPES
    ][:3]
    result = call_openai_json(prompt, image_paths) or call_gemini_json(prompt)
    if result and not result.get("_error"):
        result["model"] = model_provider()
        return result
    fallback = fallback_analysis(project)
    if result and result.get("_error"):
        fallback["model_error"] = result["_error"]
    return fallback


def next_question(project: Dict[str, Any]) -> Optional[Dict[str, str]]:
    answered = project.get("answers", {})
    questions = QUESTION_FLOW_BY_LANGUAGE[normalize_language(project.get("language"))]
    for question in questions:
        if not answered.get(question["id"]):
            return question
    return None


def fallback_topics(project: Dict[str, Any], count: int) -> List[Dict[str, str]]:
    answers = project.get("answers", {})
    if is_english(project):
        audience = answers.get("audience") or "target audience"
        goal = answers.get("goal") or "increase attention and conversion"
        style = answers.get("style") or "talking-head tips"
        seed = project.get("text") or project.get("analysis", {}).get("summary", "this material")
        templates = [
            ("Why your videos are not working: the real bottleneck", "Pain-point breakdown", "Start with a common mistake, then give one action viewers can use immediately."),
            ("Use this structure for your next short video", "Tutorial template", "A step-by-step angle makes the video easier to film and easier to save."),
            ("Same material, different angle, very different results", "Contrast angle", "Compare the ordinary version with the optimized version."),
            ("The detail beginners usually miss", "Avoid-this mistake", "A concrete mistake creates instant audience identification."),
            ("If you only have 30 seconds, say it like this", "Minimal script", "Compress the idea into one point, one example, and one action."),
            ("Check these 3 things before you post", "Checklist", "Give viewers a practical checklist they can follow."),
            ("3 shots that make ordinary material look premium", "Filming guide", "Focus on visual action and rhythm so the idea becomes shootable."),
            ("This format works well for driving DMs", "Conversion angle", "Connect the content result to the viewer's next action."),
            ("Explain the issue through one real scene", "Scene story", "Start from a specific situation and lead naturally to the insight."),
            ("Understand this logic, and topic selection gets easier", "Framework", "Good for creators who want to sound more professional."),
        ]
        return [
            {
                "id": f"topic-{index}",
                "title": title,
                "angle": angle,
                "audience": audience,
                "goal": goal,
                "style": style,
                "reason": f"{reason} Material clue: {seed[:48]}",
            }
            for index, (title, angle, reason) in enumerate(templates[:count], start=1)
        ]
    audience = answers.get("audience") or "目标用户"
    goal = answers.get("goal") or "提升关注和转化"
    style = answers.get("style") or "口播干货"
    seed = project.get("text") or project.get("analysis", {}).get("summary", "这个素材")
    templates = [
        ("为什么你一直拍不好？真正卡住的是这一步", "痛点拆解", "先否定常见误区，再给一个马上能执行的方法。"),
        ("把这个方法学会，下一条视频就能直接套", "教程模板", "用步骤化结构降低拍摄难度，适合保存转发。"),
        ("同样的素材，换个角度播放量会差很多", "对比反差", "展示普通拍法和优化拍法的差异。"),
        ("新手最容易忽略的一个细节", "避坑提醒", "用具体错误开场，制造代入感。"),
        ("如果你只有 30 秒，就这样讲清楚", "极简口播", "压缩为一个观点、一个案例、一个行动。"),
        ("别急着发布，先检查这 3 个点", "清单型", "给观众一个可直接照做的检查表。"),
        ("把普通素材拍出高级感的 3 个镜头", "拍摄指导", "强调画面、动作和节奏，让脚本更可拍。"),
        ("这类内容最适合用来引导私信", "转化型", "把内容结果和用户下一步行动绑定。"),
        ("用一个真实场景讲清楚这个问题", "场景故事", "从具体场景进入，再自然引出观点。"),
        ("看懂这个逻辑，你就知道怎么选题了", "方法论", "适合知识博主建立专业感。"),
    ]
    topics = []
    for index, (title, angle, reason) in enumerate(templates[:count], start=1):
        topics.append(
            {
                "id": f"topic-{index}",
                "title": title,
                "angle": angle,
                "audience": audience,
                "goal": goal,
                "style": style,
                "reason": f"{reason} 素材线索：{seed[:48]}",
            }
        )
    return topics


def generate_topics(project: Dict[str, Any], count: int) -> List[Dict[str, str]]:
    if is_english(project):
        prompt = f"""You are a short-video topic strategist. Based on the material and user answers, generate {count} short-video topics in English.
Requirements:
- Each topic must be directly shootable
- Avoid generic advice
- Titles should include conflict, outcome, or action
- Output strict JSON: {{"topics":[{{"id":"topic-1","title":"","angle":"","audience":"","goal":"","style":"","reason":""}}]}}

{project_brief(project)}
"""
    else:
        prompt = f"""你是短视频选题策划。基于素材和用户补充，生成 {count} 个短视频选题。
要求：
- 每个选题必须适合直接拍摄
- 不要泛泛而谈
- 标题要有冲突、结果或行动
- 输出严格 JSON：{{"topics":[{{"id":"topic-1","title":"","angle":"","audience":"","goal":"","style":"","reason":""}}]}}

{project_brief(project)}
"""
    result = call_openai_json(prompt) or call_gemini_json(prompt)
    topics = result.get("topics") if result and not result.get("_error") else None
    if isinstance(topics, list) and topics:
        return topics[:count]
    return fallback_topics(project, count)


def fallback_script(project: Dict[str, Any], topic: Dict[str, Any]) -> Dict[str, Any]:
    answers = project.get("answers", {})
    if is_english(project):
        title = topic.get("title") or "Short-video shooting script"
        audience = topic.get("audience") or answers.get("audience") or "target audience"
        style = topic.get("style") or answers.get("style") or "talking-head tips"
        goal = topic.get("goal") or answers.get("goal") or "get viewers to save and follow"
        scenes = [
            {
                "time": "0-3s",
                "shot": "Face the camera or show a close-up of the material. Put the key point in large subtitles.",
                "voiceover": f"The biggest mistake for {audience} is not filming badly. It is failing to show the result first.",
                "visual": "Quickly show the most conflicting or result-oriented part of the material.",
            },
            {
                "time": "3-10s",
                "shot": "Cut to an operation shot, example screenshot, or handheld prop.",
                "voiceover": f"This video focuses on one thing: {topic.get('angle', 'making one issue easy to understand')}.",
                "visual": "Use one example to prove the problem exists. Avoid long background explanation.",
            },
            {
                "time": "10-22s",
                "shot": "Three-part sequence: wrong way, better way, result comparison.",
                "voiceover": "Say what the viewer will get, give one action, then explain what changes when they use it.",
                "visual": "Show step 1, 2, and 3 on screen.",
            },
            {
                "time": "22-30s",
                "shot": "Return to the person or core material and close with confidence.",
                "voiceover": f"If your goal is {goal}, use this structure for your next video. Save it before filming.",
                "visual": "Keep the title and next action on the final frame.",
            },
        ]
        return {
            "title": title,
            "hook": scenes[0]["voiceover"],
            "format": style,
            "duration": "30 seconds",
            "shooting_notes": [
                "Each shot should express only one information point.",
                "The first three seconds must show a result or conflict.",
                "Visual action matters more than abstract explanation.",
            ],
            "scenes": scenes,
            "cover": {
                "title": title[:28],
                "subtitle": topic.get("angle", "One idea, clearly filmed"),
            },
            "markdown": "",
        }
    title = topic.get("title") or "短视频拍摄脚本"
    audience = topic.get("audience") or answers.get("audience") or "目标用户"
    style = topic.get("style") or answers.get("style") or "口播干货"
    goal = topic.get("goal") or answers.get("goal") or "让用户收藏并关注"
    scenes = [
        {
            "time": "0-3s",
            "shot": "正对镜头或素材特写，字幕大字压住重点。",
            "voiceover": f"{audience}最容易踩的坑，不是不会拍，而是开头没有先给结果。",
            "visual": "快速展示素材中最有冲突或最有结果感的画面。",
        },
        {
            "time": "3-10s",
            "shot": "切到操作画面、案例截图或手持道具。",
            "voiceover": f"这条视频的核心就讲一件事：{topic.get('angle', '把一个问题讲清楚')}。",
            "visual": "用 1 个案例证明问题存在，不要解释太多背景。",
        },
        {
            "time": "10-22s",
            "shot": "三段式分镜：错误做法、正确做法、对比结果。",
            "voiceover": "先说观众会得到什么，再给一个动作，最后告诉他照着做会看到什么变化。",
            "visual": "屏幕上依次出现 1、2、3 三个步骤。",
        },
        {
            "time": "22-30s",
            "shot": "回到人物或核心素材，语气收束。",
            "voiceover": f"如果你的目标是{goal}，下一条就按这个结构拍。先收藏，拍之前再看一遍。",
            "visual": "最后一帧保留标题和行动提示。",
        },
    ]
    return {
        "title": title,
        "hook": scenes[0]["voiceover"],
        "format": style,
        "duration": "30 秒",
        "shooting_notes": [
            "每个镜头只表达一个信息点。",
            "前三秒字幕必须出现结果或冲突。",
            "画面比文案更重要，能拍动作就不要只说概念。",
        ],
        "scenes": scenes,
        "cover": {
            "title": title[:14],
            "subtitle": topic.get("angle", "一条视频讲透"),
        },
        "markdown": "",
    }


def script_to_markdown(script: Dict[str, Any], language: str = "zh") -> str:
    english = normalize_language(language) == "en"
    lines = [
        f"# {script['title']}",
        "",
        f"- {'Format' if english else '形式'}：{script.get('format', '')}",
        f"- {'Duration' if english else '时长'}：{script.get('duration', '')}",
        f"- {'Opening hook' if english else '开头钩子'}：{script.get('hook', '')}",
        "",
        "## Shooting Script" if english else "## 分镜脚本",
    ]
    for scene in script.get("scenes", []):
        lines.extend(
            [
                "",
                f"### {scene.get('time', '')}",
                f"- {'Shot' if english else '镜头'}：{scene.get('shot', '')}",
                f"- {'Voiceover' if english else '口播'}：{scene.get('voiceover', '')}",
                f"- {'Visual' if english else '画面'}：{scene.get('visual', '')}",
            ]
        )
    notes = script.get("shooting_notes", [])
    if notes:
        lines.extend(["", "## Filming Notes" if english else "## 拍摄提醒"])
        lines.extend([f"- {note}" for note in notes])
    cover = script.get("cover") or {}
    lines.extend(
        [
            "",
            "## Cover Direction" if english else "## 封面建议",
            f"- {'Title' if english else '主标题'}：{cover.get('title', '')}",
            f"- {'Subtitle' if english else '副标题'}：{cover.get('subtitle', '')}",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_script(project: Dict[str, Any], topic: Dict[str, Any]) -> Dict[str, Any]:
    if is_english(project):
        prompt = f"""You are a short-video director. Based on the user's material and selected topic, generate a directly shootable script in English.
Output strict JSON:
{{
  "title":"",
  "hook":"",
  "format":"",
  "duration":"30 seconds",
  "shooting_notes":[""],
  "scenes":[{{"time":"0-3s","shot":"","voiceover":"","visual":""}}],
  "cover":{{"title":"","subtitle":""}}
}}
Requirements: English only, shootable, clear shot breakdown, strong first-three-second hook, no generic advice.

Selected topic: {json.dumps(topic, ensure_ascii=False)}

{project_brief(project)}
"""
    else:
        prompt = f"""你是短视频编导。请基于用户素材和选题生成可直接拍摄的脚本。
输出严格 JSON：
{{
  "title":"",
  "hook":"",
  "format":"",
  "duration":"30 秒",
  "shooting_notes":[""],
  "scenes":[{{"time":"0-3s","shot":"","voiceover":"","visual":""}}],
  "cover":{{"title":"","subtitle":""}}
}}
要求：中文、可拍、分镜清楚、前三秒强钩子、不要空泛。

选题：{json.dumps(topic, ensure_ascii=False)}

{project_brief(project)}
"""
    result = call_openai_json(prompt) or call_gemini_json(prompt)
    script = result if result and not result.get("_error") else fallback_script(project, topic)
    if "scenes" not in script:
        script = fallback_script(project, topic)
    script["markdown"] = script_to_markdown(script, project.get("language", "zh"))
    persist_script_package(project, topic, script)
    return script


def persist_script_package(project: Dict[str, Any], topic: Dict[str, Any], script: Dict[str, Any]) -> None:
    slug = slugify(topic.get("title") or script.get("title") or "short-video")
    output_dir = PROJECT_DIR / project["id"] / slug
    scenes = []
    for scene in script.get("scenes", []):
        scenes.append(
            {
                "duration": 3.0,
                "headline": scene.get("time", ""),
                "body": scene.get("voiceover", ""),
                "background": "#101418",
                "accent": "#2DD4BF",
            }
        )
    copy = build_copy(
        {
            "topic": script.get("title") or topic.get("title") or "短视频选题",
            "audience": topic.get("audience") or project.get("answers", {}).get("audience") or "目标用户",
            "persona": "短视频编导",
            "hook": script.get("hook") or topic.get("title") or "",
            "takeaways": [note for note in script.get("shooting_notes", [])],
            "call_to_action": "收藏起来，拍摄前按这个脚本检查。",
            "cover_title": (script.get("cover") or {}).get("title") or script.get("title"),
            "cover_subtitle": (script.get("cover") or {}).get("subtitle") or script.get("hook"),
        }
    )
    if scenes:
        copy["scenes"] = scenes
    output_dir.mkdir(parents=True, exist_ok=True)
    write_copy_markdown(output_dir / "copy.md", copy)
    write_yaml(output_dir / "project.yaml", build_video_project(copy, output_dir))
    write_cover_brief(output_dir / "cover_brief.md", copy)
    (output_dir / "script.md").write_text(script["markdown"], encoding="utf-8")


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()
    migrate_json_projects()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/admin")
def admin() -> FileResponse:
    return FileResponse(WEB_DIR / "admin.html")


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "time": now_iso(), "model": model_status()}


@app.get("/api/model-status")
def get_model_status() -> Dict[str, Any]:
    return model_status()


@app.get("/api/business-config")
def get_business_config() -> Dict[str, Any]:
    return business_config()


@app.post("/api/trial-orders")
def create_trial_order(payload: TrialOrderCreate) -> Dict[str, Any]:
    order = save_trial_order(payload)
    return {"order": order, "business": business_config()}


@app.get("/api/trial-orders")
def list_trial_orders(limit: int = 50) -> Dict[str, Any]:
    limit = max(1, min(limit, 200))
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT id, name, contact, business, platform, material, language,
                   amount_cents, currency, status, paid_at, delivered_at, created_at, updated_at
            FROM trial_orders
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {"orders": [row_to_trial_order(row) for row in rows]}


@app.patch("/api/trial-orders/{order_id}")
def update_trial_order(order_id: str, payload: TrialOrderUpdate) -> Dict[str, Any]:
    return {"order": update_trial_order_status(order_id, payload.status)}


@app.get("/api/revenue-summary")
def revenue_summary() -> Dict[str, Any]:
    return trial_revenue_summary()


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> Dict[str, Any]:
    ensure_dirs()
    project = {
        "id": uuid.uuid4().hex[:12],
        "text": payload.text.strip(),
        "language": normalize_language(payload.language),
        "assets": [],
        "answers": {},
        "topics": [],
        "scripts": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    save_project(project)
    log_project_event(project["id"], "project_created", {"text_length": len(project["text"]), "language": project["language"]})
    return project


@app.get("/api/projects")
def list_projects(limit: int = 50) -> Dict[str, Any]:
    limit = max(1, min(limit, 200))
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT id, data, created_at, updated_at
            FROM projects
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    projects = []
    for row in rows:
        data = json.loads(row["data"])
        projects.append(
            {
                "id": row["id"],
                "text": data.get("text", ""),
                "asset_count": len(data.get("assets", [])),
                "answer_count": len(data.get("answers", {})),
                "topic_count": len(data.get("topics", [])),
                "script_count": len(data.get("scripts", [])),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return {"projects": projects}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> Dict[str, Any]:
    return load_project(project_id)


@app.get("/api/projects/{project_id}/events")
def get_project_events(project_id: str) -> Dict[str, Any]:
    load_project(project_id)
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT id, event_type, payload, created_at
            FROM project_events
            WHERE project_id = ?
            ORDER BY created_at ASC
            """,
            (project_id,),
        ).fetchall()
    return {
        "events": [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    }


@app.post("/api/projects/{project_id}/assets")
def upload_asset(project_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    project = load_project(project_id)
    content_type = file.content_type or "application/octet-stream"
    if content_type not in IMAGE_TYPES and content_type not in VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="Only image and video uploads are supported")
    destination_dir = UPLOAD_DIR / project_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "asset").suffix
    destination = destination_dir / f"{uuid.uuid4().hex}{suffix}"
    with destination.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    size = destination.stat().st_size
    if size > MAX_UPLOAD_MB * 1024 * 1024:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Upload must be <= {MAX_UPLOAD_MB}MB")
    asset = {
        "id": uuid.uuid4().hex[:12],
        "filename": file.filename or destination.name,
        "path": str(destination),
        "kind": ("image" if content_type in IMAGE_TYPES else "video") if is_english(project) else ("图片" if content_type in IMAGE_TYPES else "视频"),
        "content_type": content_type,
        "size": size,
        "created_at": now_iso(),
    }
    project["assets"].append(asset)
    project["updated_at"] = now_iso()
    save_project(project)
    log_project_event(
        project_id,
        "asset_uploaded",
        {"asset_id": asset["id"], "kind": asset["kind"], "content_type": content_type, "size": size},
    )
    return asset


@app.post("/api/projects/{project_id}/analyze")
def analyze(project_id: str) -> Dict[str, Any]:
    project = load_project(project_id)
    project["analysis"] = analyze_project(project)
    project["updated_at"] = now_iso()
    save_project(project)
    log_project_event(
        project_id,
        "project_analyzed",
        {"model": project["analysis"].get("model"), "summary_length": len(project["analysis"].get("summary", ""))},
    )
    return project["analysis"]


@app.get("/api/projects/{project_id}/questions/next")
def get_next_question(project_id: str) -> Dict[str, Any]:
    project = load_project(project_id)
    question = next_question(project)
    return {"done": question is None, "question": question}


@app.post("/api/projects/{project_id}/answers")
def save_answer(project_id: str, payload: AnswerRequest) -> Dict[str, Any]:
    project = load_project(project_id)
    project.setdefault("answers", {})[payload.question_id] = payload.answer.strip()
    project["updated_at"] = now_iso()
    save_project(project)
    log_project_event(project_id, "answer_saved", {"question_id": payload.question_id, "answer_length": len(payload.answer)})
    return {"answers": project["answers"], "next": next_question(project)}


@app.post("/api/projects/{project_id}/topics")
def topics(project_id: str, payload: TopicRequest) -> Dict[str, Any]:
    project = load_project(project_id)
    project["language"] = normalize_language(payload.language)
    project["topics"] = generate_topics(project, payload.count)
    project["updated_at"] = now_iso()
    save_project(project)
    log_project_event(project_id, "topics_generated", {"count": len(project["topics"])})
    return {"topics": project["topics"]}


@app.post("/api/projects/{project_id}/scripts")
def scripts(project_id: str, payload: ScriptRequest) -> Dict[str, Any]:
    project = load_project(project_id)
    project["language"] = normalize_language(payload.language)
    script = generate_script(project, payload.topic)
    project.setdefault("scripts", []).append({"topic": payload.topic, "script": script, "created_at": now_iso()})
    project["updated_at"] = now_iso()
    save_project(project)
    log_project_event(
        project_id,
        "script_generated",
        {"topic_title": payload.topic.get("title"), "script_title": script.get("title")},
    )
    return {"script": script}


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
