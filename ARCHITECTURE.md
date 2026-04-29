# 데이터 입력/조회 웹앱 설계 및 MVP 구현

## 현재 포함된 MVP
- FastAPI + SQLite 영속 저장 구조
- JWT 로그인/사용자 조회
- 엑셀 복붙 미리보기 + 유효성 검증
- Import commit 저장 API (`/imports/commit`)
- RBAC (admin/editor/viewer)
- import/audit 테이블 기록
- 브라우저에서 실행 가능한 프론트 화면 (`frontend/index.html`)

## 다음 구현 단계
1. PostgreSQL 전환 및 마이그레이션(Alembic)
2. Next.js UI로 확장 (라우팅/상태관리)
3. 조회/검색 API, 페이지네이션
4. 관리자용 사용자/권한 관리 UI
5. 실시간 진행률(WebSocket) 및 비동기 처리
