import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent / "tasks.db"


def get_connection() -> sqlite3.Connection:
    """Open a connection with row_factory so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    """Yield a connection and auto-commit/rollback/close."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create table and seed exactly three rows if the table is empty."""
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT    NOT NULL,
                done  INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        if row[0] == 0:
            conn.executemany(
                "INSERT INTO tasks (title, done) VALUES (?, ?)",
                [
                    ("Buy groceries", 0),
                    ("Read FastAPI docs", 1),
                    ("Write unit tests", 0),
                ],
            )


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict with done as bool."""
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Task API",
    version="1.0",
    description=(
        "A simple **CRUD API** for managing tasks, built with FastAPI.\n\n"
        "## Features\n"
        "- List, create, update, and delete tasks\n"
        "- Persistent SQLite storage (`tasks.db`)\n"
        "- Full input validation with clear error messages\n\n"
        "## Storage\n"
        "> **Note:** Data is stored in `tasks.db` (SQLite). "
        "The database and table are created automatically on first run. "
        "Deleting `tasks.db` and restarting the server recreates everything."
    ),
    contact={"name": "Saravanan I", "email": "saravanan05082004@gmail.com"},
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "meta", "description": "API metadata and health checks"},
        {"name": "tasks", "description": "CRUD operations for tasks"},
    ],
)

# Initialise database on startup
init_db()


# ---------------------------------------------------------------------------
# Validation error → 400
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return HTTP 400 with a JSON error body for request validation failures."""
    errors = exc.errors()
    msg = errors[0]["msg"] if errors else "Invalid request body"
    return JSONResponse(status_code=400, content={"error": msg})


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    """Request body for creating a new task."""
    title: str

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v.strip()


class TaskUpdate(BaseModel):
    """Request body for updating an existing task (all fields optional)."""
    title: str | None = None
    done: bool | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("title must not be empty")
        return v.strip() if v is not None else v


# ---------------------------------------------------------------------------
# Root & Health  (unchanged)
# ---------------------------------------------------------------------------

@app.get("/", summary="API information", tags=["meta"])
def root():
    """Return basic API metadata and available endpoints."""
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": ["/tasks"],
    }


@app.get("/health", summary="Health check", tags=["meta"])
def health():
    """Return a simple health status to confirm the server is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Stage 1 — Read from SQLite
# ---------------------------------------------------------------------------

@app.get("/tasks", summary="List all tasks", tags=["tasks"])
def list_tasks():
    """Return all tasks stored in the database."""
    with db() as conn:
        rows = conn.execute("SELECT id, title, done FROM tasks ORDER BY id").fetchall()
    return [row_to_dict(r) for r in rows]


@app.get("/tasks/{task_id}", summary="Get a single task", tags=["tasks"])
def get_task(task_id: int):
    """Return the task with the given ID.

    - **404** with `{"error": "Task not found"}` if the task does not exist.
    """
    with db() as conn:
        row = conn.execute(
            "SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return row_to_dict(row)


# ---------------------------------------------------------------------------
# Stage 2 — Insert into SQLite
# ---------------------------------------------------------------------------

@app.post("/tasks", status_code=201, summary="Create a new task", tags=["tasks"])
def create_task(body: TaskCreate):
    """Create a task with the given title.

    - **title** is required and must not be empty (returns **400** otherwise).
    - The new task is assigned the next available ID with `done=false`.
    - Returns **201** with the created task.
    """
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (title, done) VALUES (?, ?)", (body.title, 0)
        )
        new_id = cursor.lastrowid
    return {"id": new_id, "title": body.title, "done": False}


# ---------------------------------------------------------------------------
# Stage 3 — Update and Delete with SQL
# ---------------------------------------------------------------------------

@app.put("/tasks/{task_id}", summary="Update a task", tags=["tasks"])
def update_task(task_id: int, body: TaskUpdate):
    """Update a task's title and/or done status.

    - At least one field (`title` or `done`) should be provided.
    - **400** if the body is empty or title is blank.
    - **404** if the task does not exist.
    """
    # Verify task exists first
    with db() as conn:
        row = conn.execute(
            "SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "Task not found"})
        if body.title is None and body.done is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Request body must include at least one field: title or done"},
            )
        new_title = body.title if body.title is not None else row["title"]
        new_done = int(body.done) if body.done is not None else row["done"]
        conn.execute(
            "UPDATE tasks SET title = ?, done = ? WHERE id = ?",
            (new_title, new_done, task_id),
        )
    return {"id": task_id, "title": new_title, "done": bool(new_done)}


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task", tags=["tasks"])
def delete_task(task_id: int):
    """Delete a task by ID.

    - Returns **204** with an empty body on success.
    - **404** if the task does not exist.
    """
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "Task not found"})
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return None
