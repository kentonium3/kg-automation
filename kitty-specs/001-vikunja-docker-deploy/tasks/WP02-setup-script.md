---
work_package_id: WP02
title: Automated Setup Script
lane: planned
dependencies: [WP01]
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-007
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
- T011
- T012
- T013
- T014
phase: Phase 2 - Configuration
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
review_feedback: ''
history:
- timestamp: '2026-03-26T06:31:38Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP02 – Automated Setup Script

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For stacked WPs it may point at another WP branch.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

**Implementation command**: `spec-kitty implement WP02 --base WP01`

---

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status`. If it says `has_feedback`, read `review_feedback` first.
- **You must address all feedback** before your work is complete.

---

## Objectives & Success Criteria

Create `scripts/vikunja/setup_vikunja.py` — an idempotent Python script that configures a running Vikunja instance with the correct project hierarchy, identity labels, and saved filters via the REST API.

**Success**:
- First run creates all 9 projects, 2 labels, and 3 saved filters
- Second run produces no duplicates and no errors
- Script authenticates interactively (username/password → JWT)
- No credentials persisted or committed

## Context & Constraints

- **SSH access**: `ssh office2-claude` only
- **Vikunja must be running** (WP01 complete) before testing this script
- **API base URL**: `http://100.92.197.90:3456/api/v1` (or `http://localhost:3456/api/v1` from office2)
- **Data model**: `kitty-specs/001-vikunja-docker-deploy/data-model.md`
- **Research**: `kitty-specs/001-vikunja-docker-deploy/research.md` (see R-004, R-006)
- **Constitution**: No credentials in code. Interactive auth only.

**Dependencies**: Python 3.11+ and `requests` library must be available on office2. If `requests` is not installed, present `pip install requests` to Kent or use the standard library `urllib` as fallback.

## Subtasks & Detailed Guidance

### Subtask T008 – Create setup_vikunja.py Skeleton

**Purpose**: Establish the script structure with argument parsing, configuration, and main flow.

**Steps**:
1. Create `scripts/vikunja/setup_vikunja.py`
2. Add shebang: `#!/usr/bin/env python3`
3. Structure:
   ```python
   import argparse
   import getpass
   import requests
   import sys
   import time

   VIKUNJA_URL = "http://localhost:3456/api/v1"

   def parse_args():
       parser = argparse.ArgumentParser(description="Configure Vikunja project structure")
       parser.add_argument("--url", default=VIKUNJA_URL, help="Vikunja API base URL")
       return parser.parse_args()

   def main():
       args = parse_args()
       wait_for_api(args.url)
       token = authenticate(args.url)
       create_projects(args.url, token)
       create_labels(args.url, token)
       create_filters(args.url, token)
       print("Setup complete.")

   if __name__ == "__main__":
       main()
   ```
4. Make executable: `chmod +x scripts/vikunja/setup_vikunja.py`

**Files**: `scripts/vikunja/setup_vikunja.py` (new file).
**Parallel?**: No — skeleton needed before other subtasks.

### Subtask T009 – Implement JWT Authentication

**Purpose**: Authenticate to the Vikunja API using interactive username/password input.

**Steps**:
1. Prompt for credentials:
   ```python
   def authenticate(base_url):
       username = input("Vikunja username: ")
       password = getpass.getpass("Vikunja password: ")
       resp = requests.post(f"{base_url}/login", json={
           "username": username,
           "password": password
       })
       resp.raise_for_status()
       token = resp.json().get("token")
       if not token:
           print("Error: No token in response", file=sys.stderr)
           sys.exit(1)
       return token
   ```
2. Return the JWT token for use in subsequent API calls
3. Create a helper for authenticated requests:
   ```python
   def api_headers(token):
       return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
   ```

**Files**: `scripts/vikunja/setup_vikunja.py` (add functions).
**Parallel?**: No — needed by T010-T013.
**Notes**: The token is held in memory only. Never write it to disk or log it.

### Subtask T010 – Implement Idempotent Project Hierarchy Creation

**Purpose**: Create the project structure defined in the data model, skipping any that already exist.

**Steps**:
1. Define the project hierarchy as a data structure:
   ```python
   PROJECTS = [
       {"name": "Everyday", "children": [
           {"name": "Inbox"},
           {"name": "Someday"},
       ]},
       {"name": "Personal Growth & Transformation"},
       {"name": "Business Acquisition", "children": [
           {"name": "CT-90day"},
       ]},
       {"name": "Health & Conditioning"},
       {"name": "Intentional LLC"},
       {"name": "Metal Casework"},
   ]
   ```
2. Fetch existing projects: `GET /api/v1/projects`
3. For each top-level project:
   - Check if a project with that name already exists
   - If not, create via `POST /api/v1/projects` with `{"title": name}`
   - Capture the returned project ID
4. For child projects:
   - Check if a project with that name exists under the parent
   - If not, create via `PUT /api/v1/projects/{parent_id}/projects` or set `parent_project_id` in the POST body (check API docs for correct endpoint)
   - Capture the returned project ID

