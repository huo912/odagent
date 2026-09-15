from crewai import Agent, Task

from .agent import load_config


def create_task(agent: Agent, context: list[Task], callback=None) -> Task:
    task_config = dict(load_config()["task"])
    task_config.pop("agent", None)
    task_config.pop("context", None)
    # 开启人工审核：任务完成后暂停，等待真实开发者确认无误后再继续后续任务
    return Task(
        agent=agent,
        context=context,
        callback=callback,
        human_input=True,
        **task_config,
    )