import json
import os
from pathlib import Path

os.environ.setdefault("MOCK_LLM", "1")

import cloud_service

def post_chat(text: str):
    req = cloud_service.ChatCompletionRequest(
        model="pocket-campus-agent",
        messages=[cloud_service.ChatMessage(role="user", content=text)],
    )
    return cloud_service.chat_completions(req)


def main():
    health = cloud_service.health()
    first = post_chat("请整理今天资料")
    second = post_chat("确认整理")
    quiz = post_chat("给我一道复习题")

    out = {
        "health": health,
        "first_reply": first["choices"][0]["message"]["content"],
        "second_reply": second["choices"][0]["message"]["content"],
        "quiz_reply": quiz["choices"][0]["message"]["content"],
    }
    Path("day4_selftest_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
