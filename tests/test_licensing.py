import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nex5_analyzer.gui.license_dialog import LicenseActivationDialog
from nex5_analyzer.licensing import (
    ACTIVATION_KEY_FILE_NAME,
    DEFAULT_LICENSE_PROFILE,
    format_license_artifact_inspection,
    LICENSE_FILE_NAME,
    PUBLIC_KEY_FILE_NAME,
    decode_activation_key,
    encode_activation_key,
    inspect_license_artifact_text,
    LicenseManager,
    MachineIdentity,
    build_license_claims,
    sign_license_claims,
)
from tools.license_generator_app import default_signing_root, ensure_signing_keypair, make_activation_key


def _make_private_key_pem() -> bytes:
    private_key = Ed25519PrivateKey.generate()
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _write_public_key(runtime_root: Path, private_key_pem: bytes) -> None:
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / PUBLIC_KEY_FILE_NAME).write_bytes(public_key_pem)


def test_machine_identity_fingerprint_is_order_independent() -> None:
    fields_a = {
        "platform": "Windows",
        "machine_guid": "ABC-123",
        "mac_address": "001122334455",
    }
    fields_b = {
        "mac_address": "001122334455",
        "platform": "Windows",
        "machine_guid": "ABC-123",
    }

    identity_a = MachineIdentity.from_fields(fields_a)
    identity_b = MachineIdentity.from_fields(fields_b)

    assert identity_a.fingerprint == identity_b.fingerprint


def test_license_manager_installs_and_validates_signed_license(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    storage_path = tmp_path / "licenses" / LICENSE_FILE_NAME
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields(
        {
            "platform": "Windows",
            "machine_guid": "machine-guid-001",
            "mac_address": "001122334455",
        }
    )

    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-ACME-001",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        features=["desktop", "batch"],
    )
    signed_license = sign_license_claims(claims, private_key_pem)
    incoming_path = tmp_path / "incoming-license.json"
    incoming_path.write_text(json.dumps(signed_license, indent=2), encoding="utf-8")

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=storage_path)

    installed = manager.install_license(incoming_path)
    current = manager.current_status()

    assert installed.valid is True
    assert storage_path.exists() is True
    assert current.valid is True
    assert current.claims is not None
    assert current.claims["customer_name"] == "Acme Lab"
    assert current.claims["features"] == ["desktop", "batch"]


def test_license_manager_rejects_license_for_other_machine(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})

    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint="not-the-current-machine",
        license_id="LIC-ACME-002",
    )
    signed_license = sign_license_claims(claims, private_key_pem)

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=tmp_path / LICENSE_FILE_NAME)
    result = manager.validate_license_document(signed_license)

    assert result.valid is False
    assert result.status == "machine_mismatch"


def test_license_manager_installs_pasted_activation_key(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    storage_path = tmp_path / "licenses" / LICENSE_FILE_NAME
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-ACME-KEY-001",
    )
    activation_key = encode_activation_key(sign_license_claims(claims, private_key_pem))

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=storage_path)
    result = manager.install_activation_key(activation_key)

    assert result.valid is True
    assert storage_path.exists() is True
    assert json.loads(storage_path.read_text(encoding="utf-8"))["claims"]["license_id"] == "LIC-ACME-KEY-001"


def test_license_manager_rejects_activation_key_copied_to_new_machine(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    original_identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    new_identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-002"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=original_identity.fingerprint,
        license_id="LIC-ACME-KEY-002",
    )
    activation_key = encode_activation_key(sign_license_claims(claims, private_key_pem))

    manager = LicenseManager(runtime_root, machine_identity=new_identity, storage_path=tmp_path / LICENSE_FILE_NAME)
    result = manager.install_activation_key(activation_key)

    assert result.valid is False
    assert result.status == "machine_mismatch"


