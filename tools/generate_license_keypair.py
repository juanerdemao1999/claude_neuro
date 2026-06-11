from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nex5_analyzer.licensing import PUBLIC_KEY_FILE_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an Ed25519 keypair for offline license signing.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".secrets"),
        help="Directory where the private/public keypair will be written.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing key files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = output_dir / "license_private_key.pem"
    public_key_path = output_dir / PUBLIC_KEY_FILE_NAME
    if not args.force and (private_key_path.exists() or public_key_path.exists()):
        raise SystemExit(f"Refusing to overwrite existing files in {output_dir}. Use --force to continue.")

    private_key = Ed25519PrivateKey.generate()
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_key_path.write_bytes(private_key_pem)
    public_key_path.write_bytes(public_key_pem)
    print(f"Private key: {private_key_path}")
    print(f"Public key:  {public_key_path}")
    print("Keep the private key offline. Copy the public key next to the EXE before packaging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
