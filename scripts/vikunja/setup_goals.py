#!/usr/bin/env python3
"""
setup_goals.py — Configure Vikunja with Goals project, labels, and filter.

Idempotent: safe to run multiple times. Creates only missing entities.
Authenticates interactively via username/password → JWT (not persisted).

Part of F006: Goal and Outcome Structure.
"""
import argparse
import getpass
import json
import sys
import time

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

# --- Configuration ---

DEFAULT_URL = "http://100.92.197.90:3456/api/v1"

GOALS_PROJECT_NAME = "Goals"

# metalcasework label — completes the identity label set (personal, intentional
# already exist from F001)
NEW_LABELS = [
    {"title": "metalcasework", "hex_color": "#ff9800"},
]

# Seed goal declarations — each becomes a Vikunja task in the Goals project.
# Format: canonical "On [date], I have [outcome] as evidenced by [proof]"
SEED_GOALS = [
    {
        "title": "Intentional: $5K/month consulting income",
        "description": (
            "On September 30th, 2026, I have established a consulting income of "
            "$5,000/month through Intentional LLC as evidenced by deposits "
            "totaling $5,000 or more in my Intentional LLC business checking "
            "account for the month of September 2026.\n\n"
            "**Evidence criteria:** Bank statement for Intentional LLC showing "
            "deposits of $5,000 or more for the calendar month."
        ),
        "due_date": "2026-09-30T00:00:00Z",
        "label": "intentional",
    },
    {
        "title": "Intentional: $2.5K/month consulting income by Q2",
        "description": (
            "On June 30th, 2026, I have established a consulting income of "
            "$2,500/month through Intentional LLC as evidenced by deposits "
            "totaling an average of $2,500 or more in my Intentional LLC "
            "business checking account for the months of April, May, and "
            "June 2026.\n\n"
            "**Evidence criteria:** Bank statements for Intentional LLC showing "
            "deposits averaging $2,500 or more per month for April, May, and "
            "June 2026."
        ),
        "due_date": "2026-06-30T00:00:00Z",
        "label": "intentional",
    },
    {
        "title": "Personal: Complete Against the Tide 5K",
        "description": (
            "On June 27th, 2026, I have completed the Against the Tide 5K race "
            "in Brewster as evidenced by crossing the finish line and receiving "
            "a finisher confirmation.\n\n"
            "**Evidence criteria:** Race completion confirmation or finish time "
            "from the Against the Tide event (confirmation #54200328)."
        ),
        "due_date": "2026-06-27T00:00:00Z",
        "label": "personal",
    },
]


# --- Helpers ---

def api_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def wait_for_api(base_url, timeout=30, interval=2):
    """Wait for Vikunja API to respond."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{base_url}/info", timeout=5)
            if resp.status_code == 200:
                version = resp.json().get("version", "unknown")
                print(f"[OK] Vikunja API ready ({version})")
                return
        except requests.ConnectionError:
            pass
        print(f"  Waiting for API at {base_url}...")
        time.sleep(interval)
    print(f"Error: Vikunja API not ready after {timeout}s", file=sys.stderr)
    sys.exit(1)


def authenticate(base_url):
    """Prompt for credentials and obtain JWT."""
    username = input("Vikunja username: ")
    password = getpass.getpass("Vikunja password: ")
    resp = requests.post(f"{base_url}/login", json={
        "username": username,
        "password": password,
    })
    if resp.status_code != 200:
        print(f"Error: Authentication failed (HTTP {resp.status_code})", file=sys.stderr)
        sys.exit(1)
    token = resp.json().get("token")
    if not token:
        print("Error: No token in login response", file=sys.stderr)
        sys.exit(1)
    print("[OK] Authenticated")
    return token


# --- Projects ---

def get_existing_projects(base_url, token):
    """Fetch all existing projects."""
    resp = requests.get(f"{base_url}/projects", headers=api_headers(token))
    resp.raise_for_status()
    return resp.json()


def find_project_by_name(projects, name, parent_id=None):
    """Find a project by name, optionally scoped to a parent."""
    for p in projects:
        if p["title"] == name:
            if parent_id is None:
                if p.get("parent_project_id", 0) == 0:
                    return p
            else:
                if p.get("parent_project_id") == parent_id:
                    return p
    return None


def create_goals_project(base_url, token):
    """Create the Goals project if it doesn't exist. Returns project ID."""
    print("\n--- Goals Project ---")
    existing = get_existing_projects(base_url, token)
    proj = find_project_by_name(existing, GOALS_PROJECT_NAME)

    if proj:
        print(f"  Exists: {GOALS_PROJECT_NAME} (id={proj['id']})")
        return proj["id"]

    resp = requests.put(
        f"{base_url}/projects",
        headers=api_headers(token),
        json={"title": GOALS_PROJECT_NAME},
    )
    resp.raise_for_status()
    project_id = resp.json()["id"]
    print(f"  Created: {GOALS_PROJECT_NAME} (id={project_id})")
    return project_id


