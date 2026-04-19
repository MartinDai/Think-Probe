import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.service import context_compaction_service as service


class ContextCompactionServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.runtime_dir = Path(self.temp_dir.name)

    def test_prepare_messages_for_model_compacts_and_persists_summary(self):
        messages = [
            HumanMessage(content="你必须保留结构化摘要，不要丢掉用户约束。"),
            AIMessage(content="决定采用 JSON schema 做 summary。"),
            ToolMessage(content="Command failed with timeout", tool_call_id="tool-1", name="bash"),
            HumanMessage(content="还有一个开放问题？需要确认 recent window 应该保留几轮。"),
            AIMessage(content="下一步：实现 token 估算和自动压缩。"),
        ]

        llm_response = AIMessage(
            content=json.dumps(
                {
                    "task": "你必须保留结构化摘要，不要丢掉用户约束。",
                    "constraints": ["你必须保留结构化摘要，不要丢掉用户约束。"],
                    "decisions": ["决定采用 JSON schema 做 summary。"],
                    "rejected_options": [],
                    "open_questions": ["还有一个开放问题？需要确认 recent window 应该保留几轮。"],
                    "recent_failures": ["tool: Command failed with timeout"],
                    "artifacts": [{"type": "tool", "id": "bash", "why_it_matters": "Command failed with timeout"}],
                    "next_steps": ["下一步：实现 token 估算和自动压缩。"],
                },
                ensure_ascii=False,
            )
        )

        with patch.object(service, "RUNTIME_DIR", self.runtime_dir), \
             patch.object(service, "DEFAULT_MAX_CONTEXT_TOKENS", 120), \
             patch.object(service, "DEFAULT_WARNING_RATIO", 0.5), \
             patch.object(service, "DEFAULT_COMPACT_RATIO", 0.6), \
             patch.object(service, "DEFAULT_RECENT_MESSAGE_COUNT", 2), \
             patch.object(service, "invoke_with_retry", return_value=llm_response):
            prepared = service.prepare_messages_for_model("conv-1", messages)

        self.assertEqual(prepared, messages[-2:])

        state_path = self.runtime_dir / service.CONVERSATIONS_DIR / "conv-1" / service.SESSION_STATE_FILE
        summary_path = self.runtime_dir / service.CONVERSATIONS_DIR / "conv-1" / service.ROLLING_SUMMARY_FILE
        self.assertTrue(state_path.exists())
        self.assertTrue(summary_path.exists())

        state = json.loads(state_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(state["status"], "compacted")
        self.assertTrue(state["should_compact"])
        self.assertEqual(state["kept_message_count"], 2)
        self.assertEqual(summary["task"], "你必须保留结构化摘要，不要丢掉用户约束。")
        self.assertIn("你必须保留结构化摘要，不要丢掉用户约束。", summary["constraints"])
        self.assertIn("决定采用 JSON schema 做 summary。", summary["decisions"])
        self.assertTrue(any("timeout" in item.lower() for item in summary["recent_failures"]))
        self.assertEqual(summary["artifacts"][0]["id"], "bash")

    def test_prepare_messages_for_model_keeps_history_when_under_threshold(self):
        messages = [
            HumanMessage(content="简短问题"),
            AIMessage(content="简短回答"),
        ]

        with patch.object(service, "RUNTIME_DIR", self.runtime_dir), \
             patch.object(service, "DEFAULT_MAX_CONTEXT_TOKENS", 1000), \
             patch.object(service, "DEFAULT_WARNING_RATIO", 0.7), \
             patch.object(service, "DEFAULT_COMPACT_RATIO", 0.85), \
             patch.object(service, "DEFAULT_RECENT_MESSAGE_COUNT", 3), \
             patch.object(service, "invoke_with_retry") as mocked_invoke:
            prepared = service.prepare_messages_for_model("conv-2", messages)
            state = service.load_session_state("conv-2")
            summary = service.load_rolling_summary("conv-2")

        self.assertEqual(prepared, messages)
        self.assertEqual(state["status"], "normal")
        self.assertFalse(state["should_compact"])
        self.assertEqual(summary["task"], "")
        mocked_invoke.assert_not_called()

    def test_build_compaction_prompt_renders_structured_sections(self):
        with patch.object(service, "RUNTIME_DIR", self.runtime_dir):
            service.save_session_state(
                "conv-3",
                {
                    "status": "warning",
                    "estimated_total_tokens": 900,
                    "max_context_tokens": 1000,
                },
            )
            service.save_rolling_summary(
                "conv-3",
                {
                    "task": "实现阶段 1 和阶段 2",
                    "constraints": ["不要丢失用户约束"],
                    "decisions": ["采用结构化 schema"],
                    "recent_failures": ["tool: timeout"],
                    "next_steps": ["补测试"],
                },
            )
            prompt = service.build_compaction_prompt("conv-3")

        self.assertIn("# Conversation Memory", prompt)
        self.assertIn("实现阶段 1 和阶段 2", prompt)
        self.assertIn("不要丢失用户约束", prompt)
        self.assertIn("采用结构化 schema", prompt)
        self.assertIn("补测试", prompt)

    def test_summarize_messages_falls_back_to_heuristic_when_llm_fails(self):
        messages = [
            HumanMessage(content="你必须保留这个约束。"),
            AIMessage(content="决定采用结构化输出。"),
            ToolMessage(content="Execution failed: timeout", tool_call_id="tool-1", name="bash"),
        ]

        with patch.object(service, "invoke_with_retry", side_effect=RuntimeError("llm unavailable")):
            summary = service.summarize_messages(messages, None)

        self.assertEqual(summary["task"], "你必须保留这个约束。")
        self.assertIn("你必须保留这个约束。", summary["constraints"])
        self.assertIn("决定采用结构化输出。", summary["decisions"])
        self.assertTrue(any("timeout" in item.lower() for item in summary["recent_failures"]))


if __name__ == "__main__":
    unittest.main()
