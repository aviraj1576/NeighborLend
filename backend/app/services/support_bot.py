"""Deterministic support bot: matches a message against SUPPORT_TREE. No LLM, no randomness."""
import json
import re
from typing import Tuple

from app.data.support_tree import FALLBACK_MESSAGE, STEP_GREETING_NODE, SUPPORT_TREE

FALLBACK_NODE_ID = "fallback"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def resolve_node(text: str) -> Tuple[str, dict]:
    """Return (node_id, node) for a user message.

    1. A message equal to a quick-reply label (any node) goes to that button's target.
    2. Otherwise the node whose keywords appear most often in the message wins; ties go to
       the node defined first in SUPPORT_TREE.
    3. Otherwise the fallback, which shows the root menu.
    """
    t = _normalize(text)
    for node in SUPPORT_TREE.values():
        for reply in node.get("quick_replies", []):
            if _normalize(reply["label"]) == t:
                return reply["next"], SUPPORT_TREE[reply["next"]]

    best_id, best_hits = None, 0
    for node_id, node in SUPPORT_TREE.items():
        hits = sum(1 for keyword in node.get("keywords", []) if keyword in t)
        if hits > best_hits:
            best_id, best_hits = node_id, hits
    if best_id:
        return best_id, SUPPORT_TREE[best_id]

    return FALLBACK_NODE_ID, {
        "message": FALLBACK_MESSAGE,
        "quick_replies": SUPPORT_TREE["root"]["quick_replies"],
    }


def greeting_node(step: str) -> Tuple[str, dict]:
    """The node the bot opens with for a given 'Chat with us' step."""
    node_id = STEP_GREETING_NODE.get(step, "root")
    return node_id, SUPPORT_TREE[node_id]


def bot_message_fields(node_id: str, node: dict) -> dict:
    """The content and meta columns for a bot Message row."""
    meta = {"node_id": node_id, "bot": True}
    if node.get("quick_replies"):
        meta["quick_replies"] = [reply["label"] for reply in node["quick_replies"]]
    return {"content": node["message"], "meta": json.dumps(meta)}
