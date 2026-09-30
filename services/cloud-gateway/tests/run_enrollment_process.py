#!/usr/bin/env python3
"""Shipped operator/device bootstrap. Disposable loopback PostgreSQL only; no secrets logged."""
import argparse
import base64
import concurrent.futures
import json
from pathlib import Path
import subprocess
from service_test_support import disposable_fixture, private_json, require


def command(f, binary, args, packet=None, success=True):
    r = subprocess.run([str(binary), *map(str, args)], input=json.dumps(packet).encode() if packet is not None else b"",
                       capture_output=True, timeout=15, env=f.env)
    require((r.returncode == 0) == success, "enrollment_command_status")
    f.check_logs(r.stderr)
    require(b"pkcs8" not in r.stderr and b"token" not in r.stderr, "enrollment_diagnostics_redacted")
    if not success:
        require(r.stdout == b"", "failed_enrollment_has_no_document")
        return None
    return json.loads(r.stdout) if r.stdout else None


def key(f, binaries):
    return command(f, binaries / "coding-tools-agent", ["generate-key", "--output-stdout"])


def invitation(f, binaries):
    return command(f, binaries / "coding-tools-gateway",
                   ["invite-device", "--config", f.config, "--secrets-stdin", "--output-stdout"], f.packet)


def prove(f, binaries, invite, private_key, success=True):
    identity = {k: f.config_data[k] for k in ("origin", "prefix", "connector")}
    path = private_json(f.root / "enrollment-identity.json", identity)
    return command(f, binaries / "coding-tools-agent", ["prove-enrollment", "--config", path,
                   "--bundle-stdin", "--output-stdout"], {"invitation": invite, "key": private_key}, success)


def redeem(f, binaries, proof, success=True):
    return command(f, binaries / "coding-tools-gateway", ["redeem-device", "--config", f.config,
                   "--bundle-stdin", "--output-stdout"], {"secrets": f.packet, "proof": proof}, success)


def bootstrap(f, binaries, secret_canaries):
    private_key = key(f, binaries)
    invite = invitation(f, binaries)
    secret_canaries.extend([private_key["pkcs8"], invite["token"]])
    proof = prove(f, binaries, invite, private_key)
    require("pkcs8" not in json.dumps(proof), "private_key_never_reaches_gateway")
    connection = redeem(f, binaries, proof)
    require(connection["version"] == 1 and connection["authority_epoch"] == 1,
            "native_configuration_shape")
    return {**connection, "pkcs8": private_key["pkcs8"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--pg-lib", type=Path)
    parser.add_argument("--bin-dir", type=Path, required=True)
    args = parser.parse_args()
    binaries = args.bin_dir.resolve()
    cases = []
    with disposable_fixture(args.pg_bin.resolve(), binaries / "coding-tools-gateway", args.pg_lib) as f:
        f.setup_config("https://gateway.example.invalid", "https://callback.example.invalid/callback")
        f.invoke("migrate")
        f.invoke("provision-owner", packet={**f.packet, "password": f.password})
        f.invoke("register-client")
        first = key(f, binaries)
        invite = invitation(f, binaries)
        proof = prove(f, binaries, invite, first)
        forged = {**proof, "signature": base64.urlsafe_b64encode(bytes(64)).decode().rstrip("=")}
        redeem(f, binaries, forged, False)
        require(f.sql("SELECT count(*) FROM ctm_devices") == "0", "invalid_proof_does_not_enroll")
        connection = redeem(f, binaries, proof)
        cases.append("invalid_proof_preserves_invitation_then_valid_shipped_bootstrap")
        redeem(f, binaries, proof, False)
        cases.append("single_use_proof_replay_denied")
        require(f.sql("SELECT count(*) FROM ctm_grant_projection") == "0" and
                f.sql("SELECT count(*) FROM ctm_families") == "0", "enrollment_not_approval")
        cases.append("no_implicit_device_selection_oauth_or_local_grant")
        changed = {**invite, "origin": "https://foreign.example.invalid"}
        prove(f, binaries, changed, first, False)
        cases.append("device_checks_independently_pinned_identity")
        shared = invitation(f, binaries)
        proofs = [prove(f, binaries, shared, key(f, binaries)) for _ in range(2)]
        def race(p):
            return subprocess.run([str(binaries / "coding-tools-gateway"), "redeem-device", "--config", str(f.config),
                                   "--bundle-stdin", "--output-stdout"], input=json.dumps({"secrets": f.packet, "proof": p}).encode(),
                                  capture_output=True, timeout=15, env=f.env)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(race, proofs))
        require(sum(r.returncode == 0 for r in results) == 1, "distinct_keys_single_redemption")
        require(f.sql("SELECT count(*) FROM ctm_devices") == "2", "only_one_race_device")
        for r in results:
            f.check_logs(r.stderr)
        cases.append("different_key_concurrent_redemption_one_winner")
        expired = prove(f, binaries, invitation(f, binaries), first)
        f.sql("UPDATE ctm_enrollments SET expires_at=0 WHERE NOT consumed")
        redeem(f, binaries, expired, False)
        cases.append("expired_invitation_rejected")
        persistent = prove(f, binaries, invitation(f, binaries), first)
        f.pg_stop(); f.pg_start()
        redeem(f, binaries, persistent)
        redeem(f, binaries, persistent, False)
        cases.append("database_restart_preserves_valid_invite_and_consumption")
        command(f, binaries / "coding-tools-gateway", ["revoke-device", "--config", f.config,
                "--secrets-stdin", "--device", connection["device"]], f.packet)
        require(f.sql("SELECT count(*) FROM ctm_devices WHERE revoked") == "1", "device_revoked")
        command(f, binaries / "coding-tools-control-gateway", ["select-device", "--config", f.config,
                "--secrets-stdin", "--device", connection["device"]], f.packet, False)
        cases.append("shipped_revocation_blocks_device_selection")
    print(json.dumps({"suite": "shipped_enrollment_process", "result": "PASS", "passed": len(cases),
                      "cases": cases, "physical_host": False, "production_credentials": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"suite": "shipped_enrollment_process", "result": "FAIL",
                          "case": str(exc) if isinstance(exc, RuntimeError) else "bounded_failure"}))
        raise SystemExit(1) from None
