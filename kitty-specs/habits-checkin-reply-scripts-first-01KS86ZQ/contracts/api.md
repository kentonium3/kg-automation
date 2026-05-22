# API Contracts: Python function signatures

**Mission**: `habits-checkin-reply-scripts-first-01KS86ZQ`
**Date**: 2026-05-22

Authoritative Python function signatures for the three new helpers. Implementation may add private functions; the signatures here are the public surface.

---

## `scripts/habits/morning_checkin_list.py`

### `build_morning_list(*, date: str, base_url: str = DEFAULT_BASE_URL, token_path: Path = DEFAULT_TOKEN_PATH) -> MorningList`

Build the ordered habit list for a Kent-day.

**Behavior**:
1. Read Vikunja habit tasks via existing `scripts.habits.query_active_habits_v2` (or equivalent function within this module).
2. Filter out habits already addressed today using existing `scripts.habits.exclude_completed_v2` semantics (cross-reference per-habit JSONL records).
3. Order the surviving habits deterministically. Order rule: by `vikunja_task_id ASC` (stable, immutable per memory `reference_vikunja_id_vs_identifier.md`).
4. Assign 1-indexed `position` to each surviving habit.
5. Return a `MorningList` dataclass.

**Raises**:
- `urllib.error.URLError` — Vikunja unreachable. Caller exits non-zero.
- `ValueError` — bad date format or Vikunja returned malformed data.

### `MorningList` dataclass

```python
@dataclass(frozen=True, slots=True)
class MorningList:
    schema_version: int  # always 1
    date: str            # YYYY-MM-DD, local TZ
    generated_at: str    # ISO-8601 UTC
    habits: list["MorningListHabit"]
```

### `MorningListHabit` dataclass

```python
@dataclass(frozen=True, slots=True)
class MorningListHabit:
    position: int           # 1-indexed
    vikunja_task_id: int    # positive
    title: str              # non-empty
```

### `persist_morning_list(morning_list: MorningList, *, state_dir: Path = DEFAULT_STATE_DIR) -> Path`

Atomically write the morning list to disk per research D2.

**Behavior**:
1. Compute path: `state_dir / f"morning-checkin-{morning_list.date}.json"`.
2. Write JSON to `<path>.tmp`.
3. `os.fsync()` the temp file.
4. `os.replace(<path>.tmp, <path>)`.
5. Return `<path>`.

**Raises**:
- `OSError` — filesystem error during write.

### `render_morning_message(morning_list: MorningList) -> str`

Render the WhatsApp message text for Kent.

**Behavior**:
- If `morning_list.habits` is empty: return `"All habits complete for today."`.
- Otherwise: format as the canonical multi-line message:
  ```
  Morning check-in — <Day>, <Month> <DD>:

  1. <title>
  2. <title>
  ...

  Reply with what you've done (e.g., "1 and 2 done, skipping 4")
  ```
- `<Day>` is the day-of-week derived from `morning_list.date` in America/New_York.
- `<Month> <DD>` is human-friendly date format.

### CLI `main(argv=None) -> int`

Per contracts/cli.md.

---

## `scripts/habits/parse_morning_reply.py`

### `parse_reply(*, reply_text: str, morning_list: MorningList) -> ParseResult`

Parse Kent's reply into canonical state-change tuples.

**Behavior** (per research D3 + D7):

1. Detect special tokens first (`"all done"` family + skip-all family). If found, emit a `tuple` for every position in the morning list with the matched state.
2. Tokenize the reply by punctuation + verb segmentation. Identify clusters where each cluster has a set of identifier-tokens (numbers / titles / substrings) and an inferred state (`complete`, `skipped`, `incomplete`).
3. For each identifier-token within a cluster:
   a. If it's a digit: map to position; resolve to `task_id`. Add to `tuples` with `matched_via=position`.
   b. If it exactly matches a title (case-insensitive): resolve. Add with `matched_via=exact_title`.
   c. If it's a substring uniquely matching one title (case-insensitive): resolve. Add with `matched_via=substring`.
   d. If it's a substring matching multiple titles: add to `judgment_required` with the cluster's inferred state.
   e. Otherwise: add to `errors` with type `unparseable_reply`.

