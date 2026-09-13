# Operator-applied public route revalidation

The operator supplied the live BaoTa Nginx configuration and subsequently reported applying the exact OAuth routing exceptions. The old `location /.well-known` shadow was reproduced and repaired in the real Nginx fixture on this branch. The earlier public 404 gate must not be treated as still current or silently relabelled PASS.

Run the existing no-credential public observation again from the independent hosted network, with redirects disabled and normal TLS verification. Preserve the actual endpoint/status/metadata/challenge result. This is a changed deployment condition, not a retry-until-green loop. No production Nginx, DNS, tunnels, secrets or desktop settings are modified by this check.

Keep the routing PR separate from the exclusive conversation/refresh feature. Merge only after its own public and Windows/Linux regression gates pass. The public discovery test does not prove real ChatGPT account authorization or that the new 0.4.0 desktop binary is deployed. Version remains 0.3.2 here; no new installer is built on this routing-only branch.
