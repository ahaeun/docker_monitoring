from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.docker_service import (
    get_container_logs,
    list_containers,
    restart_container,
    stop_container,
    stream_container_logs,
)

app = FastAPI(title="Docker Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/containers")
def api_list_containers():
    return list_containers()


@app.post("/api/containers/{container_id}/restart")
def api_restart_container(container_id: str):
    try:
        restart_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "restarted", "id": container_id}


@app.post("/api/containers/{container_id}/stop")
def api_stop_container(container_id: str):
    try:
        stop_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "stopped", "id": container_id}


@app.get("/api/containers/{container_id}/logs", response_class=PlainTextResponse)
def api_container_logs(container_id: str, tail: int = 100):
    try:
        return get_container_logs(container_id, tail)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/containers/{container_id}/logs/stream")
def api_container_logs_stream(container_id: str, tail: int = 100):
    def event_generator():
        try:
            for chunk in stream_container_logs(container_id, tail):
                for line in chunk.splitlines():
                    yield f"data: {line}\n\n"
        except Exception as e:
            yield f"data: [스트림 오류: {e}]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
