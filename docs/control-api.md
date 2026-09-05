# Control API와 MariaDB 상태 저장소

이 단계는 웹 화면보다 먼저 **API 요청을 영구적으로 저장하는 backend**를 만든다. API는 FastAPI, 상태 저장소는 MariaDB를 사용한다. API는 control의 `127.0.0.1:8000`에만 열리므로, 아직 VMnet2/provider 네트워크나 인터넷에 공개되지 않는다.

## 왜 요청 저장과 VM 생성을 분리하는가

웹 화면이 `POST /v1/instances`를 호출할 때 Ansible을 HTTP 요청 안에서 바로 실행하면, 브라우저 연결이 끊겼을 때 결과·재시도·실패 이유를 관리하기 어렵다.

```text
POST /v1/instances
  → MariaDB: REQUESTED 행 생성 (HTTP 202)
  → worker: scheduler와 Ansible 실행
  → MariaDB: SCHEDULING / PROVISIONING / ACTIVE 또는 ERROR로 갱신
```

worker까지 같은 배포에 포함한다. `POST`는 즉시 `202 Accepted`를 반환하고, 이후 worker가 scheduler와 Ansible을 호출한다. API 응답 속도와 실제 VM 생성 시간을 분리한 구조다.

## 역할과 데이터 모델

이 서비스는 공개 회원가입·결제 서비스가 아니라, 팀 내부 구성원이 쓰는 self-service private cloud다.

- `admin`: 사용자·전체 VM·compute 자원을 볼 수 있는 운영자
- `member`: 자신의 SSH key와 자신의 VM만 보는 사용자
- `clouduser`: 생성된 guest VM 안의 고정 Linux 계정. 사용자는 이 계정에 자신이 등록한 SSH key로 접속한다.

MariaDB는 다음 관계를 저장한다. 상세한 실제 컬럼·외래키·soft delete 보존 규칙은
[Control-plane 데이터 모델](data-model.md)에 기록한다.

```text
users ──< ssh_public_keys
  │
  └──< instances >── images
          │
          ├── compute_nodes
          ├── operations
          └── instance_events
```

VM 생성은 `instances`와 `operations(CREATE/PENDING)`를 한 transaction으로 만든다. worker가 작업을 가져가 `SCHEDULING → PROVISIONING → WAITING_FOR_IP → ACTIVE`로 바꾸며, 실패한 이유도 operation과 event에 남긴다. 삭제도 별도 `DELETE` operation으로 처리한다.

외부 browser는 `http://172.16.2.10:8080`의 Nginx portal로 접속한다. FastAPI는
`127.0.0.1:8000`에서만 listen하고 Nginx가 같은 origin으로 reverse proxy한다. 이는 API port를
관리망에 직접 노출하지 않기 위한 lab 범위의 경계다.

## 배포

control에서 저장소를 최신화한 뒤 API·MariaDB playbook을 실행한다.

```bash
cd ~/private-cloud-platform
git pull --ff-only

cd automation/ansible
ansible-playbook \
  --ask-become-pass \
  playbooks/configure-control-api.yml
```

playbook은 다음을 자동으로 수행한다.

- `mariadb-server`, `python3-pip` 설치 및 MariaDB 시작
- API 전용 MariaDB 사용자·database 생성
- control 로컬의 `/etc/private-cloud/api.env`에 난수 DB password 저장 (`0600`, Git 제외)
- Alembic migration으로 7개 control-plane 테이블 생성
- 초기 `admin`, `member1`, Rocky 이미지, compute1·compute2 카탈로그 생성
- Python virtual environment와 API 의존성 설치
- `private-cloud-api.service`와 `private-cloud-worker.service`를 systemd에 등록

초기 계정의 난수 비밀번호는 Git이나 Ansible 출력에 나오지 않는다. 첫 배포 후 control의 `user1`에서만 다음 파일을 읽어 로그인에 사용한다.

```bash
cat ~/private-cloud-initial-credentials.env
```

첫 로그인 후 안전한 비밀 관리 위치에 보관하고, 더 이상 필요 없을 때 파일을 삭제한다.

## 확인

API는 FastAPI OpenAPI 화면을 자동 제공한다. control에서 확인한다.

```bash
curl http://127.0.0.1:8000/health
systemctl --no-pager --full status private-cloud-api private-cloud-worker
curl http://127.0.0.1:8000/docs
```

`/docs`에서 먼저 `/v1/auth/login`을 호출하면 session cookie가 생기고, 이후 key·image·instance endpoint를 시험할 수 있다. `/`는 같은 API를 사용하는 self-service portal이다. admin은 전체 VM·사용자·compute 예약량을 보고, member는 자신의 키·VM만 본다.
