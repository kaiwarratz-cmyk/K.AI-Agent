"""
Vollständige Tests für die drei Architektur-Verbesserungen:
1. Parallel Tool Execution
2. Streaming in ReAct Loop (stream_chat_with_tools)
3. Anthropic Prompt Cache (cache_control)
"""
import sys
import json
import threading
import time
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, ".")

# ══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 1: _is_parallel_safe / _PARALLEL_SAFE_PREFIXES
# ══════════════════════════════════════════════════════════════════════════════

class TestParallelSafeClassification(unittest.TestCase):
    """Testet ob Tools korrekt als parallel-safe oder serial klassifiziert werden."""

    def setUp(self):
        from app.main import _is_parallel_safe
        self.safe = _is_parallel_safe

    def test_parallel_safe_tools(self):
        safe_tools = [
            "web_search",
            "brave_web_search",
            "web_fetch_smart",
            "web_fetch_js",
            "web_fetch_raw",
            "fs_read_file",
            "fs_list_dir",
            "fs_search_codebase",
            "fs_index_workspace",
            "mem_get_facts",
            "mem_get_secret",
        ]
        for tool in safe_tools:
            with self.subTest(tool=tool):
                self.assertTrue(self.safe(tool), f"{tool} sollte parallel-safe sein")

    def test_serial_only_tools(self):
        serial_tools = [
            "fs_write_file",
            "fs_edit_replace",
            "fs_append",
            "sys_cmd_exec",
            "sys_python_exec",
            "web_download",
            "git_commit",
            "git_push",
            "mem_save_fact",
            "mem_delete_fact",
            "mem_save_secret",
            "mem_update_plan",
            "terminal_run",
            "terminal_background_run",
            "send_messenger_file",
        ]
        for tool in serial_tools:
            with self.subTest(tool=tool):
                self.assertFalse(self.safe(tool), f"{tool} sollte NICHT parallel-safe sein")

    def test_empty_string(self):
        from app.main import _is_parallel_safe
        self.assertFalse(_is_parallel_safe(""))
        self.assertFalse(_is_parallel_safe(None))

    def test_prefix_matching(self):
        """Stellt sicher dass Präfix-Matching korrekt funktioniert."""
        from app.main import _is_parallel_safe
        # web_fetch_smart_extended → startswith("web_fetch_smart") → True
        self.assertTrue(_is_parallel_safe("web_fetch_smart_extended"))
        # sys_python_exec_v2 → kein safe-Präfix → False
        self.assertFalse(_is_parallel_safe("sys_python_exec_v2"))


# ══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 2: Parallel Dispatch Logik (ohne echte Tool-Ausführung)
# ══════════════════════════════════════════════════════════════════════════════

class TestParallelDispatchLogic(unittest.TestCase):
    """
    Testet die Batch-Bildungslogik des Parallel Dispatchers.
    Simuliert was im ReAct-Loop passiert.
    """

    def _make_batch(self, tool_calls):
        """Repliziert die Batch-Bildungslogik aus dem ReAct-Loop."""
        from app.main import _is_parallel_safe
        _batch = []
        _found_serial = False
        for tc in tool_calls:
            tc_kind = str(tc.get("kind", "")).strip()
            if not _found_serial and _is_parallel_safe(tc_kind):
                _batch.append(tc)
            else:
                _found_serial = True
                break
        if not _batch:
            _batch = [tool_calls[0]]
        return _batch

    def test_three_parallel_searches_batched(self):
        """3× web_search → alle drei im Batch."""
        tool_calls = [
            {"kind": "web_search", "query": "A", "_tool_id": "1"},
            {"kind": "web_search", "query": "B", "_tool_id": "2"},
            {"kind": "web_search", "query": "C", "_tool_id": "3"},
        ]
        batch = self._make_batch(tool_calls)
        self.assertEqual(len(batch), 3)
        self.assertEqual([t["query"] for t in batch], ["A", "B", "C"])

    def test_serial_first_not_batched(self):
        """sys_python_exec als erster Call → nur dieser im Batch."""
        tool_calls = [
            {"kind": "sys_python_exec", "code": "print(1)", "_tool_id": "1"},
            {"kind": "web_search", "query": "X", "_tool_id": "2"},
        ]
        batch = self._make_batch(tool_calls)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["kind"], "sys_python_exec")

    def test_mixed_stops_at_first_serial(self):
        """parallel, parallel, serial → nur die ersten beiden im Batch."""
        tool_calls = [
            {"kind": "web_search", "query": "A", "_tool_id": "1"},
            {"kind": "fs_read_file", "path": "/x", "_tool_id": "2"},
            {"kind": "fs_write_file", "path": "/y", "content": "z", "_tool_id": "3"},
        ]
        batch = self._make_batch(tool_calls)
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch[0]["kind"], "web_search")
        self.assertEqual(batch[1]["kind"], "fs_read_file")

    def test_single_parallel_tool(self):
        """Ein einzelner parallel-safe Call → Batch der Größe 1."""
        tool_calls = [{"kind": "mem_get_facts", "key": "x", "_tool_id": "1"}]
        batch = self._make_batch(tool_calls)
        self.assertEqual(len(batch), 1)

    def test_parallel_execution_concurrent(self):
        """Stellt sicher dass parallele Tools WIRKLICH gleichzeitig laufen."""
        from concurrent.futures import ThreadPoolExecutor
        execution_times = []
        lock = threading.Lock()

        def fake_tool(name, delay):
            time.sleep(delay)
            with lock:
                execution_times.append((name, time.time()))

        tools = [("web_search_A", 0.05), ("web_search_B", 0.05), ("web_search_C", 0.05)]
        start = time.time()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda t: fake_tool(*t), tools))
        total = time.time() - start

        # Bei serieller Ausführung: ~0.15s. Bei paralleler: ~0.05s (+Overhead)
        self.assertLess(total, 0.12, f"Parallele Ausführung dauerte zu lang: {total:.3f}s (serial wäre ~0.15s)")
        print(f"  ✓ Parallele Ausführung: {total*1000:.0f}ms (serial wäre ~150ms)")


