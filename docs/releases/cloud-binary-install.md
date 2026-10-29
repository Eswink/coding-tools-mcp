# Standalone cloud binary bundle

This artifact family is required alongside the Windows NSIS and Linux desktop DEB/AppImage files for the full release. It is not included in the desktop-only structural bundle. Publication must verify both families against the same product version and immutable source commit.

## Contents and platform
The Linux amd64 archive contains exactly four release executables in bin/: coding-tools-gateway, coding-tools-agent, coding-tools-control-gateway and coding-tools-mcp-gateway, plus manifest.json and this README. The manifest records product and independent component versions, source commit/tree, CI run, target and SHA256 digests. The outer receipt records the archive digest.

Build target is x86_64-unknown-linux-gnu on Ubuntu22.04. The workflow verifies real release CLI behavior on the build runner and consumes the same archive on Ubuntu24.04 for isolated process tests. This is not a CentOSStream8, musl, ARM, Docker-image or existing VPS compatibility claim. Check the recorded dynamic library dependencies before selecting a deployment host.

## Local installation and verification
1. Obtain the archive, outer archive receipt and SHA256SUMS.txt from the same verified candidate run. Verify SHA256SUMS.txt before extraction and compare source/version identity with the selected desktop release.
2. Extract only into a new directory owned by the intended service operator. Do not extract into an existing workspace, system directory or directory containing credentials. The archive has no absolute paths, links, configuration or state files.
3. Run each executable with --help and --version. Every printed cloud product version must match the selected RC. The cloud-agent and local-agent library component versions may differ and are recorded separately.
4. Keep configuration and secret files outside the extracted binary directory and outside Git. Use the executable's explicit configuration and stdin/private-file interfaces; no sample credential, signing key, password, token or production DSN is supplied by this bundle.
5. Provision a supported database and minimum runtime permissions through a separately reviewed operator procedure. Migration, owner/client/device provisioning and service startup are explicit operations. Do not infer permission to alter a VPS, firewall, Nginx/Baota, TLS, WAF or database from downloading this artifact.

## Executable roles
- coding-tools-gateway: standalone identity service and its explicit local provisioning commands
- coding-tools-control-gateway: opt-in identity and Agent control service with explicit device selection
- coding-tools-mcp-gateway: MCP control-plane service; workspace execution still requires a connected authorized host
- coding-tools-agent: outbound Agent transport process; it does not independently grant local workspace execution authority

Use the current binary's --help as the command syntax authority. Do not run overlapping gateway variants on the same configured listener. Preserve identity state and revocation semantics during upgrades; replacing binaries is not permission to roll back or delete the database.

## Actual acceptance and limits
The exact downloaded release bytes are used for the existing standalone HTTP/PostgreSQL process suite and the gateway/control/Agent authenticated WSS process suite. Fixture credentials are ephemeral, held in private temporary test directories and never packaged. These suites do not contact the VPS or real ChatGPT. MCP executable acceptance here covers actual CLI startup/help/version and rejected missing arguments; it does not claim an additional full public-MCP business process test. The exact-source integration workflow remains required independently.

No service unit, Docker image, production configuration or credential is silently installed. The existing deploy/cloud-gateway review blueprints remain separate review material. A usable binary artifact is not proof that the user's live deployment topology is ready. Windows production sandbox design and the complete release ledger remain release blockers until explicitly resolved.
