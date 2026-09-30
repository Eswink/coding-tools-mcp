"""Receipt for the actual platform fixture run; not native application wiring proof."""
import hashlib,json,platform,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
paths=sorted((root/'src-tauri/src/workspace_snapshots').glob('*.rs'))+sorted((root/'tests/snapshot-fixture').glob('Cargo.*'))+[root/'tests/snapshot-fixture/src/lib.rs',root/'.github/workflows/workspace-snapshot-native.yml']
receipt={'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'platform':platform.platform(),'native_application_wiring_verified':False,'scope':'real filesystem operations on disposable synthetic fixtures only','source_files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(root/'snapshot-native-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