# ══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 3: stream_chat_with_tools + _stream_with_tools_openai
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamChatWithTools(unittest.TestCase):
    """Testet stream_chat_with_tools mit gemockter HTTP-Verbindung."""

    def _make_router(self, provider_type="openai_compatible"):
        from app.llm_router import LLMRouter
        cfg = {
            "llm": {
                "active_provider_id": "test",
                "temperature": 0.2,
            },
            "providers": {
                "test": {
                    "type": provider_type,
                    "base_url": "https://api.test.com",
                    "api_key": "test-key-123",
                    "default_model": "gpt-4",
                    "enabled": True,
                }
            }
        }
        return LLMRouter(cfg)

    def _make_sse_lines(self, chunks, tool_calls=None):
        """Erzeugt SSE-Zeilen wie sie von einer OpenAI-API kommen würden."""
        lines = []
        for chunk in chunks:
            data = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
            lines.append(f"data: {json.dumps(data)}")

        if tool_calls:
            for idx, tc in enumerate(tool_calls):
                # Erste Delta: id + name
                data = {"choices": [{"delta": {"tool_calls": [{"index": idx, "id": tc["id"], "function": {"name": tc["name"], "arguments": ""}}]}, "finish_reason": None}]}
                lines.append(f"data: {json.dumps(data)}")
                # Argument-Delta
                data = {"choices": [{"delta": {"tool_calls": [{"index": idx, "function": {"arguments": json.dumps(tc["args"])}}]}, "finish_reason": "tool_calls"}]}
                lines.append(f"data: {json.dumps(data)}")
            # Final finish
            data = {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}
            lines.append(f"data: {json.dumps(data)}")
        else:
            data = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
            lines.append(f"data: {json.dumps(data)}")

        lines.append("data: [DONE]")
        return lines

    def test_text_streaming_chunks_received(self):
        """Text-Tokens werden live via on_text_chunk callback geliefert."""
        router = self._make_router()
        received_chunks = []

        sse_lines = self._make_sse_lines(["Hallo", " ", "Welt", "!"])
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = iter(sse_lines)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_resp
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            text, tool_calls, stop = router._stream_with_tools_openai(
                messages=[{"role": "user", "content": "Test"}],
                tools=[],
                on_text_chunk=received_chunks.append,
                provider_id="test",
            )

        self.assertEqual("".join(received_chunks), "Hallo Welt!")
        self.assertEqual(text, "Hallo Welt!")
        self.assertEqual(tool_calls, [])
        self.assertEqual(stop, "stop")
        print(f"  ✓ Streaming Text: {''.join(received_chunks)!r} empfangen in {len(received_chunks)} Chunks")

    def test_tool_call_parsed_from_stream(self):
        """Tool-Calls werden aus den Streaming-Deltas korrekt zusammengesetzt."""
        router = self._make_router()

        sse_lines = self._make_sse_lines(
            ["Ich suche nach "],
            tool_calls=[{"id": "call_abc123", "name": "web_search", "args": {"query": "Python asyncio"}}]
        )
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = iter(sse_lines)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_resp
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            text, tool_calls, stop = router._stream_with_tools_openai(
                messages=[{"role": "user", "content": "Suche Python"}],
                tools=[],
                on_text_chunk=lambda _: None,
                provider_id="test",
            )

        self.assertEqual(len(tool_calls), 1)
        tc = tool_calls[0]
        self.assertEqual(tc["kind"], "web_search")
        self.assertEqual(tc["_tool_id"], "call_abc123")
        self.assertEqual(tc["query"], "Python asyncio")
        self.assertEqual(stop, "tool_calls")
        print(f"  ✓ Tool-Call aus Stream: kind={tc['kind']!r}, query={tc['query']!r}")

    def test_fallback_on_non_openai_provider(self):
        """Gemini-Provider → stream_chat_with_tools fällt auf chat_messages_with_tools zurück."""
        router = self._make_router(provider_type="gemini")

        with patch.object(router, "chat_messages_with_tools", return_value=("antwort", [], "stop")) as mock_fallback:
            result = router.stream_chat_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                on_text_chunk=lambda _: None,
            )
            mock_fallback.assert_called_once()
            self.assertEqual(result, ("antwort", [], "stop"))
        print("  ✓ Gemini-Provider: Fallback auf chat_messages_with_tools korrekt")

    def test_fallback_on_stream_error(self):
        """HTTP-Fehler im Stream → transparenter Fallback, keine Exception."""
        router = self._make_router()

        with patch.object(router, "_stream_with_tools_openai", side_effect=Exception("Netzwerkfehler")):
            with patch.object(router, "chat_messages_with_tools", return_value=("fallback", [], "stop")) as mock_fallback:
                result = router.stream_chat_with_tools(
                    messages=[{"role": "user", "content": "test"}],
                    tools=[],
                )
                mock_fallback.assert_called_once()
                self.assertEqual(result[0], "fallback")
        print("  ✓ Netzwerkfehler im Stream: Fallback ohne Exception")

    def test_chunk_callback_not_called_on_tool_only_response(self):
        """Wenn LLM nur Tool-Calls zurückgibt (kein Text), wird on_text_chunk nicht aufgerufen."""
        router = self._make_router()
        callback_calls = []

        sse_lines = self._make_sse_lines(
            [],  # kein Text
            tool_calls=[{"id": "tc_1", "name": "fs_read_file", "args": {"path": "/x"}}]
        )
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = iter(sse_lines)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_resp
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            text, tool_calls, _ = router._stream_with_tools_openai(
                messages=[],
                tools=[],
                on_text_chunk=callback_calls.append,
                provider_id="test",
            )

        self.assertEqual(callback_calls, [], "on_text_chunk sollte NICHT aufgerufen werden wenn kein Text")
        self.assertEqual(len(tool_calls), 1)
        print("  ✓ Kein Text → on_text_chunk nicht aufgerufen, Tool-Call korrekt")


