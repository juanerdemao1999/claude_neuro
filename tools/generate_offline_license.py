from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from nex5_analyzer.licensing import build_license_claims, encode_activation_key, sign_license_claims


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a signed offline activation key for one machine.")
    parser.add_argument("--private-key", required=True, type=Path, help="Path to license_private_key.pem")
    parser.add_argument("--customer", required=True, help="Customer or lab name")
    parser.add_argument("--fingerprint", required=True, help="Machine fingerprint from the app request dialog")
    parser.add_argument("--license-id", required=True, help="Unique license identifier")
    parser.add_argument(
        "--expires-at",
        help="Optional ISO-8601 UTC timestamp, for example 2027-04-12T00:00:00+00:00",
    )
    parser.add_argument(
        "--feature",
        action="append",
        default=[],
        help="Optional feature flag to embed in the license. Repeat for multiple features.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Where to write the activation key file")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write the legacy JSON license document instead of a pasteable activation key.",
    )
    return parser.parse_args()


def _parse_optional_expiry(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def main() -> int:
    args = parse_args()
    private_key_pem = args.private_key.read_bytes()
    claims = build_license_claims(
        customer_name=args.customer,
        machine_fingerprint=args.fingerprint,
        license_id=args.license_id,
        expires_at=_parse_optional_expiry(args.expires_at),
        features=args.feature,
    )
    signed_license = sign_license_claims(claims, private_key_pem)

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.json:
        output_path.write_text(json.dumps(signed_license, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        output_path.write_text(encode_activation_key(signed_license), encoding="utf-8")
    print(f"Activation key written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
