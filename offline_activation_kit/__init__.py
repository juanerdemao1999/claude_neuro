from .activation import (
    ActivationConfig,
    LicenseManager,
    LicenseValidationResult,
    MachineIdentity,
    build_license_claims,
    decode_activation_key,
    encode_activation_key,
    resolve_runtime_root,
    sign_license_claims,
)

__all__ = [
    "ActivationConfig",
    "LicenseManager",
    "LicenseValidationResult",
    "MachineIdentity",
    "build_license_claims",
    "decode_activation_key",
    "encode_activation_key",
    "resolve_runtime_root",
    "sign_license_claims",
]
