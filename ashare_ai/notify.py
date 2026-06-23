from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import requests


def send_webhook(provider: str, url: str, title: str, content: str) -> bool:
    if not url:
        return False

    provider = (provider or "").lower()
    payload: dict

    if provider == "wecom":
        payload = {"msgtype": "text", "text": {"content": f"{title}\n\n{content}"}}
    elif provider == "serverchan":
        payload = {"title": title, "desp": content}
    else:
        payload = {"title": title, "text": content}

    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    return True


def send_email(host: str, port: int, user: str, password: str, to_addr: str, subject: str, body: str) -> bool:
    if not (host and user and password and to_addr):
        return False

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = user
    message["To"] = to_addr

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.sendmail(user, [to_addr], message.as_string())
    return True