# ══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 4: Anthropic Prompt Cache
# ══════════════════════════════════════════════════════════════════════════════

class TestAnthropicPromptCache(unittest.TestCase):
    """Testet ob cache_control korrekt in Anthropic-API-Calls injiziert wird."""

    def _make_router(self, model="claude-sonnet-4-6"):
        from app.llm_router import LLMRouter
        cfg = {
            "llm": {
                "active_provider_id": "anthropic",
                "temperature": 0.2,
            },
            "providers": {
                "anthropic": {
                    "type": "anthropic",
                    "base_url": "https://api.anthropic.com",
                    "api_key": "sk-ant-test",
                    "default_model": model,
                    "enabled": True,
                }
            }
        }
        return LLMRouter(cfg)

    def test_cache_control_injected_for_large_system_prompt(self):
        """System-Prompt >=4096 Chars → cache_control wird gesetzt."""
        router = self._make_router("claude-sonnet-4-6")
        large_system = "Du bist K.AI. " * 300  # >4096 chars
        self.assertGreaterEqual(len(large_system), 4096)

        messages = [
            {"role": "system", "content": large_system},
            {"role": "user", "content": "Hallo"},
        ]

        captured_payload = {}
        def mock_post(url, headers=None, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "content": [{"type": "text", "text": "antwort"}],
                "stop_reason": "end_turn",
                "usage": {"cache_creation_input_tokens": 1500, "cache_read_input_tokens": 0, "input_tokens": 1500},
            }
            return resp

        mock_client_instance = MagicMock()
        mock_client_instance.post = mock_post
        mock_client_instance.__enter__ = lambda s: s
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client_instance):
            router._msgs_with_tools_anthropic(
                base_url="https://api.anthropic.com",
                api_key="sk-ant-test",
                model="claude-sonnet-4-6",
                messages=messages,
                tools=[],
                temperature=0.2,
                timeout=30,
            )

        system = captured_payload.get("system")
        self.assertIsInstance(system, list, "system sollte eine Liste sein (strukturiert)")
        self.assertEqual(len(system), 1)
        self.assertEqual(system[0].get("type"), "text")
        self.assertIn("cache_control", system[0], "cache_control fehlt im System-Block")
        self.assertEqual(system[0]["cache_control"], {"type": "ephemeral"})
        print(f"  ✓ cache_control gesetzt für {len(large_system)}-char System-Prompt")

    def test_no_cache_control_for_small_system_prompt(self):
        """System-Prompt <4096 Chars → KEIN cache_control (zu klein für Caching)."""
        router = self._make_router("claude-sonnet-4-6")
        small_system = "Du bist K.AI."
        self.assertLess(len(small_system), 4096)

        messages = [
            {"role": "system", "content": small_system},
            {"role": "user", "content": "Hallo"},
        ]

        captured_payload = {}
        def mock_post(url, headers=None, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "content": [{"type": "text", "text": "antwort"}],
                "stop_reason": "end_turn",
            }
            return resp

        mock_client_instance = MagicMock()
        mock_client_instance.post = mock_post
        mock_client_instance.__enter__ = lambda s: s
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client_instance):
            router._msgs_with_tools_anthropic(
                base_url="https://api.anthropic.com",
                api_key="sk-ant-test",
                model="claude-sonnet-4-6",
                messages=messages,
                tools=[],
                temperature=0.2,
                timeout=30,
            )

        system = captured_payload.get("system")
        # Kleiner System-Prompt → plain string, kein cache_control
        self.assertIsInstance(system, str, "Kleiner System-Prompt sollte plain string bleiben")
        self.assertNotIn("cache_control", str(system))
        print(f"  ✓ Kein cache_control für kleinen System-Prompt ({len(small_system)} chars)")

    def test_beta_header_sent(self):
        """anthropic-beta: prompt-caching-2024-07-31 Header wird immer gesendet."""
        router = self._make_router("claude-sonnet-4-6")
        captured_headers = {}

        def mock_post(url, headers=None, json=None, **kwargs):
            if headers:
                captured_headers.update(headers)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
            }
            return resp

        mock_client_instance = MagicMock()
        mock_client_instance.post = mock_post
        mock_client_instance.__enter__ = lambda s: s
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client_instance):
            router._msgs_with_tools_anthropic(
                base_url="https://api.anthropic.com",
                api_key="sk-ant-test",
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                temperature=0.2,
                timeout=30,
            )

        self.assertIn("anthropic-beta", captured_headers)
        self.assertEqual(captured_headers["anthropic-beta"], "prompt-caching-2024-07-31")
        print(f"  ✓ anthropic-beta Header: {captured_headers['anthropic-beta']!r}")

    def test_no_cache_for_claude2(self):
        """Claude 2 unterstützt kein Caching → cache_control nicht gesetzt."""
        router = self._make_router("claude-2.1")
        large_system = "x" * 5000  # Groß genug, aber falsches Modell

        messages = [
            {"role": "system", "content": large_system},
            {"role": "user", "content": "test"},
        ]

        captured_payload = {}
        def mock_post(url, headers=None, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
            }
            return resp

        mock_client_instance = MagicMock()
        mock_client_instance.post = mock_post
        mock_client_instance.__enter__ = lambda s: s
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client_instance):
            router._msgs_with_tools_anthropic(
                base_url="https://api.anthropic.com",
                api_key="sk-ant-test",
                model="claude-2.1",
                messages=messages,
                tools=[],
                temperature=0.2,
                timeout=30,
            )

        system = captured_payload.get("system")
        # Claude 2 → plain string (kein cache_control)
        self.assertIsInstance(system, str, "Claude 2 sollte plain string system haben")
        print("  ✓ Claude 2: Kein Cache (Modell nicht unterstützt)")

    def test_cache_stats_logged_on_hit(self):
        """Cache-Hit in Response → _log_cache_stats wird aufgerufen."""
        router = self._make_router("claude-sonnet-4-6")
        large_system = "K.AI System. " * 400

        messages = [
            {"role": "system", "content": large_system},
            {"role": "user", "content": "test"},
        ]

        def mock_post(url, headers=None, json=None, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 2800,
                    "input_tokens": 100,
                },
            }
            return resp

        mock_client_instance = MagicMock()
        mock_client_instance.post = mock_post
        mock_client_instance.__enter__ = lambda s: s
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client_instance):
            with patch.object(router, "_log_cache_stats") as mock_log:
                router._msgs_with_tools_anthropic(
                    base_url="https://api.anthropic.com",
                    api_key="sk-ant-test",
                    model="claude-sonnet-4-6",
                    messages=messages,
                    tools=[],
                    temperature=0.2,
                    timeout=30,
                )
                mock_log.assert_called_once()
                usage_arg = mock_log.call_args[0][0]
                self.assertEqual(usage_arg.get("cache_read_input_tokens"), 2800)
        print("  ✓ Cache-Hit: _log_cache_stats mit 2800 cache_read_input_tokens aufgerufen")


