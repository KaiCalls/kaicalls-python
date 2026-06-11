"""KaiCalls API client.

Thin typed wrapper over the KaiCalls public REST API
(https://www.kaicalls.com/docs/api). The live OpenAPI document at
``GET /api/v1/openapi.json`` is the canonical surface.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Union

import requests

DEFAULT_BASE_URL = "https://www.kaicalls.com"
DEFAULT_TIMEOUT = 30.0

_ACTIVE_CALL_STATUSES = {"queued", "ringing", "in-progress", "in_progress", "started"}


class KaiCallsError(Exception):
    """Raised for any non-2xx API response (and SDK-level timeouts)."""

    def __init__(self, status: int, code: str, message: str, body: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.body = body

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"KaiCallsError(status={self.status}, code={self.code!r}, message={str(self)!r})"


class KaiObject(dict):
    """Dict with attribute access: ``call.id`` == ``call['id']``.

    Unknown attributes return ``None`` rather than raising, so new server
    fields and optional fields are safe to read.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return _wrap(self[name])
        except KeyError:
            return None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _wrap(value: Any) -> Any:
    if isinstance(value, KaiObject):
        return value
    if isinstance(value, dict):
        return KaiObject(value)
    if isinstance(value, list):
        return [_wrap(v) for v in value]
    return value


