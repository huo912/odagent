from pathlib import Path

from crewai import Agent, Crew, Process, Task

from odagent.agents.database_analyst.agent import create_agent as create_database_agent
from odagent.agents.database_analyst.task import create_task as create_database_task
from odagent.agents.requirements_analyst.agent import (
    create_agent as create_requirements_agent,
)
from odagent.agents.requirements_analyst.task import (
    create_task as create_requirements_task,
)
from odagent.agents.senior_fullstack_engineer.agent import (
    create_agent as create_fullstack_agent,
)
from odagent.agents.senior_fullstack_engineer.task import (
    create_task as create_fullstack_task,
)
from odagent.agents.senior_software_test_engineer.agent import (
    create_agent as create_test_agent,
)
from odagent.agents.senior_software_test_engineer.task import (
    create_task as create_test_task,
)
from odagent.agents.software_architect.agent import create_agent as create_architect_agent
from odagent.agents.software_architect.task import create_task as create_architect_task
from odagent.checkpoint import get_checkpoint_manager
from odagent.memory import get_memory_store
from odagent.tracker import ProgressTracker, make_step_callback, make_task_callback

# 各 Agent 的展示名称（用于进度追踪）
AGENT_NAMES = {
    "requirements_analyst": "需求分析师",
    "software_architect": "软件架构师",
    "database_analyst": "数据库架构师",
    "senior_fullstack_engineer": "资深全栈工程师",
    "senior_software_test_engineer": "资深测试工程师",
}

# 统一输出目录：odagent/output（与 server.py / main.py 的 PROJECT_ROOT 一致）
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


