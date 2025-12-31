from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.groq_client import GroqClient


class CrewEngine:
    def __init__(self) -> None:
        self._groq = None

    def _groq_client(self) -> GroqClient:
        if self._groq is None:
            self._groq = GroqClient()
        return self._groq

    def run_agent(self, agent: dict[str, Any], input_text: str, context: dict[str, Any] | None) -> dict[str, Any]:
        if settings.use_crewai:
            crew_response = self._run_with_crewai(agent, input_text, context)
            if crew_response is not None:
                return crew_response
        return self._run_with_groq(agent, input_text, context)

    def run_crew(
        self,
        agents: list[dict[str, Any]],
        objective: str,
        context: dict[str, Any] | None,
        crew_name: str | None,
    ) -> dict[str, Any]:
        if settings.use_crewai:
            crew_response = self._run_crew_with_crewai(agents, objective, context, crew_name)
            if crew_response is not None:
                return crew_response
        return self._run_crew_with_groq(agents, objective, context, crew_name)

    def _run_with_groq(self, agent: dict[str, Any], input_text: str, context: dict[str, Any] | None) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an autonomous data-retrieval agent. "
                    f"Role: {agent['role']}. Goal: {agent['goal']}"
                ),
            },
            {"role": "user", "content": input_text},
        ]
        if context:
            messages.append({"role": "user", "content": f"Context: {context}"})
        data = self._groq_client().chat(messages)
        content = data["choices"][0]["message"]["content"]
        return {"agent": agent["name"], "output": content, "model": agent["model"]}

    def _run_crew_with_groq(
        self,
        agents: list[dict[str, Any]],
        objective: str,
        context: dict[str, Any] | None,
        crew_name: str | None,
    ) -> dict[str, Any]:
        responses = []
        prior_outputs: list[str] = []
        for agent in agents:
            stitched = objective
            if prior_outputs:
                stitched += "\n\nPrior agent outputs:\n" + "\n".join(prior_outputs)
            if context:
                stitched += f"\n\nContext: {context}"
            result = self._run_with_groq(agent, stitched, None)
            responses.append(result)
            prior_outputs.append(result["output"])
        return {
            "crew": crew_name or "default-crew",
            "objective": objective,
            "responses": responses,
        }

    def _run_with_crewai(self, agent: dict[str, Any], input_text: str, context: dict[str, Any] | None) -> dict[str, Any] | None:
        try:
            from crewai import Agent, Crew, Task

            description = input_text
            if context:
                description += f"\n\nContext: {context}"

            crew_agent = Agent(
                role=agent["role"],
                goal=agent["goal"],
                backstory=f"Agent name: {agent['name']}.",
                allow_delegation=False,
                verbose=False,
            )
            task = Task(description=description, expected_output="Actionable response.")
            crew = Crew(agents=[crew_agent], tasks=[task])
            output = crew.kickoff()
            return {"agent": agent["name"], "output": str(output), "mode": "crewai"}
        except Exception:
            return None

    def _run_crew_with_crewai(
        self,
        agents: list[dict[str, Any]],
        objective: str,
        context: dict[str, Any] | None,
        crew_name: str | None,
    ) -> dict[str, Any] | None:
        try:
            from crewai import Agent, Crew, Task

            description = objective
            if context:
                description += f"\n\nContext: {context}"

            crew_agents = [
                Agent(
                    role=agent["role"],
                    goal=agent["goal"],
                    backstory=f"Agent name: {agent['name']}.",
                    allow_delegation=False,
                    verbose=False,
                )
                for agent in agents
            ]
            task = Task(description=description, expected_output="Actionable response.")
            crew = Crew(agents=crew_agents, tasks=[task])
            output = crew.kickoff()
            return {"crew": crew_name or "default-crew", "output": str(output), "mode": "crewai"}
        except Exception:
            return None
