"""Bidirectional sync between Obsidian markdown TODO files and ClawChat todo DB."""

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.todo import Todo
from utils import deserialize_tags, make_id, serialize_tags

logger = logging.getLogger(__name__)

# Regex patterns for parsing Obsidian tasks
_TASK_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"- \[(?P<marker>[ x>])\]\s+"
    r"(?P<title>.+)$"
)
_DUE_RE = re.compile(r"@due\((?P<date>\d{4}-\d{2}-\d{2})\)")
_COMPLETED_RE = re.compile(r"@completed\((?P<date>\d{4}-\d{2}-\d{2})\)")

# Priority emoji mapping from section headers
_PRIORITY_EMOJI_MAP = {
    "\U0001f534": "urgent",   # 🔴
    "\U0001f7e0": "medium",   # 🟠
    "\U0001f7e1": "medium",   # 🟡
    "\U0001f535": "low",      # 🔵
}

_SECTION_HEADER_RE = re.compile(r"^#{1,6}\s+(.+)$")


@dataclass
class ObsidianTask:
    title: str
    completed: bool
    in_progress: bool
    due_date: datetime | None
    completed_date: datetime | None
    priority: str
    file_path: str  # relative to vault
    line_number: int
    source_id: str
    project: str
    indent: str = ""


@dataclass
class SyncResult:
    synced: int = 0
    created: int = 0
    updated: int = 0
    written_back: int = 0
    file_count: int = 0
    task_count: int = 0


@dataclass
class WriteBackChange:
    file_path: str  # relative to vault
    title: str
    source_id: str
    new_completed: bool
    completed_date: datetime | None
    is_new: bool = False
    new_task_line: str = ""


def _make_source_id(file_path: str, title: str) -> str:
    """Generate a stable source_id by hashing file_path:title."""
    # Strip metadata tags from title before hashing for stability
    clean_title = re.sub(r"\s*@\w+\([^)]*\)", "", title).strip()
    raw = f"{file_path}:{clean_title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _extract_project(file_path: str) -> str:
    """Extract project name from file path.

    For paths like '01_Projects/MyProject/TODO.md', returns 'MyProject'.
    For paths like '00_Inbox/TODO.md', returns 'Inbox'.
    """
    parts = Path(file_path).parts
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else "default"


def _detect_priority_from_header(header_text: str) -> str | None:
    """Detect priority from a section header containing emoji."""
    for emoji, priority in _PRIORITY_EMOJI_MAP.items():
        if emoji in header_text:
            return priority
    return None