# --- Labels ---

def get_existing_labels(base_url, token):
    """Fetch all existing labels as a dict keyed by title."""
    resp = requests.get(f"{base_url}/labels", headers=api_headers(token))
    resp.raise_for_status()
    return {lb["title"]: lb for lb in (resp.json() or [])}


def create_labels(base_url, token):
    """Create identity labels, skipping existing. Returns label dict."""
    print("\n--- Labels ---")
    existing = get_existing_labels(base_url, token)

    for label in NEW_LABELS:
        if label["title"] in existing:
            print(f"  Exists: {label['title']} (id={existing[label['title']]['id']})")
        else:
            resp = requests.put(
                f"{base_url}/labels",
                headers=api_headers(token),
                json=label,
            )
            resp.raise_for_status()
            created = resp.json()
            existing[created["title"]] = created
            print(f"  Created: {label['title']} (id={created['id']})")

    return existing


# --- Tasks ---

def get_project_tasks(base_url, token, project_id):
    """Fetch all tasks in a project."""
    resp = requests.get(
        f"{base_url}/projects/{project_id}/tasks",
        headers=api_headers(token),
    )
    resp.raise_for_status()
    return resp.json() or []


def create_seed_goals(base_url, token, project_id, labels):
    """Create seed goal declaration tasks, skipping existing by title."""
    print("\n--- Seed Goal Declarations ---")
    existing_tasks = get_project_tasks(base_url, token, project_id)
    existing_by_title = {t["title"]: t for t in existing_tasks}

    for goal in SEED_GOALS:
        if goal["title"] in existing_by_title:
            task = existing_by_title[goal["title"]]
            # Check if label is missing and assign if needed
            task_labels = {l["title"] for l in (task.get("labels") or [])}
            if goal["label"] not in task_labels:
                label_obj = labels.get(goal["label"])
                if label_obj:
                    resp = requests.put(
                        f"{base_url}/tasks/{task['id']}/labels",
                        headers=api_headers(token),
                        json={"label_id": label_obj["id"]},
                    )
                    resp.raise_for_status()
                    print(f"  Exists: {goal['title']} (label repaired: {goal['label']})")
                else:
                    print(f"  Exists: {goal['title']} (label '{goal['label']}' not found)")
            else:
                print(f"  Exists: {goal['title']}")
            continue

        label_obj = labels.get(goal["label"])
        if not label_obj:
            print(f"  Warning: Label '{goal['label']}' not found, skipping: {goal['title']}")
            continue

        task_data = {
            "title": goal["title"],
            "description": goal["description"],
            "due_date": goal["due_date"],
        }

        resp = requests.put(
            f"{base_url}/projects/{project_id}/tasks",
            headers=api_headers(token),
            json=task_data,
        )
        resp.raise_for_status()
        task_id = resp.json()["id"]
        print(f"  Created: {goal['title']} (id={task_id})")

        # Assign label via separate endpoint
        resp = requests.put(
            f"{base_url}/tasks/{task_id}/labels",
            headers=api_headers(token),
            json={"label_id": label_obj["id"]},
        )
        resp.raise_for_status()
        print(f"    Label assigned: {goal['label']}")


# --- Filters ---

def get_existing_filter_titles(base_url, token):
    """Detect existing saved filters by checking projects for filter-backed entries."""
    projects = get_existing_projects(base_url, token)
    return {p["title"] for p in projects}


