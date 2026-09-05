"""Ansible image catalog playbook이 검증한 이미지를 MariaDB에 등록한다."""

from __future__ import annotations

import os

from app.database import SessionLocal
from app.models import Image


REQUIRED = (
    "PRIVATE_CLOUD_CATALOG_IMAGE_ID",
    "PRIVATE_CLOUD_CATALOG_DISPLAY_NAME",
    "PRIVATE_CLOUD_CATALOG_OS_FAMILY",
    "PRIVATE_CLOUD_CATALOG_OS_VERSION",
    "PRIVATE_CLOUD_CATALOG_SOURCE_PATH",
    "PRIVATE_CLOUD_CATALOG_SHA256",
)


def main() -> None:
    values = {key: os.environ.get(key, "") for key in REQUIRED}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"catalog 등록 환경 변수가 없습니다: {', '.join(missing)}")
    if len(values["PRIVATE_CLOUD_CATALOG_SHA256"]) != 64:
        raise RuntimeError("catalog SHA256 값은 64자리여야 합니다.")

    with SessionLocal.begin() as session:
        image = session.get(Image, values["PRIVATE_CLOUD_CATALOG_IMAGE_ID"])
        if image is None:
            image = Image(
                id=values["PRIVATE_CLOUD_CATALOG_IMAGE_ID"],
                display_name=values["PRIVATE_CLOUD_CATALOG_DISPLAY_NAME"],
                os_family=values["PRIVATE_CLOUD_CATALOG_OS_FAMILY"],
                os_version=values["PRIVATE_CLOUD_CATALOG_OS_VERSION"],
                disk_format="qcow2",
                source_path=values["PRIVATE_CLOUD_CATALOG_SOURCE_PATH"],
                sha256=values["PRIVATE_CLOUD_CATALOG_SHA256"],
                is_enabled=True,
            )
            session.add(image)
        else:
            image.display_name = values["PRIVATE_CLOUD_CATALOG_DISPLAY_NAME"]
            image.os_family = values["PRIVATE_CLOUD_CATALOG_OS_FAMILY"]
            image.os_version = values["PRIVATE_CLOUD_CATALOG_OS_VERSION"]
            image.disk_format = "qcow2"
            image.source_path = values["PRIVATE_CLOUD_CATALOG_SOURCE_PATH"]
            image.sha256 = values["PRIVATE_CLOUD_CATALOG_SHA256"]
            image.is_enabled = True


if __name__ == "__main__":
    main()
