import json
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.data.support_tree import SUPPORT_TREE
from app.database import SessionLocal
from app.main import app
from app.models import (
    AdminAuditLog, Conversation, Message, Notification, SupportTicket, SupportTicketStatus, User,
)
from app.services.auth import create_access_token
from app.services.support_bot import bot_message_fields, greeting_node, resolve_node


class TestBotTree(unittest.TestCase):
    """Pure logic, no HTTP."""

    def test_button_label_routes_to_its_target(self):
        node_id, node = resolve_node("Photo upload problems")
        self.assertEqual(node_id, "photos")
        self.assertIn("6 views", node["message"])

    def test_label_match_ignores_case_and_spacing(self):
        self.assertEqual(resolve_node("  talk   TO a Human ")[0], "human")

    def test_keywords_route_and_most_hits_wins(self):
        self.assertEqual(resolve_node("my PHOTO is blurry")[0], "photos")
        self.assertEqual(resolve_node("the borrower is late with the return")[0], "returns")
        self.assertEqual(resolve_node("I want to make an offer on the price")[0], "offers")

    def test_unknown_text_falls_back_to_root_menu(self):
        node_id, node = resolve_node("zzzz qqqq")
        self.assertEqual(node_id, "fallback")
        self.assertEqual(node["quick_replies"], SUPPORT_TREE["root"]["quick_replies"])

    def test_human_node_escalates(self):
        node_id, node = resolve_node("Talk to a human")
        self.assertEqual(node_id, "human")
        self.assertTrue(node["escalate"])

    def test_tree_is_consistent(self):
        """Every quick-reply target exists, every node has a message: keeps added nodes honest."""
        for node_id, node in SUPPORT_TREE.items():
            self.assertTrue(node.get("message"), node_id)
            for reply in node.get("quick_replies", []):
                self.assertIn(reply["next"], SUPPORT_TREE, f"{node_id} -> {reply['next']}")

    def test_greeting_depends_on_step(self):
        self.assertEqual(greeting_node("return_flow")[0], "returns")
        self.assertEqual(greeting_node("something_new")[0], "root")

    def test_bot_message_fields_carry_quick_replies(self):
        fields = bot_message_fields("root", SUPPORT_TREE["root"])
        meta = json.loads(fields["meta"])
        self.assertTrue(meta["bot"])
        self.assertIn("Talk to a human", meta["quick_replies"])
        self.assertNotIn("quick_replies", json.loads(bot_message_fields("human", SUPPORT_TREE["human"])["meta"]))


