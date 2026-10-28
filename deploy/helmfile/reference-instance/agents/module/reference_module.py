"""The reference instance's module: one job flow, `echo`, that crosses the
layers the way a real flow does (evidence from knowledge, a completion
through inference) and answers with what it got. No product logic."""

from __future__ import annotations

from typing import Any

from app.flows import Answer, Flow, FlowContext, ModuleContext


def _echo(ctx: FlowContext, body: dict[str, Any]) -> Answer:
    with ctx.step("search"):
        passages = ctx.evidence(str(body.get("query", "")))
    with ctx.step("answer"):
        text = ctx.complete("answer", {"text": " ".join(p.content for p in passages)})
    return Answer({"answer": text, "passages": len(passages)})


class ReferenceModule:
    base_agents_api = 1

    def setup(self, ctx: ModuleContext) -> None:
        self.log = ctx.log

    def prompts(self) -> dict[str, str]:
        return {"answer": "Answer from: $text"}

    def flows(self) -> dict[str, Flow]:
        return {"echo": Flow(mode="job", steps=("search", "answer"), prompts=("answer",),
                             run=_echo)}


def factory() -> ReferenceModule:
    return ReferenceModule()