def _compact(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


class _Http:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: Optional[requests.Session] = None,
    ):
        if not api_key:
            raise ValueError("KaiCalls: api_key is required (kc_live_...)")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def request(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        all_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if headers:
            all_headers.update(headers)

        response = self.session.request(
            method,
            self.base_url + path,
            params=_compact(query or {}) or None,
            json=body,
            headers=all_headers,
            timeout=self.timeout,
        )
        return _handle_response(response)


def _handle_response(response: requests.Response) -> Any:
    try:
        data = response.json() if response.text else None
    except ValueError:
        data = response.text

    if not (200 <= response.status_code < 300):
        err = (data or {}).get("error") if isinstance(data, dict) else None
        code = (err or {}).get("code") or f"http_{response.status_code}"
        message = (err or {}).get("message") or f"KaiCalls API error (HTTP {response.status_code})"
        raise KaiCallsError(response.status_code, code, message, data)

    return _wrap(data)


class _Calls:
    def __init__(self, http: _Http):
        self._http = http

    def create(
        self,
        agent_id: str,
        to: str,
        name: Optional[str] = None,
        context: Optional[str] = None,
        first_message: Optional[str] = None,
        lead_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        max_duration: Optional[int] = None,
    ) -> KaiObject:
        """Start an outbound call. Requires calls:write."""
        return self._http.request(
            "POST",
            "/api/v1/calls",
            body=_compact(
                {
                    "agent_id": agent_id,
                    "to": to,
                    "name": name,
                    "context": context,
                    "first_message": first_message,
                    "lead_id": lead_id,
                    "webhook_url": webhook_url,
                    "max_duration": max_duration,
                }
            ),
        )

    def get(self, call_id: str) -> KaiObject:
        """Fetch one call (summary, recording_url, quality_dimensions)."""
        return self._http.request("GET", "/api/v1/calls", query={"id": call_id})

    def list(
        self,
        limit: Optional[int] = None,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        after: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/calls",
            query={"limit": limit, "agent_id": agent_id, "status": status, "after": after},
        )

    def wait(
        self,
        call_id: str,
        interval: float = 3.0,
        timeout: float = 600.0,
    ) -> KaiObject:
        """Poll a call until it leaves an active status, or raise on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            call = self.get(call_id)
            if str(call.get("status")) not in _ACTIVE_CALL_STATUSES:
                return call
            if time.monotonic() >= deadline:
                raise KaiCallsError(
                    0,
                    "wait_timeout",
                    f'Call {call_id} still "{call.get("status")}" after {timeout}s',
                    call,
                )
            time.sleep(interval)


class _Recordings:
    def __init__(self, http: _Http):
        self._http = http

    def get(self, call_id: str) -> KaiObject:
        """Signed recording URL + status for one call. Requires calls:read."""
        return self._http.request("GET", "/api/v1/recordings", query={"call_id": call_id})


class _Agents:
    def __init__(self, http: _Http):
        self._http = http

    def list(self) -> KaiObject:
        return self._http.request("GET", "/api/v1/agents")

    def get(self, agent_id: str) -> KaiObject:
        return self._http.request("GET", "/api/v1/agents", query={"id": agent_id})

    def create(
        self,
        business_id: str,
        name: str,
        system_prompt: str,
        first_message: Optional[str] = None,
        voice: Optional[Dict[str, Any]] = None,
        model: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> KaiObject:
        """Create a voice agent. Requires agents:write."""
        return self._http.request(
            "POST",
            "/api/v1/agents",
            body=_compact(
                {
                    "business_id": business_id,
                    "name": name,
                    "system_prompt": system_prompt,
                    "first_message": first_message,
                    "voice": voice,
                    "model": model,
                    "metadata": metadata,
                }
            ),
        )

    def update(self, id: str, **fields: Any) -> KaiObject:
        """Partial update — pass only the snake_case fields to change.

        Supported fields include: name, inbound_prompt, outbound_prompt,
        sms_prompt, first_message, outbound_first_message, outbound_llm,
        sms_llm, voice, model, metadata, max_duration, vapi_config,
        transfer_enabled, transfer_phone_number.
        """
        return self._http.request(
            "PATCH", "/api/v1/agents", body=_compact({"id": id, **fields})
        )

    def versions(
        self, agent_id: str, version: Optional[int] = None, limit: Optional[int] = None
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/agents/versions",
            query={"agent_id": agent_id, "version": version, "limit": limit},
        )


class _Leads:
    def __init__(self, http: _Http):
        self._http = http

    def list(
        self,
        status: Optional[Union[str, Iterable[str]]] = None,
        source: Optional[str] = None,
        agent_id: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        updated_after: Optional[str] = None,
        updated_before: Optional[str] = None,
        score_gte: Optional[int] = None,
        score_lte: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> KaiObject:
        if status is not None and not isinstance(status, str):
            status = ",".join(status)
        return self._http.request(
            "GET",
            "/api/v1/leads",
            query={
                "status": status,
                "source": source,
                "agent_id": agent_id,
                "phone": phone,
                "email": email,
                "created_after": created_after,
                "created_before": created_before,
                "updated_after": updated_after,
                "updated_before": updated_before,
                "score_gte": score_gte,
                "score_lte": score_lte,
                "limit": limit,
            },
        )

    def get(self, lead_id: str) -> KaiObject:
        return self._http.request("GET", "/api/v1/leads", query={"id": lead_id})

    def create(self, business_id: str, **fields: Any) -> KaiObject:
        """Create a lead. Requires leads:write."""
        return self._http.request(
            "POST", "/api/v1/leads", body=_compact({"business_id": business_id, **fields})
        )

    def update(self, id: str, **fields: Any) -> KaiObject:
        """Update a lead — pass only the fields to change. Requires leads:write."""
        return self._http.request("PATCH", "/api/v1/leads", body=_compact({"id": id, **fields}))

    def audit(
        self,
        window_hours: Optional[int] = None,
        stalled_days: Optional[int] = None,
        hot_score: Optional[int] = None,
        as_of: Optional[str] = None,
    ) -> KaiObject:
        """Pipeline health snapshot (hot/stalled leads, signups, voicemails)."""
        return self._http.request(
            "GET",
            "/api/v1/leads/audit",
            query={
                "window_hours": window_hours,
                "stalled_days": stalled_days,
                "hot_score": hot_score,
                "as_of": as_of,
            },
        )


class _Sms:
    def __init__(self, http: _Http):
        self._http = http

    def send(
        self,
        to: str,
        from_agent_id: str,
        message: str,
        lead_id: Optional[str] = None,
    ) -> KaiObject:
        """Send an SMS from an agent's number (DNC/consent checks apply)."""
        return self._http.request(
            "POST",
            "/api/v1/sms/send",
            body=_compact(
                {"to": to, "from_agent_id": from_agent_id, "message": message, "lead_id": lead_id}
            ),
        )

    def update_prompt(
        self, agent_id: str, sms_prompt: str, reason: Optional[str] = None
    ) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/sms/update-prompt",
            body=_compact({"agent_id": agent_id, "sms_prompt": sms_prompt, "reason": reason}),
        )

    def conversations(self, id: Optional[str] = None, limit: Optional[int] = None) -> KaiObject:
        return self._http.request(
            "GET", "/api/v1/sms/conversations", query={"id": id, "limit": limit}
        )

    def messages(
        self,
        conversation_id: Optional[str] = None,
        direction: Optional[str] = None,
        after: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/sms/messages",
            query={
                "conversation_id": conversation_id,
                "direction": direction,
                "after": after,
                "limit": limit,
            },
        )


