import json
import os
import time
import importlib.util
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

try:
    import requests
except ModuleNotFoundError:
    requests = None


ROOT = Path(__file__).resolve().parent
PRODUCT_ROOT = ROOT.parent
DAY1_ROOT = PRODUCT_ROOT / "Phase1_Day1_大模型能力矩阵实训包" / "outputs"
DAY2_ROOT = PRODUCT_ROOT / "Phase1_Day2_Prompt产品实训包" / "outputs"
DAY3_PACKAGE = PRODUCT_ROOT / "Phase1_Day3_桌面AgentCore实训包"
DAY3_OUTPUTS = DAY3_PACKAGE / "outputs"
DAY3_WORKSPACE = DAY3_OUTPUTS / "agent_workspace"
DAY3_CORE_PATH = DAY3_PACKAGE / "day3_agent_core.py"
WORKSPACE = ROOT / "day4_agent_workspace"
TRACE = ROOT / "day4_trace_log.jsonl"
ENV_PATH = Path(os.environ.get("ENV_PATH", PRODUCT_ROOT / "local_siliconflow.env"))
_DAY3_CORE_MODULE = None


def load_env() -> None:
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)
    os.environ.setdefault("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    os.environ.setdefault("MODEL_TEXT", "Pro/moonshotai/Kimi-K2.6")
    os.environ.setdefault("MODEL_AGENT", os.environ.get("MODEL_B", "deepseek-ai/DeepSeek-V4-Flash"))
    os.environ.setdefault("MODEL_REVIEW", os.environ.get("MODEL_C", "Qwen/Qwen3.6-27B"))


load_env()


app = FastAPI(title="Phase1 Day4 Device-to-Agent Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model: str = "pocket-campus-agent"
    messages: List[ChatMessage]
    temperature: float = 0.25
    stream: bool = False


class DeviceAskRequest(BaseModel):
    device_id: str = "cores3-01"
    text: str
    scenario: str = "StudyFlow S3"


class AgentRunRequest(BaseModel):
    intent: str
    device_id: str = "cores3-01"
    source: str = "manual"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_event(event_type: str, payload: Dict[str, Any]) -> None:
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    with TRACE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": now(), "type": event_type, "payload": payload}, ensure_ascii=False) + "\n")


def current_device_text(raw_text: str) -> Dict[str, str]:
    text = (raw_text or "").strip()
    marker = "Current user message:"
    if marker in text:
        current = text.split(marker, 1)[1].strip()
        lines = [line.strip() for line in current.splitlines() if line.strip()]
        return {"text": lines[-1] if lines else current, "kind": "current_user_message"}

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return {"text": lines[-1], "kind": "chat_history"}
    return {"text": text, "kind": "single_message"}


def read_text(path: Path, limit: int = 5000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[:limit]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def latest_file(folder: Path, pattern: str = "*") -> Optional[Path]:
    if not folder.exists():
        return None
    files = [path for path in folder.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def file_meta(path: Optional[Path]) -> Dict[str, str]:
    if path is None:
        return {"path": "", "mtime": "", "bytes": "0"}
    return {
        "path": str(path.relative_to(ROOT)) if ROOT in path.resolve().parents or path.resolve() == ROOT else str(path),
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "bytes": str(path.stat().st_size),
    }


def latest_summary() -> str:
    candidates = [
        WORKSPACE / "summaries" / "course_summary.md",
        DAY3_WORKSPACE / "summaries" / "course_summary.md",
        DAY3_WORKSPACE / "course_summary_for_device.md",
    ]
    for path in candidates:
        text = read_text(path, 4000)
        if text.strip():
            return text
    return "暂未找到课程摘要。"


def latest_tasks() -> str:
    candidates = [
        WORKSPACE / "summaries" / "tasks.md",
        DAY3_WORKSPACE / "summaries" / "tasks.md",
        DAY3_WORKSPACE / "todo_and_risk_for_device.md",
    ]
    for path in candidates:
        text = read_text(path, 3000)
        if text.strip():
            return text
    return "暂未找到待办清单。"


def latest_risks() -> str:
    candidates = [
        WORKSPACE / "summaries" / "risks.md",
        DAY3_WORKSPACE / "summaries" / "risks.md",
        DAY3_WORKSPACE / "todo_and_risk_for_device.md",
    ]
    for path in candidates:
        text = read_text(path, 3000)
        if text.strip():
            return text
    return "暂未找到风险清单。"


def load_course_context() -> str:
    parts = [
        "# Day3摘要\n" + latest_summary(),
        "# Day3待办\n" + latest_tasks(),
        "# Day3风险\n" + latest_risks(),
        "# Day1模型路由\n" + read_text(DAY1_ROOT / "day1_to_day2_brief.json", 3000),
        "# Day2产品规格\n" + read_text(DAY2_ROOT / "product_spec.json", 3000),
        "# Day2提示词库\n" + read_text(DAY2_ROOT / "prompt_library.json", 3000),
        "# Day2评测用例\n" + read_text(DAY2_ROOT / "eval_cases.json", 2500),
        "# Day2 Agent Handoff\n" + read_text(DAY2_ROOT / "agent_handoff" / "day2_agent_contract.json", 3500),
        "# Day3复盘\n" + read_text(DAY3_OUTPUTS / "after_review.md", 2000),
    ]
    return "\n\n".join(part for part in parts if part.strip())[:16000]


def load_day3_agent_core():
    global _DAY3_CORE_MODULE
    if _DAY3_CORE_MODULE is not None:
        return _DAY3_CORE_MODULE
    if not DAY3_CORE_PATH.exists():
        log_event("day3_core.missing", {"path": str(DAY3_CORE_PATH)})
        return None
    try:
        spec = importlib.util.spec_from_file_location("phase1_day3_agent_core", DAY3_CORE_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot create module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _DAY3_CORE_MODULE = module
        return module
    except Exception as exc:
        log_event("day3_core.import_error", {"path": str(DAY3_CORE_PATH), "error": f"{type(exc).__name__}: {exc}"})
        return None


def extract_user_text(messages: List[ChatMessage]) -> str:
    chunks: List[str] = []
    for message in messages:
        if message.role != "user":
            continue
        content = message.content
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        chunks.append(str(item.get("text", "")))
                    elif "text" in item:
                        chunks.append(str(item.get("text", "")))
                else:
                    chunks.append(str(item))
        else:
            chunks.append(str(content))
    return "\n".join(part for part in chunks if part.strip()).strip()


def call_siliconflow(prompt: str, model: Optional[str] = None, max_tokens: int = 900) -> str:
    if os.environ.get("MOCK_LLM") == "1":
        return ""
    if requests is None:
        log_event("llm.error", {"model": model or os.environ.get("MODEL_TEXT", ""), "error": "requests module is not installed"})
        return ""
    api_key = os.environ.get("SILICONFLOW_API_KEY", "")
    if not api_key:
        return ""
    base_url = os.environ["SILICONFLOW_BASE_URL"].rstrip("/")
    model_id = model or os.environ.get("MODEL_TEXT", "Pro/moonshotai/Kimi-K2.6")
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是 StudyFlow S3 设备触发网关的云端大脑。回答必须短、具体、可执行，适合 M5Stack CoreS3 小屏和语音播报。不要编造不存在的课程资料。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.25,
                "max_tokens": max_tokens,
            },
            timeout=80,
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0].get("message", {})
        content = message.get("content") or message.get("reasoning_content") or ""
        if isinstance(content, list):
            content = "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
        return str(content).strip()
    except Exception as exc:
        log_event("llm.error", {"model": model_id, "error": f"{type(exc).__name__}: {exc}"})
        return ""


def short(text: str, limit: int = 120) -> str:
    text = " ".join(text.strip().split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_review_cards(summary: str) -> List[Dict[str, str]]:
    prompt = f"""
根据下面课程摘要，为 M5Stack CoreS3 设备生成3张复习卡。只输出JSON数组，每项包含 question, answer, hint。

课程摘要：
{summary[:4000]}
"""
    raw = call_siliconflow(prompt, model=os.environ.get("MODEL_TEXT"), max_tokens=900)
    if raw:
        try:
            start = raw.find("[")
            end = raw.rfind("]")
            if start >= 0 and end > start:
                cards = json.loads(raw[start : end + 1])
                if isinstance(cards, list) and cards:
                    return [
                        {
                            "question": str(item.get("question", ""))[:120],
                            "answer": str(item.get("answer", ""))[:200],
                            "hint": str(item.get("hint", ""))[:120],
                        }
                        for item in cards[:3]
                    ]
        except Exception as exc:
            log_event("cards.parse_error", {"error": f"{type(exc).__name__}: {exc}", "raw": raw[:600]})
    return [
        {
            "question": "Agent为什么必须通过安全工具层操作文件？",
            "answer": "因为它需要限制操作范围、保留轨迹，并避免误删或越权访问。",
            "hint": "安全边界、可追踪、可回滚。",
        },
        {
            "question": "AI Learning Capability Module 的关键工程产物是什么？",
            "answer": "提示词库、上下文包、JSON Schema、多模态上下文 Schema、评测样例和 Agent 动作合约。",
            "hint": "提示词资产需要成为可调用能力。",
        },
        {
            "question": "M5Stack S3 在本系统里承担什么角色？",
            "answer": "它是设备触发网关，负责触发任务、展示短反馈，并让本机 Agent 与云端模型协同工作。",
            "hint": "边缘设备负责触发和展示。",
        },
    ]


def execute_agent(intent: str, device_id: str, source: str) -> Dict[str, Any]:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for sub in ["voice_inbox", "summaries", "cards", "evidence"]:
        (WORKSPACE / sub).mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    voice_file = WORKSPACE / "voice_inbox" / f"{stamp}_{device_id}.txt"
    voice_file.write_text(f"来源：{source}\n设备：{device_id}\n时间：{now()}\n意图：{intent}\n", encoding="utf-8")
    log_event("perceive.voice_intent", {"device_id": device_id, "intent": intent, "file": str(voice_file.relative_to(ROOT))})

    context = load_course_context()
    log_event("perceive.course_context", {"chars": len(context)})

    core = load_day3_agent_core()
    if core and hasattr(core, "run_day3_agent_core"):
        result = core.run_day3_agent_core(
            intent=intent,
            workspace=WORKSPACE,
            course_context=context,
            call_llm=call_siliconflow,
            model_agent=os.environ.get("MODEL_AGENT"),
            model_text=os.environ.get("MODEL_TEXT"),
            device_id=device_id,
            source=source,
            log_event=log_event,
        )
        reply = result["reply"]
        outputs = result.get("outputs", [])
    else:
        summary_md = (
            "# Day3 Agent Core 课程摘要\n\n"
            "Day4设备网关已收到请求，但没有找到可导入的Day3 Agent Core。"
            "当前使用兜底整理：保留设备输入、生成简要待办、风险和复习卡。\n"
        )
        tasks_md = "# Day3 Agent Core 待办\n\n- 检查 day3_agent_core.py 是否存在。\n- 确认 Day4 Bridge 能导入 Day3 Core。\n- 重新运行设备触发流程。\n"
        risks_md = "# Day3 Agent Core 风险\n\n- Day3/Day4边界被破坏会导致课程目标混乱。\n- 设备重复消息必须去重。\n- 文件操作必须限制在 workspace。\n"
        cards = build_review_cards(summary_md)
        outputs = {
            "summaries/course_summary.md": summary_md,
            "summaries/tasks.md": tasks_md,
            "summaries/risks.md": risks_md,
            "cards/review_cards.json": json.dumps(cards, ensure_ascii=False, indent=2),
        }
        for rel, content in outputs.items():
            path = WORKSPACE / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            log_event("act.write_file.fallback", {"path": rel, "chars": len(content)})
        reply = "Day3桌面Agent已整理完成：摘要、待办、风险和复习卡已更新。可以说“给我一道复习题”。"
        (WORKSPACE / "latest_device_reply.txt").write_text(reply, encoding="utf-8")
        outputs = list(outputs.keys()) + ["latest_device_reply.txt"]

    evidence = {
        "ts": now(),
        "device_id": device_id,
        "intent_file": str(voice_file.relative_to(ROOT)),
        "outputs": list(outputs) + ["day4_trace_log.jsonl"],
        "agent_core": str(DAY3_CORE_PATH),
    }
    (WORKSPACE / "evidence" / f"{stamp}_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event("reflect.completed", evidence)
    return {"reply": reply, "display_text": short(reply), "executed": True, "evidence": evidence}


def answer_from_context(text: str) -> str:
    if any(word in text for word in ["摘要", "总结", "今天学了什么"]):
        return short(latest_summary(), 160)
    if any(word in text for word in ["待办", "下一步", "任务"]):
        return short(latest_tasks(), 160)
    if any(word in text for word in ["风险", "注意"]):
        return short(latest_risks(), 160)
    if any(word in text for word in ["复习题", "抽背", "出题", "考我"]):
        cards_path = WORKSPACE / "cards" / "review_cards.json"
        cards = []
        if cards_path.exists():
            cards = json.loads(cards_path.read_text(encoding="utf-8"))
        if not cards:
            cards = build_review_cards(latest_summary())
            cards_path.parent.mkdir(parents=True, exist_ok=True)
            cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
        card = cards[int(time.time()) % len(cards)]
        return short(f"复习题：{card['question']} 提示：{card['hint']}", 160)

    prompt = f"""
设备输入：{text}

课程上下文：
{load_course_context()}

请给适合 M5Stack CoreS3 显示和播报的短回答。不超过100字。如果用户要操作文件，提醒他说“请整理今天资料”并再次“确认整理”。
"""
    return short(call_siliconflow(prompt, model=os.environ.get("MODEL_TEXT"), max_tokens=500) or "我可以整理今天资料、生成复习题、查看待办或风险。")


def route_device_text(text: str, device_id: str = "cores3-01", source: str = "device") -> Dict[str, Any]:
    parsed = current_device_text(text)
    effective_text = parsed["text"]
    input_kind = parsed["kind"]
    log_event("device.input", {"device_id": device_id, "text": text, "effective_text": effective_text, "input_kind": input_kind, "source": source})
    wants_organize = any(word in effective_text for word in ["整理资料", "整理今天", "整理课程", "整理文件", "帮我整理"])
    confirms = any(word in effective_text for word in ["确认整理", "确认执行", "开始整理", "执行整理"])

    if confirms:
        if input_kind == "chat_history":
            reply = read_text(WORKSPACE / "latest_device_reply.txt", 160) or "已收到确认，Day3桌面Agent正在整理资料。"
            log_event("dedupe.skip_history_execute", {"effective_text": effective_text, "reply": reply})
            return {"reply": reply, "display_text": short(reply), "executed": False, "deduped": True}
        return execute_agent(effective_text, device_id=device_id, source=source)
    if wants_organize:
        reply = "我将调用Day3桌面Agent整理课程资料。为避免误操作，请再说：确认整理。"
        log_event("plan.needs_confirmation", {"reply": reply})
        return {"reply": reply, "display_text": short(reply), "executed": False, "needs_confirmation": True}

    reply = answer_from_context(effective_text)
    log_event("device.reply", {"reply": reply})
    return {"reply": reply, "display_text": short(reply), "executed": False, "needs_confirmation": False}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "phase1-day4-device-agent-gateway",
        "time": now(),
        "day3_exists": DAY3_CORE_PATH.exists() and DAY3_WORKSPACE.exists(),
        "workspace": str(WORKSPACE),
        "trace": str(TRACE),
        "model_text": os.environ.get("MODEL_TEXT"),
        "model_agent": os.environ.get("MODEL_AGENT"),
        "mock_llm": os.environ.get("MOCK_LLM", "0"),
    }


@app.get("/v1/models")
def models() -> Dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "pocket-campus-agent", "object": "model", "owned_by": "phase1-day4"},
            {"id": "pocket-review-coach", "object": "model", "owned_by": "phase1-day4"},
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest) -> Dict[str, Any]:
    user_text = extract_user_text(req.messages)
    result = route_device_text(user_text, device_id="openai-compatible-client", source="openai-compatible")
    reply = result["reply"]
    return {
        "id": f"chatcmpl-day4-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.post("/device/ask")
def device_ask(req: DeviceAskRequest) -> Dict[str, Any]:
    return route_device_text(req.text, device_id=req.device_id, source=req.scenario)


@app.post("/agent/run")
def agent_run(req: AgentRunRequest) -> Dict[str, Any]:
    return execute_agent(req.intent, device_id=req.device_id, source=req.source)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    trace_lines = TRACE.read_text(encoding="utf-8").splitlines()[-50:] if TRACE.exists() else []
    report = read_json(WORKSPACE / "reports" / "agent_run_report.json", {})
    retrieval = read_json(WORKSPACE / "knowledge" / "retrieval_result.json", [])
    cards = read_json(WORKSPACE / "cards" / "review_cards.json", [])
    latest_voice = latest_file(WORKSPACE / "voice_inbox", "*.txt")
    latest_evidence = latest_file(WORKSPACE / "evidence", "*.json")
    voice_text = read_text(latest_voice, 2200) if latest_voice else "暂无设备输入。"
    evidence = read_json(latest_evidence, {}) if latest_evidence else {}
    latest_reply = read_text(WORKSPACE / "latest_device_reply.txt", 1200) or read_text(DAY3_WORKSPACE / "latest_device_reply.txt", 1200)

    rows = []
    timeline = []
    for line in trace_lines:
        try:
            item = json.loads(line)
            event_type = item.get("type", "")
            payload = item.get("payload", {})
            if event_type in {
                "device.input",
                "plan.needs_confirmation",
                "perceive.voice_intent",
                "perceive.course_context",
                "tool.list_files",
                "tool.search_workspace",
                "rag.retrieve",
                "llm.generate",
                "reflect.completed",
                "device.reply",
            } or event_type.startswith("tool.write_file"):
                timeline.append(
                    f"<div class='event'><b>{escape(event_type)}</b><span>{escape(item.get('ts',''))}</span>"
                    f"<p>{escape(json.dumps(payload, ensure_ascii=False)[:260])}</p></div>"
                )
            rows.append(
                f"<tr><td>{escape(item.get('ts',''))}</td><td>{escape(event_type)}</td>"
                f"<td><pre>{escape(json.dumps(payload, ensure_ascii=False, indent=2)[:900])}</pre></td></tr>"
            )
        except Exception:
            rows.append(f"<tr><td colspan='3'><pre>{escape(line)}</pre></td></tr>")

    tool_calls = report.get("tool_calls", []) if isinstance(report, dict) else []
    tool_cards = "".join(
        f"<div class='mini'><b>{escape(str(call.get('tool','')))}</b><span>{' OK' if call.get('ok') else ' FAIL'}</span>"
        f"<p>{escape(str(call.get('result_preview',''))[:420])}</p></div>"
        for call in tool_calls[-12:]
    )
    retrieval_cards = "".join(
        f"<div class='mini'><b>{escape(str(item.get('chunk_id','')))}</b><span>{escape(str(item.get('source_path','')))}</span>"
        f"<p>{escape(str(item.get('excerpt','')))}</p><em>score={escape(str(item.get('score','')))}</em></div>"
        for item in retrieval[:8]
    )
    review_cards = "".join(
        f"<div class='mini'><b>{escape(str(card.get('question','')))}</b><p>{escape(str(card.get('answer','')))}</p><em>{escape(str(card.get('hint','')))}</em></div>"
        for card in cards[:4]
    )
    outputs = report.get("outputs", []) if isinstance(report, dict) else []
    output_list = "".join(f"<li>{escape(str(path))}</li>" for path in outputs)
    voice_meta = file_meta(latest_voice)
    evidence_meta = file_meta(latest_evidence)
    evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2) if evidence else "暂无 evidence 文件。"
    report_summary = {
        "ts": report.get("ts") if isinstance(report, dict) else "",
        "intent": report.get("intent") if isinstance(report, dict) else "",
        "generation_source": report.get("generation_source") if isinstance(report, dict) else "",
        "knowledge_chunks": report.get("knowledge_chunks") if isinstance(report, dict) else 0,
        "retrieval_hits": len(retrieval),
        "tool_calls": len(tool_calls),
        "outputs": outputs,
    }
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Day4 Device-to-Agent Bridge</title>
  <style>
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;margin:0;background:#f6f7f9;color:#17202a;line-height:1.55}}
    header{{background:#243746;color:white;padding:28px 36px}} main{{max-width:1180px;margin:24px auto;padding:0 20px}}
    .grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}} .two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .panel{{background:white;border:1px solid #d8dee6;border-radius:8px;padding:18px;margin:14px 0}}
    .kpi{{font-size:26px;font-weight:750}} .muted{{color:#667789}} .toolbar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} button{{appearance:none;border:0;background:#0f766e;color:white;border-radius:6px;padding:9px 12px;font-weight:700;cursor:pointer}} label{{display:flex;gap:6px;align-items:center;color:#334155}}
    .flow{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}} .step{{background:#eef8f6;border:1px solid #b8ded8;border-radius:8px;padding:13px;text-align:center;font-weight:700}} .event,.mini{{border:1px solid #d8dee6;background:#fbfcfd;border-radius:8px;padding:12px;margin:8px 0}} .event span,.mini span{{color:#667789;margin-left:8px}} .event p,.mini p{{margin:8px 0;color:#314252}} .mini em{{color:#667789}}
    table{{width:100%;border-collapse:collapse}} td,th{{border:1px solid #d8dee6;padding:9px;vertical-align:top}} pre{{white-space:pre-wrap;word-break:break-word;background:#f8fafc;padding:10px;border-radius:6px;max-height:360px;overflow:auto}} code{{background:#f1f5f9;border:1px solid #d8dee6;border-radius:5px;padding:1px 5px}}
    @media(max-width:900px){{.grid,.two,.flow{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
<header><h1>Day4 Device-to-Agent Bridge</h1><p>M5Stack CoreS3 / ESP-Claw / 微信通过 OpenAI-compatible API 调用 Day3 Agent Core。</p></header>
<main>
  <div class="grid">
    <div class="panel"><div class="kpi">{'可用' if DAY3_WORKSPACE.exists() else '缺失'}</div><div class="muted">Day3资料</div></div>
    <div class="panel"><div class="kpi">{len(trace_lines)}</div><div class="muted">最近Trace事件</div></div>
    <div class="panel"><div class="kpi">{len(tool_calls)}</div><div class="muted">Day3工具调用</div></div>
    <div class="panel"><div class="kpi">{len(retrieval)}</div><div class="muted">RAG命中</div></div>
  </div>
  <div class="panel toolbar">
    <button onclick="location.reload()">刷新Dashboard</button>
    <label><input id="autoRefresh" type="checkbox"> 每5秒自动刷新</label>
    <span class="muted">当前模型：{escape(os.environ.get('MODEL_AGENT',''))}</span>
  </div>
  <div class="panel">
    <h2>设备到Agent链路</h2>
    <div class="flow"><div class="step">Device<br>S3/微信</div><div class="step">Bridge<br>/v1/chat</div><div class="step">Confirm<br>二次确认</div><div class="step">AgentCore<br>Tool + RAG</div><div class="step">Return<br>短回复/复习题</div></div>
  </div>
  <div class="two">
    <div class="panel"><h2>最新设备输入</h2><p class="muted">{escape(voice_meta['path'])} · {escape(voice_meta['mtime'])}</p><pre>{escape(voice_text)}</pre></div>
    <div class="panel"><h2>最新回复</h2><pre>{escape(latest_reply or '暂无回复。')}</pre></div>
  </div>
  <div class="two">
    <div class="panel"><h2>Agent运行报告</h2><pre>{escape(json.dumps(report_summary, ensure_ascii=False, indent=2))}</pre></div>
    <div class="panel"><h2>最新Evidence</h2><p class="muted">{escape(evidence_meta['path'])} · {escape(evidence_meta['mtime'])}</p><pre>{escape(evidence_text[:3000])}</pre></div>
  </div>
  <div class="panel"><h2>关键事件链</h2>{''.join(timeline[-18:]) or '<p class="muted">暂无关键事件。</p>'}</div>
  <div class="panel"><h2>Day3 Tool Use</h2>{tool_cards or '<p class="muted">暂无工具调用。请从设备或微信发送“请整理今天资料”，再发送“确认整理”。</p>'}</div>
  <div class="panel"><h2>Day3 RAG 命中</h2>{retrieval_cards or '<p class="muted">暂无RAG结果。</p>'}</div>
  <div class="two">
    <div class="panel"><h2>复习卡</h2>{review_cards or '<p class="muted">暂无复习卡。</p>'}</div>
    <div class="panel"><h2>输出文件</h2><ul>{output_list or '<li>暂无输出。</li>'}</ul></div>
  </div>
  <div class="grid">
    <div class="panel"><div class="kpi">{escape(os.environ.get('MODEL_AGENT',''))}</div><div class="muted">Agent模型</div></div>
    <div class="panel"><div class="kpi">{escape(os.environ.get('MODEL_TEXT',''))}</div><div class="muted">文本模型</div></div>
    <div class="panel"><div class="kpi">{'模拟' if os.environ.get('MOCK_LLM') == '1' else '真实'}</div><div class="muted">LLM模式</div></div>
    <div class="panel"><div class="kpi">{'可用' if WORKSPACE.exists() else '缺失'}</div><div class="muted">Day4 Workspace</div></div>
  </div>
  <div class="panel"><h2>当前摘要</h2><pre>{escape(latest_summary())}</pre></div>
  <div class="panel"><h2>当前待办</h2><pre>{escape(latest_tasks())}</pre></div>
  <div class="panel"><h2>当前风险</h2><pre>{escape(latest_risks())}</pre></div>
  <div class="panel"><h2>最近轨迹</h2><table><tr><th>时间</th><th>事件</th><th>内容</th></tr>{''.join(rows)}</table></div>
</main>
<script>
let autoTimer = null;
const box = document.getElementById("autoRefresh");
box.addEventListener("change", function(event) {{
  if (event.target.checked) {{
    autoTimer = setInterval(function() {{ location.reload(); }}, 5000);
  }} else if (autoTimer) {{
    clearInterval(autoTimer);
    autoTimer = null;
  }}
}});
</script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    uvicorn.run("cloud_service:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=False)
