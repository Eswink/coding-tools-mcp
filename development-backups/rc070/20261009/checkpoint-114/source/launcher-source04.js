const fsroot='/workspace/work/rc070/rsa-cargo-resolver-owned01';
const quote=x=>"'"+String(x).replace(/'/g,"'\"'\"'")+"'";
const shell={shell:'/bin/bash',login:false};
const complete=async r=>{while(r.session_id)r=await tools.write_stdin({session_id:r.session_id,chars:'',yield_time_ms:1000,max_output_tokens:12000});return r;};
const pr=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/python3 -B - <<'PY'\nfrom pathlib import Path\nprint((Path('"+fsroot+"')/'STARTUP-PACKET01.json').read_text())\nPY",max_output_tokens:12000,yield_time_ms:1000}));
if(pr.exit_code!==0)throw new Error('PACKET_READ_FAILED');const packet=JSON.parse(pr.output);
const phases=[],after=[];let primary=null;let started=false;let state=null;
const guard=async label=>{
 let limit=30;
 if(state?.startedMonotonic){
  const tick=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s 2s /usr/bin/python3 -B -c 'import time; print(time.monotonic())'",max_output_tokens:1000,yield_time_ms:1000}));
  if(tick.exit_code!==0)throw new Error('CURRENT_MONOTONIC_UNCONFIRMED');
  const current=Number(tick.output.trim());if(!Number.isFinite(current))throw new Error('CURRENT_MONOTONIC_INVALID');
  limit=Math.max(.1,120-(current-state.startedMonotonic)-2);
 }
 const cmd=['/usr/bin/timeout','--signal=TERM','--kill-after=2s',limit.toFixed(3)+'s','/usr/bin/python3','-B',fsroot+'/cargo-source-guard03.py',label].map(quote).join(' ');
 const r=await complete(await tools.exec_command({...shell,cmd,yield_time_ms:1000,max_output_tokens:12000}));
 if(r.exit_code!==0)throw new Error('GUARD_NATIVE_FAIL:'+label+':'+r.exit_code+':'+r.output);
 const v=JSON.parse(r.output);if(v.errors.length)throw new Error('GUARD_FAILED:'+JSON.stringify(v.errors));state=v;return v;
};
try{
 state=await guard('begin');started=true;
 for(let i=0;i<packet.commands.length;i++){
  let phaseError=null;
  try{
   state=await guard('before-'+i);const remaining=120-state.elapsedSeconds-4;
   if(!(remaining>0))throw new Error('NO_COMMAND_DEADLINE_REMAINING');
   const cap=Math.floor((2097152-state.rawTotal)/2);if(cap<=0)throw new Error('NO_RAW_CAP_REMAINING');
   const vector=['/usr/bin/timeout','--signal=TERM','--kill-after=2s',remaining.toFixed(3)+'s','/usr/bin/prlimit','--fsize='+cap+':'+cap,'--','/usr/bin/env','-i',...Object.entries(packet.exactEnvironment).map(([k,v])=>k+'='+v),...packet.commands[i]];
   const stdout=fsroot+'/raw/phase-'+i+'.stdout';const stderr=fsroot+'/raw/phase-'+i+'.stderr';
   const r=await complete(await tools.exec_command({...shell,cmd:'umask 022\n'+vector.map(quote).join(' ')+' > '+quote(stdout)+' 2> '+quote(stderr),workdir:packet.cwd,yield_time_ms:1000,max_output_tokens:1000}));
   phases.push({phase:i,actualNativeExit:r.exit_code,wrappedArgv:vector,command:packet.commands[i],stdout,stderr,perStreamActualCap:cap,childUmask:'0022'});
   if(r.exit_code!==0)throw new Error('NATIVE_CARGO_FAIL:'+i+':'+r.exit_code);
  }catch(e){phaseError=e;}
  finally{
   try{
    const v=await guard('after-'+i);after.push(v);
    const p=phases.find(x=>x.phase===i);if(p&&v.raw.some(x=>x.file.startsWith('phase-'+i+'.')&&x.bytes>=p.perStreamActualCap))throw new Error('RAW_REACHED_CAP:'+i);
   }catch(e){phaseError=phaseError?new AggregateError([phaseError,e],'original phase and mandatory after failures'):e;}
  }
  if(phaseError)throw phaseError;
 }
 // The original metadata stream must be complete UTF-8 JSON with the required graph shape.
 const check=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s "+Math.max(.1,120-state.elapsedSeconds-4).toFixed(3)+"s /usr/bin/python3 -B - <<'PY'\nimport json,pathlib\nD=pathlib.Path('"+fsroot+"');v=json.loads((D/'raw/phase-2.stdout').read_bytes().decode('utf-8'));assert isinstance(v,dict) and isinstance(v.get('packages'),list) and v['packages'] and isinstance(v.get('resolve'),dict) and isinstance(v['resolve'].get('nodes'),list) and isinstance(v.get('workspace_members'),list);ids=[p['id'] for p in v['packages']];assert len(ids)==len(set(ids));assert all(isinstance(n,dict) and n['id'] in ids and isinstance(n['features'],list) for n in v['resolve']['nodes']);assert not any(p['name'] in ['rsa','sqlx-mysql'] for p in v['packages']);W=D/'f13-candidate';nodes={n['id']:n for n in v['resolve']['nodes']}\nfor name in ('sqlx','sqlx-macros-core'):\n rows=[p for p in v['packages'] if p['name']==name];assert len(rows)==1;row=rows[0];assert row['version']=='0.8.6' and row['source'] is None and row['manifest_path']==str(W/'services/cloud-gateway/vendor'/name/'Cargo.toml');assert not ({'mysql','all-databases'} & set(nodes[row['id']]['features']))\np=D/'ACTUAL-METADATA-SCHEMA-SAFE01.json';r={'packages':len(v['packages']),'nodes':len(nodes),'completeNativeMetadataJSON':True,'twoExactOwnedPatchManifestPaths':True,'RSAAndMySQLAbsent':True,'activeMySQLAllDatabasesDenied':True,'scope':'RESOLUTION_ONLY_NOT_BUILD_AUDIT_OR_RC'}\nwith p.open('x') as f:json.dump(r,f,indent=2)\np.chmod(0o600)\nprint(json.dumps(r))\nPY",yield_time_ms:1000,max_output_tokens:2500}));
 if(check.exit_code!==0)throw new Error('METADATA_FULL_JSON_SCHEMA_FAILED:'+check.exit_code+':'+check.output);
}catch(e){primary=e;}
finally{if(started){try{after.push(await guard('final'));}catch(e){primary=primary?new AggregateError([primary,e],'original launch and mandatory final failures'):e;}}}
const result={phases,after,primary:primary?String(primary):null,scope:'ACTUAL_OFFLINE_CARGO_RESOLUTION_ONLY',familyClosureClaim:false,productWired:false,buildAuditInstallRCQualified:false,postWriterDeadline:'PENDING_EXTERNAL_NATIVE_TICK'};
try{
 const pre=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s 2s /usr/bin/python3 -B -c 'import time; print(time.monotonic())'",max_output_tokens:1000,yield_time_ms:1000}));
 if(pre.exit_code!==0||!Number.isFinite(Number(pre.output.trim())))throw new Error('PRE_WRITER_CLOCK_UNKNOWN');
 const writerRemaining=state?.startedMonotonic?120-(Number(pre.output.trim())-state.startedMonotonic)-2:1;
 if(!(writerRemaining>0))throw new Error('NO_WRITER_DEADLINE_REMAINING');
 const w=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s "+Math.min(3,writerRemaining).toFixed(3)+"s /usr/bin/python3 -B - <<'PY'\nfrom pathlib import Path\nimport json\nv=json.loads("+JSON.stringify(JSON.stringify(result))+")\np=Path('"+fsroot+"')/'ACTUAL-ROOT-CARGO-RECEIPT02.json'\nwith p.open('x') as f:json.dump(v,f,indent=2)\np.chmod(0o600)\nprint({'phases':len(v['phases']),'exits':[x['actualNativeExit'] for x in v['phases']],'primary':v['primary'],'scope':v['scope']})\nPY",max_output_tokens:2500,yield_time_ms:1000}));
 if(w.exit_code!==0)throw new Error('ROOT_RECEIPT_WRITER_FAILED:'+w.exit_code+':'+w.output);
 const post=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s 2s /usr/bin/python3 -B -c 'import time; print(time.monotonic())'",max_output_tokens:1000,yield_time_ms:1000}));
 if(post.exit_code!==0||!Number.isFinite(Number(post.output.trim())))throw new Error('POST_WRITER_CLOCK_UNKNOWN');
 const elapsed=state?.startedMonotonic?Number(post.output.trim())-state.startedMonotonic:null;
 if(elapsed===null||elapsed>120)throw new Error('POST_WRITER_LATE_OR_UNCONFIRMED');
 text(w);text({actualPostWriterElapsedSeconds:elapsed,postWriterDeadlineVerified:true,scope:result.scope,nativeFamilyClosure:false,RCQualified:false});
}catch(e){primary=primary?new AggregateError([primary,e],'original launch and receipt writer failures'):e;}
if(primary)throw primary;
