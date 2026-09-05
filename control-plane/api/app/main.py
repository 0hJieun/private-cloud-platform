"""인증된 사용자의 요청을 durable operation으로 기록하는 control API."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI, HTTPException, Request, status
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.models import (
    ComputeNode,
    Image,
    Instance,
    InstanceEvent,
    InstanceStatus,
    Operation,
    OperationStatus,
    OperationType,
    SshPublicKey,
    User,
    UserRole,
)
from app.schemas import (
    HealthRead,
    ImageRead,
    InstanceCreate,
    InstanceRead,
    LoginRequest,
    OperationRead,
    SshPublicKeyCreate,
    SshPublicKeyRead,
    UserCreate,
    UserRead,
)
from app.security import hash_password, ssh_fingerprint, verify_password


app = FastAPI(
    title="Private Cloud Control API",
    version="0.2.0",
    description="사용자·SSH 키·인스턴스 요청을 MariaDB에 기록하고 worker에 전달하는 control-plane API",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret,
    same_site="lax",
    https_only=False,  # 현재 lab은 HTTP. Nginx HTTPS 배포 단계에서 true로 바꾼다.
)


def instance_read(instance: Instance, session: Session) -> InstanceRead:
    """외부 API에는 compute UUID 대신 사람이 읽을 수 있는 노드 이름을 보인다."""

    compute = session.get(ComputeNode, instance.assigned_compute_id) if instance.assigned_compute_id else None
    return InstanceRead(
        id=instance.id,
        name=instance.name,
        owner_id=instance.owner_id,
        image_id=instance.image_id,
        requested_vcpus=instance.requested_vcpus,
        requested_memory_mb=instance.requested_memory_mb,
        requested_disk_gb=instance.requested_disk_gb,
        status=instance.status,
        assigned_compute=compute.name if compute else None,
        provider_ip=instance.provider_ip,
        guest_username=instance.guest_username,
        error_message=instance.error_message,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


def user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def require_user(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    user = session.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다.")
    return user


def owned_instance_or_404(instance_id: str, user: User, session: Session) -> Instance:
    instance = session.get(Instance, instance_id)
    if not instance or (user.role != UserRole.ADMIN and instance.owner_id != user.id):
        # 다른 사용자의 존재 여부도 알리지 않도록 동일하게 404를 반환한다.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="인스턴스를 찾지 못했습니다.")
    return instance


@app.get("/health", response_model=HealthRead, tags=["platform"])
def health(session: Session = Depends(get_session)) -> HealthRead:
    session.execute(text("SELECT 1"))
    return HealthRead(status="ok", environment=get_settings().environment)


@app.post("/v1/auth/login", response_model=UserRead, tags=["auth"])
def login(payload: LoginRequest, request: Request, session: Session = Depends(get_session)) -> UserRead:
    user = session.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자명 또는 비밀번호가 올바르지 않습니다.")
    request.session.clear()
    request.session["user_id"] = user.id
    return user_read(user)


@app.post("/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
def logout(request: Request) -> None:
    request.session.clear()


@app.get("/v1/me", response_model=UserRead, tags=["auth"])
def me(user: User = Depends(require_user)) -> UserRead:
    return user_read(user)


@app.get("/v1/users", response_model=list[UserRead], tags=["users"])
def list_users(_: User = Depends(require_admin), session: Session = Depends(get_session)) -> list[UserRead]:
    return [user_read(item) for item in session.scalars(select(User).order_by(User.username))]


@app.post("/v1/users", response_model=UserRead, status_code=status.HTTP_201_CREATED, tags=["users"])
def create_user(
    payload: UserCreate, _: User = Depends(require_admin), session: Session = Depends(get_session)
) -> UserRead:
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 사용자명입니다.") from error
    session.refresh(user)
    return user_read(user)


@app.get("/v1/ssh-keys", response_model=list[SshPublicKeyRead], tags=["ssh-keys"])
def list_ssh_keys(user: User = Depends(require_user), session: Session = Depends(get_session)) -> list[SshPublicKeyRead]:
    keys = session.scalars(
        select(SshPublicKey).where(SshPublicKey.owner_id == user.id).order_by(SshPublicKey.name)
    )
    return [
        SshPublicKeyRead(
            id=item.id, name=item.name, fingerprint=item.fingerprint, is_active=item.is_active, created_at=item.created_at
        )
        for item in keys
    ]


@app.post("/v1/ssh-keys", response_model=SshPublicKeyRead, status_code=status.HTTP_201_CREATED, tags=["ssh-keys"])
def add_ssh_key(
    payload: SshPublicKeyCreate, user: User = Depends(require_user), session: Session = Depends(get_session)
) -> SshPublicKeyRead:
    try:
        fingerprint = ssh_fingerprint(payload.public_key)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    key = SshPublicKey(
        owner_id=user.id,
        name=payload.name,
        public_key=payload.public_key.strip(),
        fingerprint=fingerprint,
    )
    session.add(key)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 키 또는 키 이름입니다.") from error
    session.refresh(key)
    return SshPublicKeyRead(id=key.id, name=key.name, fingerprint=key.fingerprint, is_active=key.is_active, created_at=key.created_at)


@app.get("/v1/images", response_model=list[ImageRead], tags=["images"])
def list_images(_: User = Depends(require_user), session: Session = Depends(get_session)) -> list[ImageRead]:
    return [
        ImageRead(
            id=item.id,
            display_name=item.display_name,
            os_family=item.os_family,
            os_version=item.os_version,
            disk_format=item.disk_format,
            sha256=item.sha256,
            available=item.is_enabled,
        )
        for item in session.scalars(select(Image).where(Image.is_enabled.is_(True)).order_by(Image.display_name))
    ]


@app.get("/v1/instances", response_model=list[InstanceRead], tags=["instances"])
def list_instances(user: User = Depends(require_user), session: Session = Depends(get_session)) -> list[InstanceRead]:
    statement = select(Instance).where(Instance.deleted_at.is_(None)).order_by(Instance.created_at.desc())
    if user.role != UserRole.ADMIN:
        statement = statement.where(Instance.owner_id == user.id)
    return [instance_read(item, session) for item in session.scalars(statement)]


@app.get("/v1/instances/{instance_id}", response_model=InstanceRead, tags=["instances"])
def get_instance(
    instance_id: str, user: User = Depends(require_user), session: Session = Depends(get_session)
) -> InstanceRead:
    return instance_read(owned_instance_or_404(instance_id, user, session), session)


@app.post(
    "/v1/instances",
    response_model=InstanceRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["instances"],
)
def request_instance(
    payload: InstanceCreate, user: User = Depends(require_user), session: Session = Depends(get_session)
) -> InstanceRead:
    image = session.get(Image, payload.image_id)
    if not image or not image.is_enabled:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="선택한 이미지를 사용할 수 없습니다.")
    ssh_key = session.get(SshPublicKey, payload.ssh_public_key_id)
    if not ssh_key or not ssh_key.is_active or ssh_key.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="선택한 SSH 공개키를 사용할 수 없습니다.")
    instance = Instance(
        name=payload.name,
        active_name=payload.name,
        owner_id=user.id,
        image_id=image.id,
        ssh_public_key_id=ssh_key.id,
        requested_vcpus=payload.vcpus,
        requested_memory_mb=payload.memory_mb,
        requested_disk_gb=payload.disk_gb,
        status=InstanceStatus.REQUESTED,
    )
    session.add(instance)
    try:
        session.flush()
        operation = Operation(instance_id=instance.id, operation_type=OperationType.CREATE, status=OperationStatus.PENDING)
        session.add(operation)
        session.add(
            InstanceEvent(
                instance_id=instance.id,
                operation_id=operation.id,
                previous_status=None,
                next_status=InstanceStatus.REQUESTED,
                message="사용자가 인스턴스 생성을 요청했습니다.",
            )
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="같은 이름의 인스턴스 요청이 이미 존재합니다.",
        ) from error
    session.refresh(instance)
    return instance_read(instance, session)


@app.get("/v1/instances/{instance_id}/operations", response_model=list[OperationRead], tags=["instances"])
def list_operations(
    instance_id: str, user: User = Depends(require_user), session: Session = Depends(get_session)
) -> list[OperationRead]:
    owned_instance_or_404(instance_id, user, session)
    return [
        OperationRead(
            id=item.id,
            operation_type=item.operation_type,
            status=item.status,
            attempts=item.attempts,
            error_message=item.error_message,
            created_at=item.created_at,
            started_at=item.started_at,
            completed_at=item.completed_at,
        )
        for item in session.scalars(
            select(Operation).where(Operation.instance_id == instance_id).order_by(Operation.created_at.desc())
        )
    ]


@app.delete("/v1/instances/{instance_id}", response_model=OperationRead, status_code=status.HTTP_202_ACCEPTED, tags=["instances"])
def request_delete_instance(
    instance_id: str, user: User = Depends(require_user), session: Session = Depends(get_session)
) -> OperationRead:
    instance = owned_instance_or_404(instance_id, user, session)
    if instance.status in {InstanceStatus.REQUESTED, InstanceStatus.SCHEDULING, InstanceStatus.PROVISIONING, InstanceStatus.DELETE_REQUESTED, InstanceStatus.DELETING}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 처리 중인 인스턴스입니다.")
    if instance.status == InstanceStatus.DELETED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 삭제된 인스턴스입니다.")

    old_status = instance.status
    instance.status = InstanceStatus.DELETE_REQUESTED
    operation = Operation(instance_id=instance.id, operation_type=OperationType.DELETE, status=OperationStatus.PENDING)
    session.add(operation)
    session.add(
        InstanceEvent(
            instance_id=instance.id,
            operation_id=operation.id,
            previous_status=old_status,
            next_status=InstanceStatus.DELETE_REQUESTED,
            message="사용자가 인스턴스 삭제를 요청했습니다.",
        )
    )
    session.commit()
    session.refresh(operation)
    return OperationRead(
        id=operation.id,
        operation_type=operation.operation_type,
        status=operation.status,
        attempts=operation.attempts,
        error_message=operation.error_message,
        created_at=operation.created_at,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
    )