def test_license_manager_installs_activation_key_file(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    storage_path = tmp_path / "licenses" / LICENSE_FILE_NAME
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-ACME-KEY-003",
    )
    activation_key = encode_activation_key(sign_license_claims(claims, private_key_pem))
    key_path = tmp_path / ACTIVATION_KEY_FILE_NAME
    key_path.write_text(activation_key, encoding="utf-8")

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=storage_path)
    result = manager.install_license(key_path)

    assert result.valid is True
    assert storage_path.exists() is True


def test_license_manager_finds_public_key_in_pyinstaller_internal_dir(tmp_path: Path) -> None:
    runtime_root = tmp_path / "dist"
    internal_root = runtime_root / "_internal"
    storage_path = tmp_path / "licenses" / LICENSE_FILE_NAME
    private_key_pem = _make_private_key_pem()
    _write_public_key(internal_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-INTERNAL-KEY-001",
    )
    activation_key = encode_activation_key(sign_license_claims(claims, private_key_pem))

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=storage_path)
    result = manager.install_activation_key(activation_key)

    assert manager.public_key_path() == internal_root / PUBLIC_KEY_FILE_NAME
    assert result.valid is True


def test_activation_key_round_trip_preserves_signed_document(tmp_path: Path) -> None:
    private_key_pem = _make_private_key_pem()
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-ACME-KEY-004",
    )
    document = sign_license_claims(claims, private_key_pem)

    restored = decode_activation_key(encode_activation_key(document))

    assert restored == document


def test_signed_license_contains_protocol_metadata() -> None:
    private_key_pem = _make_private_key_pem()
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-META-001",
    )

    document = sign_license_claims(claims, private_key_pem)

    assert document["protocol"]["profile_id"] == DEFAULT_LICENSE_PROFILE.profile_id
    assert document["protocol"]["product"] == DEFAULT_LICENSE_PROFILE.product
    assert document["protocol"]["activation_key_prefix"]


def test_license_artifact_inspection_describes_activation_key_recipe() -> None:
    private_key_pem = _make_private_key_pem()
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-INSPECT-001",
        features=["desktop", "batch"],
    )
    activation_key = encode_activation_key(sign_license_claims(claims, private_key_pem))

    inspection = inspect_license_artifact_text(activation_key)

    assert inspection.source_format == "activation_key"
    assert inspection.profile_id == DEFAULT_LICENSE_PROFILE.profile_id
    assert inspection.product == "nex5-spike-lfp"
    assert inspection.features == ("desktop", "batch")
    assert inspection.decode_steps[0].startswith("Strip the fixed prefix")


def test_license_artifact_inspection_format_includes_profile_and_steps() -> None:
    private_key_pem = _make_private_key_pem()
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-FORMAT-001",
    )
    inspection = inspect_license_artifact_text(encode_activation_key(sign_license_claims(claims, private_key_pem)))

    report = format_license_artifact_inspection(inspection)

    assert DEFAULT_LICENSE_PROFILE.profile_id in report
    assert "Decode / verify steps:" in report
    assert "1. Strip the fixed prefix" in report


def test_license_manager_accepts_legacy_document_without_protocol_metadata(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-LEGACY-001",
    )
    legacy_document = sign_license_claims(claims, private_key_pem)
    legacy_document.pop("protocol")

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=tmp_path / LICENSE_FILE_NAME)
    result = manager.validate_license_document(legacy_document)

    assert result.valid is True


def test_license_generator_app_creates_keypair_and_matching_activation_key(tmp_path: Path) -> None:
    key_paths = ensure_signing_keypair(tmp_path)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})

    activation_key = make_activation_key(
        private_key_path=key_paths.private_key_path,
        machine_code=identity.fingerprint,
        customer_name="Acme Lab",
        license_id="LIC-GUI-001",
    )
    manager = LicenseManager(tmp_path, machine_identity=identity, storage_path=tmp_path / LICENSE_FILE_NAME)
    result = manager.install_activation_key(activation_key)

    assert key_paths.private_key_path.exists() is True
    assert key_paths.bundled_public_key_path.exists() is True
    assert key_paths.bundled_public_key_matches is True
    assert result.valid is True
    assert result.claims["license_id"] == "LIC-GUI-001"


