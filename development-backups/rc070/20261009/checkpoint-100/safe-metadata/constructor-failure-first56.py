import json,sys,tempfile,zipfile
from pathlib import Path
from types import SimpleNamespace
out=Path(__file__).with_name('ZIP-CONSTRUCTOR-FAILURE-FIRST56.json')
owned=Path(tempfile.mkdtemp(prefix='nt-owned-badzip-'));p=owned/'bad.zip';p.write_bytes(b'owned malformed ZIP')
real=p.open('rb');cancel=KeyboardInterrupt('ordinary-real-input-close-cancel');observed=[]
def closing():
    observed.append(sys.exception());real.close();raise cancel
proxy=SimpleNamespace(read=real.read,seek=real.seek,tell=real.tell,close=closing)
original=zipfile.io.open
zipfile.io.open=lambda *a,**k:proxy
try:
    try:zipfile.ZipFile(p)
    except BaseException as actual:
        assert actual is cancel and len(observed)==1 and isinstance(observed[0],zipfile.BadZipFile)
        value={'scope':'actual stdlib ZipFile(path) constructor with owned malformed regular ZIP and controlled actual input close cancellation','actual_primary_type':type(observed[0]).__name__,'primary_object_preserved':actual is observed[0],'close_cancel_object_preserved':actual is cancel,'underlying_actual_file_closed':real.closed,'actual_native_api_calls':0,'official_zip_downloads':0,'go_processes':0}
    else:raise AssertionError('malformed ZIP constructor admitted')
finally:zipfile.io.open=original
out.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
