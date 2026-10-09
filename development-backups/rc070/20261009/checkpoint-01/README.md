# RC0.7 source recovery checkpoint01

This directory stores user-authorized source backups on a dedicated backup branch. It changes no RC runtime file. This backup commit is not a release candidate, CI qualification, tag, GitHub Release or installation result. Copying old source/test identity never proves the final0.7 candidate passed.

| Family | Actual parent | Recoverable source | Expected full tree | Status |
|---|---|---|---|---|
| contracts755-fixed3-frozen8 | D6 c60f9667fa8431e27fabbc497c19b4abfef5b965 | Eight exact source files | 7fc8df465d177137111fc2dda1b23cbae062e0b4 /1849 entries | Historical frozen source; lost execution bytes are not reconstructed |
| contracts755-recovered-newline8 | D6 | Eight exact newly restored/corrected source files | b227335c6503c8b9d2575802522758a308684be8 /1849 entries | Distinct new recovery increment; whole755 NOT_RUN at this checkpoint |
| postpublish-old18 | D6 | Exact18-path UTF8 patch plus full1864 native source manifest | 3637f0b23ab15c75e2bf734a3ebae35d408fa3d5 | Historical component source, actual five installed slots NOT_RUN |
| publisher-historical-finite11 | F13 13cd343d942b7a68912d42a8f9235c02ed647764 | Exact52-path UTF8 patch plus full1877 native source manifest | 733a1d5bd53ae0f3b2c3fe44463ac20566c6c47f | Historical source; original85 failed77P/8nonpass; no current candidate PASS |
| windows-recovered-exact73 | D6 | Exact73 source files and public expected identities of40 missing foundation files | Incomplete113-path family; no complete candidate tree claimed | Forty foundation files remain MISSING; do not replace with D6 bytes or guesses |
| native-linux-proposal-only | No implemented candidate | Public recovery design revision3 | No code/native tree | Trusted activation issuer and native placement/installation remain BLOCKED/NOT_RUN |

The publisher active unreviewed/unfinished snapshot, later NEW28 and Stage11 work in progress are intentionally absent. They need a later separately frozen checkpoint. PR98 cancellation and Issue86 snapshot pause remain intact. No JSON report/UID/path/environment label creates authority. No final version/tag/server-condition/Release/postinstall gate is complete here.

Files under family/source preserve exact original UTF8 bytes with `.source` appended to each original filename. These copies are inert backups. Each SOURCE-MANIFEST records original path, Git mode, framed Git blob SHA1, content SHA256 and length. Patches preserve their exact approved historical parent, not whichever branch is currently checked out. Full SOURCE-TREE manifests contain only native path/mode/blob/length/SHA identities. All original sources and patches were independently rehashed and reconstructed through private Git indexes; the four complete family trees above actually matched.

No raw TLS/header/cookie/request evidence, credentials, local.env, host environment files, Git metadata directory, cache, node_modules or Library signed URLs are included. Workflow source may contain normal symbolic GitHub secret references; no actual token values are exported. The GitHub repository is public. MANIFEST.json records all checkpoint file hashes except itself; the remote Git tree independently binds MANIFEST.json and every blob.

## Recovery

Use a separate fresh repository for each family. Clone without checking out main, fetch the exact required public base and detach there. Retrieve this backup directory from its backup branch into a separate path. Before using any file, verify its size/SHA256/framed Git blob against MANIFEST.json and the family manifest. Follow AGENTS.md, mcp-probe-kit resume/spec/heartbeat rules and fresh GitNexus impact before editing runtime symbols; this checkpoint gives no permission to bypass those rules.

For postpublish-old18:

```bash
git clone --no-checkout https://github.com/Eswink/coding-tools-mcp.git old18-recovery
git -C old18-recovery fetch origin c60f9667fa8431e27fabbc497c19b4abfef5b965
git -C old18-recovery checkout --detach c60f9667fa8431e27fabbc497c19b4abfef5b965
git -C old18-recovery apply --index /ABSOLUTE_CHECKPOINT/postpublish-old18/source.patch
git -C old18-recovery write-tree
```

The result must be3637f0b23ab15c75e2bf734a3ebae35d408fa3d5 with1864 entries. For publisher finite11 use a separate clone checked out at exactF13, apply publisher-historical-finite11/source.patch, and require733a1d5bd53ae0f3b2c3fe44463ac20566c6c47f /1877 entries. Applying that patch to D6 is not its original contract.

For either contracts755 eight-file family, start from exactD6 in a separate clone. For every listed record copy its backup `.source` file to the recorded original_path, create only the needed directories, restore its original Git mode, and stage those eight exact paths. Require the corresponding tree and1849 entries above, then compare all path/mode/blob/SHA/length values. Do not combine the historical fixed3 and recovered-newline variants.

For Windows, restore only the73 listed files over exactD6, preserving each original path/mode/blob. This is an incomplete recovery view: the40 separately listed MISSING files have expected hashes only and no saved bytes. Such a view cannot qualify a full Windows native build or positive lifecycle test. Preserve refusal until the real foundation bytes and authorizations are recovered or newly implemented in a separately reviewed scope.

After recovery, all final tests, native ownership/GUI/install, exact0.7 source/version/security/artifact gates, real GitHub prerelease creation and anonymous download/hash/install/start validation still have to run on the final candidate. Historical PASS components and this backup roundtrip are not substitutes.
