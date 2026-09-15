from pathlib import Path
from typing import Any

import yaml
from crewai import Agent
from crewai.agent.planning_config import PlanningConfig

from odagent.llm import create_llm
from odagent.memory import build_memory_context, get_memory_tools


AGENT_KEY = "requirements_analyst"


def load_config() -> dict[str, dict[str, Any]]:
    config_path = (
        Path(__file__).parents[2]
        / "config"
        / Path(__file__).parent.name
        / "config.yaml"
    )
    with config_path.open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def create_agent() -> Agent:
    agent_config = dict(load_config()["agent"])
    llm = create_llm()
    # 使用低推理成本模式：跳过每步的 PlannerObserver LLM 调用。
    # 避免模型返回无效 JSON（StepObservation）导致报错，并显著缩短执行时间。
    max_attempts = agent_config.pop("max_reasoning_attempts", None)
    agent_config.pop("reasoning", None)
    planning_config = PlanningConfig(
        reasoning_effort="low",
        max_attempts=max_attempts,
    )
    # 记忆系统：将历史记忆注入 backstory，并绑定记忆读写工具
    memory_context = build_memory_context(AGENT_KEY)
    if memory_context:
        agent_config["backstory"] = (
            f"{agent_config.get('backstory', '')}\n\n{memory_context}"
        )
    memory_tools = get_memory_tools(AGENT_KEY)
    return Agent(
        **agent_config,
        llm=llm,
        planning_config=planning_config,
        tools=memory_tools,
    )