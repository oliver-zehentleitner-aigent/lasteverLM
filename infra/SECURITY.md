# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it
through GitHub's private vulnerability reporting on the lasteverLM
repository ("Security" tab, "Report a vulnerability"). You will get an
answer within a few days.

## What this directory handles

- Vultr API keys, database credentials, object storage keys and
  inference API keys are read from the environment by the `Makefile` and
  written to Kubernetes Secrets. None of them are stored in this
  repository, and `build/` and every `*.env` file are ignored by Git.
- OpenTofu state contains the object storage keys and the cluster's
  admin credentials (the `vultr_kubernetes` resource stores the
  kubeconfig and its client key). It is kept local and ignored by Git,
  and `make up` sets it to mode 600; treat `tofu/*.tfstate` like a
  secret. The managed database is not in the state: it is created by
  hand and taken as an input.
- The managed database requires TLS for every connection; every
  connection string uses `sslmode=verify-full` against the project CA.