**Files**: `scripts/vikunja/setup_vikunja.py` (add function).
**Parallel?**: Yes — can be developed alongside T011 after T008/T009.
**Notes**:
- Parent projects must be created before children (need parent ID for the child)
- Match by exact name (case-sensitive)
- Log each action: "Created project: X" or "Project already exists: X"

### Subtask T011 – Implement Idempotent Label Creation

**Purpose**: Create `personal` and `intentional` identity labels, skipping if they already exist.

**Steps**:
1. Define labels:
   ```python
   LABELS = [
       {"title": "personal", "hex_color": "#2196f3"},   # blue
       {"title": "intentional", "hex_color": "#4caf50"}, # green
   ]
   ```
2. Fetch existing labels: `GET /api/v1/labels`
3. For each label:
   - Check if a label with that title already exists
   - If not, create via `PUT /api/v1/labels` with `{"title": title, "hex_color": color}`
4. Log each action

**Files**: `scripts/vikunja/setup_vikunja.py` (add function).
**Parallel?**: Yes — can be developed alongside T010 after T008/T009.
**Notes**: Colors should be visually distinct. The exact API endpoint for label creation may be `PUT /api/v1/labels` or `POST /api/v1/labels` — check the Vikunja API docs for the pinned version.

### Subtask T012 – Verify Saved Filter Syntax

**Purpose**: Confirm that the filter expressions work with the pinned Vikunja version before implementing filter creation.

**Steps**:
1. With Vikunja running (WP01 complete), test filter creation via the API:
   ```bash
   curl -X POST http://localhost:3456/api/v1/filters \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"title": "test-filter", "filters": {"filter_by": ["due_date"], "filter_comparator": ["less"], "filter_value": ["now"], "filter_concat": "and"}}'
   ```
2. Check the response for success or error
3. If the filter format differs from expected, document the correct format
4. Delete the test filter after verification
5. Record the verified filter syntax for use in T013

**Files**: None — verification step.
**Parallel?**: No — must complete before T013.
**Notes**: Vikunja's filter API changed significantly between versions. The filter body may use:
- Simple expression format: `{"filter": "due_date < now && done = false"}`
- Structured format: `{"filters": {"filter_by": [...], "filter_comparator": [...], ...}}`
Check the API documentation for the pinned version. The func-spec syntax (`due_date <= now/d && done = false`) is illustrative — the actual API format must be discovered here.

### Subtask T013 – Implement Idempotent Saved Filter Creation

**Purpose**: Create Today, Upcoming, and Overdue saved filters using the syntax verified in T012.

**Steps**:
1. Define filters using the syntax confirmed in T012:
   ```python
   FILTERS = [
       {"title": "Today", "filter": "<verified syntax for tasks due today>"},
       {"title": "Upcoming", "filter": "<verified syntax for tasks due within 14 days>"},
       {"title": "Overdue", "filter": "<verified syntax for past-due tasks>"},
   ]
   ```
2. Fetch existing filters: `GET /api/v1/filters`
3. For each filter:
   - Check if a filter with that title already exists
   - If not, create via `POST /api/v1/filters`
4. Log each action

**Files**: `scripts/vikunja/setup_vikunja.py` (add function).
**Parallel?**: No — depends on T012 output.
**Notes**: Use the exact filter syntax verified in T012. Do not guess.

### Subtask T014 – Add API Readiness Check

**Purpose**: Ensure the script waits for Vikunja to be ready before attempting API calls.

**Steps**:
1. Implement a readiness check function:
   ```python
   def wait_for_api(base_url, timeout=30, interval=2):
       """Wait for Vikunja API to respond."""
       start = time.time()
       while time.time() - start < timeout:
           try:
               resp = requests.get(f"{base_url}/info", timeout=5)
               if resp.status_code == 200:
                   print(f"Vikunja API ready at {base_url}")
                   return
           except requests.ConnectionError:
               pass
           print(f"Waiting for Vikunja API at {base_url}...")
           time.sleep(interval)
       print(f"Error: Vikunja API not ready after {timeout}s", file=sys.stderr)
       sys.exit(1)
   ```
2. Call this at the start of `main()` before authentication

**Files**: `scripts/vikunja/setup_vikunja.py` (add function).
**Parallel?**: No — foundational utility.

## Risks & Mitigations

- **Filter syntax differs from expected**: T012 verifies before implementation. Adjust T013 accordingly.
- **API not ready when script runs**: T014 adds readiness check with 30-second timeout.
- **Parent project IDs needed for children**: T010 creates parents first and captures IDs.
- **`requests` not installed**: Script should fail with a clear message; present `pip install requests` to Kent.
- **Rate limiting on Vikunja API**: Unlikely for single-user local instance, but add brief sleep between bulk operations if needed.

## Review Guidance

- Run script twice and confirm no duplicates in Vikunja UI
- Verify all 9 projects exist with correct parent-child relationships
- Verify both labels are visible and have distinct colors
- Verify all 3 saved filters appear in the sidebar and return expected results
- Confirm no credentials are logged, written to disk, or committed
- Check that the readiness wait works when Vikunja is slow to start

## Activity Log

- 2026-03-26T06:31:38Z – system – lane=planned – Prompt created.
