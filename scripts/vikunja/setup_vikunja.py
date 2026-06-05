#!/usr/bin/env python3
"""
setup_vikunja.py — Configure Vikunja with project hierarchy, labels, and filters.

Idempotent: safe to run multiple times. Creates only missing entities.
Authenticates interactively via username/password → JWT (not persisted).
"""
import argparse
import getpass
import sys
import time

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

from scripts.common.vikunja_config import get_vikunja_base_url

# --- Configuration ---

#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_URL: str = ""

PROJECTS = [
    {"name": "Everyday", "children": [
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

LABELS = [
    {"title": "personal", "hex_color": "#2196f3"},
    {"title": "intentional", "hex_color": "#4caf50"},
]

FILTERS = [
    {
        "title": "Today",
        "filters": {
            "filter": "due_date >= now/d && due_date < now/d+1d && done = false",
            "sort_by": ["due_date"],
            "order_by": ["asc"],
        },
    },
    {
        "title": "Upcoming",
        "filters": {
            "filter": "due_date > now/d && due_date <= now+14d && done = false",
            "sort_by": ["due_date"],
            "order_by": ["asc"],
        },
    },
    {
        "title": "Overdue",
        "filters": {
            "filter": "due_date < now/d && done = false",
            "sort_by": ["due_date"],
            "order_by": ["asc"],
        },
    },
    {
        "title": "Goals",
        "filters": {
            "filter": "project = 11 && done = false",
            "sort_by": ["due_date"],
            "order_by": ["asc"],
        },
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
            resp = requests.get(f"{base_url}info", timeout=5)
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
    resp = requests.post(f"{base_url}login", json={
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
    resp = requests.get(f"{base_url}projects", headers=api_headers(token))
    resp.raise_for_status()
    return resp.json()


def find_project_by_name(projects, name, parent_id=None):
    """Find a project by name, optionally scoped to a parent."""
    for p in projects:
        if p["title"] == name:
            if parent_id is None:
                # Top-level: match if no parent or parent_project_id == 0
                if p.get("parent_project_id", 0) == 0:
                    return p
            else:
                if p.get("parent_project_id") == parent_id:
                    return p
    return None


def create_projects(base_url, token):
    """Create project hierarchy, skipping existing."""
    print("\n--- Projects ---")
    existing = get_existing_projects(base_url, token)

    for top in PROJECTS:
        proj = find_project_by_name(existing, top["name"])
        if proj:
            print(f"  Exists: {top['name']}")
            parent_id = proj["id"]
        else:
            resp = requests.put(
                f"{base_url}projects",
                headers=api_headers(token),
                json={"title": top["name"]},
            )
            resp.raise_for_status()
            parent_id = resp.json()["id"]
            print(f"  Created: {top['name']}")
            # Refresh existing list
            existing = get_existing_projects(base_url, token)

        for child in top.get("children", []):
            c = find_project_by_name(existing, child["name"], parent_id)
            if c:
                print(f"  Exists: {top['name']} / {child['name']}")
            else:
                resp = requests.put(
                    f"{base_url}projects",
                    headers=api_headers(token),
                    json={"title": child["name"], "parent_project_id": parent_id},
                )
                resp.raise_for_status()
                print(f"  Created: {top['name']} / {child['name']}")
                existing = get_existing_projects(base_url, token)


# --- Labels ---

def create_labels(base_url, token):
    """Create identity labels, skipping existing."""
    print("\n--- Labels ---")
    resp = requests.get(f"{base_url}labels", headers=api_headers(token))
    resp.raise_for_status()
    existing = {lb["title"]: lb for lb in (resp.json() or [])}

    for label in LABELS:
        if label["title"] in existing:
            print(f"  Exists: {label['title']}")
        else:
            resp = requests.put(
                f"{base_url}labels",
                headers=api_headers(token),
                json=label,
            )
            resp.raise_for_status()
            print(f"  Created: {label['title']}")


# --- Filters ---

def get_existing_filter_titles(base_url, token):
    """Detect existing saved filters by checking projects for filter-backed entries.

    Vikunja 0.24.x has no GET /filters list endpoint. Saved filters appear as
    projects, so we check the projects list for known filter titles.
    """
    projects = get_existing_projects(base_url, token)
    return {p["title"] for p in projects}


def create_filters(base_url, token):
    """Create saved filters, skipping existing."""
    print("\n--- Saved Filters ---")
    existing_titles = get_existing_filter_titles(base_url, token)

    for filt in FILTERS:
        if filt["title"] in existing_titles:
            print(f"  Exists: {filt['title']}")
        else:
            resp = requests.put(
                f"{base_url}filters",
                headers=api_headers(token),
                json=filt,
            )
            resp.raise_for_status()
            print(f"  Created: {filt['title']}")


# --- Main ---

def parse_args():
    parser = argparse.ArgumentParser(
        description="Configure Vikunja project structure, labels, and filters"
    )
    parser.add_argument(
        "--url", default=None,
        help="Vikunja API base URL (default: from VIKUNJA_BASE_URL env or config file)."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    args.url = args.url or get_vikunja_base_url()
    print(f"Vikunja Setup — {args.url}\n")

    wait_for_api(args.url)
    token = authenticate(args.url)
    create_projects(args.url, token)
    create_labels(args.url, token)
    create_filters(args.url, token)

    print("\n[OK] Setup complete.")


if __name__ == "__main__":
    main()