def create_goals_filter(base_url, token, project_id):
    """Create the Goals saved filter if it doesn't exist."""
    print("\n--- Goals Filter ---")
    existing_titles = get_existing_filter_titles(base_url, token)

    filter_title = "Goals"
    if filter_title in existing_titles:
        print(f"  Exists: {filter_title}")
        return

    # Use the same filter expression syntax as F001's filters.
    # Filter by project and exclude done tasks, sorted by due date.
    filter_data = {
        "title": filter_title,
        "filters": {
            "filter": f"project = {project_id} && done = false",
            "sort_by": ["due_date"],
            "order_by": ["asc"],
        },
    }

    resp = requests.put(
        f"{base_url}/filters",
        headers=api_headers(token),
        json=filter_data,
    )
    resp.raise_for_status()
    print(f"  Created: {filter_title}")


# --- Verification ---

def verify(base_url, token, project_id, labels):
    """Verify all goal infrastructure was created correctly."""
    print("\n--- Verification ---")
    errors = []

    # Check metalcasework label
    current_labels = get_existing_labels(base_url, token)
    if "metalcasework" not in current_labels:
        errors.append("metalcasework label not found")
    else:
        label = current_labels["metalcasework"]
        expected_color = "ff9800"
        actual_color = label.get("hex_color", "").lstrip("#")
        if actual_color != expected_color:
            errors.append(f"metalcasework label color is {actual_color}, expected {expected_color}")
        print(f"  [OK] Label: metalcasework (id={label['id']}, color={label['hex_color']})")

    # Check Goals project
    projects = get_existing_projects(base_url, token)
    goals_proj = find_project_by_name(projects, GOALS_PROJECT_NAME)
    if not goals_proj:
        errors.append("Goals project not found")
    else:
        print(f"  [OK] Project: Goals (id={goals_proj['id']})")

    # Check tasks
    tasks = get_project_tasks(base_url, token, project_id)
    if not tasks:
        errors.append("No tasks found in Goals project")
    else:
        for task in tasks:
            issues = []
            if not task.get("description"):
                issues.append("missing description")
            if not task.get("due_date") or task["due_date"] == "0001-01-01T00:00:00Z":
                issues.append("missing due_date")
            if not task.get("labels"):
                issues.append("missing labels")
            if issues:
                errors.append(f"Task '{task['title']}': {', '.join(issues)}")
            else:
                print(f"  [OK] Task: {task['title']} (due={task['due_date'][:10]}, labels={[l['title'] for l in task['labels']]})")

    # Check filter
    filter_titles = get_existing_filter_titles(base_url, token)
    if "Goals" not in filter_titles:
        errors.append("Goals saved filter not found")
    else:
        print("  [OK] Filter: Goals")

    if errors:
        print(f"\n[FAIL] {len(errors)} verification error(s):")
        for e in errors:
            print(f"  - {e}")
        return False

    print("\n[OK] All verification checks passed.")
    return True


# --- Main ---

def parse_args():
    parser = argparse.ArgumentParser(
        description="Configure Vikunja with Goals project, seed declarations, and filter (F006)"
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help=f"Vikunja API base URL (default: {DEFAULT_URL})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be created without making API calls"
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Only run verification checks, don't create anything"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"Vikunja Goals Setup (F006) — {args.url}\n")

    if args.dry_run:
        print("[DRY RUN] Would create:")
        print(f"  Label: metalcasework (#ff9800)")
        print(f"  Project: {GOALS_PROJECT_NAME}")
        for goal in SEED_GOALS:
            print(f"  Task: {goal['title']} (due: {goal['due_date'][:10]}, label: {goal['label']})")
        print(f"  Filter: Goals")
        return

    wait_for_api(args.url)
    token = authenticate(args.url)

    if args.verify_only:
        labels = get_existing_labels(args.url, token)
        projects = get_existing_projects(args.url, token)
        goals_proj = find_project_by_name(projects, GOALS_PROJECT_NAME)
        if not goals_proj:
            print("[FAIL] Goals project not found")
            sys.exit(1)
        ok = verify(args.url, token, goals_proj["id"], labels)
        sys.exit(0 if ok else 1)

    labels = create_labels(args.url, token)
    project_id = create_goals_project(args.url, token)
    create_seed_goals(args.url, token, project_id, labels)
    create_goals_filter(args.url, token, project_id)

    ok = verify(args.url, token, project_id, labels)
    if ok:
        print("\n[OK] Goals setup complete.")
    else:
        print("\n[WARN] Setup completed with verification errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
