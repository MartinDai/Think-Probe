import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools import file_editor


class ApplyPatchToolTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace_dir = Path(self.temp_dir.name)

        patcher_thread = patch.object(file_editor, "get_thread_id", return_value="test-thread")
        patcher_workspace = patch.object(file_editor, "get_workspace_dir", return_value=self.workspace_dir)
        self.addCleanup(patcher_thread.stop)
        self.addCleanup(patcher_workspace.stop)
        patcher_thread.start()
        patcher_workspace.start()

    def _invoke(self, patch_text: str) -> str:
        return file_editor.apply_patch.invoke(
            {"operation": patch_text},
            config={"configurable": {"thread_id": "test-thread"}},
        )

    def test_apply_patch_updates_existing_file(self):
        target = self.workspace_dir / "app.py"
        target.write_text("print('old')\n", encoding="utf-8")

        result = self._invoke(
            {
                "type": "update_file",
                "path": "app.py",
                "diff": "@@\n-print('old')\n+print('new')\n",
            }
        )

        self.assertIn("Status: Success", result)
        self.assertIn("Updated: app.py", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "print('new')\n")

    def test_apply_patch_adds_new_file(self):
        result = self._invoke(
            {
                "type": "create_file",
                "path": "new_module.py",
                "diff": "VALUE = 42\n\nprint(VALUE)\n",
            }
        )

        self.assertIn("Added: new_module.py", result)
        self.assertEqual(
            (self.workspace_dir / "new_module.py").read_text(encoding="utf-8"),
            "VALUE = 42\n\nprint(VALUE)\n",
        )

    def test_apply_patch_deletes_existing_file(self):
        target = self.workspace_dir / "obsolete.txt"
        target.write_text("unused\n", encoding="utf-8")

        result = self._invoke(
            {
                "type": "delete_file",
                "path": "obsolete.txt",
                "diff": "",
            }
        )

        self.assertIn("Deleted: obsolete.txt", result)
        self.assertFalse(target.exists())

    def test_apply_patch_reports_hunk_mismatch(self):
        target = self.workspace_dir / "service.py"
        target.write_text("value = 1\n", encoding="utf-8")

        result = self._invoke(
            {
                "type": "update_file",
                "path": "service.py",
                "diff": "@@\n-value = 2\n+value = 3\n",
            }
        )

        self.assertIn("Error:", result)
        self.assertIn("Hunk did not match file contents", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "value = 1\n")

    def test_apply_patch_failure_does_not_modify_target_file(self):
        first = self.workspace_dir / "first.py"
        second = self.workspace_dir / "second.py"
        first.write_text("a = 1\n", encoding="utf-8")
        second.write_text("b = 2\n", encoding="utf-8")

        result = self._invoke(
            {
                "type": "update_file",
                "path": "second.py",
                "diff": "@@\n-b = 3\n+b = 20\n",
            }
        )

        self.assertIn("Error:", result)
        self.assertEqual(first.read_text(encoding="utf-8"), "a = 1\n")
        self.assertEqual(second.read_text(encoding="utf-8"), "b = 2\n")

    def test_apply_patch_blocks_path_escape(self):
        result = self._invoke(
            {
                "type": "create_file",
                "path": "../outside.py",
                "diff": "print('nope')\n",
            }
        )

        self.assertIn("Error:", result)
        self.assertIn("Path traversal", result)


if __name__ == "__main__":
    unittest.main()
