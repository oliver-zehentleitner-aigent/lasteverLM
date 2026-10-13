#!/usr/bin/env python3
"""Writes the chart values that differ per deployment, as YAML on stdout.

Reads the environment (see docs/operations.md, "Inputs") and prints a
values file for `helm upgrade`. JSON strings such as MODEL_PRICES are
passed through untouched, which `--set` cannot do because it parses
commas and braces itself. Fails loud on a missing required variable.
"""

import json
import os
import sys

REQUIRED = ["DOMAIN", "ACME_EMAIL", "LLM_MODEL", "EMBEDDING_MODEL", "MODEL_PRICES", "S3_ENDPOINT"]


def main() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f"missing: {', '.join(missing)}", file=sys.stderr)
        return 1
    try:
        json.loads(os.environ["MODEL_PRICES"])
    except json.JSONDecodeError as exc:
        print(f"MODEL_PRICES is not valid JSON: {exc}", file=sys.stderr)
        return 1
    env = os.environ
    values = {
        "domain": env["DOMAIN"],
        "acmeEmail": env["ACME_EMAIL"],
        "registry": env.get("REGISTRY", "ghcr.io/oliver-zehentleitner"),
        "imageTag": env.get("TAG", "latest"),
        "config": {
            "inferenceBaseUrl": env.get("INFERENCE_BASE_URL", "https://api.vultrinference.com/v1"),
            "llmModel": env["LLM_MODEL"],
            "embeddingModel": env["EMBEDDING_MODEL"],
            "embeddingDimension": int(env.get("EMBEDDING_DIMENSION", "1536")),
            "modelPrices": env["MODEL_PRICES"],
            "similarityFloor": env.get("SIMILARITY_FLOOR", ""),
            "ttsModel": env.get("TTS_MODEL", ""),
            "ttsVoice": env.get("TTS_VOICE") or "ryan",
            "s3Endpoint": env["S3_ENDPOINT"],
            "s3Bucket": env.get("S3_BUCKET", "lasteverlm-sources"),
        },
    }
    # JSON is valid YAML, and json.dumps quotes every string safely.
    print(json.dumps(values, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
