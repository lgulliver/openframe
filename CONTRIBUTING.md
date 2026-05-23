# Contributing

## Scope

OpenFrame is a public open source project for running multi-repo OpenCode workspaces in Docker. Contributions should keep the project simple to operate, explicit about trust boundaries, and safe by default.

## Before you start

- Open an issue or discussion for substantial changes before writing a large patch.
- Keep changes focused. Avoid bundling unrelated fixes into one pull request.
- Do not commit secrets, tokens, or local machine state.

## Development

1. Copy `.env.example` to `.env` for local development.
2. Build the image with `docker compose build`.
3. Start the stack with `docker compose up`.
4. Make your change and verify the affected path manually.

Useful local checks:

- `python3 -m py_compile manager.py`
- `docker compose config`
- `sh -n docker/bootstrap.sh`
- `sh -n docker/entrypoint.sh`
- `sh -n docker/install-tools.sh`
- `for f in docker/install.d/*.sh; do sh -n "$f"; done`

## Pull requests

- Describe the problem being solved and the chosen approach.
- Note any security implications, especially around credentials, repo access, command execution, or container tooling.
- Update documentation when user-facing behavior changes.
- Prefer additive, reviewable commits over force-pushed history rewrites.

## Security

- Treat `.env`, `.data/`, and generated local state as non-committable.
- Keep new settings opt-in where possible.
- Default to least privilege for runtime behavior and permissions.

If you find a security issue, please avoid filing a public exploit write-up in an issue before maintainers have a chance to assess it.
