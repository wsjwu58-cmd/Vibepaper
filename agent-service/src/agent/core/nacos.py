"""Nacos 服务注册（OpenAPI）：临时实例注册 + 心跳 + 注销。

与 Spring Cloud Alibaba 一致使用 ephemeral 实例；注册 IP 取通往 Nacos 的出站网卡，
避免默认路由指向公网/WLAN 导致实例不可达、被标记 unhealthy。
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time

import httpx

from .config import settings

logger = logging.getLogger(__name__)


def local_ip() -> str:
    """优先使用配置覆盖；否则探测到 Nacos 的出站 IP。"""
    override = (settings.nacos_register_ip or "").strip()
    if override:
        return override
    host, _, port_s = settings.nacos_addr.partition(":")
    port = int(port_s) if port_s.isdigit() else 8848
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((host, port))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


class NacosRegistrar:
    def __init__(self, service_name: str, port: int):
        self.service_name = service_name
        self.port = port
        self.ip = local_ip()
        self.addr = settings.nacos_addr
        self.token: str | None = None
        self._stop = False
        self._thread: threading.Thread | None = None
        self._registered = False
        self._beat_interval = 5

    def login(self) -> bool:
        try:
            r = httpx.post(
                f"http://{self.addr}/nacos/v1/auth/login",
                data={
                    "username": settings.nacos_username,
                    "password": settings.nacos_password,
                },
                timeout=5,
                trust_env=False,
            )
            if r.status_code == 200:
                self.token = r.json().get("accessToken")
                return True
            logger.warning("nacos login http %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("nacos login failed: %s", e)
        return False

    def _ensure_token(self) -> bool:
        if self.token:
            return True
        return self.login()

    def register(self) -> bool:
        if not self._ensure_token():
            return False
        params = {
            "serviceName": self.service_name,
            "ip": self.ip,
            "port": str(self.port),
            "namespaceId": "",
            "groupName": "DEFAULT_GROUP",
            "clusterName": "DEFAULT",
            "ephemeral": "true",
            "weight": "1",
            "enabled": "true",
            "healthy": "true",
            "metadata": json.dumps({"app": self.service_name}, separators=(",", ":")),
            "accessToken": self.token or "",
        }
        try:
            r = httpx.post(
                f"http://{self.addr}/nacos/v1/ns/instance",
                params=params,
                timeout=5,
                trust_env=False,
            )
            if r.status_code == 200:
                self._registered = True
                logger.info("nacos registered %s -> %s:%s", self.service_name, self.ip, self.port)
                return True
            if r.status_code in (401, 403):
                self.token = None
            logger.warning("nacos register http %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("nacos register failed: %s", e)
        return False

    def beat(self) -> bool:
        if not self._registered:
            return self.register()
        if not self._ensure_token():
            self._registered = False
            return False
        beat = json.dumps(
            {
                "cluster": "DEFAULT",
                "ip": self.ip,
                "port": self.port,
                "serviceName": self.service_name,
                "scheduled": True,
                "weight": 1,
                "metadata": {"app": self.service_name},
            },
            separators=(",", ":"),
        )
        params = {
            "serviceName": self.service_name,
            "groupName": "DEFAULT_GROUP",
            "ephemeral": "true",
            "beat": beat,
            "accessToken": self.token or "",
        }
        try:
            r = httpx.put(
                f"http://{self.addr}/nacos/v1/ns/instance/beat",
                params=params,
                timeout=5,
                trust_env=False,
            )
            if r.status_code == 200:
                try:
                    interval_ms = r.json().get("clientBeatInterval")
                    if isinstance(interval_ms, int) and interval_ms > 0:
                        self._beat_interval = max(1, interval_ms // 1000)
                except Exception:
                    pass
                return True
            if r.status_code in (401, 403):
                self.token = None
            self._registered = False
            logger.warning("nacos beat http %s: %s", r.status_code, r.text[:200])
            return False
        except Exception as e:
            self._registered = False
            logger.warning("nacos beat failed: %s", e)
            return False

    def deregister(self):
        if not self._ensure_token():
            return
        params = {
            "serviceName": self.service_name,
            "ip": self.ip,
            "port": str(self.port),
            "namespaceId": "",
            "groupName": "DEFAULT_GROUP",
            "clusterName": "DEFAULT",
            "ephemeral": "true",
            "accessToken": self.token or "",
        }
        try:
            httpx.delete(
                f"http://{self.addr}/nacos/v1/ns/instance",
                params=params,
                timeout=5,
                trust_env=False,
            )
            logger.info("nacos deregistered %s", self.service_name)
        except Exception as e:
            logger.warning("nacos deregister failed: %s", e)
        finally:
            self._registered = False

    def start(self):
        self.register()

        def _loop():
            while not self._stop:
                try:
                    ok = self.beat()
                    time.sleep(3 if not ok else self._beat_interval)
                except Exception:
                    time.sleep(3)

        self._thread = threading.Thread(target=_loop, daemon=True, name=f"nacos-{self.service_name}")
        self._thread.start()

    def stop(self):
        self._stop = True
        self.deregister()
