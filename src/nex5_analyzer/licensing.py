from __future__ import annotations

import base64
import binascii
import hashlib
import json
import platform
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization


PRODUCT_ID = "nex5-spike-lfp"
LICENSE_SCHEMA_VERSION = 1
PUBLIC_KEY_FILE_NAME = "license_public_key.pem"
LICENSE_FILE_NAME = "license.json"
ACTIVATION_KEY_FILE_NAME = "activation.key"
ACTIVATION_KEY_PREFIX = "NEX5-LIC-1."
SIGNATURE_ALGORITHM = "ed25519"
LICENSE_DOCUMENT_KIND = "signed-license"
LICENSE_TRANSPORT_ENCODING = "base64url-json"
LICENSE_PROTOCOL_PROFILE_ID = "nex5-offline-license-ed25519-v1"


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
class LicenseProtocolProfile:
    profile_id: str
    product: str
    schema_version: int = LICENSE_SCHEMA_VERSION
    document_kind: str = LICENSE_DOCUMENT_KIND
    transport_encoding: str = LICENSE_TRANSPORT_ENCODING
    activation_key_prefix: str = ACTIVATION_KEY_PREFIX
    signature_algorithm: str = SIGNATURE_ALGORITHM

    def metadata(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "product": self.product,
            "schema_version": self.schema_version,
            "document_kind": self.document_kind,
            "transport_encoding": self.transport_encoding,
            "activation_key_prefix": self.activation_key_prefix,
            "signature_algorithm": self.signature_algorithm,
        }


DEFAULT_LICENSE_PROFILE = LicenseProtocolProfile(
    profile_id=LICENSE_PROTOCOL_PROFILE_ID,
    product=PRODUCT_ID,
)


@dataclass(frozen=True, slots=True)
class LicenseArtifactInspection:
    source_format: str
    schema_version: int | None
    profile_id: str | None
    document_kind: str | None
    transport_encoding: str | None
    signature_algorithm: str | None
    activation_key_prefix: str | None
    product: str | None
    license_id: str | None
    customer_name: str | None
    machine_fingerprint: str | None
    issued_at: str | None
    expires_at: str | None
    features: tuple[str, ...]
    decode_steps: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_format": self.source_format,
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "document_kind": self.document_kind,
            "transport_encoding": self.transport_encoding,
            "signature_algorithm": self.signature_algorithm,
            "activation_key_prefix": self.activation_key_prefix,
            "product": self.product,
            "license_id": self.license_id,
            "customer_name": self.customer_name,
            "machine_fingerprint": self.machine_fingerprint,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "features": list(self.features),
            "decode_steps": list(self.decode_steps),
        }


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def build_protocol_metadata(profile: LicenseProtocolProfile = DEFAULT_LICENSE_PROFILE) -> dict[str, Any]:
    return profile.metadata()


def load_license_document_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith(ACTIVATION_KEY_PREFIX):
        return decode_activation_key(cleaned)
    document = json.loads(cleaned)
    if not isinstance(document, dict):
        raise ValueError("License payload is not a JSON object.")
    return document


def inspect_license_document(
    document: Mapping[str, Any],
    *,
    source_format: str = "json_document",
) -> LicenseArtifactInspection:
    protocol: Mapping[str, Any] = {}
    raw_protocol = document.get("protocol")
    if isinstance(raw_protocol, Mapping):
        protocol = raw_protocol

    claims: Mapping[str, Any] = {}
    raw_claims = document.get("claims")
    if isinstance(raw_claims, Mapping):
        claims = raw_claims

    raw_features = claims.get("features")
    features: tuple[str, ...] = ()
    if isinstance(raw_features, (list, tuple)):
        features = tuple(
            cleaned
            for item in raw_features
            if (cleaned := str(item).strip())
        )

    decode_steps: list[str]
    if source_format == "activation_key":
        decode_steps = [
            f"Strip the fixed prefix `{ACTIVATION_KEY_PREFIX}` from the activation key.",
            "Base64url-decode the remaining payload into a UTF-8 JSON document.",
        ]
    else:
        decode_steps = ["Parse the UTF-8 JSON document directly."]
    decode_steps.extend(
        [
            "Read the embedded protocol metadata to identify the profile and transport rules.",
            "Verify the `signature` against canonical JSON bytes of `claims` using the Ed25519 public key.",
            "Check `claims.product`, `claims.machine_fingerprint`, and `claims.expires_at` before accepting it.",
        ]
    )

    return LicenseArtifactInspection(
        source_format=source_format,
        schema_version=document.get("schema_version"),
        profile_id=_clean_optional_text(protocol.get("profile_id")),
        document_kind=_clean_optional_text(protocol.get("document_kind")) or LICENSE_DOCUMENT_KIND,
        transport_encoding=_clean_optional_text(protocol.get("transport_encoding")),
        signature_algorithm=_clean_optional_text(document.get("signature_algorithm"))
        or _clean_optional_text(protocol.get("signature_algorithm")),
        activation_key_prefix=_clean_optional_text(protocol.get("activation_key_prefix"))
        or (ACTIVATION_KEY_PREFIX if source_format == "activation_key" else None),
        product=_clean_optional_text(claims.get("product")) or _clean_optional_text(protocol.get("product")),
        license_id=_clean_optional_text(claims.get("license_id")),
        customer_name=_clean_optional_text(claims.get("customer_name")),
        machine_fingerprint=_clean_optional_text(claims.get("machine_fingerprint")),
        issued_at=_clean_optional_text(claims.get("issued_at")),
        expires_at=_clean_optional_text(claims.get("expires_at")),
        features=features,
        decode_steps=tuple(decode_steps),
    )


