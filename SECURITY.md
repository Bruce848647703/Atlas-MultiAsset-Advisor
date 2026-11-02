# Security

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Use GitHub's
[private vulnerability reporting](https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/security/advisories/new)
or contact the maintainer directly. We aim to acknowledge reports within a few
days.

## Deployment notes

Atlas is read-only research software: it does not place orders and should never
hold brokerage or exchange credentials.

- **Access gate.** Streamlit ships without authentication. `ATLAS_ACCESS_TOKEN`
  enables a single shared password; for anything beyond a trusted LAN, put
  nginx/Caddy in front with HTTPS and real user auth. Never deploy with the
  default placeholder token.
- **Public exposure.** Bind to `127.0.0.1` unless you have a proxy with TLS,
  rate limiting, and auth. Keep XSRF protection enabled.
- **Containers.** The image runs as non-root and refuses to start without
  `ATLAS_ACCESS_TOKEN`; compose binds to localhost by default. Do not set
  `ATLAS_ALLOW_INSECURE=1` on a reachable host.
- **Secrets.** `DEEPSEEK_API_KEY` and `ATLAS_ACCESS_TOKEN` are read from the
  environment only. Do not commit them, and rotate any key that has been
  pasted into a repo, log, or screenshot.
- **Untrusted input.** LLM tool arguments are schema-validated and budgeted;
  external news/PDF text is sanitised and marked untrusted before it reaches the
  model. Treat any new tool that writes files or makes network requests as an
  attack surface, and keep the "data, not instructions" rule in the system prompt.

## Supported versions

The `main` branch is the supported line. Pin a commit SHA if you need
reproducible deployments.