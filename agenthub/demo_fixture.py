"""Generate the bundled synthetic demo without shipping developer fixture folders."""
from pathlib import Path

# This is synthetic example content, never user/account data.
FILES = {'.gitignore': '__pycache__/\n*.pyc\n', 'AGENTS.md': 'Edit only app/, tests/ and README.md. Do not edit these instructions.\nNo package install, subagents, external messaging, commits, pushes, merges or publishing.\nKeep functions backwards compatible and run the existing unittest suite.\n', 'README.md': '# Todo demo\nPython standard library only. Keep list_tasks(tasks) backwards compatible.\nTest: python -m unittest discover -s tests -v.\n', 'TASK.md': 'Add list_tasks(tasks, status="all", query=""):\n- status all/done/pending; other values raise ValueError.\n- query strips outer whitespace and matches title case-insensitively.\n- filters combine, preserve input order and do not modify input.\n- keep list_tasks(tasks) backwards compatible.\nAdd meaningful tests including combined filters and no matches.\n', 'app/tasks.py': '"""Starter for an isolated Agent Hub workflow."""\n\ndef list_tasks(tasks):\n    """Return a new list of tasks while preserving the original task records."""\n    return list(tasks)\n', 'tests/test_tasks.py': 'import unittest\nfrom app.tasks import list_tasks\n\nclass TasksTests(unittest.TestCase):\n    def test_copy(self):\n        """Verify copy."""\n        tasks = [{\'title\': \'Demo\', \'done\': False}]\n        self.assertEqual(list_tasks(tasks), tasks)\n        self.assertIsNot(list_tasks(tasks), tasks)\n\n    def test_empty(self):\n        """Verify empty."""\n        self.assertEqual(list_tasks([]), [])\n'}


def write_demo(target):
    """Create a new synthetic demo directory and refuse to overwrite existing files."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    for name, content in FILES.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    return target