class _Transcripts:
    def __init__(self, http: _Http):
        self._http = http

    def list(
        self,
        limit: Optional[int] = None,
        agent_id: Optional[str] = None,
        after: Optional[str] = None,
        days: Optional[int] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/transcripts",
            query={"limit": limit, "agent_id": agent_id, "after": after, "days": days},
        )


class _PhoneNumbers:
    def __init__(self, http: _Http):
        self._http = http

    def list(
        self, business_id: Optional[str] = None, phone_number: Optional[str] = None
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/phone-numbers",
            query={"business_id": business_id, "phone_number": phone_number},
        )

    def available(
        self,
        country: Optional[str] = None,
        area_code: Optional[str] = None,
        capability: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/phone-numbers/available",
            query={
                "country": country,
                "area_code": area_code,
                "capability": capability,
                "limit": limit,
            },
        )

    def assign(
        self,
        phone_number: str,
        business_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/phone-numbers",
            body=_compact(
                {"phone_number": phone_number, "business_id": business_id, "agent_id": agent_id}
            ),
        )

    def release(self, phone_number: str, business_id: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "DELETE",
            "/api/v1/phone-numbers",
            query={"phone_number": phone_number, "business_id": business_id},
        )


class _Workspaces:
    def __init__(self, http: _Http):
        self._http = http

    def list(self) -> KaiObject:
        return self._http.request("GET", "/api/v1/workspaces")

    def get(self, workspace_id: str) -> KaiObject:
        return self._http.request("GET", "/api/v1/workspaces", query={"id": workspace_id})

    def create(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        external_ref: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/workspaces",
            body=_compact({"name": name, "metadata": metadata, "external_ref": external_ref}),
        )

    def update(self, id: str, **fields: Any) -> KaiObject:
        """Rename, update metadata, or run a lifecycle action.

        Pass ``action="pause"|"resume"|"cancel"|"teardown"`` (requires
        lifecycle:write) or ``name=...`` / ``metadata=...``.
        """
        return self._http.request(
            "PATCH", "/api/v1/workspaces", body=_compact({"id": id, **fields})
        )