def test_license_generator_frozen_root_prefers_parent_private_key(tmp_path: Path, monkeypatch) -> None:
    exe_dir = tmp_path / "dist_license_generator"
    secrets_dir = tmp_path / ".secrets"
    exe_dir.mkdir()
    secrets_dir.mkdir()
    (secrets_dir / "license_private_key.pem").write_text("private-key", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "NEX5LicenseGenerator.exe"))

    # default_signing_root() resolves the executable path (which may normalize to
    # an 8.3 short path on Windows), so compare against the resolved tmp_path.
    assert default_signing_root() == tmp_path.resolve()


def test_license_manager_rejects_expired_license(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})

    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-ACME-003",
        expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    signed_license = sign_license_claims(claims, private_key_pem)

    manager = LicenseManager(
        runtime_root,
        machine_identity=identity,
        storage_path=tmp_path / LICENSE_FILE_NAME,
        now_provider=lambda: datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    result = manager.validate_license_document(signed_license)

    assert result.valid is False
    assert result.status == "expired"


def test_machine_request_payload_contains_current_fingerprint() -> None:
    identity = MachineIdentity.from_fields(
        {
            "platform": "Windows",
            "machine_guid": "machine-guid-001",
            "mac_address": "001122334455",
        }
    )

    payload = identity.request_payload()

    assert payload["fingerprint"] == identity.fingerprint
    assert payload["product"] == "nex5-spike-lfp"
    assert payload["machine"]["machine_guid"] == "machine-guid-001"


def test_license_activation_dialog_imports_valid_license(monkeypatch, tmp_path: Path, qapp) -> None:
    runtime_root = tmp_path / "runtime"
    storage_path = tmp_path / "licenses" / LICENSE_FILE_NAME
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})

    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-ACME-004",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    signed_license = sign_license_claims(claims, private_key_pem)
    incoming_path = tmp_path / "incoming-license.json"
    incoming_path.write_text(json.dumps(signed_license, indent=2), encoding="utf-8")

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=storage_path)
    dialog = LicenseActivationDialog(manager)

    monkeypatch.setattr(
        "nex5_analyzer.gui.license_dialog.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(incoming_path), "JSON Files (*.json)"),
    )
    monkeypatch.setattr("nex5_analyzer.gui.license_dialog.QMessageBox.information", lambda *args, **kwargs: None)
    monkeypatch.setattr("nex5_analyzer.gui.license_dialog.QMessageBox.warning", lambda *args, **kwargs: None)

    dialog._import_license()

    assert dialog.validation_result is not None
    assert dialog.validation_result.valid is True
    assert storage_path.exists() is True
    dialog.close()


def test_license_activation_dialog_accepts_pasted_activation_key(monkeypatch, tmp_path: Path, qapp) -> None:
    runtime_root = tmp_path / "runtime"
    storage_path = tmp_path / "licenses" / LICENSE_FILE_NAME
    private_key_pem = _make_private_key_pem()
    _write_public_key(runtime_root, private_key_pem)
    identity = MachineIdentity.from_fields({"machine_guid": "machine-guid-001"})
    claims = build_license_claims(
        customer_name="Acme Lab",
        machine_fingerprint=identity.fingerprint,
        license_id="LIC-ACME-KEY-005",
    )
    activation_key = encode_activation_key(sign_license_claims(claims, private_key_pem))

    manager = LicenseManager(runtime_root, machine_identity=identity, storage_path=storage_path)
    dialog = LicenseActivationDialog(manager)
    monkeypatch.setattr("nex5_analyzer.gui.license_dialog.QMessageBox.information", lambda *args, **kwargs: None)
    monkeypatch.setattr("nex5_analyzer.gui.license_dialog.QMessageBox.warning", lambda *args, **kwargs: None)

    dialog.key_edit.setPlainText(activation_key)
    dialog._activate_from_key_text()

    assert dialog.validation_result is not None
    assert dialog.validation_result.valid is True
    assert storage_path.exists() is True
    dialog.close()
