$ErrorActionPreference = "Stop"
& "C:\Program Files\Python312\python.exe" tooling/scripts/sync_mermaid_views.py --write
& "C:\Program Files\Python312\python.exe" tooling/scripts/validate_docs.py
