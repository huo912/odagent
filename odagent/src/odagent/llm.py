import os
from pathlib import Path

from crewai import LLM
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def create_llm() -> LLM:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未找到 LLM API Key。请在项目根目录 .env 中设置 "
            "OPENAI_API_KEY=sk-...，或在当前 Bash 会话执行："
            " export OPENAI_API_KEY=sk-..."
        )

    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", "0"))

    return LLM(
        model="moma_deepseek-v4-flash",
        # model="qwen3.8-27b",
        base_url="http://10.105.1.5:4001/v1",
        api_key=api_key,
        max_tokens=16000,
        timeout=timeout,
        max_retries=max_retries,
    )