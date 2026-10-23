# -*- coding: utf-8 -*-
"""阿里云 OSS 图床示例：上传、缩略图、签名 URL、30 天转低频存储。"""

import base64
import csv
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import oss2
from oss2.credentials import EnvironmentVariableCredentialsProvider, StaticCredentialsProvider

DEFAULT_ENDPOINT = "https://oss-cn-beijing.aliyuncs.com"
DEFAULT_BUCKET = "jxxyyy"
DEFAULT_REGION = "cn-beijing"

EXT_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # OSS 图片处理原图上限为 20 MB
IMAGE_PREFIX = "images/"
THUMB_PREFIX = "thumbs/"


class ImageHost:
    def __init__(self):
        auth = oss2.ProviderAuthV4(self._credentials_provider())
        self.bucket = oss2.Bucket(
            auth,
            os.environ.get("OSS_ENDPOINT", DEFAULT_ENDPOINT),
            os.environ.get("OSS_BUCKET", DEFAULT_BUCKET),
            region=os.environ.get("OSS_REGION", DEFAULT_REGION),
        )

    def upload(self, file_obj, filename, content_type=None):
        """上传原图并在服务端生成 WebP 缩略图，返回对象 key 和临时访问 URL。"""
        ext = Path(filename).suffix.lower()
        if ext not in EXT_CONTENT_TYPES:
            raise ValueError(f"不支持的图片后缀: {ext}")

        data = file_obj.read()
        if not data:
            raise ValueError("文件为空")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("图片超过 20 MB")

        # 客户端有时传 application/octet-stream，这里以扩展名兜底。
        content_type = (content_type or "").split(";")[0]
        if not content_type.startswith("image/"):
            content_type = mimetypes.guess_type(filename)[0] or EXT_CONTENT_TYPES[ext]
        if not content_type.startswith("image/"):
            raise ValueError("Content-Type 不是图片")

        now = datetime.now(timezone.utc)
        key = f"{IMAGE_PREFIX}{now:%Y/%m/%d}/{uuid.uuid4().hex}{ext}"
        self.bucket.put_object(key, data, headers={"Content-Type": content_type})

        try:
            thumb_key = self.create_thumbnail(key)
        except Exception:
            # 缩略图失败时不留下孤儿原图；生产环境也可改为保留并记录日志。
            self.bucket.delete_object(key)
            raise

        return {
            "key": key,
            "thumb_key": thumb_key,
            "url": self.signed_url(key),
            "thumb_url": self.signed_url(thumb_key),
        }

    def create_thumbnail(self, key, width=480, quality=82):
        """用 OSS 图片处理持久化在服务端生成缩略图，不经过本地下载再上传。"""
        relative = key[len(IMAGE_PREFIX):] if key.startswith(IMAGE_PREFIX) else key
        thumb_key = f"{THUMB_PREFIX}{relative.rsplit('.', 1)[0]}_w{width}.webp"
        style = f"image/resize,m_lfit,w_{width},h_{width}/format,webp/quality,q_{quality}"
        process = "{}|sys/saveas,o_{},b_{}".format(
            style,
            self._b64(thumb_key),
            self._b64(self.bucket.bucket_name),
        )
        self.bucket.process_object(key, process)
        return thumb_key

    def signed_url(self, key, expires=3600):
        """生成私有 Object 的临时 GET URL，默认 1 小时有效。"""
        return self.bucket.sign_url("GET", key, expires, slash_safe=True)

    def thumbnail_url(self, key, width=480, expires=3600):
        """可选方案：不落盘，实时生成缩略图。"""
        style = f"image/resize,m_lfit,w_{width},h_{width}/format,webp/quality,q_82"
        return self.bucket.sign_url(
            "GET",
            key,
            expires,
            params={"x-oss-process": style},
            slash_safe=True,
        )

    @staticmethod
    def _credentials_provider():
        """优先读取 OSS_ACCESS_KEY_CSV，否则使用环境变量凭证。"""
        csv_path = os.environ.get("OSS_ACCESS_KEY_CSV")
        if not csv_path:
            return EnvironmentVariableCredentialsProvider()

        with open(ImageHost._resolve_csv_path(csv_path), newline="", encoding="utf-8-sig") as f:
            row = next(csv.DictReader(f))

        access_key_id = row.get("AccessKey ID") or row.get("AccessKeyId")
        access_key_secret = row.get("AccessKey Secret") or row.get("AccessKeySecret")
        if not access_key_id or not access_key_secret:
            raise ValueError("AccessKey.csv 缺少 AccessKey ID / AccessKey Secret 列")

        return StaticCredentialsProvider(access_key_id.strip(), access_key_secret.strip())

    @staticmethod
    def _resolve_csv_path(path):
        """支持在 WSL 中直接填 Windows 路径，例如 C:\\Users\\...\\AccessKey.csv。"""
        path = os.path.expanduser(path)
        if os.path.exists(path):
            return path
        if len(path) >= 3 and path[1] == ":" and path[2] in ("\\", "/"):
            wsl_path = f"/mnt/{path[0].lower()}/" + path[3:].replace("\\", "/")
            if os.path.exists(wsl_path):
                return wsl_path
        return path

    @staticmethod
    def _b64(value):
        return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


if __name__ == "__main__":
    # 只读检查生命周期，不会修改网页上已配置好的规则。
    host = ImageHost()
    try:
        lifecycle = host.bucket.get_bucket_lifecycle()
    except oss2.exceptions.NoSuchLifecycle:
        print("未配置生命周期规则")
    else:
        for rule in lifecycle.rules:
            transitions = rule.storage_transitions or []
            print(
                rule.id,
                f"prefix={rule.prefix!r}",
                rule.status,
                [(t.days, t.storage_class) for t in transitions],
            )
