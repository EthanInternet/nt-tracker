import os
import requests
import base64
import hashlib

def push_image(webhook: str, png_path: str):
    with open(png_path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode()
    md5 = hashlib.md5(raw).hexdigest()
    payload = {"msgtype": "image", "image": {"base64": b64, "md5": md5}}
    r = requests.post(webhook, json=payload, timeout=10)
    print("image push:", r.json())

def push_markdown(webhook: str, text: str):
    payload = {"msgtype": "markdown", "markdown": {"content": text}}
    r = requests.post(webhook, json=payload, timeout=10)
    print("md push:", r.json())
