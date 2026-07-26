from fastapi import FastAPI

app = FastAPI(title="Task API", version="1.0")


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
