## Habit tracking delegation

When Kent sends a message about habits — completing a habit ("meditation
done", "did my steps", "skipped training"), asking about habit status
("how am I doing on habits?", "show my track record"), or managing habits
("add daily journaling", "pause steps habit"):

1. Delegate to felix-admin-habits:
   ```bash
   openclaw agent --agent felix-admin-habits \
     --message "<Kent's exact message>" --json --timeout 120
   ```
2. Relay the result back to Kent via WhatsApp.

Do NOT handle habit tracking yourself. felix-admin-habits has the standing
orders, Vikunja project access, and completion state logic.
