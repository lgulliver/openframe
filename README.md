# openframe

Run a multi-repo OpenCode remote environment in Docker.

## What this does

- Builds a Debian-based remote workstation image on top of a pinned official Python slim runtime and installs a pinned OpenCode version into it.
- Publishes an Alpine-based variant for lighter deployments.
- Mounts a host repo root into the container as `/repos`.
- Starts a control-plane dashboard on port `4096`.
- Launches one repo-scoped `opencode web` instance per repo, on demand.
- Lets you clone existing repos or create new ones directly from the dashboard.
- Tracks running instances, recent session counts, and last activity.
- Shuts idle repo instances down automatically after a configurable timeout.
- Includes a baseline toolchain for remote coding: `git`, `gh`, `ripgrep`, `fd`, `jq`, `curl`, `wget`, `bash`, `zsh`, `make`, `python3`, `pip`, `nodejs`, `npm`, `openssh-client`, `terraform`.
- Supports build-time package manifests and startup hooks for provisioning extra SDKs and tools.
- Applies optional global git config at container startup.
- Ships a broader non-apt toolchain: .NET 10, Go 1.26, Rust, Azure CLI, kubectl 1.36.0, Helm 4.1.4, Terraform 1.15.4, AWS CLI, Python 3.14, Node 24 via nvm, and Bun 1.3.14.

## Quick start

Use the published image from GHCR by default.

```bash
cp .env.example .env
docker compose pull
docker compose up
```

Then:

1. Set `REPOS_PATH` in `.env` to the host directory that contains the repos you want to expose.
2. Set `OPENCODE_SERVER_PASSWORD`.
3. Set at least one provider API key, or add it later from the dashboard UI.
4. Open `http://localhost:4096`.

The dashboard is protected with HTTP basic auth. Username defaults to `opencode`.

Published images currently target `linux/amd64` only.

## Image variants

Openframe publishes two image families:

- `ghcr.io/lgulliver/openframe:<version>`
  Full Debian/glibc workstation image. This is the default and the recommended choice.
- `ghcr.io/lgulliver/openframe:<version>-alpine`
  Lighter Alpine image with the control plane and baseline CLI tooling.

Both published image families are currently `linux/amd64` only.

Use the Alpine tag by overriding `REMOTE_IMAGE_NAME` in `.env`.

The Alpine image is intentionally narrower:

- it includes the manager, OpenCode, and baseline CLI tools
- it does not include the full pinned SDK workstation stack from the Debian image
- browser terminal behavior on musl-based runtimes is not the primary supported path

## Local build

If you want to modify the workstation image locally instead of pulling GHCR:

```bash
cp .env.example .env
docker compose build
docker compose up
```

You can also point `REMOTE_IMAGE_NAME` at a local tag before running `docker compose up`.

## How it works

The top-level container no longer runs one `opencode web` process directly.

Instead it runs [manager.py](manager.py), which:

- scans `/repos` for candidate repos
- shows them in a dashboard
- starts a dedicated `opencode web` process for a repo when you open it
- stores that repo instance state under `.data/instances/<repo>/`
- stops idle repo instances automatically

Each repo instance gets its own port from the configured instance range. The dashboard links you directly to that repo instance.

## Configuration

Main settings live in `.env`.