# ══════════════════════════════════════════════════════════════════════════════
# TEST GROUP 5: _history_to_anthropic — tool role Handling
# ══════════════════════════════════════════════════════════════════════════════

class TestHistoryToAnthropicToolRole(unittest.TestCase):
    """Stellt sicher dass role='tool' History-Einträge korrekt konvertiert werden."""

    def test_single_tool_result_converted(self):
        from app.llm_router import LLMRouter
        messages = [
            {"role": "assistant", "content": "", "_tool_calls": [
                {"kind": "web_search", "_tool_id": "tc_1", "query": "test"}
            ]},
            {"role": "tool", "_tool_id": "tc_1", "content": "Suchergebnis XYZ"},
        ]
        system, converted = LLMRouter._history_to_anthropic(messages)

        # Assistent-Turn mit tool_use Block
        self.assertEqual(converted[0]["role"], "assistant")
        self.assertIsInstance(converted[0]["content"], list)
        tool_use_block = converted[0]["content"][0]
        self.assertEqual(tool_use_block["type"], "tool_use")
        self.assertEqual(tool_use_block["id"], "tc_1")

        # Tool-Result-Turn als user mit tool_result Block
        self.assertEqual(converted[1]["role"], "user")
        self.assertIsInstance(converted[1]["content"], list)
        tool_result_block = converted[1]["content"][0]
        self.assertEqual(tool_result_block["type"], "tool_result")
        self.assertEqual(tool_result_block["tool_use_id"], "tc_1")
        self.assertEqual(tool_result_block["content"], "Suchergebnis XYZ")
        print("  ✓ Einzel-Tool-Result korrekt in Anthropic-Format konvertiert")

    def test_multiple_tool_results_merged(self):
        """Mehrere aufeinanderfolgende tool-Results werden in einen user-Block gemergt."""
        from app.llm_router import LLMRouter
        messages = [
            {"role": "assistant", "content": "", "_tool_calls": [
                {"kind": "web_search", "_tool_id": "tc_1", "query": "A"},
                {"kind": "web_search", "_tool_id": "tc_2", "query": "B"},
            ]},
            {"role": "tool", "_tool_id": "tc_1", "content": "Ergebnis A"},
            {"role": "tool", "_tool_id": "tc_2", "content": "Ergebnis B"},
        ]
        system, converted = LLMRouter._history_to_anthropic(messages)

        # Alle tool_results sollten im selben user-Turn sein
        user_turns = [m for m in converted if m["role"] == "user"]
        self.assertEqual(len(user_turns), 1, "Alle tool_results sollten in einem user-Turn sein")
        self.assertEqual(len(user_turns[0]["content"]), 2)
        ids = [b["tool_use_id"] for b in user_turns[0]["content"]]
        self.assertIn("tc_1", ids)
        self.assertIn("tc_2", ids)
        print("  ✓ Mehrere Tool-Results in einem user-Turn gemergt")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("K.AI Architektur-Verbesserungen — Vollständiger Test")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_groups = [
        (TestParallelSafeClassification, "1. Parallel-Safe Klassifizierung"),
        (TestParallelDispatchLogic,       "2. Parallel Dispatch Logik"),
        (TestStreamChatWithTools,         "3. stream_chat_with_tools"),
        (TestAnthropicPromptCache,        "4. Anthropic Prompt Cache"),
        (TestHistoryToAnthropicToolRole,  "5. History → Anthropic Format"),
    ]

    for cls, name in test_groups:
        print(f"\n{'─' * 70}")
        print(f"  {name}")
        print(f"{'─' * 70}")
        group_suite = loader.loadTestsFromTestCase(cls)
        runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w") if False else None)
        result = unittest.TextTestRunner(verbosity=2, stream=__import__("sys").stdout).run(group_suite)
        suite.addTests(group_suite)

    print(f"\n{'=' * 70}")
    print("Fertig.")
