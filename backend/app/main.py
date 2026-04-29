from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Generator, List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = "sqlite:///./app.db"
SECRET_KEY = "change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.viewer.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20), default="paste")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    success_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ImportJobError(Base):
    __tablename__ = "import_job_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(String(255))


class Record(Base):
    __tablename__ = "records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class User(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ImportPreviewRequest(BaseModel):
    pasted_text: str


class ImportPreviewRow(BaseModel):
    row_no: int
    columns: List[str]


class ImportErrorOut(BaseModel):
    row_no: int
    column_name: str
    message: str


class ImportPreviewResponse(BaseModel):
    headers: List[str]
    rows: List[ImportPreviewRow]
    errors: List[ImportErrorOut]


class ImportCommitRequest(BaseModel):
    pasted_text: str


class ImportCommitResponse(BaseModel):
    job_id: int
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int


app = FastAPI(title="Data Import Platform", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_users(db: Session) -> None:
    if db.scalar(select(UserModel).where(UserModel.email == "admin@example.com")):
        return
    db.add_all(
        [
            UserModel(email="admin@example.com", name="Admin", password_hash=pwd_context.hash("admin1234"), role=Role.admin.value),
            UserModel(email="editor@example.com", name="Editor", password_hash=pwd_context.hash("editor1234"), role=Role.editor.value),
            UserModel(email="viewer@example.com", name="Viewer", password_hash=pwd_context.hash("viewer1234"), role=Role.viewer.value),
        ]
    )
    db.commit()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_users(db)


def authenticate_user(db: Session, email: str, password: str) -> Optional[UserModel]:
    user = db.scalar(select(UserModel).where(UserModel.email == email))
    if not user or not pwd_context.verify(password, user.password_hash):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> UserModel:
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc
    user = db.scalar(select(UserModel).where(UserModel.email == email))
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*roles: Role):
    def _checker(user: UserModel = Depends(get_current_user)) -> UserModel:
        if user.role not in [role.value for role in roles]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _checker


def parse_paste_text(pasted_text: str) -> tuple[list[str], list[ImportPreviewRow], list[ImportErrorOut]]:
    lines = [line for line in pasted_text.splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="No data found")
    headers = lines[0].split("\t")
    rows: list[ImportPreviewRow] = []
    errors: list[ImportErrorOut] = []
    for idx, line in enumerate(lines[1:], start=2):
        columns = line.split("\t")
        rows.append(ImportPreviewRow(row_no=idx, columns=columns))
        if len(columns) != len(headers):
            errors.append(ImportErrorOut(row_no=idx, column_name="*", message="Column count mismatch"))
        for col_idx, value in enumerate(columns):
            if not value.strip():
                col_name = headers[col_idx] if col_idx < len(headers) else f"col_{col_idx+1}"
                errors.append(ImportErrorOut(row_no=idx, column_name=col_name, message="Required value is empty"))
    return headers, rows, errors


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token({"sub": user.email, "role": user.role}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return Token(access_token=token)


@app.get("/auth/me", response_model=User)
async def me(current_user: UserModel = Depends(get_current_user)):
    return User(id=current_user.id, email=current_user.email, name=current_user.name, role=Role(current_user.role))


@app.post("/imports/preview", response_model=ImportPreviewResponse)
async def import_preview(payload: ImportPreviewRequest, _: UserModel = Depends(require_roles(Role.admin, Role.editor, Role.viewer))):
    headers, rows, errors = parse_paste_text(payload.pasted_text)
    return ImportPreviewResponse(headers=headers, rows=rows, errors=errors)


@app.post("/imports/commit", response_model=ImportCommitResponse)
async def import_commit(payload: ImportCommitRequest, user: UserModel = Depends(require_roles(Role.admin, Role.editor)), db: Session = Depends(get_db)):
    headers, rows, errors = parse_paste_text(payload.pasted_text)
    job = ImportJob(created_by=user.id, source_type="paste", status="saving", total_rows=len(rows))
    db.add(job)
    db.flush()

    code_idx = headers.index("record_code") if "record_code" in headers else 0
    name_idx = headers.index("name") if "name" in headers else 1 if len(headers) > 1 else 0
    memo_idx = headers.index("memo") if "memo" in headers else None

    success_rows = 0
    for row in rows:
        if any(err.row_no == row.row_no for err in errors):
            continue
        record_code = row.columns[code_idx].strip() if code_idx < len(row.columns) else ""
        name = row.columns[name_idx].strip() if name_idx < len(row.columns) else ""
        memo = row.columns[memo_idx].strip() if memo_idx is not None and memo_idx < len(row.columns) else None
        if not record_code or not name:
            errors.append(ImportErrorOut(row_no=row.row_no, column_name="record_code/name", message="Required values missing"))
            continue
        if db.scalar(select(Record).where(Record.record_code == record_code)):
            errors.append(ImportErrorOut(row_no=row.row_no, column_name="record_code", message="Duplicate record_code"))
            continue
        db.add(Record(record_code=record_code, name=name, memo=memo, created_by=user.id))
        success_rows += 1

    for err in errors:
        db.add(ImportJobError(job_id=job.id, row_no=err.row_no, column_name=err.column_name, message=err.message))

    job.success_rows = success_rows
    job.failed_rows = len(rows) - success_rows
    job.status = "done"
    job.finished_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor_user_id=user.id, action="IMPORT_DONE", target_type="import_job", target_id=str(job.id)))
    db.commit()

    return ImportCommitResponse(job_id=job.id, status=job.status, total_rows=job.total_rows, success_rows=job.success_rows, failed_rows=job.failed_rows)