```env
OPENCODE_VERSION=1.15.10
REMOTE_IMAGE_NAME=ghcr.io/lgulliver/openframe:1.15.10
REPOS_PATH=../
APT_PACKAGES_FILE=docker/apt-packages.txt
EXTRA_APT_PACKAGES=
DOTNET_SDK_VERSION=10.0.300
GO_VERSION=1.26.3
PYTHON_VERSION=3.14.5
NODE_VERSION=24.16.0
NVM_VERSION=0.40.3
KUBECTL_VERSION=v1.36.0
HELM_VERSION=v4.1.4
TERRAFORM_VERSION=1.15.4
BUN_VERSION=1.3.14
OPENCODE_PORT=4096
OPENCODE_HOSTNAME=0.0.0.0
INSTANCE_HOST=0.0.0.0
INSTANCE_PORT_START=4300
INSTANCE_PORT_END=4399
INSTANCE_IDLE_TIMEOUT_SECONDS=1800
OPENCODE_SERVER_USERNAME=opencode
OPENCODE_SERVER_PASSWORD=change-me
GIT_USER_NAME=
GIT_USER_EMAIL=
GIT_DEFAULT_BRANCH=main
GIT_CORE_EDITOR=
GIT_AUTH_USERNAME=
GIT_AUTH_PASSWORD=
GITHUB_TOKEN=
OPENCODE_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_GENERATIVE_AI_API_KEY=
```

Key settings:

- `REPOS_PATH`
  Points to the host directory containing the repos you want to expose. In your current layout, `../` mounts `/Users/lgulliver/repos` into the container as `/repos`.
- `OPENCODE_VERSION`
  The exact OpenCode version installed into the Debian runtime at build time.
- `REMOTE_IMAGE_NAME`
  The image Compose runs by default. The example points at the published Debian GHCR image, but you can override it with a local tag or the Alpine variant tag.
- `DOTNET_SDK_VERSION`, `GO_VERSION`, `PYTHON_VERSION`, `NODE_VERSION`, `NVM_VERSION`, `KUBECTL_VERSION`, `HELM_VERSION`, `TERRAFORM_VERSION`, `BUN_VERSION`
  Build-time versions for the pinned runtime, SDK, and CLI toolchain. `PYTHON_VERSION` selects the official `python:<version>-slim-bookworm` base image for the main workstation image.
- `OPENCODE_PORT`
  Port for the control-plane dashboard.
- `INSTANCE_PORT_START` and `INSTANCE_PORT_END`
  Published host/container port range used for repo-specific OpenCode instances.
- `INSTANCE_IDLE_TIMEOUT_SECONDS`
  How long an unused repo instance stays up before being terminated.
- `OPENCODE_API_KEY`
  Passed through automatically to every spawned repo-scoped OpenCode process.
  If left empty in env, it can be set later from the dashboard UI.
- `APT_PACKAGES_FILE`
  Build-time package manifest copied into the image. Use this for repeatable SDK and CLI installs from Debian apt.
- `EXTRA_APT_PACKAGES`
  Extra Debian packages to bake into the workstation image.
- `GIT_USER_NAME`, `GIT_USER_EMAIL`, `GIT_DEFAULT_BRANCH`, `GIT_CORE_EDITOR`
  Applied as global git config each time the container starts.
  If these are left empty, they can be set later from the dashboard UI.
- `GIT_AUTH_USERNAME`, `GIT_AUTH_PASSWORD`, `GITHUB_TOKEN`
  Used for non-interactive HTTPS git clone operations from the dashboard. For GitHub PAT auth, setting `GITHUB_TOKEN` alone is enough.

## Dashboard Model

This repo is intentionally shaped like a control plane above OpenCode, not a single OpenCode workspace.

The dashboard gives you:

- a list of repos under `/repos`
- clone and create actions for repos under `/repos`
- running vs stopped state per repo
- per-repo OpenCode URL and port
- recent session count for running repos
- last access time

The dashboard is the “overall view.” OpenCode itself remains the per-repo coding surface.

Clone and create actions are implemented by the manager process itself:

- clone runs `git clone <url> /repos/<name>`
- create makes `/repos/<name>`, writes a minimal `README.md`, and can initialize git

## Tooling And Git Setup

There are now three ways to extend the environment:

- Base image tools
  The image includes the default coding toolchain.
- Build-time package manifest
  Add Debian packages to [docker/apt-packages.txt](docker/apt-packages.txt) for repeatable installs during `docker compose build`.
- Startup hooks
  Put idempotent scripts in [docker/startup.d](docker/startup.d) for setup that should run when the container starts.

