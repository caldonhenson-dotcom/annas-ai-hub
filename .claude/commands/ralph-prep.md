---
description: Prepare a Ralph Loop session — generate prd.json and progress.txt
user-invocable: true
---

Prepare a Ralph Loop autonomous coding session for the task: $ARGUMENTS

1. Break the task into atomic user stories (each completable in one fresh context window)
2. Order by dependency (independent tasks first, dependent tasks later)
3. Generate `prd.json` with structure:
```json
{
  "project": "YourProjectName",
  "task": "<task description>",
  "stories": [
    {"id": 1, "title": "...", "description": "...", "acceptance": ["..."], "status": "not-done", "depends_on": []},
  ]
}
```
4. Generate `progress.txt` with header:
```
# Ralph Loop Progress
Task: <task>
Started: <timestamp>
---
```
5. Generate `ralph.sh` shell script that loops through stories

Output all three files. Review the stories for completeness before writing.
