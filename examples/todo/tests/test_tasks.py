import unittest
from app.tasks import list_tasks

class TasksTests(unittest.TestCase):
    def test_copy(self):
        tasks = [{'title': 'Demo', 'done': False}]
        self.assertEqual(list_tasks(tasks), tasks)
        self.assertIsNot(list_tasks(tasks), tasks)

    def test_empty(self):
        self.assertEqual(list_tasks([]), [])
