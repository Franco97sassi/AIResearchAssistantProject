# Security policy

## Supported versions

Security fixes are applied to the latest release on `main`.

| Version | Supported |
| --- | --- |
| 1.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private PDFs, or personal
data. Use GitHub's **Report a vulnerability** private advisory for this repository. If private
reporting is unavailable, contact the repository owner through the private contact method shown
on their GitHub profile and include only the minimum information needed to reproduce the issue.

You should receive acknowledgement within 72 hours and an initial assessment within seven days.
Coordinated disclosure is requested until a fix is available. Good-faith research that avoids
privacy violations, service disruption, and data destruction is welcome.

## Deployment responsibilities

- Replace example credentials and enable `AUTH_REQUIRED` outside local development.
- Keep model keys in a secrets manager; never expose them through `VITE_*` variables.
- Restrict `/metrics`, `/traces`, OTLP ports, Redis, and ChromaDB to trusted networks.
- Treat uploaded documents, vector embeddings, chat history, traces, and backups as sensitive.
- Exercise `DELETE /tenants/me/data` and backup restoration in staging before production use.
- Apply dependency and base-image security updates regularly.

Pattern-based prompt-injection and PII checks are defense-in-depth controls, not a security
boundary. See the limitations and production trade-offs in the main README.
