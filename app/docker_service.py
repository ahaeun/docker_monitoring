import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import docker
from dotenv import load_dotenv

from app.ssh_docker import start_ssh_docker_tunnel

load_dotenv()

_client = None
_tunnel_server = None
_ssh_client = None

# 이 프로세스 전체에서 동시에 열리는 Docker API 호출(=SSH 세션) 개수를 제한한다.
# 요청 하나(ThreadPoolExecutor)만 제한해도 여러 요청이 겹치면 합산 개수가 넘칠 수 있어
# 전역으로 제한한다. sshd 기본 MaxSessions(10)보다 낮게 잡아 여유를 둔다.
_docker_call_semaphore = threading.Semaphore(6)


def get_client():
    global _client
    if _client is None:
        ssh_host = os.environ.get("SSH_HOST")
        if ssh_host:
            _client = _create_ssh_tunnel_client(ssh_host)
        else:
            _client = docker.from_env()
    return _client


def _create_ssh_tunnel_client(ssh_host: str):
    global _tunnel_server, _ssh_client

    port = int(os.environ.get("SSH_PORT", "22"))
    username = os.environ.get("SSH_USER")
    password = os.environ.get("SSH_PASSWORD")

    _tunnel_server, bound_port, _ssh_client = start_ssh_docker_tunnel(
        ssh_host, port, username, password
    )
    return docker.DockerClient(base_url=f"tcp://127.0.0.1:{bound_port}")


def _calc_cpu_percent(stats: dict) -> float:
    cpu_delta = (
        stats["cpu_stats"]["cpu_usage"]["total_usage"]
        - stats["precpu_stats"]["cpu_usage"]["total_usage"]
    )
    system_delta = stats["cpu_stats"].get(
        "system_cpu_usage", 0
    ) - stats["precpu_stats"].get("system_cpu_usage", 0)
    online_cpus = stats["cpu_stats"].get("online_cpus") or len(
        stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])
    )
    if system_delta > 0 and cpu_delta > 0:
        return round((cpu_delta / system_delta) * online_cpus * 100, 2)
    return 0.0


def _calc_memory(stats: dict) -> dict:
    usage = stats["memory_stats"].get("usage", 0)
    limit = stats["memory_stats"].get("limit", 1)
    percent = round((usage / limit) * 100, 2) if limit else 0.0
    return {
        "usage_mb": round(usage / (1024 * 1024), 2),
        "limit_mb": round(limit / (1024 * 1024), 2),
        "percent": percent,
    }


def _fetch_stats(container) -> dict:
    try:
        with _docker_call_semaphore:
            stats = container.stats(stream=False)
        return {
            "cpu_percent": _calc_cpu_percent(stats),
            "memory": _calc_memory(stats),
        }
    except Exception:
        return {"cpu_percent": 0.0, "memory": {"usage_mb": 0, "limit_mb": 0, "percent": 0.0}}


_SIZE_UNITS_TO_MB = {
    "b": 1 / (1024 * 1024),
    "kib": 1 / 1024,
    "kb": 1 / 1024,
    "mib": 1,
    "mb": 1,
    "gib": 1024,
    "gb": 1024,
    "tib": 1024 * 1024,
    "tb": 1024 * 1024,
}


def _parse_size_to_mb(text: str) -> float:
    match = re.match(r"([\d.]+)\s*([A-Za-z]+)", text.strip())
    if not match:
        return 0.0
    value, unit = float(match.group(1)), match.group(2).lower()
    return round(value * _SIZE_UNITS_TO_MB.get(unit, 1), 2)


def _fetch_all_stats_via_ssh() -> dict:
    """SSH 세션 1개로 실행 중인 모든 컨테이너의 stats를 한 번에 가져온다.

    컨테이너마다 개별 stats() 호출(=SSH 세션 1개씩)을 하면 세션 생성 비용이
    컨테이너 수만큼 곱해져 느려지므로, 원격에서 `docker stats`를 한 번만 실행해
    로컬(원격 서버 기준) 소켓으로 전체를 모아오게 한다.
    """
    stdin, stdout, stderr = _ssh_client.exec_command(
        "docker stats --no-stream --format '{{json .}}'"
    )
    result = {}
    for line in stdout:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            usage_str, limit_str = row["MemUsage"].split("/")
            result[row["ID"]] = {
                "cpu_percent": float(row["CPUPerc"].rstrip("%")),
                "memory": {
                    "usage_mb": _parse_size_to_mb(usage_str),
                    "limit_mb": _parse_size_to_mb(limit_str),
                    "percent": float(row["MemPerc"].rstrip("%")),
                },
            }
        except Exception:
            continue
    return result


def list_containers() -> list[dict]:
    client = get_client()
    with _docker_call_semaphore:
        containers = client.containers.list(all=True)
    running = [c for c in containers if c.status == "running"]

    stats_by_id = {}
    if running:
        if _ssh_client is not None:
            with _docker_call_semaphore:
                stats_by_id = _fetch_all_stats_via_ssh()
        else:
            max_workers = min(len(running), 6)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for container, stats in zip(running, executor.map(_fetch_stats, running)):
                    stats_by_id[container.short_id] = stats

    result = []
    for container in containers:
        stats = stats_by_id.get(
            container.short_id,
            {"cpu_percent": 0.0, "memory": {"usage_mb": 0, "limit_mb": 0, "percent": 0.0}},
        )
        result.append({
            "id": container.short_id,
            "name": container.name,
            "image": container.attrs.get("Config", {}).get("Image") or container.attrs.get("Image", "unknown"),
            "status": container.status,
            "cpu_percent": stats["cpu_percent"],
            "memory": stats["memory"],
        })
    return result


def restart_container(container_id: str) -> None:
    client = get_client()
    with _docker_call_semaphore:
        container = client.containers.get(container_id)
        container.restart()


def stop_container(container_id: str) -> None:
    client = get_client()
    with _docker_call_semaphore:
        container = client.containers.get(container_id)
        container.stop()


def get_container_logs(container_id: str, tail: int = 100) -> str:
    client = get_client()
    with _docker_call_semaphore:
        container = client.containers.get(container_id)
        logs = container.logs(tail=tail, timestamps=True)
    return logs.decode("utf-8", errors="replace")


def stream_container_logs(container_id: str, tail: int = 100):
    client = get_client()
    with _docker_call_semaphore:
        container = client.containers.get(container_id)
        for chunk in container.logs(stream=True, follow=True, tail=tail, timestamps=True):
            yield chunk.decode("utf-8", errors="replace")
