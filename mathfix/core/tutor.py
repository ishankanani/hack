"""Tutor chat about one solved problem: hints, next step, why, simpler, show answer, free questions."""
from __future__ import annotations

from ..ai import prompts
from ..ai.router import Router
from ..db import Repo
from ..mathcheck.text import latex_to_text, pretty_text
from ..schemas import Solution


class Tutor:
    def __init__(self, router: Router, repo: Repo):
        self.router = router
        self.repo = repo

    async def reply(self, user_id: int, solution_row: dict, action: str, text: str = "", step: int = 1, *,
                    grade: str | None = None, lang: str = "en") -> str:
        sol = Solution.model_validate_json(solution_row["solution_json"])
        steps = "\n".join(f"{i}. {s.say} {latex_to_text(s.math)}".strip() for i, s in enumerate(sol.steps, 1))
        student, language = prompts.student_context(grade, lang)
        system = prompts.TUTOR_SYSTEM.format(student=student, language=language,
                                             problem=solution_row["problem_text"], steps=steps,
                                             answer=sol.final_answer)
        if action == "ask":
            question = text.strip()[:1000]
        else:
            question = prompts.TUTOR_ACTIONS[action].format(n=step)
        history = await self.repo.recent_turns(user_id, solution_row["id"])
        messages = [{"role": "system", "content": system}]
        messages += [{"role": t["role"], "content": t["text"]} for t in history]
        messages.append({"role": "user", "content": question})
        res = await self.router.run("tutor", messages, effort="low")
        answer = clean_reply(str(res.data))[:1500]
        await self.repo.add_turn(user_id, solution_row["id"], "user", question)
        await self.repo.add_turn(user_id, solution_row["id"], "assistant", answer)
        return answer


def clean_reply(text: str) -> str:
    """Models sometimes write LaTeX like \\(x^2\\) or **bold** even when asked not to; Telegram can't show it."""
    return pretty_text(text)
