from __future__ import annotations

import unittest

from nemotronos_agent.task_store import TaskStore


class TaskStoreTests(unittest.TestCase):
    def test_task_can_store_voice_memory(self) -> None:
        store = TaskStore()
        task = store.create_task("Open Notepad")

        updated = store.update_task(task.id, memory={"voice_transcript": "long note"})

        self.assertEqual(updated.memory["voice_transcript"], "long note")


if __name__ == "__main__":
    unittest.main()