Use the package manifest for apt-installable SDKs and CLIs. Use startup hooks for installers, auth setup, or dotfile/bootstrap work that should not live directly in the Dockerfile.

The image now also includes build-time installers under [docker/install.d](docker/install.d) for:

- `.NET SDK 10.0.300`
- `Go 1.26.3`
- latest stable Rust via `rustup`
- Azure CLI from Microsoft's Debian repo
- `kubectl v1.36.0`
- `Helm v4.1.4`
- `Terraform 1.15.4`
- latest AWS CLI v2 from the official installer
- `Python 3.14.5` from the official slim runtime image
- `nvm 0.40.3` with `Node 24.16.0 LTS`
- `Bun 1.3.14`

The Alpine image is a separate published variant built from [Dockerfile.alpine](Dockerfile.alpine). It includes the control plane, OpenCode, and the baseline CLI stack, but not the full Debian SDK/toolchain layer.

Git config is applied from env on container startup:

- `GIT_USER_NAME`
- `GIT_USER_EMAIL`
- `GIT_DEFAULT_BRANCH`
- `GIT_CORE_EDITOR`

If those env vars are not set, use the dashboard `Git Settings` action. The manager persists those values under `.data/manager-settings.json` and writes a shared git config consumed by spawned repo instances.

API keys and additional OpenCode runtime settings can also be managed from the dashboard `API Keys + Config` action. The manager persists them in `.data/manager-settings.json` and applies them to newly spawned repo instances.

HTTPS clone auth can also be supplied from env:

- `GITHUB_TOKEN`
  Used automatically for GitHub HTTPS clones with username `x-access-token`.
- `GIT_AUTH_USERNAME` and `GIT_AUTH_PASSWORD`
  Generic basic-auth credentials for other HTTPS git remotes.

## Session and Lifecycle Behavior

Repo processes and OpenCode sessions are separate concerns.

- Opening a repo starts its OpenCode web backend if it is not already running.
- Closing your browser does not immediately kill that backend.
- Idle backends are stopped automatically by the manager.
- Session data persists on disk under `.data/instances/<repo>/`, so reopening the repo preserves prior OpenCode history and state.

## Permissions

The container always loads [opencode.json](opencode.json) via `OPENCODE_CONFIG`.

Current defaults:

- `read`, `glob`, `grep`, and `lsp` are allowed
- `bash` and `edit` require approval
- `.env` files are blocked by default
- `external_directory` is denied

That keeps the remote environment usable without silently granting unrestricted shell and file-edit access everywhere.

## Working Commands

The included [Makefile](Makefile) wraps the common commands.

- `make build`
- `make up`
- `make up-d`
- `make down`
- `make shell`
- `make attach PORT=4300`

`make attach` connects a local TUI to a specific repo instance port.

## Notes

- The dashboard runs on `4096` by default, while repo instances use the configured instance port range.
- The container sets `BROWSER=/bin/true` so spawned OpenCode instances do not try to open a browser in-container.
- The container runs [docker/bootstrap.sh](docker/bootstrap.sh) before starting the manager. That applies git config and any startup hooks.
- Git settings from the UI are persisted locally under `.data/manager-settings.json` and applied to future repo instances through a shared git config file.
- API keys and extra OpenCode config from the UI are also persisted locally under `.data/manager-settings.json`. The manager materializes a generated OpenCode config for child instances and injects the configured runtime env vars when those instances start.
- Repo discovery is currently shallow: it lists first-level directories under `/repos`.
- Browser terminal support depends on PTY support in the container runtime. This repo now uses a glibc-based Debian runtime because the musl-based path did not satisfy OpenCode's PTY library.
- The Alpine image exists for lighter deployments, but the Debian/glibc image remains the primary fully provisioned workstation target.
- I validated the compose configuration, but I have not yet runtime-tested a full multi-instance launch sequence in Docker.