def _parse_date(date_str: str) -> datetime | None:
    """Parse a YYYY-MM-DD date string into a timezone-aware datetime."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_markdown_file(file_path: str, vault_path: str) -> list[ObsidianTask]:
    """Parse a single markdown file for task items."""
    abs_path = os.path.join(vault_path, file_path)
    tasks: list[ObsidianTask] = []

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read %s: %s", abs_path, e)
        return tasks

    current_priority = "medium"  # default
    project = _extract_project(file_path)

    for line_number, line in enumerate(lines, start=1):
        line_stripped = line.rstrip("\n\r")

        # Check for section headers that might indicate priority
        header_match = _SECTION_HEADER_RE.match(line_stripped)
        if header_match:
            detected = _detect_priority_from_header(header_match.group(1))
            if detected is not None:
                current_priority = detected
            continue

        # Check for task items
        task_match = _TASK_RE.match(line_stripped)
        if not task_match:
            continue

        marker = task_match.group("marker")
        raw_title = task_match.group("title").strip()
        indent = task_match.group("indent")

        completed = marker == "x"
        in_progress = marker == ">"

        # Extract due date
        due_date = None
        due_match = _DUE_RE.search(raw_title)
        if due_match:
            due_date = _parse_date(due_match.group("date"))

        # Extract completed date
        completed_date = None
        comp_match = _COMPLETED_RE.search(raw_title)
        if comp_match:
            completed_date = _parse_date(comp_match.group("date"))

        # Clean title: remove metadata tags for display
        clean_title = re.sub(r"\s*@\w+\([^)]*\)", "", raw_title).strip()

        source_id = _make_source_id(file_path, raw_title)

        tasks.append(ObsidianTask(
            title=clean_title,
            completed=completed,
            in_progress=in_progress,
            due_date=due_date,
            completed_date=completed_date,
            priority=current_priority,
            file_path=file_path,
            line_number=line_number,
            source_id=source_id,
            project=project,
            indent=indent,
        ))

    return tasks


def scan_vault(vault_path: str) -> list[ObsidianTask]:
    """Recursively scan the vault for markdown files and parse tasks."""
    all_tasks: list[ObsidianTask] = []
    vault = Path(vault_path)

    if not vault.is_dir():
        logger.error("Vault path does not exist or is not a directory: %s", vault_path)
        return all_tasks

    for md_file in vault.rglob("*.md"):
        # Skip hidden directories/files
        rel = md_file.relative_to(vault)
        if any(part.startswith(".") for part in rel.parts):
            continue

        rel_path = str(rel)
        file_tasks = parse_markdown_file(rel_path, vault_path)
        all_tasks.extend(file_tasks)

    return all_tasks


async def sync_obsidian_todos(db: AsyncSession, vault_path: str) -> SyncResult:
    """Full bidirectional sync between Obsidian vault and ClawChat DB."""
    result = SyncResult()

    # 1. Parse all markdown files
    parsed_tasks = scan_vault(vault_path)
    result.task_count = len(parsed_tasks)

    # Count unique files
    result.file_count = len({t.file_path for t in parsed_tasks})

    # 2. Load all DB todos where source = "obsidian"
    stmt = select(Todo).where(Todo.source == "obsidian")
    rows = (await db.execute(stmt)).scalars().all()
    db_todos_by_source_id: dict[str, Todo] = {
        t.source_id: t for t in rows if t.source_id
    }

    # Track parsed source_ids for orphan detection
    parsed_source_ids = {t.source_id for t in parsed_tasks}

    # Collect write-back changes
    write_back_changes: list[WriteBackChange] = []

    # 3. Process each parsed task
    for task in parsed_tasks:
        existing = db_todos_by_source_id.get(task.source_id)

        if existing is not None:
            # Task exists in DB -- check for changes
            # Determine which side is newer using file mtime vs DB updated_at
            file_abs = os.path.join(vault_path, task.file_path)
            try:
                file_mtime = datetime.fromtimestamp(
                    os.path.getmtime(file_abs), tz=timezone.utc
                )
            except OSError:
                file_mtime = datetime.min.replace(tzinfo=timezone.utc)

            db_updated = existing.updated_at
            if db_updated and db_updated.tzinfo is None:
                db_updated = db_updated.replace(tzinfo=timezone.utc)

            obsidian_status = "completed" if task.completed else "pending"
            db_status = existing.status or "pending"

            if file_mtime > (db_updated or datetime.min.replace(tzinfo=timezone.utc)):
                # Obsidian is newer -- update DB
                changed = False
                if existing.title != task.title:
                    existing.title = task.title
                    changed = True
                if db_status != obsidian_status:
                    existing.status = obsidian_status
                    if obsidian_status == "completed":
                        existing.completed_at = task.completed_date or datetime.now(timezone.utc)
                    else:
                        existing.completed_at = None
                    changed = True
                if existing.due_date != task.due_date:
                    existing.due_date = task.due_date
                    changed = True
                if existing.priority != task.priority:
                    existing.priority = task.priority
                    changed = True
                if changed:
                    existing.updated_at = datetime.now(timezone.utc)
                    result.updated += 1
            else:
                # DB is newer -- write back to Obsidian
                db_completed = db_status == "completed"
                if db_completed != task.completed:
                    write_back_changes.append(WriteBackChange(
                        file_path=task.file_path,
                        title=task.title,
                        source_id=task.source_id,
                        new_completed=db_completed,
                        completed_date=existing.completed_at,
                    ))

            result.synced += 1
        else:
            # New task from Obsidian -- create in DB
            tags = ["obsidian"]
            if task.project:
                tags.append(task.project)

            status = "completed" if task.completed else "pending"

            new_todo = Todo(
                id=make_id("todo_"),
                title=task.title,
                status=status,
                priority=task.priority,
                due_date=task.due_date,
                completed_at=task.completed_date if task.completed else None,
                tags=serialize_tags(tags),
                source="obsidian",
                source_id=task.source_id,
            )
            db.add(new_todo)
            result.created += 1

    # 4. Check for DB-only todos that should be written back to Obsidian
    # (new todos created in ClawChat with source="obsidian" that are not yet in any file)
    for source_id, db_todo in db_todos_by_source_id.items():
        if source_id not in parsed_source_ids:
            # This was either deleted from Obsidian or was created in ClawChat.
            # If it has no file_path info in its source_id, it might be new from ClawChat.
            # We leave existing orphaned todos as-is (don't delete).
            pass

    # Also handle DB todos with source="obsidian" but no source_id
    # (created via ClawChat targeting obsidian) -- append to inbox
    stmt_new = select(Todo).where(
        Todo.source == "obsidian",
        Todo.source_id.is_(None),
    )
    new_from_clawchat = (await db.execute(stmt_new)).scalars().all()
    for todo in new_from_clawchat:
        due_str = ""
        if todo.due_date:
            due_str = f" @due({todo.due_date.strftime('%Y-%m-%d')})"

        marker = "x" if todo.status == "completed" else " "
        comp_str = ""
        if todo.status == "completed" and todo.completed_at:
            comp_str = f" @completed({todo.completed_at.strftime('%Y-%m-%d')})"

        task_line = f"- [{marker}] {todo.title}{due_str}{comp_str}"

        # Generate source_id for this todo so it won't be re-appended
        source_id = _make_source_id("00_Inbox/TODO.md", task_line)
        todo.source_id = source_id
        todo.updated_at = datetime.now(timezone.utc)

        write_back_changes.append(WriteBackChange(
            file_path="00_Inbox/TODO.md",
            title=todo.title,
            source_id=source_id,
            new_completed=todo.status == "completed",
            completed_date=todo.completed_at,
            is_new=True,
            new_task_line=task_line,
        ))

    # 5. Write back changes to markdown files
    if write_back_changes:
        result.written_back = write_back_to_obsidian(vault_path, write_back_changes)

    await db.commit()
    return result


def write_back_to_obsidian(vault_path: str, changes: list[WriteBackChange]) -> int:
    """Write changes back to Obsidian markdown files.

    Returns the number of changes successfully written.
    """
    written = 0

    # Group changes by file
    changes_by_file: dict[str, list[WriteBackChange]] = {}
    for change in changes:
        changes_by_file.setdefault(change.file_path, []).append(change)

    for file_path, file_changes in changes_by_file.items():
        abs_path = os.path.join(vault_path, file_path)

        # Handle new tasks that need to be appended
        new_tasks = [c for c in file_changes if c.is_new]
        updates = [c for c in file_changes if not c.is_new]

        # Process updates to existing lines
        if updates:
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read %s for write-back: %s", abs_path, e)
                continue

            modified = False
            for change in updates:
                # Find the line matching this task by title
                for i, line in enumerate(lines):
                    task_match = _TASK_RE.match(line.rstrip("\n\r"))
                    if not task_match:
                        continue

                    raw_title = task_match.group("title").strip()
                    clean = re.sub(r"\s*@\w+\([^)]*\)", "", raw_title).strip()
                    if clean != change.title:
                        continue

                    indent = task_match.group("indent")
                    new_marker = "x" if change.new_completed else " "

                    # Rebuild the line
                    title_part = raw_title

                    if change.new_completed:
                        # Add @completed tag if not present
                        if "@completed(" not in title_part and change.completed_date:
                            date_str = change.completed_date.strftime("%Y-%m-%d")
                            title_part = f"{title_part} @completed({date_str})"
                        # Update checkbox
                        lines[i] = f"{indent}- [{new_marker}] {title_part}\n"
                    else:
                        # Remove @completed tag
                        title_part = re.sub(r"\s*@completed\([^)]*\)", "", title_part)
                        lines[i] = f"{indent}- [{new_marker}] {title_part}\n"

                    modified = True
                    written += 1
                    break

            if modified:
                try:
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                except OSError as e:
                    logger.error("Failed to write %s: %s", abs_path, e)

        # Process new tasks to append
        if new_tasks:
            try:
                # Ensure the file exists
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)

                # Read existing content or start fresh
                existing_content = ""
                if os.path.exists(abs_path):
                    with open(abs_path, "r", encoding="utf-8") as f:
                        existing_content = f.read()

                # Find or create the ClawChat section
                clawchat_header = "## ClawChat"
                if clawchat_header not in existing_content:
                    if existing_content and not existing_content.endswith("\n"):
                        existing_content += "\n"
                    existing_content += f"\n{clawchat_header}\n"

                # Append new tasks after the ClawChat header
                new_lines = "\n".join(c.new_task_line for c in new_tasks)
                # Insert after the header line
                header_idx = existing_content.index(clawchat_header)
                header_end = existing_content.index("\n", header_idx) + 1
                existing_content = (
                    existing_content[:header_end]
                    + new_lines + "\n"
                    + existing_content[header_end:]
                )

                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(existing_content)

                written += len(new_tasks)
            except OSError as e:
                logger.error("Failed to append to %s: %s", abs_path, e)

    return written


# --- Status helpers ---

_last_sync_time: datetime | None = None


def get_last_sync_time() -> datetime | None:
    return _last_sync_time


def set_last_sync_time(dt: datetime) -> None:
    global _last_sync_time
    _last_sync_time = dt
