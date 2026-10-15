# Security

## Reporting

Report a vulnerability privately to the maintainer through GitHub's
"Report a vulnerability" on this repository, or by e-mail to the address
in the maintainer's GitHub profile. Do not open a public issue for it.
You get an answer within a few days.

## Scope

Everything in this repository: the services, the frontend, the Helm
chart and the workflows. Out of scope: the cloud platform itself and
the model provider.

## What the system does about it

- Secrets come from the environment only; nothing in the repository
  holds a credential, and `.gitignore` keeps local env files out.
- Every request carries a bearer token; services verify it themselves.
  Login is a single-use magic link; no passwords are stored.
- Rate limiting at the ingress and a per-IP block and ban layer in the
  services; every request is logged with its address for 30 days for
  this purpose only. The visitor log keeps hashes, never addresses.
- Containers run as non-root; uploads are size- and type-checked and
  stored outside the containers.
- Model output is treated as untrusted content: sanitized before
  rendering, never executed.

## Known limitations

- The mail configuration, including the SMTP password, comes only from
  a Kubernetes Secret in the environment; it is never stored in the
  database and the admin panel shows it read-only, without the password.
- The OpenTofu state holds the cluster's admin kubeconfig (issue #288);
  the state is kept out of the repository.
- There is no audit log of admin actions yet.
