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

이번 단계는 첫 번째 화살표와 상태 저장소까지 구현한다. worker는 다음 단계에서 추가한다. 그러므로 API에 `POST`를 보내도 지금은 VM이 생성되지 않으며, `REQUESTED` 상태가 저장되는 것이 정상이다.

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
- Python virtual environment와 API 의존성 설치
- `private-cloud-api.service`를 systemd에 등록하고 `127.0.0.1:8000`에서 실행

## 확인

API는 FastAPI OpenAPI 화면을 자동 제공한다. control에서 확인한다.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/images
curl http://127.0.0.1:8000/v1/instances

curl --request POST http://127.0.0.1:8000/v1/instances \
  --header 'Content-Type: application/json' \
  --data '{
    "name": "api-demo01",
    "image": "rocky-9-genericcloud",
    "vcpus": 1,
    "memory_mb": 1024,
    "disk_gb": 10
  }'
```

`http://127.0.0.1:8000/docs`에서는 같은 API를 브라우저 UI로 호출할 수 있다. API 인증과 Nginx 공개는 관리자 웹 화면 단계에서 함께 적용한다.
