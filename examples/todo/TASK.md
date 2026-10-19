Add list_tasks(tasks, status="all", query=""):
- status all/done/pending; other values raise ValueError.
- query strips outer whitespace and matches title case-insensitively.
- filters combine, preserve input order and do not modify input.
- keep list_tasks(tasks) backwards compatible.
Add meaningful tests including combined filters and no matches.
