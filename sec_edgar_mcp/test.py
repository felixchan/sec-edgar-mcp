from openai import OpenAI
import os
import json


API_KEY = os.getenv("OPENAI_API_KEY", "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")

client = OpenAI(api_key=API_KEY)


def _print_section(title: str):
    print("\n" + "=" * 10 + f" {title} " + "=" * 10)


def _safe_json(obj):
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return str(obj)


def print_response_debug(r):
    _print_section("Response Meta")
    for key in [
        "id",
        "model",
        "status",
        "created_at",
        "stop_reason",
    ]:
        print(f"{key}:", getattr(r, key, None))

    usage = getattr(r, "usage", None)
    if usage:
        # usage may be a pydantic model; convert defensively
        try:
            usage_dict = (
                usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
            )
        except Exception:
            usage_dict = str(usage)
        print("usage:", _safe_json(usage_dict))

    output = getattr(r, "output", None)
    if output:
        _print_section("Output Items")
        for i, item in enumerate(output):
            itype = getattr(item, "type", None)
            print(f"[{i}] type={itype}")
            if itype == "message":
                role = getattr(item, "role", None)
                content = getattr(item, "content", None)
                print(f"  role={role}")
                if isinstance(content, list):
                    for seg in content:
                        seg_type = getattr(seg, "type", None)
                        text_val = getattr(seg, "text", None)
                        # Some SDKs use 'text', some 'output_text'
                        if isinstance(text_val, str) and text_val.strip():
                            print(f"  {seg_type}: {text_val}")
                        else:
                            # Generic fallback for non-text segments
                            try:
                                print(f"  {seg_type}: {_safe_json(seg)}")
                            except Exception:
                                pass
            elif itype in {"tool_call", "function_call"}:
                name = getattr(item, "name", None) or getattr(item, "tool_name", None)
                call_id = getattr(item, "id", None) or getattr(item, "call_id", None)
                args = getattr(item, "arguments", None) or getattr(item, "input", None)
                print(f"  tool_name={name}")
                print(f"  call_id={call_id}")
                print(f"  arguments={args}")
            elif itype in {"tool_result", "function_call_output"}:
                call_id = getattr(item, "call_id", None)
                output_val = getattr(item, "output", None) or getattr(
                    item, "content", None
                )
                print(f"  result_for_call_id={call_id}")
                print(f"  output={output_val}")

    # Convenience text, if available
    text = getattr(r, "output_text", None)
    if text:
        _print_section("Output Text")
        print(text)

    # Chat Completions fallback
    if hasattr(r, "choices") and r.choices:
        _print_section("Chat Fallback Message")
        try:
            msg = r.choices[0].message
            print("role:", getattr(msg, "role", None))
            print("content:", getattr(msg, "content", None))
            tcalls = getattr(msg, "tool_calls", None) or []
            if tcalls:
                _print_section("Chat Tool Calls")
                for tc in tcalls:
                    fn = getattr(tc, "function", None)
                    if fn:
                        print("  name:", getattr(fn, "name", None))
                        print("  arguments:", getattr(fn, "arguments", None))
        except Exception as e:
            print("(chat fallback parse error)", e)


USE_STREAMING = os.getenv("USE_STREAMING", "0").lower() in {"1", "true", "yes"}
SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp/edgar")

# Tools used for the call
tools = [
    {
        "type": "mcp",
        "server_label": "edgar-mcp",
        "server_url": SERVER_URL,
        "require_approval": "never",
    },
]

# prompt = (
#     "Analyze AAPL’s latest proxy (DEF 14A/DEFM14A). Use the MCP tool "
#     "analyze_proxy_def14a and return: filing.form, filing.accession, filing.date, "
#     "filing.url, full_text_len, and which of sections.{related_party,director_independence,"
#     "board_committees,beneficial_ownership,exclusive_forum,governance_overview}.present are true."
# )

prompt = "Find any company with a DEFM14A filed in the last 365 days. Run analyze_proxy_def14a and return the same JSON shape as above for a single ticker, plus assert {'is_transaction_proxy': filing.form == 'DEFM14A'}. Pass only if is_transaction_proxy == true and sections_present.beneficial_ownership == true."

if USE_STREAMING:
    # Live streaming view: prints tool calls and deltas as they happen.
    _print_section("Streaming Mode")
    try:
        with client.responses.stream(
            model="gpt-5-mini",
            tools=tools,
            input=prompt,
            tool_choice="auto",
            parallel_tool_calls=True,
            reasoning={"effort": "medium"},
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", None)
                # Show key milestones and tool events
                if etype in {
                    "response.created",
                    "response.completed",
                    "response.error",
                    "response.refusal.delta",
                    "response.output_text.delta",
                    "response.output_text.done",
                    "response.message.delta",
                    "response.message.completed",
                    "response.tool_call.created",
                    "response.tool_call.delta",
                    "response.tool_call.completed",
                    "response.function_call.arguments.delta",
                    "response.function_call.completed",
                }:
                    print(f"EVENT: {etype}")
                    try:
                        payload = (
                            event.model_dump()
                            if hasattr(event, "model_dump")
                            else dict(event)
                        )
                        print(_safe_json(payload))
                    except Exception:
                        print(str(event))
            final = stream.get_final_response()
            _print_section("Final Response (Streaming)")
            print_response_debug(final)
    except Exception as e:
        _print_section("Streaming Error")
        print(e)
else:
    # One-shot call with rich debug printing
    resp = client.responses.create(
        model="gpt-5-mini",
        tools=tools,
        input=prompt,
        tool_choice="auto",
        parallel_tool_calls=True,
        reasoning={"effort": "medium"},
    )
    print_response_debug(resp)
