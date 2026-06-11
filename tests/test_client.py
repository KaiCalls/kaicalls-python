import json
import unittest
from unittest.mock import patch

from kaicalls import KaiCalls, KaiCallsError, signup


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body


class FakeSession:
    """Records requests and replays canned responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.requests.append(
            {"method": method, "url": url, "params": params, "json": json, "headers": headers}
        )
        return self.responses.pop(0)


class ClientTests(unittest.TestCase):
    def test_requires_api_key(self):
        with self.assertRaises(ValueError):
            KaiCalls(api_key="")

    def test_calls_create_posts_documented_shape(self):
        session = FakeSession([FakeResponse({"id": "call-1", "status": "queued"}, 201)])
        kai = KaiCalls(api_key="kc_live_test", session=session)

        call = kai.calls.create(
            agent_id="agent-1",
            to="+15125551234",
            name="John Smith",
            context="Follow up",
            lead_id="lead-1",
        )

        self.assertEqual(call.id, "call-1")
        req = session.requests[0]
        self.assertEqual(req["method"], "POST")
        self.assertEqual(req["url"], "https://www.kaicalls.com/api/v1/calls")
        self.assertEqual(req["headers"]["Authorization"], "Bearer kc_live_test")
        self.assertEqual(
            req["json"],
            {
                "agent_id": "agent-1",
                "to": "+15125551234",
                "name": "John Smith",
                "context": "Follow up",
                "lead_id": "lead-1",
            },
        )

    def test_calls_get_uses_query_id(self):
        session = FakeSession([FakeResponse({"id": "call-1", "status": "ended"})])
        kai = KaiCalls(api_key="kc_live_test", session=session)
        kai.calls.get("call-1")
        self.assertEqual(session.requests[0]["params"], {"id": "call-1"})

    def test_calls_wait_polls_until_terminal(self):
        session = FakeSession(
            [
                FakeResponse({"id": "c", "status": "queued"}),
                FakeResponse({"id": "c", "status": "in-progress"}),
                FakeResponse({"id": "c", "status": "ended", "summary": "All done"}),
            ]
        )
        kai = KaiCalls(api_key="kc_live_test", session=session)
        with patch("kaicalls.client.time.sleep"):
            result = kai.calls.wait("c", interval=0)
        self.assertEqual(result.status, "ended")
        self.assertEqual(result.summary, "All done")
        self.assertEqual(len(session.requests), 3)

    def test_attribute_access_wraps_nested_objects(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "id": "call-1",
                        "quality_dimensions": {"empathy": 88},
                        "missing": None,
                    }
                )
            ]
        )
        kai = KaiCalls(api_key="kc_live_test", session=session)
        call = kai.calls.get("call-1")
        self.assertEqual(call.quality_dimensions.empathy, 88)
        self.assertIsNone(call.nonexistent_field)

    def test_agents_update_sends_only_given_fields(self):
        session = FakeSession([FakeResponse({"id": "agent-1", "updated": True})])
        kai = KaiCalls(api_key="kc_live_test", session=session)
        kai.agents.update(
            id="agent-1",
            inbound_prompt="New prompt",
            vapi_config={"endCallPhrases": ["goodbye"]},
        )
        req = session.requests[0]
        self.assertEqual(req["method"], "PATCH")
        self.assertEqual(
            req["json"],
            {
                "id": "agent-1",
                "inbound_prompt": "New prompt",
                "vapi_config": {"endCallPhrases": ["goodbye"]},
            },
        )

    def test_leads_list_joins_statuses(self):
        session = FakeSession([FakeResponse({"leads": [], "has_more": False})])
        kai = KaiCalls(api_key="kc_live_test", session=session)
        kai.leads.list(status=["new", "contacted"], limit=10)
        self.assertEqual(
            session.requests[0]["params"], {"status": "new,contacted", "limit": 10}
        )

    def test_sms_send_documented_shape(self):
        session = FakeSession([FakeResponse({"success": True, "message_sid": "SM1"})])
        kai = KaiCalls(api_key="kc_live_test", session=session)
        res = kai.sms.send(to="+15125551234", from_agent_id="agent-1", message="Hi!")
        self.assertTrue(res.success)
        self.assertEqual(
            session.requests[0]["json"],
            {"to": "+15125551234", "from_agent_id": "agent-1", "message": "Hi!"},
        )

    def test_communication_runs_create_sends_idempotency_key(self):
        session = FakeSession([FakeResponse({"success": True}, 201)])
        kai = KaiCalls(api_key="kc_live_test", session=session)
        kai.communication_runs.create({"business_id": "biz-1"}, idempotency_key="idem-1")
        self.assertEqual(session.requests[0]["headers"]["Idempotency-Key"], "idem-1")

    def test_error_raises_kaicalls_error(self):
        session = FakeSession(
            [
                FakeResponse(
                    {"error": {"code": "forbidden", "message": "Missing required scope"}}, 403
                )
            ]
        )
        kai = KaiCalls(api_key="kc_live_test", session=session)
        with self.assertRaises(KaiCallsError) as ctx:
            kai.calls.create(agent_id="a", to="+1")
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(ctx.exception.code, "forbidden")
        self.assertIn("Missing required scope", str(ctx.exception))

    def test_signup_without_api_key(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "api_key": "kc_live_new",
                        "business_id": "biz-1",
                        "agent_id": None,
                        "phone_number": None,
                    },
                    201,
                )
            ]
        )
        result = signup(
            business_name="Smith Law", email="a@b.com", plan_id="starter", session=session
        )
        self.assertEqual(result.api_key, "kc_live_new")
        req = session.requests[0]
        self.assertEqual(
            req["json"],
            {"business_name": "Smith Law", "email": "a@b.com", "plan_id": "starter"},
        )
        self.assertNotIn("Authorization", req["headers"])

    def test_raw_request_escape_hatch(self):
        session = FakeSession([FakeResponse({"ok": True})])
        kai = KaiCalls(api_key="kc_live_test", session=session)
        kai.request("GET", "/api/sdr/pipeline", query={"businessId": "biz-1"})
        req = session.requests[0]
        self.assertEqual(req["url"], "https://www.kaicalls.com/api/sdr/pipeline")
        self.assertEqual(req["params"], {"businessId": "biz-1"})


if __name__ == "__main__":
    unittest.main()
