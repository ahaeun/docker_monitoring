# Docker Dashboard

FastAPI + Docker SDK로 만든 간단한 웹 기반 Docker 컨테이너 대시보드.
컨테이너 목록, 상태, CPU/메모리 사용량을 확인하고 재시작·로그 조회를 웹에서 처리합니다.

## 폴더 구조
```
docker-dashboard/
├── requirements.txt
├── .env.example        # DOCKER_HOST 등 접속 환경변수 템플릿
└── app/
    ├── main.py            # FastAPI 라우트 (대시보드 + API)
    ├── docker_service.py  # Docker SDK 래핑 (조회/재시작/로그/CPU·메모리 계산)
    └── templates/
        └── index.html     # 웹 대시보드 UI (3초 주기 폴링)
```

## 설치 및 실행
```bash
cd docker-dashboard
pip3 install -r requirements.txt
cp .env.example .env   # 로컬 Docker만 쓸 경우 그대로 둬도 됨
python3 -m uvicorn app.main:app --reload --port 8080
```

브라우저에서 `http://localhost:8000` 접속. 로컬에 Docker Desktop(또는 Docker daemon)이 떠 있어야 합니다.

## Docker 접속 방식
`app/docker_service.py`의 `docker.from_env()`가 환경변수를 읽어 접속 대상을 결정합니다.

- 기본값: 아무 것도 설정하지 않으면 로컬 소켓(`/var/run/docker.sock`)에 자동 접속
- 원격 Docker 서버에 붙이고 싶으면 `.env`에 아래 값을 채우면 됩니다 (`.env.example` 참고)
  - `DOCKER_HOST` — 예: `tcp://192.168.0.10:2375`
  - `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH` — TLS 접속 시

## API

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/` | 대시보드 웹 페이지 |
| GET | `/api/containers` | 컨테이너 목록 + 상태 + CPU/메모리 조회 |
| POST | `/api/containers/{id}/restart` | 컨테이너 재시작 |
| GET | `/api/containers/{id}/logs?tail=100` | 컨테이너 로그 조회 |

## 참고
- `/api/containers`는 실행 중인 컨테이너의 `stats()`를 `ThreadPoolExecutor`로 병렬 조회합니다.
- 이 앱을 컨테이너로 띄울 경우 호스트 Docker 소켓을 마운트해야 합니다:
  ```bash
  docker run -v /var/run/docker.sock:/var/run/docker.sock -p 8000:8000 <image>
  ```
