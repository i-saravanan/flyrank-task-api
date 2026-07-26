from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Task API", version="1.0")

# ---------------------------------------------------------------------------
# In-memory storage — the ONLY persistence layer for this project
# ---------------------------------------------------------------------------
tasks: list[dict] = [
    {"id": 1, "title": "Buy groceries", "done": False},
    {"id": 2, "title": "Read FastAPI docs", "done": True},
    {"id": 3, "title": "Write unit tests", "done": False},
]
next_id: int = 4  # auto-increment counter


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
# Stage 2 — Read
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
