from __future__ import annotations

import base64
import binascii
import hashlib
import json
import platform
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_timestamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _parse_timestamp(value).isoformat()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_windows_machine_guid() -> str | None:
    if platform.system().lower() != "windows":
        return None
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _read_mac_address() -> str | None:
    node = uuid.getnode()
    if (node >> 40) % 2:
        return None
    return f"{node:012x}"


@dataclass(frozen=True, slots=True)
class ActivationConfig:
    app_name: str
    product_id: str
    storage_dir_name: str
    key_prefix: str = "APP-LIC-1."
    schema_version: int = 1
    public_key_file_name: str = "license_public_key.pem"
    license_file_name: str = "license.json"
    activation_key_file_name: str = "activation.key"
    signature_algorithm: str = "ed25519"


@dataclass(frozen=True, slots=True)
class MachineIdentity:
    fields: dict[str, str]
    fingerprint: str

    @classmethod
    def from_fields(cls, fields: Mapping[str, Any]) -> "MachineIdentity":
        normalized = {
            str(key): str(value).strip()
            for key, value in fields.items()
            if value is not None and str(value).strip()
        }
        if not normalized:
            raise ValueError("Machine identity must include at least one non-empty field.")
        fingerprint = hashlib.sha256(_canonical_json_bytes(normalized)).hexdigest()
        return cls(fields=normalized, fingerprint=fingerprint)

    @classmethod
    def collect(cls) -> "MachineIdentity":
        fields: dict[str, str] = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "machine": platform.machine(),
        }
        hostname = platform.node().strip()
        if hostname:
            fields["hostname"] = hostname
        machine_guid = _read_windows_machine_guid()
        if machine_guid:
            fields["machine_guid"] = machine_guid
        mac_address = _read_mac_address()
        if mac_address:
            fields["mac_address"] = mac_address
        return cls.from_fields(fields)

    def request_payload(self, config: ActivationConfig) -> dict[str, Any]:
        return {
            "schema_version": config.schema_version,
            "product": config.product_id,
            "fingerprint": self.fingerprint,
            "machine": dict(self.fields),
        }


@dataclass(slots=True)
class LicenseValidationResult:
    status: str
    message: str
    claims: dict[str, Any] | None = None
    source_path: Path | None = None

    @property
    def valid(self) -> bool:
        return self.status == "valid"


def default_license_storage_path(config: ActivationConfig) -> Path:
    return Path.home() / config.storage_dir_name / config.license_file_name


