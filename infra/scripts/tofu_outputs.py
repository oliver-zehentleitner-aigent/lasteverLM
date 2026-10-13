#!/usr/bin/env python3
"""Turns `tofu output -json` (stdin) into the cluster.env assignments.

`tofu output -raw <name>` exits 0 and prints a warning to stdout when the
state is missing or has no outputs, so a shell loop over it writes the
warning into cluster.env as a value. This reads every output at once and
fails, printing only the names, when one is missing or empty.
"""

import json
import shlex
import sys

# cluster.env name <- tofu output name
OUTPUTS = {
    "VKE_ID": "vke_id",
    "S3_ENDPOINT": "s3_endpoint",
    "S3_BUCKET": "s3_bucket",
    "S3_REGION": "s3_region",
    "S3_ACCESS_KEY": "s3_access_key",
    "S3_SECRET_KEY": "s3_secret_key",
}


def assignments(outputs: dict) -> list[str]:
    missing = [
        name
        for name in OUTPUTS.values()
        if not isinstance(outputs.get(name), dict) or not outputs[name].get("value")
    ]
    if missing:
        raise ValueError(f"tofu outputs missing or empty: {', '.join(missing)} (run make up first)")
    return [f"{env}={shlex.quote(str(outputs[name]['value']))}" for env, name in OUTPUTS.items()]


def main() -> int:
    try:
        lines = assignments(json.load(sys.stdin))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"tofu_outputs: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