class TestSupportChat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db = SessionLocal()
        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        users = {}
        for role in ("user", "other", "admin"):
            users[role] = User(
                name=f"Sup {role}", username=f"sup_{role}_{suffix}",
                email=f"sup_{role}_{suffix}@test.com", password_hash="test",
                is_admin=(role == "admin"),
            )
        db.add_all(users.values())
        db.commit()
        cls.ids = {role: u.id for role, u in users.items()}
        db.close()
        cls.headers = {
            role: {"Authorization": f"Bearer {create_access_token(uid)}"}
            for role, uid in cls.ids.items()
        }

    def _open(self, role="user", step="handover_photos", entity_id="lend-123"):
        res = self.client.post(
            "/api/support/chat",
            json={"context_step": step, "entity_type": "borrow_request", "entity_id": entity_id},
            headers=self.headers[role],
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def _say(self, conv_id, text, role="user"):
        return self.client.post(f"/api/support/conversations/{conv_id}/messages",
                                json={"content": text}, headers=self.headers[role])

    def _messages(self, conv_id):
        db = SessionLocal()
        try:
            return [
                (m.sender_id, m.content, m.is_system, json.loads(m.meta) if m.meta else None)
                for m in db.query(Message).filter(Message.conversation_id == conv_id)
                .order_by(Message.created_at).all()
            ]
        finally:
            db.close()

    def test_open_creates_thread_with_context_and_greeting(self):
        info = self._open(step="handover_photos", entity_id="lend-open-1")
        system_line, greeting = self._messages(info["conversation_id"])[-2:]
        self.assertTrue(system_line[2])  # system line first
        self.assertIn("handover_photos", system_line[1])
        self.assertIn("lend-open-1", system_line[1])
        self.assertFalse(greeting[2])
        self.assertEqual(greeting[3]["node_id"], "photos")  # context-aware opening
        self.assertIn("Still stuck", greeting[3]["quick_replies"])  # leads to the human node
        db = SessionLocal()
        try:
            conv = db.get(Conversation, info["conversation_id"])
            self.assertEqual(conv.borrower_id, self.ids["user"])
            self.assertEqual(conv.lender.username, "nl_support")
        finally:
            db.close()

    def test_reopening_same_step_reuses_ticket_other_step_makes_new_one(self):
        a = self._open(step="return_flow", entity_id="lend-reuse")
        b = self._open(step="return_flow", entity_id="lend-reuse")
        self.assertEqual((a["conversation_id"], a["ticket_id"]), (b["conversation_id"], b["ticket_id"]))
        c = self._open(step="dispute", entity_id="lend-reuse")
        self.assertEqual(a["conversation_id"], c["conversation_id"])  # one support thread per user
        self.assertNotEqual(a["ticket_id"], c["ticket_id"])
        self.assertEqual(self._open(role="other")["conversation_id"] != a["conversation_id"], True)

    def test_open_validates_input_and_needs_login(self):
        bad = self.client.post("/api/support/chat", json={"context_step": "Bad Step!"}, headers=self.headers["user"])
        self.assertEqual(bad.status_code, 422)
        bad = self.client.post("/api/support/chat", json={"context_step": "ok", "entity_type": "user"},
                               headers=self.headers["user"])
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.client.post("/api/support/chat", json={"context_step": "ok"}).status_code, 401)

    def test_bot_replies_and_history_visible_through_conversation_api(self):
        conv_id = self._open(step="listing_create", entity_id=None)["conversation_id"]
        res = self._say(conv_id, "my return is late")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["user_message"]["content"], "my return is late")
        self.assertEqual(json.loads(body["bot_message"]["meta"])["node_id"], "returns")
        self.assertFalse(body["escalated"])
        history = self.client.get(f"/api/conversations/{conv_id}", headers=self.headers["user"]).json()
        self.assertEqual(history["messages"][-1]["id"], body["bot_message"]["id"])
        self.assertIn("quick_replies", json.loads(history["messages"][-1]["meta"]))

    def test_support_thread_is_private_to_its_owner(self):
        conv_id = self._open()["conversation_id"]
        self.assertEqual(self._say(conv_id, "hi", "other").status_code, 403)
        self.assertEqual(self.client.get(f"/api/conversations/{conv_id}", headers=self.headers["other"]).status_code, 403)
        self.assertEqual(self._say("no-such-conversation", "hi").status_code, 404)
        self.assertEqual(self._say(conv_id, "   ").status_code, 400)  # blank, same as the normal chat endpoint

    def test_cannot_use_support_endpoint_on_a_normal_conversation(self):
        db = SessionLocal()
        try:
            conv = Conversation(borrower_id=self.ids["user"], lender_id=self.ids["other"])
            db.add(conv)
            db.commit()
            conv_id = conv.id
        finally:
            db.close()
        self.assertEqual(self._say(conv_id, "hello").status_code, 403)

    def test_escalation_admin_view_reply_and_close(self):
        conv_id = self._open(step="dispute", entity_id="lend-escalate")["conversation_id"]
        res = self._say(conv_id, "Talk to a human")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["escalated"])
        self.assertIn("flagged", res.json()["bot_message"]["content"])

        db = SessionLocal()
        try:
            ticket = db.query(SupportTicket).filter(
                SupportTicket.conversation_id == conv_id, SupportTicket.context_step == "dispute"
            ).one()
            self.assertEqual(ticket.status, SupportTicketStatus.escalated)
            ticket_id = ticket.id
            self.assertGreaterEqual(db.query(Notification).filter(
                Notification.user_id == self.ids["admin"], Notification.notification_type == "support_escalation"
            ).count(), 1)
        finally:
            db.close()

        # humans have the chat now: no more bot replies
        quiet = self._say(conv_id, "are you there?")
        self.assertIsNone(quiet.json()["bot_message"])
        self.assertTrue(quiet.json()["escalated"])

        # admin sees it, reads the thread, replies
        listing = self.client.get("/api/admin/support/escalations", headers=self.headers["admin"]).json()
        row = next(r for r in listing if r["id"] == ticket_id)
        self.assertEqual(row["context_step"], "dispute")
        self.assertEqual(row["entity_id"], "lend-escalate")
        self.assertEqual(row["last_user_message"], "are you there?")
        detail = self.client.get(f"/api/admin/support/escalations/{ticket_id}", headers=self.headers["admin"]).json()
        self.assertTrue(any(m["content"] == "are you there?" for m in detail["messages"]))

        reply = self.client.post(f"/api/admin/support/escalations/{ticket_id}/reply",
                                 json={"content": "We're on it."}, headers=self.headers["admin"])
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertTrue(json.loads(reply.json()["meta"])["admin"])
        db = SessionLocal()
        try:
            self.assertEqual(db.query(Notification).filter(
                Notification.user_id == self.ids["user"], Notification.notification_type == "support_reply"
            ).count() >= 1, True)
            actions = [l.action for l in db.query(AdminAuditLog).filter(AdminAuditLog.target_id == ticket_id).all()]
            self.assertEqual(actions, ["support_reply"])
        finally:
            db.close()
        user_view = self.client.get(f"/api/conversations/{conv_id}", headers=self.headers["user"]).json()
        self.assertEqual(user_view["messages"][-1]["content"], "We're on it.")

        closed = self.client.post(f"/api/admin/support/escalations/{ticket_id}/close", headers=self.headers["admin"])
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["status"], "closed")
        self.assertEqual(self.client.post(f"/api/admin/support/escalations/{ticket_id}/close",
                                          headers=self.headers["admin"]).status_code, 409)
        self.assertEqual(self.client.post(f"/api/admin/support/escalations/{ticket_id}/reply",
                                          json={"content": "late"}, headers=self.headers["admin"]).status_code, 409)
        self.assertNotIn(ticket_id, [r["id"] for r in
                         self.client.get("/api/admin/support/escalations", headers=self.headers["admin"]).json()])

    def test_escalating_from_a_thread_without_a_ticket_still_works(self):
        db = SessionLocal()
        try:
            support = db.query(User).filter(User.username == "nl_support").first()
            conv = Conversation(borrower_id=self.ids["other"], lender_id=support.id)
            db.add(conv)
            db.commit()
            conv_id = conv.id
        finally:
            db.close()
        res = self._say(conv_id, "Talk to a human", "other")
        self.assertTrue(res.json()["escalated"])

    def test_admin_support_endpoints_reject_non_admins(self):
        info = self._open(step="negotiation", entity_id="lend-private")
        self._say(info["conversation_id"], "Talk to a human")
        ticket_id = info["ticket_id"]
        for role in ("user", "other"):
            h = self.headers[role]
            self.assertEqual(self.client.get("/api/admin/support/escalations", headers=h).status_code, 403)
            self.assertEqual(self.client.get(f"/api/admin/support/escalations/{ticket_id}", headers=h).status_code, 403)
            self.assertEqual(self.client.post(f"/api/admin/support/escalations/{ticket_id}/reply",
                                              json={"content": "x"}, headers=h).status_code, 403)
            self.assertEqual(self.client.post(f"/api/admin/support/escalations/{ticket_id}/close", headers=h).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/support/escalations").status_code, 401)


if __name__ == "__main__":
    unittest.main()
