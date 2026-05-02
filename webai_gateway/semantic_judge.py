from __future__ import annotations

import re
from dataclasses import dataclass

from webai_gateway.tool_bridge import BridgeResult, ToolBridgeContext


@dataclass(frozen=True)
class SemanticJudgeResult:
    verdict: str
    confidence: float
    reason: str


_PENDING_ACTION_RE = re.compile(
    r"\b(?:next|continue|need|needs|must|should|will|todo|fixme)\b|(?:下一步|继续|需要|必须|应该|建议|待|补充|补全|完善)",
    re.IGNORECASE,
)


def judge_bridge_semantics(result: BridgeResult, context: ToolBridgeContext, *, controller_state: str) -> SemanticJudgeResult:
    if result.tool_calls:
        return SemanticJudgeResult("allow", 0.99, "tool_call")
    if result.error is not None:
        if result.error.kind.startswith("unsafe"):
            return SemanticJudgeResult("ask_user", 0.8, result.error.kind)
        return SemanticJudgeResult("retry", 0.9 if result.error.repairable else 0.65, result.error.kind)
    text = (result.content or result.raw_content or "").strip()
    if controller_state == "RETRY":
        return SemanticJudgeResult("retry", 0.85, "controller_retry")
    if context.allowed_names and _PENDING_ACTION_RE.search(text):
        return SemanticJudgeResult("retry", 0.7, "pending_action_text")
    return SemanticJudgeResult("allow", 0.6, "no_local_pending_signal")
