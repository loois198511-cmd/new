# Backend (FastAPI)

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Demo Accounts
- admin@example.com / admin1234
- editor@example.com / editor1234
- viewer@example.com / viewer1234

## Endpoints
- `POST /auth/login`
- `GET /auth/me`
- `POST /imports/preview` (admin/editor/viewer)
- `POST /imports/commit` (admin/editor only)

## Paste Format
첫 줄은 헤더여야 하며 `record_code`, `name`, `memo` 컬럼을 권장합니다.