class ODAgentCrew:
    """编排各角色模块，不包含具体 agent/task 定义。"""

    def __init__(
        self,
        tracker: ProgressTracker | None = None,
        run_id: str = "",
        resume: bool = False,
    ) -> None:
        self.tracker = tracker
        self.run_id = run_id
        self.resume = resume
        self._checkpoint = get_checkpoint_manager()
        self._memory = get_memory_store()

    def kickoff(self, inputs: dict, selected_agents: list[str] | None = None) -> None:
        """执行 Crew，并在开始时标记选中的 Agent 为运行中。

        Args:
            inputs: 任务输入（如 {"requirement": ...}）。
            selected_agents: 需要执行的 agent key 列表；为 None 时执行全部。
        """
        crew = self.crew(selected_agents=selected_agents)  # 先注册选中的 Agent
        if self.tracker is not None:
            self.tracker.clear_pause_state()
            self.tracker.mark_all_running()
        crew.kickoff(inputs=inputs)

    def _should_skip(self, agent_key: str) -> bool:
        """检查点恢复：若该 Agent 已完成且开启恢复，则跳过。"""
        return self.resume and bool(self.run_id) and self._checkpoint.is_completed(
            self.run_id, agent_key
        )

    def _mark_done(self, agent_key: str, output_file: str = "") -> None:
        """任务完成后写入检查点，并保存一条记忆。"""
        if not output_file:
            # 从任务配置中获取输出文件名
            output_file = {
                "requirements_analyst": "requirements_analysis.md",
                "software_architect": "software_architecture.md",
                "database_analyst": "database_design.md",
                "senior_fullstack_engineer": "fullstack_code.md",
                "senior_software_test_engineer": "software_test_plan.md",
            }.get(agent_key, "")
        if self.run_id:
            self._checkpoint.mark_completed(
                self.run_id, agent_key, output_file=output_file
            )
        # 记录该 Agent 已完成，供后续 Agent 参考
        self._memory.save(
            agent_key,
            key=f"last_run_{agent_key}",
            content=f"最近一次任务已完成，输出文件：{output_file or '（无）'}",
        )

    def crew(self, selected_agents: list[str] | None = None) -> Crew:
        """构建 Crew，仅包含选中的 Agent 及其任务。

        Args:
            selected_agents: 需要执行的 agent key 列表；为 None 时执行全部。
        """
        if selected_agents is None:
            selected_agents = list(AGENT_NAMES.keys())
        selected = [k for k in AGENT_NAMES if k in selected_agents]

        agents = {
            "requirements_analyst": create_requirements_agent(),
            "software_architect": create_architect_agent(),
            "database_analyst": create_database_agent(),
            "senior_fullstack_engineer": create_fullstack_agent(),
            "senior_software_test_engineer": create_test_agent(),
        }

        # 注册进度追踪（仅选中的 Agent）
        if self.tracker is not None:
            for key in selected:
                agent = agents[key]
                self.tracker.register_agent(key, agent.role)
                self.tracker.register_agent_instance(key, agent)
                # 以 max_iter 作为预估总步数，用于计算进度百分比
                total_steps = getattr(agent, "max_iter", 0) or 0
                self.tracker.set_total_steps(key, total_steps)

        def cb(name: str):
            if self.tracker is None:
                return None
            base = make_task_callback(self.tracker, name)

            def wrapped(output):
                base(output)
                # 任务完成后写入检查点与记忆
                self._mark_done(name, output_file=getattr(output, "raw", "") or "")

            return wrapped

        def step_cb(name: str):
            if self.tracker is None:
                return None
            return make_step_callback(self.tracker, name)

        # 按依赖顺序构建任务；context 只引用已选中且已创建的任务
        tasks: dict[str, Task] = {}

        if "requirements_analyst" in selected:
            if not self._should_skip("requirements_analyst"):
                tasks["requirements_analyst"] = create_requirements_task(
                    agents["requirements_analyst"],
                    [],
                    callback=cb("requirements_analyst"),
                )
        if "software_architect" in selected:
            ctx = [tasks[k] for k in ("requirements_analyst",) if k in tasks]
            if not self._should_skip("software_architect"):
                tasks["software_architect"] = create_architect_task(
                    agents["software_architect"], ctx, callback=cb("software_architect")
                )
        if "database_analyst" in selected:
            ctx = [
                tasks[k]
                for k in ("requirements_analyst", "software_architect")
                if k in tasks
            ]
            if not self._should_skip("database_analyst"):
                tasks["database_analyst"] = create_database_task(
                    agents["database_analyst"], ctx, callback=cb("database_analyst")
                )
        if "senior_fullstack_engineer" in selected:
            ctx = [
                tasks[k]
                for k in ("requirements_analyst", "software_architect", "database_analyst")
                if k in tasks
            ]
            if not self._should_skip("senior_fullstack_engineer"):
                tasks["senior_fullstack_engineer"] = create_fullstack_task(
                    agents["senior_fullstack_engineer"],
                    ctx,
                    callback=cb("senior_fullstack_engineer"),
                )
        if "senior_software_test_engineer" in selected:
            ctx = [
                tasks[k]
                for k in ("requirements_analyst", "senior_fullstack_engineer")
                if k in tasks
            ]
            if not self._should_skip("senior_software_test_engineer"):
                tasks["senior_software_test_engineer"] = create_test_task(
                    agents["senior_software_test_engineer"],
                    ctx,
                    callback=cb("senior_software_test_engineer"),
                )

        # 统一输出目录：将相对 output_file 覆盖为绝对路径，写入 odagent/output
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for task in tasks.values():
            if task.output_file:
                task.output_file = str(OUTPUT_DIR / Path(task.output_file).name)

        crew = Crew(
            agents=[agents[k] for k in selected],
            tasks=list(tasks.values()),
            process=Process.sequential,
            verbose=True,
        )

        # 为每个选中的 Agent 设置 step_callback，实现实时 token 更新与独立耗时。
        # 必须在 Crew 构造之后设置，因为 Crew 构造时会复制 agent 对象，
        # 直接对 agents dict 中的对象设置会被覆盖。
        # crew.agents 与 selected 顺序一致，按顺序 zip 关联名字。
        for key, agent in zip(selected, crew.agents):
            agent.step_callback = step_cb(key)

        return crew