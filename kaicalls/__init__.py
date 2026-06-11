"""Official KaiCalls SDK — give your AI agent a phone.

Usage::

    from kaicalls import KaiCalls

    kai = KaiCalls(api_key="kc_live_...")
    call = kai.calls.create(agent_id="uuid-abc123", to="+15125551234", name="John Smith")
    result = kai.calls.wait(call.id)
    print(result.summary)

Docs: https://www.kaicalls.com/docs/api
"""

from .client import KaiCalls, KaiCallsError, KaiObject, signup

__all__ = ["KaiCalls", "KaiCallsError", "KaiObject", "signup"]
__version__ = "0.1.0"
