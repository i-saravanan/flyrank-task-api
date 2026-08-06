import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator

# Load environment variables
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "tasks")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "dev")


def get_connection():
    """Open a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


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
        with conn.cursor() as cur:
            schema_path = Path(__file__).parent / "schema.sql"
            if schema_path.exists():
                with open(schema_path, "r") as f:
                    cur.execute(f.read())
            
            cur.execute("SELECT COUNT(*) FROM tasks")
            count = cur.fetchone()[0]
            if count == 0:
                cur.executemany(
                    "INSERT INTO tasks (title, done) VALUES (%s, %s)",
                    [
                        ("Buy groceries", False),
                        ("Read FastAPI docs", True),
                        ("Write unit tests", False),
                    ],
                )


def row_to_dict(row: dict) -> dict:
    """Convert a row dict to a plain dict with done as bool."""
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
# Stage 2 — Read from Postgres  (GET /tasks, GET /tasks/{id})
# ---------------------------------------------------------------------------

@app.get("/tasks", summary="List all tasks", tags=["tasks"])
def list_tasks():
    """Return all tasks stored in the database."""
    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, title, done FROM tasks ORDER BY id")
            rows = cur.fetchall()
    return [row_to_dict(r) for r in rows]


@app.get("/tasks/{task_id}", summary="Get a single task", tags=["tasks"])
def get_task(task_id: int):
    """Return the task with the given ID.

    - **404** with `{"error": "Task not found"}` if the task does not exist.
    """
    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, title, done FROM tasks WHERE id = %s", (task_id,)
            )
            row = cur.fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return row_to_dict(row)



# ---------------------------------------------------------------------------
# Stage 3 — Full CRUD on Postgres  (POST, PUT, DELETE)
# ---------------------------------------------------------------------------

@app.post("/tasks", status_code=201, summary="Create a new task", tags=["tasks"])
def create_task(body: TaskCreate):
    """Create a task with the given title.

    - **title** is required and must not be empty (returns **400** otherwise).
    - The new task is assigned the next available ID with `done=false`.
    - Returns **201** with the created task.
    """
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING id",
                (body.title, False)
            )
            new_id = cur.fetchone()[0]
    return {"id": new_id, "title": body.title, "done": False}


@app.put("/tasks/{task_id}", summary="Update a task", tags=["tasks"])
def update_task(task_id: int, body: TaskUpdate):
    """Update a task's title and/or done status.

    - At least one field (`title` or `done`) should be provided.
    - **400** if the body is empty or title is blank.
    - **404** if the task does not exist.
    """
    with db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, title, done FROM tasks WHERE id = %s", (task_id,)
            )
            row = cur.fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"error": "Task not found"})
            if body.title is None and body.done is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Request body must include at least one field: title or done"},
                )
            new_title = body.title if body.title is not None else row["title"]
            new_done = body.done if body.done is not None else row["done"]
            cur.execute(
                "UPDATE tasks SET title = %s, done = %s WHERE id = %s",
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
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM tasks WHERE id = %s", (task_id,)
            )
            row = cur.fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"error": "Task not found"})
            cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    return None

