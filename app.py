# -*- coding: utf-8 -*-
"""最小上传接口：POST /upload，form-data 字段名为 file。"""

from flask import Flask, jsonify, request

from image_host import ImageHost

app = Flask(__name__)
# 略大于 20 MB，给 multipart 表单边界留余量。
app.config["MAX_CONTENT_LENGTH"] = 21 * 1024 * 1024
host = ImageHost()


@app.post("/upload")
def upload():
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "缺少 file 字段"}), 400
    try:
        return jsonify(host.upload(file.stream, file.filename, file.mimetype))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
