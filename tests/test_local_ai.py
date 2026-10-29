import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.local_ai import LocalOllamaAssistant
from core.tools import Tool, ToolRegistry
from tools.workspace import WorkspaceSearch


class LocalOllamaAssistantTests(unittest.TestCase):
    def test_returns_a_local_model_chat_answer(self):
        registry = ToolRegistry()
        chat = Mock(return_value={"message": {"content": "A concise local answer."}})
        assistant = LocalOllamaAssistant(registry, chat=chat)

        self.assertEqual(assistant.respond("What is a task list?"), "A concise local answer.")
        request = chat.call_args.args[0]
        self.assertEqual(request["model"], "llama3.2:3b")
        self.assertFalse(request["stream"])
        self.assertEqual(request["messages"][-1], {"role": "user", "content": "What is a task list?"})

    def test_follow_up_uses_only_recent_memory_and_start_over_clears_it(self):
        registry = ToolRegistry()
        chat = Mock(
            side_effect=(
                {"message": {"content": "It keeps reminders together."}},
                {"message": {"content": "Because it is easier to find them."}},
                {"message": {"content": "A local assistant."}},
            )
        )
        assistant = LocalOllamaAssistant(registry, chat=chat)

        assistant.respond("What is a reminder list?")
        assistant.respond("Why?")

        previous = chat.call_args_list[1].args[0]["messages"]
        self.assertEqual(previous[1], {"role": "assistant", "content": "It keeps reminders together."})
        self.assertEqual(previous[-1]["content"], "Why?")
        memory = [item["content"] for item in assistant._history]
        self.assertNotIn("What is a reminder list?", memory)
        self.assertNotIn("Why?", memory)
        self.assertIn("cleared", assistant.respond("start over").casefold())
        assistant.respond("What is Mercury?")
        fresh = chat.call_args_list[-1].args[0]["messages"]
        self.assertEqual(len(fresh), 2)
        self.assertEqual(fresh[-1]["content"], "What is Mercury?")

    def test_executes_one_registered_tool_then_asks_model_to_explain_result(self):
        registry = ToolRegistry()
        registry.register(Tool("lookup", "Look up a phrase.", {"query": "string"}, "run", lambda query: f"Found {query}"))
        calls = []
        responses = iter(
            (
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"function": {"name": "lookup", "arguments": {"query": "blue river"}}}],
                    }
                },
                {"message": {"content": "The files mention a blue river."}},
            )
        )

        def fake_chat(body):
            calls.append(body)
            return next(responses)

        assistant = LocalOllamaAssistant(registry, chat=fake_chat)

        self.assertEqual(assistant.respond("Search my files for blue river"), "The files mention a blue river.")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["tools"][0]["function"]["name"], "lookup")
        self.assertNotIn("tools", calls[1])
        self.assertEqual(calls[1]["messages"][-2]["role"], "tool")
        self.assertEqual(calls[1]["messages"][-2]["content"], "Found blue river")
        self.assertIn("plain text", calls[1]["messages"][-1]["content"])

    def test_refuses_unknown_or_invalid_tool_calls(self):
        for name, arguments in (
            ("not_registered", {"query": "text"}),
            ("lookup", {"query": "text", "extra": "value"}),
            ("lookup", {"query": 123}),
        ):
            registry = ToolRegistry()
            registry.register(Tool("lookup", "Look up a phrase.", {"query": "string"}, "run", Mock()))
            chat = Mock(
                return_value={
                    "message": {
                        "tool_calls": [{"function": {"name": name, "arguments": arguments}}]
                    }
                }
            )
            assistant = LocalOllamaAssistant(registry, chat=chat)

            self.assertIn("run it", assistant.respond("do the lookup"))
            chat.assert_called_once()

    def test_refuses_remote_model_endpoint(self):
        with self.assertRaisesRegex(ValueError, "localhost"):
            LocalOllamaAssistant(ToolRegistry(), base_url="https://example.com")

    def test_workspace_question_is_searched_before_the_model_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("## Run\n\npython main.py\n", encoding="utf-8")
            registry = ToolRegistry()
            registry.register(
                Tool(
                    "search_workspace",
                    "Find text files.",
                    {"query": "string"},
                    "run",
                    WorkspaceSearch(root).search,
                )
            )
            chat = Mock(return_value={"message": {"content": "Run `python main.py`."}})
            assistant = LocalOllamaAssistant(registry, chat=chat)

            self.assertEqual(
                assistant.respond("What does the README say about how to start Mercury voice mode?"),
                "Run `python main.py`.",
            )

        request = chat.call_args.args[0]
        self.assertNotIn("tools", request)
        self.assertIn("README.md:1: ## Run", request["messages"][-1]["content"])
        self.assertIn("python main.py", request["messages"][-1]["content"])

    def test_reports_unavailable_local_service_without_logging_user_text(self):
        registry = ToolRegistry()
        assistant = LocalOllamaAssistant(registry, chat=Mock(side_effect=OSError("offline")))

        self.assertIn("isn't available", assistant.respond("private question text"))


if __name__ == "__main__":
    unittest.main()