**Returns**: `ParseResult` dataclass.

### `ParseResult` dataclass

```python
@dataclass(frozen=True, slots=True)
class ParseResult:
    schema_version: int       # always 1
    reply_text: str
    morning_list_path: str    # for echo / debug
    tuples: list["ParseTuple"]
    judgment_required: list["JudgmentItem"]
    errors: list["ParseError"]
```

### `ParseTuple` / `JudgmentItem` / `ParseError`

```python
@dataclass(frozen=True, slots=True)
class ParseTuple:
    task_id: int
    state: Literal["complete", "incomplete", "skipped"]
    matched_via: Literal["position", "exact_title", "substring", "special_token"]
    position: Optional[int] = None

@dataclass(frozen=True, slots=True)
class JudgmentItem:
    token: str
    candidate_task_ids: list[int]
    candidate_titles: list[str]
    inferred_state: Literal["complete", "incomplete", "skipped"]

@dataclass(frozen=True, slots=True)
class ParseError:
    type: Literal["no_morning_list", "invalid_token", "unparseable_reply"]
    detail: str
```

### `load_morning_list(*, date: str, state_dir: Path = DEFAULT_STATE_DIR) -> MorningList`

Read the persisted morning list JSON for a date.

**Raises**:
- `FileNotFoundError` — no morning list for that date. Caller maps to exit code 4.
- `json.JSONDecodeError` — corrupted file.
- `ValueError` — schema mismatch.

### CLI `main(argv=None) -> int`

Per contracts/cli.md.

---

## `scripts/habits/judgment/disambiguate_reply.py`

### `disambiguate(*, reply_text: str, ambiguity: JudgmentItem, model: str = "claude-haiku-4-5", api_key_path: Path = DEFAULT_API_KEY_PATH) -> DisambiguationResult`

Narrow LLM judgment call. Per research D4 + D5.

**Behavior**:
1. Load API key from `api_key_path`.
2. Build the cache-aware prompt: system prompt (cached) + user prompt with `reply_text` + `ambiguity.token` + `ambiguity.candidate_titles`.
3. Single-turn call to Anthropic API.
4. Parse the response as JSON. Validate shape against Entity 4 (data-model.md).
5. If `result=chosen`: verify `chosen_task_id` is in `ambiguity.candidate_task_ids`. If not, raise `DisambiguatorError`.
6. Return `DisambiguationResult`.

**Raises**:
- `DisambiguatorError` — invalid response, out-of-set task_id, or API error.

### `DisambiguationResult` dataclass

```python
@dataclass(frozen=True, slots=True)
class DisambiguationResult:
    schema_version: int  # always 1
    result: Literal["chosen", "clarify"]
    chosen_task_id: Optional[int]  # required if result=chosen
    reason: str
    suggested_question: Optional[str]  # required if result=clarify
```

### `DisambiguatorError`

```python
class DisambiguatorError(Exception):
    """Raised when the LLM disambiguation response is malformed or invalid."""
```

### CLI `main(argv=None) -> int`

Per contracts/cli.md.

---

## Module constants (shared)

```python
# All three modules
DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/habits")
HTTP_TIMEOUT_SECONDS = 30
LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")

# Disambiguator only
DEFAULT_API_KEY_PATH = Path("/data/services/openclaw/secrets/anthropic")
DEFAULT_MODEL = "claude-haiku-4-5"
```

---

## Cross-references

- Phase 3 reference (consumed as-is): `scripts/habits/record_completion.py`
- #309 reference (parser-pattern source): `scripts/escalation/reconcile_completions.py`
- #343 reference (disambiguator pattern source): `scripts/doc_audit/judgment/client.py`
- Memory: `reference_codex_speckitty_profile.md` (review dispatch convention)
