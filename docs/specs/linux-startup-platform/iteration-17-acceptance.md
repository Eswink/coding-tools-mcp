# Iteration 17 acceptance — Ubuntu secure-storage recovery

Status: **PASSED / OPERATOR ACCEPTED**

## Accepted candidate

- Version: `0.6.0-rc.4`
- Product source: `afcaae34e700e468b08eb97187ef9b12a0be1388`
- Linux RC workflow: `34976767756` — passed
- Windows RC workflow: `34976767781` — passed
- DEB SHA-256: `4b9fb575897f70cef8f1271675f4dc14485db02f5339dee450d8b0e61178031f`
- AppImage SHA-256: `b7a6dcf79dd096a184a4ac5f572450d8b7f8a08c7fcf2b7a9ff43f82981041d0`
- Linux package artifact digest: `sha256:c6d18965a7872b45644d98f1a74fe8486e4309f4752693ec1d747d56f638f232`

## Real affected-machine acceptance

The operator retested the exact RC4 candidate on the previously affected Ubuntu 24.04 desktop environment and reported that all requested acceptance steps passed successfully for both the DEB and AppImage packages.

This closes the Round 17G real-operator gate. The accepted behavior includes successful secure-storage recovery and return to normal application operation on the affected machine.

## Resolved Linux failure chain

Round 17 established two separate Linux startup conditions rather than treating them as one generic keyring failure:

1. The application could inherit a different session D-Bus from the systemd user manager/GNOME Keyring. RC3 added bounded selection of the canonical user-owned `$XDG_RUNTIME_DIR/bus` only after proving that route is usable and Secret Service is available there.
2. After the correct bus route was selected, the affected fresh profile could have a reachable Secret Service but no persistent `default` collection. RC4 classifies this as `secret_service_default_collection_missing` and permits an explicit recovery action to ask the desktop Secret Service to create the default collection only when no managed configuration already exists.

The application does not read or persist the Secret Service password and does not start/restart privileged credential daemons.

## Security invariants retained

The accepted implementation remains fail-closed:

- no plaintext configuration fallback;
- no raw `0600` master-key file;
- no replacement master key for existing ciphertext;
- no reset or overwrite of an existing encrypted configuration when its key is unavailable;
- no silent fallback to another credential mechanism;
- background MCP, Actions, tunnel and chat-approval services start only after secure configuration reaches Ready;
- Windows credential behavior remains unchanged.

The conditional Round 17D passphrase-vault fallback is therefore **not required** for this defect.

## Release boundary

Round 17 is complete and the release gate is now open for the accepted RC4 source/bytes. `v0.5.0` remains immutable.

Any product-byte change after this acceptance invalidates the RC4 operator evidence. Such a change must use `0.6.0-rc.5` or later and repeat the full automated Linux/Windows gates plus real affected-machine acceptance before Stable promotion.
