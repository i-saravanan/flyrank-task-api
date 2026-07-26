from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator

app = FastAPI(title="Task API", version="1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return HTTP 400 with a JSON error body for request validation failures."""
    errors = exc.errors()
    msg = errors[0]["msg"] if errors else "Invalid request body"
    return JSONResponse(status_code=400, content={"error": msg})


# ---------------------------------------------------------------------------
# In-memory storage — the ONLY persistence layer for this project
# ---------------------------------------------------------------------------
tasks: list[dict] = [
    {"id": 1, "title": "Buy groceries", "done": False},
    {"id": 2, "title": "Read FastAPI docs", "done": True},
    {"id": 3, "title": "Write unit tests", "done": False},
]
next_id: int = 4  # auto-increment counter


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


def find_task(task_id: int) -> dict | None:
    """Return the task dict with the given id, or None."""
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None


# ---------------------------------------------------------------------------
# Root & Health
# ---------------------------------------------------------------------------

@app.get("/", summary="API information")
def root():
    """Return basic API metadata and available endpoints."""
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": ["/tasks"],
    }


@app.get("/health", summary="Health check")
def health():
    """Return a simple health status to confirm the server is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Stage 2 — Read  /  Stage 3 — Create
# ---------------------------------------------------------------------------

@app.get("/tasks", summary="List all tasks")
def list_tasks():
    """Return all tasks stored in memory."""
    return tasks


@app.get("/tasks/{task_id}", summary="Get a single task")
def get_task(task_id: int):
    """Return the task with the given ID.

    - **404** with `{"error": "Task <id> not found"}` if the task does not exist.
    """
    task = find_task(task_id)
    if task is None:
        return JSONResponse(status_code=404, content={"error": f"Task {task_id} not found"})
    return task


@app.post("/tasks", status_code=201, summary="Create a new task")
def create_task(body: TaskCreate):
    """Create a task with the given title.

    - **title** is required and must not be empty (returns **400** otherwise).
    - The new task is assigned the next available ID with `done=false`.
    - Returns **201** with the created task.
    """
    global next_id
    new_task = {"id": next_id, "title": body.title, "done": False}
    tasks.append(new_task)
    next_id += 1
    return new_task
