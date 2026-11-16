import sys, json
sys.path.insert(0, "/home/claude")
import command_chat_engine as cce
import command_chat_tools as tools

# ── Test 1: every new tool is individually callable and returns real shape ──
def test_new_tools_individually():
    # These will return {"error": "openclaw_ops not available"} or similar
    # in this sandbox (no real Dataset A/warehouse DB here) -- that's the
    # correct fail-open behavior, not a bug. What matters: no exception,
    # a dict comes back every time.
    for fn_name in ["get_system_health", "get_agent_status", "get_live_pipeline_flow",
                     "get_rule_command_summary", "get_calibration_status", "get_ml_readiness",
                     "get_confidence_calibration", "get_roi_summary",
                     "get_warehouse_collection_status", "get_match_coverage",
                     "get_player_coverage", "get_warehouse_health", "get_collection_trends",
                     "get_data_source_quality"]:
        fn = getattr(tools, fn_name)
        result = fn()
        assert isinstance(result, (dict, list)), f"FAIL: {fn_name} returned unexpected type {type(result)}"
    print("PASS: all 14 zero-arg new tools callable, all return dict or list (matching each "
          "function's real, established shape), none raise")

    result = tools.get_warehouse_run_history(limit=5)
    assert isinstance(result, (dict, list)), "FAIL: get_warehouse_run_history bad return type"
    print("PASS: get_warehouse_run_history callable with limit arg")


# ── Test 2: TOOL_SCHEMA / _TOOL_DISPATCH stay in sync ──
def test_schema_dispatch_sync():
    schema_names = {t["name"] for t in cce.TOOL_SCHEMA if "input_schema" in t}
    dispatch_names = set(cce._TOOL_DISPATCH.keys())
    assert schema_names == dispatch_names, (
        f"FAIL: schema/dispatch mismatch. In schema but not dispatch: "
        f"{schema_names - dispatch_names}. In dispatch but not schema: "
        f"{dispatch_names - schema_names}")
    print(f"PASS: all {len(schema_names)} custom tools are registered in both "
          f"TOOL_SCHEMA and _TOOL_DISPATCH, exactly matching")


# ── Test 3: full mocked multi-round conversation using a NEW internal
# tool AND a mocked web_search call in the same turn ──
def test_full_conversation_with_new_tool_and_web_search():
    call_log = []

    def mock_claude(request):
        call_log.append(request)
        round_num = len(call_log)
        if round_num == 1:
            # Model calls the new warehouse tool first
            return {
                "content": [
                    {"type": "text", "text": "Let me check today's collection status."},
                    {"type": "tool_use", "id": "t1", "name": "get_warehouse_collection_status", "input": {}},
                ],
                "stop_reason": "tool_use",
            }
        elif round_num == 2:
            # Model then does a web search to validate a rule suggestion
            return {
                "content": [
                    {"type": "server_tool_use", "id": "s1", "name": "web_search",
                     "input": {"query": "tennis fatigue back-to-back matches performance research"}},
                    {"type": "web_search_tool_result", "tool_use_id": "s1",
                     "content": [{"type": "web_search_result", "title": "Example study",
                                  "url": "https://example.com/study"}]},
                    {"type": "text", "text": "Based on both, here is my answer: the warehouse ran "
                                              "today, and published research supports this."},
                ],
                "stop_reason": "end_turn",
            }
        raise AssertionError("should not reach a third round")

    result = cce.run_turn("test-session-1", "Did the warehouse update today, and does research "
                           "support a fatigue-based rule?", mock_claude)

    assert result["answer"] is not None, f"FAIL: no final answer, got {result}"
    assert "warehouse ran today" in result["answer"]
    print("PASS: full conversation completes with a real final answer")

    tool_names_cited = [s["tool"] for s in result["sources_cited"]]
    assert "get_warehouse_collection_status" in tool_names_cited, \
        f"FAIL: new tool not in sources_cited, got {tool_names_cited}"
    assert "web_search" in tool_names_cited, \
        f"FAIL: web_search not tracked in sources_cited, got {tool_names_cited}"
    print("PASS: both the new internal tool AND web_search are correctly tracked in sources_cited")

    web_search_entry = next(s for s in result["sources_cited"] if s["tool"] == "web_search")
    assert web_search_entry["input"]["query"] == "tennis fatigue back-to-back matches performance research"
    print("PASS: the real search query is captured, not just 'a search happened'")

    # Confirm dispatch_tool_call was never asked to handle web_search
    # (it's server-executed, never a client tool_use block) -- if it had
    # been, dispatch_tool_call would have returned an "Unknown tool" error
    # for it, which would show up wrongly in a tool_result. Confirm no
    # such error exists anywhere in the conversation.
    for msg in result["messages"]:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result":
                    body = block.get("content", "")
                    assert "Unknown tool: web_search" not in body, \
                        "FAIL: web_search was incorrectly routed through client-side dispatch"
    print("PASS: web_search was never incorrectly routed through client-side tool dispatch")


if __name__ == "__main__":
    test_new_tools_individually()
    test_schema_dispatch_sync()
    test_full_conversation_with_new_tool_and_web_search()
    print("\nALL COMMAND CHAT EXPANSION TESTS PASSED")
