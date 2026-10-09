const fsroot='/workspace/work/rc070/rsa-cargo-resolver-owned01';
const quote=x=>"'"+String(x).replace(/'/g,"'\"'\"'")+"'";
const packetResult=await tools.exec_command({cmd:"python3 - <<'PY'\nfrom pathlib import Path\nprint((Path('"+fsroot+"')/'STARTUP-PACKET01.json').read_text())\nPY",max_output_tokens:15000});
if(packetResult.exit_code!==0)throw new Error('PACKET_READ_FAILED');
const packet=JSON.parse(packetResult.output);const phases=[];const after=[];let primary=null;let started=false;
const guard=async label=>{const r=await tools.exec_command({cmd:'/usr/bin/python3 -B '+quote(fsroot+'/cargo-source-guard01.py')+' '+quote(label),max_output_tokens:10000,yield_time_ms:1000});let v=r;if(r.session_id){v=await tools.write_stdin({session_id:r.session_id,chars:'',yield_time_ms:1000,max_output_tokens:10000});if(v.session_id)throw new Error('GUARD_UNCONFIRMED_ASYNC');}const s=JSON.parse(v.output);if(v.exit_code!==0||s.errors.length)throw new Error('GUARD_FAILED:'+JSON.stringify(s.errors));return s;};
try{
 let state=await guard('begin');started=true;
 for(let i=0;i<packet.commands.length;i++){
  let phaseError=null;
  try{
   state=await guard('before-'+i);
   const remaining=120-state.elapsedSeconds-4;
   if(!(remaining>0))throw new Error('NO_COMMAND_DEADLINE_REMAINING');
   const cap=Math.floor((2097152-state.rawTotal)/2);if(cap<=0)throw new Error('NO_RAW_CAP_REMAINING');
   const vector=['/usr/bin/timeout','--signal=TERM','--kill-after=2s',remaining.toFixed(3)+'s','/usr/bin/prlimit','--fsize='+cap+':'+cap,'--','/usr/bin/env','-i',...Object.entries(packet.exactEnvironment).map(([k,v])=>k+'='+v),...packet.commands[i]];
   const stdout=fsroot+'/raw/phase-'+i+'.stdout';const stderr=fsroot+'/raw/phase-'+i+'.stderr';
   let r=await tools.exec_command({cmd:vector.map(quote).join(' ')+' > '+quote(stdout)+' 2> '+quote(stderr),workdir:packet.cwd,yield_time_ms:1000,max_output_tokens:1000});
   while(r.session_id){r=await tools.write_stdin({session_id:r.session_id,chars:'',yield_time_ms:1000,max_output_tokens:1000});}
   phases.push({phase:i,actualNativeExit:r.exit_code,wrappedArgv:vector,command:packet.commands[i],stdout,stderr});
   if(r.exit_code!==0)throw new Error('NATIVE_CARGO_FAIL:'+i+':'+r.exit_code);
  }catch(e){phaseError=e;}
  finally{try{after.push(await guard('after-'+i));}catch(e){phaseError=phaseError?new AggregateError([phaseError,e],'original phase and mandatory after failures'):e;}}
  if(phaseError)throw phaseError;
 }
}catch(e){primary=e;}
finally{if(started){try{after.push(await guard('final'));}catch(e){primary=primary?new AggregateError([primary,e],'original launch and mandatory final failures'):e;}}}
const result={phases,after,primary:primary?String(primary):null,scope:'ACTUAL_OFFLINE_CARGO_RESOLUTION_ONLY',familyClosureClaim:false,productWired:false,buildAuditInstallRCQualified:false};
const literal=JSON.stringify(JSON.stringify(result));
text(await tools.exec_command({cmd:"python3 - <<'PY'\nfrom pathlib import Path\nimport json\nv=json.loads("+literal+")\np=Path('"+fsroot+"')/'ACTUAL-ROOT-CARGO-RECEIPT01.json'\nwith p.open('x') as f:json.dump(v,f,indent=2)\np.chmod(0o600)\nprint({'phases':len(v['phases']),'exits':[x['actualNativeExit'] for x in v['phases']],'primary':v['primary'],'scope':v['scope']})\nPY",max_output_tokens:2500}));
if(primary)throw primary;