class _Webhooks:
    def __init__(self, http: _Http):
        self._http = http

    def list(self, business_id: Optional[str] = None) -> KaiObject:
        return self._http.request("GET", "/api/v1/webhooks", query={"business_id": business_id})

    def create(
        self,
        webhook_url: str,
        business_id: Optional[str] = None,
        events: Optional[List[str]] = None,
        description: Optional[str] = None,
        id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> KaiObject:
        """Create/upsert a subscription. The signing secret is returned ONCE."""
        return self._http.request(
            "POST",
            "/api/v1/webhooks",
            body=_compact(
                {
                    "webhook_url": webhook_url,
                    "business_id": business_id,
                    "events": events,
                    "description": description,
                    "id": id,
                    "is_active": is_active,
                }
            ),
        )

    def delete(self, id: str, business_id: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "DELETE", "/api/v1/webhooks", query={"id": id, "business_id": business_id}
        )

    def test(
        self,
        id: str,
        business_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/webhooks/test",
            body=_compact({"id": id, "business_id": business_id, "data": data}),
        )

    def rotate_secret(self, id: str, business_id: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/webhooks/rotate-secret",
            body=_compact({"id": id, "business_id": business_id}),
        )


class _Analytics:
    def __init__(self, http: _Http):
        self._http = http

    def dashboard(self, days: Optional[int] = None) -> KaiObject:
        return self._http.request("GET", "/api/v1/analytics/dashboard", query={"days": days})

    def calls(
        self,
        days: Optional[int] = None,
        group_by: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/analytics/calls",
            query={"days": days, "group_by": group_by, "agent_id": agent_id},
        )

    def funnel(self, days: Optional[int] = None, source: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "GET", "/api/v1/analytics/funnel", query={"days": days, "source": source}
        )

    def agents(self, days: Optional[int] = None, agent_id: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "GET", "/api/v1/analytics/agents", query={"days": days, "agent_id": agent_id}
        )

    def weekly(self) -> KaiObject:
        return self._http.request("GET", "/api/v1/analytics/weekly")

    def businesses(self, days: Optional[int] = None) -> KaiObject:
        return self._http.request("GET", "/api/v1/analytics/businesses", query={"days": days})


class _Evals:
    def __init__(self, http: _Http):
        self._http = http

    def create(
        self,
        agent_id: str,
        business_id: str,
        name: str,
        messages: List[Dict[str, Any]],
        description: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/evals",
            body=_compact(
                {
                    "agent_id": agent_id,
                    "business_id": business_id,
                    "name": name,
                    "messages": messages,
                    "description": description,
                }
            ),
        )

    def list(self, agent_id: Optional[str] = None) -> KaiObject:
        return self._http.request("GET", "/api/v1/evals", query={"agent_id": agent_id})

    def get(self, eval_id: str) -> KaiObject:
        return self._http.request("GET", "/api/v1/evals", query={"id": eval_id})

    def update(self, id: str, **fields: Any) -> KaiObject:
        return self._http.request("PATCH", "/api/v1/evals", body=_compact({"id": id, **fields}))

    def delete(self, eval_id: str) -> KaiObject:
        return self._http.request("DELETE", "/api/v1/evals", query={"id": eval_id})

    def run(
        self,
        eval_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        wait: Optional[bool] = None,
        max_wait_ms: Optional[int] = None,
    ) -> KaiObject:
        """Run one eval (eval_id) or all of an agent's evals (agent_id)."""
        return self._http.request(
            "POST",
            "/api/v1/evals/run",
            body=_compact(
                {
                    "eval_id": eval_id,
                    "agent_id": agent_id,
                    "wait": wait,
                    "max_wait_ms": max_wait_ms,
                }
            ),
        )

    def get_run(
        self,
        run_id: Optional[str] = None,
        vapi_run_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/evals/run",
            query={"run_id": run_id, "vapi_run_id": vapi_run_id, "agent_id": agent_id},
        )


class _Events:
    def __init__(self, http: _Http):
        self._http = http

    def list(self, **filters: Any) -> KaiObject:
        """Durable events. Filters: business_id, event_id, event_type,
        object_type, object_id, status, from_ (mapped to from), to, limit."""
        if "from_" in filters:
            filters["from"] = filters.pop("from_")
        return self._http.request("GET", "/api/v1/events", query=_compact(filters))

    def deliveries(self, **filters: Any) -> KaiObject:
        return self._http.request("GET", "/api/v1/event-deliveries", query=_compact(filters))

    def replay(
        self,
        event_id: Optional[str] = None,
        event_ids: Optional[List[str]] = None,
        filter: Optional[Dict[str, Any]] = None,
        business_id: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/events/replay",
            body=_compact(
                {
                    "event_id": event_id,
                    "event_ids": event_ids,
                    "filter": filter,
                    "business_id": business_id,
                }
            ),
        )

    def backfill(
        self,
        from_: str,
        to: str,
        business_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/events/backfill",
            body=_compact(
                {
                    "from": from_,
                    "to": to,
                    "business_id": business_id,
                    "event_type": event_type,
                    "status": status,
                }
            ),
        )


class _CommunicationRuns:
    def __init__(self, http: _Http):
        self._http = http

    def validate(self, body: Dict[str, Any]) -> KaiObject:
        return self._http.request("POST", "/api/v1/communication-runs/validate", body=body)

    def preview(self, body: Dict[str, Any]) -> KaiObject:
        return self._http.request("POST", "/api/v1/communication-runs/preview", body=body)

    def create(self, body: Dict[str, Any], idempotency_key: str) -> KaiObject:
        return self._http.request(
            "POST",
            "/api/v1/communication-runs",
            body=body,
            headers={"Idempotency-Key": idempotency_key},
        )

    def list(
        self,
        business_id: Optional[str] = None,
        id: Optional[str] = None,
        external_ref: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET",
            "/api/v1/communication-runs",
            query={
                "business_id": business_id,
                "id": id,
                "external_ref": external_ref,
                "limit": limit,
            },
        )

    def pause(self, id: str, business_id: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "PATCH",
            "/api/v1/communication-runs",
            body=_compact({"id": id, "action": "pause", "business_id": business_id}),
        )

    def cancel(self, id: str, business_id: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "PATCH",
            "/api/v1/communication-runs",
            body=_compact({"id": id, "action": "cancel", "business_id": business_id}),
        )

    def jobs(self, **filters: Any) -> KaiObject:
        return self._http.request("GET", "/api/v1/communication-jobs", query=_compact(filters))

    def attempts(self, **filters: Any) -> KaiObject:
        return self._http.request(
            "GET", "/api/v1/communication-attempts", query=_compact(filters)
        )


class _Discovery:
    def __init__(self, http: _Http):
        self._http = http

    def capabilities(self, business_id: Optional[str] = None) -> KaiObject:
        return self._http.request(
            "GET", "/api/v1/capabilities", query={"business_id": business_id}
        )

    def openapi(self) -> KaiObject:
        return self._http.request("GET", "/api/v1/openapi.json")

    def schemas(self, name: Optional[str] = None) -> KaiObject:
        return self._http.request("GET", "/api/v1/schemas", query={"name": name})

    def health(self) -> KaiObject:
        return self._http.request("GET", "/api/v1/health")


class _Account:
    def __init__(self, http: _Http):
        self._http = http

    def balance(self) -> KaiObject:
        return self._http.request("GET", "/api/v1/balance")

    def usage(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> KaiObject:
        return self._http.request(
            "GET", "/api/v1/usage", query={"start": start, "end": end, "limit": limit}
        )


class KaiCalls:
    """KaiCalls API client.

    Args:
        api_key: Your ``kc_live_...`` API key.
        base_url: API origin override (default ``https://www.kaicalls.com``).
        timeout: Per-request timeout in seconds (default 30).
        session: Optional ``requests.Session`` (useful for testing/proxies).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: Optional[requests.Session] = None,
    ):
        self._http = _Http(api_key, base_url=base_url, timeout=timeout, session=session)
        self.calls = _Calls(self._http)
        self.recordings = _Recordings(self._http)
        self.agents = _Agents(self._http)
        self.leads = _Leads(self._http)
        self.sms = _Sms(self._http)
        self.transcripts = _Transcripts(self._http)
        self.phone_numbers = _PhoneNumbers(self._http)
        self.workspaces = _Workspaces(self._http)
        self.webhooks = _Webhooks(self._http)
        self.analytics = _Analytics(self._http)
        self.evals = _Evals(self._http)
        self.events = _Events(self._http)
        self.communication_runs = _CommunicationRuns(self._http)
        self.discovery = _Discovery(self._http)
        self.account = _Account(self._http)

    def request(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Raw escape hatch for endpoints not yet wrapped, e.g.
        ``kai.request("GET", "/api/sdr/pipeline", query={"businessId": ...})``."""
        return self._http.request(method, path, query=query, body=body, headers=headers)


def signup(
    business_name: str,
    email: str,
    business_type: Optional[str] = None,
    website: Optional[str] = None,
    phone_forward_to: Optional[str] = None,
    plan_id: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> KaiObject:
    """Create a brand-new KaiCalls account (no API key required; 5/hour/IP).

    Returns the new account including ``api_key`` — store it securely.
    """
    sess = session or requests.Session()
    response = sess.request(
        "POST",
        base_url.rstrip("/") + "/api/v1/signup",
        json=_compact(
            {
                "business_name": business_name,
                "email": email,
                "business_type": business_type,
                "website": website,
                "phone_forward_to": phone_forward_to,
                "plan_id": plan_id,
            }
        ),
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    return _handle_response(response)
