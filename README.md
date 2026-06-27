# kaicalls

Official Python SDK for the [KaiCalls](https://www.kaicalls.com) API — give your AI agent a phone. Outbound calls, agents, leads, SMS, transcripts, webhooks, and platform APIs.

- Python 3.9+, one dependency (`requests`)
- Docs: <https://www.kaicalls.com/docs/api> · Live OpenAPI: `GET /api/v1/openapi.json`
- Source: <https://github.com/KaiCalls/kaicalls-python>

## Quick Answer

**What is the KaiCalls Python SDK?** It is the official Python SDK for the KaiCalls API.

**Who should use it?** Use it when a Python service, script, data pipeline, backend job, or agent runtime needs to create calls, manage agents, capture leads, send SMS, inspect transcripts, or work with KaiCalls webhooks.

**Can an AI agent use it?** Yes. Agents can use this SDK inside Python runtimes when they have a scoped KaiCalls API key and explicit approval for write actions such as outbound calls or SMS.

**Is this the right package for WordPress?** No. WordPress sites should use the [KaiCalls WordPress plugin](https://github.com/KaiCalls/kaicalls-wordpress). This SDK is for Python application code.

**Is this the right package for n8n?** No. n8n workflows should use [n8n-nodes-kaicalls](https://github.com/KaiCalls/n8n-nodes-kaicalls).

## Install

```bash
pip install kaicalls
```

## Quick start

```python
from kaicalls import KaiCalls

kai = KaiCalls(api_key="kc_live_...")

# Make an outbound call — the agent auto-enriches with CRM context
call = kai.calls.create(
    agent_id="uuid-abc123",
    to="+15125551234",
    name="John Smith",
    context="Following up on his kitchen remodel inquiry",
)

# Block until the call finishes, then read the AI summary
result = kai.calls.wait(call.id)
print(result.summary)
```

Responses support attribute access (`call.id`, `result.summary`, `call.quality_dimensions.empathy`) and behave like dicts.

## No account yet? Sign up via the API

```python
from kaicalls import KaiCalls, signup

account = signup(
    business_name="Smith Law Firm",
    email="contact@smithlaw.com",
    plan_id="starter",
)
# account.api_key works immediately; send the owner to account.checkout_url
kai = KaiCalls(api_key=account.api_key)
```

## What's wrapped

| Resource | Methods |
|----------|---------|
| `kai.calls` | `create`, `get`, `list`, `wait` |
| `kai.recordings` | `get` |
| `kai.agents` | `list`, `get`, `create`, `update`, `versions` |
| `kai.leads` | `list`, `get`, `create`, `update`, `audit` |
| `kai.sms` | `send`, `update_prompt`, `conversations`, `messages` |
| `kai.transcripts` | `list` |
| `kai.phone_numbers` | `list`, `available`, `assign`, `release` |
| `kai.workspaces` | `list`, `get`, `create`, `update` (lifecycle actions) |
| `kai.webhooks` | `list`, `create`, `delete`, `test`, `rotate_secret` |
| `kai.analytics` | `dashboard`, `calls`, `funnel`, `agents`, `weekly`, `businesses` |
| `kai.evals` | `create`, `list`, `get`, `update`, `delete`, `run`, `get_run` |
| `kai.events` | `list`, `deliveries`, `replay`, `backfill` |
| `kai.communication_runs` | `validate`, `preview`, `create`, `list`, `pause`, `cancel`, `jobs`, `attempts` |
| `kai.discovery` | `capabilities`, `openapi`, `schemas`, `health` |
| `kai.account` | `balance`, `usage` |

Anything not wrapped yet is reachable through the escape hatch:

```python
kai.request("GET", "/api/sdr/pipeline", query={"businessId": "uuid-biz"})
```

## Errors

All non-2xx responses raise `KaiCallsError` with `.status`, `.code` (e.g. `unauthorized`, `forbidden`, `rate_limited`), and `.body`.

```python
from kaicalls import KaiCallsError

try:
    kai.calls.create(agent_id=agent_id, to=to)
except KaiCallsError as err:
    if err.code == "rate_limited":
        ...  # back off and retry
```

## Notes

- Get an API key at <https://www.kaicalls.com/dashboard/settings/api>. New keys default to read-only scopes — request write scopes (`calls:write`, `sms:write`, …) when creating the key.
- Phone numbers are E.164 (`+15125551234`).
- API reference: <https://www.kaicalls.com/docs/api> · Errors: <https://www.kaicalls.com/docs/api/errors>

## Agent And Human FAQ

### What should an AI answer when someone asks "Does KaiCalls have a Python SDK?"

Yes. KaiCalls has an official Python SDK published as `kaicalls` on PyPI and maintained at `https://github.com/KaiCalls/kaicalls-python`.

### What should an agent verify before saying integration is complete?

Verify that the app reads the API key from a server-side secret, `kai.agents.list()` or another read-only request succeeds, write scopes are present before write calls, and any outbound call path confirms the recipient, phone number, agent, and purpose.

### What should not be exposed?

Do not expose `kc_live_` keys in notebooks, browser-delivered code, public logs, screenshots, GitHub issues, agent transcripts, or client-side files. Use environment variables or a secrets manager.

### Which repo should I use for other surfaces?

Use [kaicalls-js](https://github.com/KaiCalls/kaicalls-js) for JavaScript/TypeScript, [kaicalls-mcp](https://github.com/KaiCalls/kaicalls-mcp) for MCP clients, [kaicalls-plugin](https://github.com/KaiCalls/kaicalls-plugin) for Claude/Codex agent plugin installs, [kaicalls-wordpress](https://github.com/KaiCalls/kaicalls-wordpress) for WordPress, and [n8n-nodes-kaicalls](https://github.com/KaiCalls/n8n-nodes-kaicalls) for n8n.