def build_license_claims(
    *,
    config: ActivationConfig,
    customer_name: str,
    machine_fingerprint: str,
    license_id: str,
    expires_at: datetime | str | None = None,
    issued_at: datetime | str | None = None,
    features: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    issued_timestamp = _normalize_timestamp(issued_at or _utc_now())
    normalized_features: list[str] = []
    seen_features: set[str] = set()
    for feature in features or []:
        cleaned = str(feature).strip()
        if not cleaned or cleaned in seen_features:
            continue
        seen_features.add(cleaned)
        normalized_features.append(cleaned)
    return {
        "schema_version": config.schema_version,
        "product": config.product_id,
        "license_id": str(license_id).strip(),
        "customer_name": str(customer_name).strip(),
        "machine_fingerprint": str(machine_fingerprint).strip().lower(),
        "issued_at": issued_timestamp,
        "expires_at": _normalize_timestamp(expires_at),
        "features": normalized_features,
    }


def sign_license_claims(claims: Mapping[str, Any], private_key_pem: bytes) -> dict[str, Any]:
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(_canonical_json_bytes(dict(claims)))
    return {
        "schema_version": claims.get("schema_version", 1),
        "signature_algorithm": "ed25519",
        "claims": dict(claims),
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def encode_activation_key(document: Mapping[str, Any], config: ActivationConfig) -> str:
    encoded = base64.urlsafe_b64encode(_canonical_json_bytes(document)).decode("ascii")
    return config.key_prefix + encoded.rstrip("=")


def decode_activation_key(activation_key: str, config: ActivationConfig) -> dict[str, Any]:
    cleaned = "".join(str(activation_key).split())
    if not cleaned.startswith(config.key_prefix):
        raise ValueError("Activation key has an unsupported prefix.")
    payload = cleaned[len(config.key_prefix) :]
    payload += "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
    document = json.loads(decoded.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Activation key payload is not a license document.")
    return document


def resolve_runtime_root(explicit_root: Path | None = None) -> Path:
    if explicit_root is not None:
        return explicit_root.resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


class LicenseManager:
    def __init__(
        self,
        runtime_root: Path,
        config: ActivationConfig,
        *,
        machine_identity: MachineIdentity | None = None,
        storage_path: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.config = config
        self.machine_identity = machine_identity or MachineIdentity.collect()
        self.storage_path = storage_path or default_license_storage_path(config)
        self.now_provider = now_provider or _utc_now

    def public_key_search_paths(self) -> tuple[Path, ...]:
        return (
            self.runtime_root / self.config.public_key_file_name,
            self.runtime_root / "_internal" / self.config.public_key_file_name,
        )

    def public_key_path(self) -> Path:
        for path in self.public_key_search_paths():
            if path.exists():
                return path
        return self.public_key_search_paths()[0]

    def candidate_license_paths(self) -> tuple[Path, ...]:
        paths = [
            self.storage_path,
            self.runtime_root / self.config.license_file_name,
            self.runtime_root / self.config.activation_key_file_name,
        ]
        seen: set[Path] = set()
        unique_paths: list[Path] = []
        for path in paths:
            resolved = Path(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            unique_paths.append(resolved)
        return tuple(unique_paths)

    def public_key_exists(self) -> bool:
        return self.public_key_path().exists()

    def machine_request_payload(self) -> dict[str, Any]:
        return self.machine_identity.request_payload(self.config)

    def current_status(self) -> LicenseValidationResult:
        if not self.public_key_exists():
            return LicenseValidationResult(
                status="missing_public_key",
                message=f"未找到授权公钥文件：{self.public_key_path().name}",
            )
        for license_path in self.candidate_license_paths():
            if license_path.exists():
                return self.validate_license_file(license_path)
        return LicenseValidationResult(
            status="missing_license",
            message="未检测到有效授权，请导入激活密钥。",
        )

    def validate_license_file(self, path: Path) -> LicenseValidationResult:
        try:
            document = self._load_license_document_text(Path(path).read_text(encoding="utf-8"))
        except OSError:
            return LicenseValidationResult(
                status="license_read_error",
                message="授权文件无法读取。",
                source_path=Path(path),
            )
        except ValueError as exc:
            return LicenseValidationResult(
                status="invalid_license_file",
                message=f"授权文件格式无效：{exc}",
                source_path=Path(path),
            )
        result = self.validate_license_document(document)
        result.source_path = Path(path)
        return result

    def _load_license_document_text(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith(self.config.key_prefix):
            return decode_activation_key(cleaned, self.config)
        document = json.loads(cleaned)
        if not isinstance(document, dict):
            raise ValueError("授权内容不是有效对象。")
        return document

    def validate_license_document(self, document: Mapping[str, Any]) -> LicenseValidationResult:
        try:
            public_key = serialization.load_pem_public_key(self.public_key_path().read_bytes())
        except OSError:
            return LicenseValidationResult(
                status="missing_public_key",
                message=f"未找到授权公钥文件：{self.public_key_path().name}",
            )
        except ValueError:
            return LicenseValidationResult(
                status="invalid_public_key",
                message="授权公钥文件格式无效。",
            )

        claims = document.get("claims")
        signature_text = document.get("signature")
        if not isinstance(claims, dict) or not isinstance(signature_text, str):
            return LicenseValidationResult(
                status="invalid_document",
                message="授权文件缺少 claims 或 signature 字段。",
            )
        if document.get("signature_algorithm") != self.config.signature_algorithm:
            return LicenseValidationResult(
                status="unsupported_algorithm",
                message="授权签名算法不受支持。",
            )
        if claims.get("schema_version") != self.config.schema_version or document.get("schema_version") != self.config.schema_version:
            return LicenseValidationResult(
                status="schema_mismatch",
                message="授权版本与当前程序不兼容。",
            )
        try:
            signature = base64.b64decode(signature_text.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            return LicenseValidationResult(
                status="invalid_signature_encoding",
                message="授权签名编码无效。",
            )
        try:
            public_key.verify(signature, _canonical_json_bytes(claims))
        except InvalidSignature:
            return LicenseValidationResult(
                status="invalid_signature",
                message="授权签名校验失败。",
            )

        product = str(claims.get("product", "")).strip()
        if product != self.config.product_id:
            return LicenseValidationResult(
                status="product_mismatch",
                message="该授权不属于当前产品。",
            )
        expected_fingerprint = self.machine_identity.fingerprint.lower()
        bound_fingerprint = str(claims.get("machine_fingerprint", "")).strip().lower()
        if bound_fingerprint != expected_fingerprint:
            return LicenseValidationResult(
                status="machine_mismatch",
                message="当前授权未绑定到这台电脑，请重新申请机器码对应的激活文件。",
                claims=dict(claims),
            )

        expires_at = _parse_timestamp(claims.get("expires_at"))
        now = self.now_provider().astimezone(timezone.utc)
        if expires_at is not None and expires_at < now:
            return LicenseValidationResult(
                status="expired",
                message="当前授权已过期。",
                claims=dict(claims),
            )

        return LicenseValidationResult(
            status="valid",
            message="授权有效。",
            claims=dict(claims),
        )

    def install_license(self, source_path: Path) -> LicenseValidationResult:
        result = self.validate_license_file(source_path)
        if not result.valid:
            return result
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        document = self._load_license_document_text(Path(source_path).read_text(encoding="utf-8"))
        self.storage_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        installed = self.current_status()
        installed.source_path = self.storage_path
        return installed

    def install_activation_key(self, activation_key: str) -> LicenseValidationResult:
        try:
            document = decode_activation_key(activation_key, self.config)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return LicenseValidationResult(
                status="invalid_activation_key",
                message="激活密钥格式无效，请检查是否完整复制。",
            )
        result = self.validate_license_document(document)
        if not result.valid:
            return result
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        installed = self.current_status()
        installed.source_path = self.storage_path
        return installed