def inspect_license_artifact_text(text: str) -> LicenseArtifactInspection:
    cleaned = text.strip()
    source_format = "activation_key" if cleaned.startswith(ACTIVATION_KEY_PREFIX) else "json_document"
    return inspect_license_document(load_license_document_text(cleaned), source_format=source_format)


def format_license_artifact_inspection(inspection: LicenseArtifactInspection) -> str:
    features = ", ".join(inspection.features) if inspection.features else "(none)"
    lines = [
        f"Source format:         {inspection.source_format}",
        f"Profile id:            {inspection.profile_id or '(missing)'}",
        f"Document kind:         {inspection.document_kind or '(missing)'}",
        f"Transport encoding:    {inspection.transport_encoding or '(missing)'}",
        f"Signature algorithm:   {inspection.signature_algorithm or '(missing)'}",
        f"Activation key prefix: {inspection.activation_key_prefix or '(n/a)'}",
        f"Product:               {inspection.product or '(missing)'}",
        f"License id:            {inspection.license_id or '(missing)'}",
        f"Customer:              {inspection.customer_name or '(missing)'}",
        f"Machine fingerprint:   {inspection.machine_fingerprint or '(missing)'}",
        f"Issued at:             {inspection.issued_at or '(missing)'}",
        f"Expires at:            {inspection.expires_at or '(none)'}",
        f"Features:              {features}",
        "",
        "Decode / verify steps:",
    ]
    for index, step in enumerate(inspection.decode_steps, start=1):
        lines.append(f"{index}. {step}")
    return "\n".join(lines)


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

    def request_payload(self) -> dict[str, Any]:
        return {
            "schema_version": LICENSE_SCHEMA_VERSION,
            "product": PRODUCT_ID,
            "fingerprint": self.fingerprint,
            "machine": dict(self.fields),
            "license_protocol": build_protocol_metadata(),
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


def default_license_storage_path() -> Path:
    return Path.home() / ".nex5_analyzer" / LICENSE_FILE_NAME


def build_license_claims(
    *,
    customer_name: str,
    machine_fingerprint: str,
    license_id: str,
    expires_at: datetime | str | None = None,
    issued_at: datetime | str | None = None,
    features: list[str] | tuple[str, ...] | None = None,
    product: str = PRODUCT_ID,
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
        "schema_version": LICENSE_SCHEMA_VERSION,
        "product": product,
        "license_id": str(license_id).strip(),
        "customer_name": str(customer_name).strip(),
        "machine_fingerprint": str(machine_fingerprint).strip().lower(),
        "issued_at": issued_timestamp,
        "expires_at": _normalize_timestamp(expires_at),
        "features": normalized_features,
    }


def sign_license_claims(
    claims: Mapping[str, Any],
    private_key_pem: bytes,
    *,
    profile: LicenseProtocolProfile = DEFAULT_LICENSE_PROFILE,
) -> dict[str, Any]:
    claims_product = str(claims.get("product", "")).strip()
    if claims_product != profile.product:
        raise ValueError(
            f"Claims product `{claims_product}` does not match profile product `{profile.product}`."
        )
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(_canonical_json_bytes(dict(claims)))
    return {
        "schema_version": LICENSE_SCHEMA_VERSION,
        "protocol": build_protocol_metadata(profile),
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "claims": dict(claims),
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def encode_activation_key(document: Mapping[str, Any]) -> str:
    encoded = base64.urlsafe_b64encode(_canonical_json_bytes(document)).decode("ascii")
    return ACTIVATION_KEY_PREFIX + encoded.rstrip("=")


def decode_activation_key(activation_key: str) -> dict[str, Any]:
    cleaned = "".join(str(activation_key).split())
    if not cleaned.startswith(ACTIVATION_KEY_PREFIX):
        raise ValueError("Activation key has an unsupported prefix.")
    payload = cleaned[len(ACTIVATION_KEY_PREFIX) :]
    payload += "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
    document = json.loads(decoded.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Activation key payload is not a license document.")
    return document


class LicenseManager:
    def __init__(
        self,
        runtime_root: Path,
        *,
        machine_identity: MachineIdentity | None = None,
        storage_path: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.machine_identity = machine_identity or MachineIdentity.collect()
        self.storage_path = storage_path or default_license_storage_path()
        self.now_provider = now_provider or _utc_now

    def public_key_search_paths(self) -> tuple[Path, ...]:
        return (
            self.runtime_root / PUBLIC_KEY_FILE_NAME,
            self.runtime_root / "_internal" / PUBLIC_KEY_FILE_NAME,
        )

    def public_key_path(self) -> Path:
        for path in self.public_key_search_paths():
            if path.exists():
                return path
        return self.public_key_search_paths()[0]

    def candidate_license_paths(self) -> tuple[Path, ...]:
        paths = [
            self.storage_path,
            self.runtime_root / LICENSE_FILE_NAME,
            self.runtime_root / ACTIVATION_KEY_FILE_NAME,
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
        return self.machine_identity.request_payload()

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
            message="未找到许可证文件，请导入客户许可证。",
        )

    def validate_license_file(self, path: Path) -> LicenseValidationResult:
        try:
            document = self._load_license_document_text(Path(path).read_text(encoding="utf-8"))
        except OSError:
            return LicenseValidationResult(
                status="license_read_error",
                message="许可证文件无法读取。",
                source_path=Path(path),
            )
        except ValueError as exc:
            return LicenseValidationResult(
                status="invalid_license_file",
                message=f"许可证文件格式无效：{exc}",
                source_path=Path(path),
            )
        result = self.validate_license_document(document)
        result.source_path = Path(path)
        return result

    def _load_license_document_text(self, text: str) -> dict[str, Any]:
        return load_license_document_text(text)
        if not isinstance(document, dict):
            raise ValueError("许可证内容不是有效对象。")
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

        protocol = document.get("protocol")
        if protocol is not None and not isinstance(protocol, dict):
            return LicenseValidationResult(
                status="invalid_document",
                message="License protocol metadata is malformed.",
            )

        claims = document.get("claims")
        signature_text = document.get("signature")
        if not isinstance(claims, dict) or not isinstance(signature_text, str):
            return LicenseValidationResult(
                status="invalid_document",
                message="许可证缺少 claims 或 signature 字段。",
            )
        if isinstance(protocol, dict):
            declared_protocol_algorithm = str(protocol.get("signature_algorithm", "")).strip()
            if declared_protocol_algorithm and declared_protocol_algorithm != SIGNATURE_ALGORITHM:
                return LicenseValidationResult(
                    status="unsupported_algorithm",
                    message="License protocol declares an unsupported signature algorithm.",
                )
            declared_protocol_schema = protocol.get("schema_version")
            if declared_protocol_schema is not None and declared_protocol_schema != LICENSE_SCHEMA_VERSION:
                return LicenseValidationResult(
                    status="schema_mismatch",
                    message="License protocol schema version does not match this application.",
                )
        if document.get("signature_algorithm") != SIGNATURE_ALGORITHM:
            return LicenseValidationResult(
                status="unsupported_algorithm",
                message="许可证签名算法不受支持。",
            )
        if claims.get("schema_version") != LICENSE_SCHEMA_VERSION or document.get("schema_version") != LICENSE_SCHEMA_VERSION:
            return LicenseValidationResult(
                status="schema_mismatch",
                message="许可证版本与当前程序不兼容。",
            )
        try:
            signature = base64.b64decode(signature_text.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            return LicenseValidationResult(
                status="invalid_signature_encoding",
                message="许可证签名编码无效。",
            )
        try:
            public_key.verify(signature, _canonical_json_bytes(claims))
        except InvalidSignature:
            return LicenseValidationResult(
                status="invalid_signature",
                message="许可证签名校验失败。",
            )

        product = str(claims.get("product", "")).strip()
        if product != PRODUCT_ID:
            return LicenseValidationResult(
                status="product_mismatch",
                message="许可证并非当前产品使用。",
            )
        expected_fingerprint = self.machine_identity.fingerprint.lower()
        bound_fingerprint = str(claims.get("machine_fingerprint", "")).strip().lower()
        if bound_fingerprint != expected_fingerprint:
            return LicenseValidationResult(
                status="machine_mismatch",
                message="当前许可证未绑定到这台机器。",
                claims=dict(claims),
            )

        expires_at = _parse_timestamp(claims.get("expires_at"))
        now = self.now_provider().astimezone(timezone.utc)
        if expires_at is not None and expires_at < now:
            return LicenseValidationResult(
                status="expired",
                message="当前许可证已过期。",
                claims=dict(claims),
            )

        return LicenseValidationResult(
            status="valid",
            message="许可证有效。",
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
            document = decode_activation_key(activation_key)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return LicenseValidationResult(
                status="invalid_activation_key",
                message="激活密钥格式无效，请检查是否复制完整。",
            )
        result = self.validate_license_document(document)
        if not result.valid:
            return result
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        installed = self.current_status()
        installed.source_path = self.storage_path
        return installed
