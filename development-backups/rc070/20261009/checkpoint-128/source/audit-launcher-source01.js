const fsroot='/workspace/work/rc070/rsa-gateway-audit-build-owned03';
const quote=x=>"'"+String(x).replace(/'/g,"'\"'\"'")+"'";
const shell={shell:'/bin/bash',login:false};
const complete=async r=>{while(r.session_id)r=await tools.write_stdin({session_id:r.session_id,chars:'',yield_time_ms:1000,max_output_tokens:6000});return r;};
const pr=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/python3 -B - <<'PY'\nfrom pathlib import Path\nprint((Path('"+fsroot+"')/'AUDIT-STARTUP-PACKET03.json').read_text())\nPY",max_output_tokens:6000,yield_time_ms:1000}));
if(pr.exit_code!==0)throw new Error('PACKET_READ_FAILED');const packet=JSON.parse(pr.output);
const phases=[],after=[];let primary=null;let started=false;let state=null;
const guard=async label=>{
 let limit=30;
 if(state?.startedMonotonic){
  const tick=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s 2s /usr/bin/python3 -B -c 'import time; print(time.monotonic())'",max_output_tokens:1000,yield_time_ms:1000}));
  if(tick.exit_code!==0)throw new Error('CURRENT_MONOTONIC_UNCONFIRMED');
  const current=Number(tick.output.trim());if(!Number.isFinite(current))throw new Error('CURRENT_MONOTONIC_INVALID');
  limit=Math.max(.1,60-(current-state.startedMonotonic)-2);
 }
 const cmd=['/usr/bin/timeout','--signal=TERM','--kill-after=2s',limit.toFixed(3)+'s','/usr/bin/python3','-B',fsroot+'/audit-source-guard01.py',label].map(quote).join(' ');
 const r=await complete(await tools.exec_command({...shell,cmd,yield_time_ms:1000,max_output_tokens:6000}));
 if(r.exit_code!==0)throw new Error('GUARD_NATIVE_FAIL:'+label+':'+r.exit_code+':'+r.output);
 const v=JSON.parse(r.output);if(v.errors.length)throw new Error('GUARD_FAILED:'+JSON.stringify(v.errors));state=v;return v;
};
try{
 state=await guard('begin');started=true;
 for(let i=0;i<packet.commands.length;i++){
  let phaseError=null;
  try{
   state=await guard('before-'+i);const remaining=60-state.elapsedSeconds-4;
   if(!(remaining>0))throw new Error('NO_COMMAND_DEADLINE_REMAINING');
   const cap=Math.floor((2097152-state.rawTotal)/2);if(cap<=0)throw new Error('NO_RAW_CAP_REMAINING');
   const vector=['/usr/bin/timeout','--signal=TERM','--kill-after=2s',remaining.toFixed(3)+'s','/usr/bin/prlimit','--fsize='+cap+':'+cap,'--','/usr/bin/env','-i',...Object.entries(packet.exactEnvironment).map(([k,v])=>k+'='+v),...packet.commands[i]];
   const stdout=fsroot+'/raw/phase-'+i+'.stdout';const stderr=fsroot+'/raw/phase-'+i+'.stderr';
   const r=await complete(await tools.exec_command({...shell,cmd:'umask 022\n'+vector.map(quote).join(' ')+' > '+quote(stdout)+' 2> '+quote(stderr),workdir:packet.cwd,yield_time_ms:1000,max_output_tokens:1000}));
   phases.push({phase:i,actualNativeExit:r.exit_code,wrappedArgv:vector,command:packet.commands[i],stdout,stderr,perStreamActualCap:cap,childUmask:'0022'});
   if(r.exit_code!==0)throw new Error('NATIVE_AUDIT_FAIL:'+i+':'+r.exit_code);
  }catch(e){phaseError=e;}
  finally{
   try{
    const v=await guard('after-'+i);after.push(v);
    const p=phases.find(x=>x.phase===i);if(p&&v.raw.some(x=>x.file.startsWith('phase-'+i+'.')&&x.bytes>=p.perStreamActualCap))throw new Error('RAW_REACHED_CAP:'+i);
   }catch(e){phaseError=phaseError?new AggregateError([phaseError,e],'original phase and mandatory after failures'):e;}
  }
  if(phaseError)throw phaseError;
 }
 // Read the complete native JSON; raw warnings remain in the private original report.
 const check=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s "+Math.max(.1,60-state.elapsedSeconds-4).toFixed(3)+"s /usr/bin/python3 -B - <<'PY'\nimport json,pathlib\nD=pathlib.Path('"+fsroot+"');assert (D/'raw/phase-0.stdout').read_text().strip()=='cargo-audit 0.22.2'\ndef pairs(xs):\n d={}\n for k,v in xs:\n  if k in d:raise ValueError('duplicate JSON key')\n  d[k]=v\n return d\nv=json.loads((D/'raw/phase-1.stdout').read_bytes().decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))\nassert isinstance(v,dict) and set(v)=={'database','lockfile','settings','vulnerabilities','warnings'};assert type(v['lockfile']['dependency-count']) is int and v['lockfile']['dependency-count']==216\ns=v['settings'];assert s['target_arch']==[] and s['target_os']==[] and s['severity'] is None and s['ignore']==[] and s['informational_warnings']==['unmaintained','unsound','notice']\nw=v['vulnerabilities'];assert type(w['count']) is int and w['count']==0 and w['list']==[] and w['found'] is False\nd=v['database'];assert type(d['advisory-count']) is int and d['advisory-count']>0\nr={'completeNativeAuditJSON':True,'dependencyCount':216,'vulnerabilities':0,'ignore':[],'targetFilters':[],'warnings':v['warnings'],'scope':'AUDIT_ONLY_NOT_BUILD_INSTALL_RELEASE'}\np=D/'ACTUAL-AUDIT-SCHEMA-SAFE03.json'\nwith p.open('x') as f:json.dump(r,f,indent=2)\np.chmod(0o600);print(json.dumps(r))\nPY",yield_time_ms:1000,max_output_tokens:2500}));
 if(check.exit_code!==0)throw new Error('AUDIT_FULL_JSON_SCHEMA_FAILED:'+check.exit_code+':'+check.output);
}catch(e){primary=e;}
finally{if(started){try{after.push(await guard('final'));}catch(e){primary=primary?new AggregateError([primary,e],'original launch and mandatory final failures'):e;}}}
const result={phases,after,primary:primary?String(primary):null,scope:'ACTUAL_RAW_GATEWAY_LOCK_AUDIT_ONLY',familyClosureClaim:false,productWired:false,buildAuditInstallRCQualified:false,postWriterDeadline:'PENDING_EXTERNAL_NATIVE_TICK'};
try{
 const pre=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s 2s /usr/bin/python3 -B -c 'import time; print(time.monotonic())'",max_output_tokens:1000,yield_time_ms:1000}));
 if(pre.exit_code!==0||!Number.isFinite(Number(pre.output.trim())))throw new Error('PRE_WRITER_CLOCK_UNKNOWN');
 const writerRemaining=state?.startedMonotonic?60-(Number(pre.output.trim())-state.startedMonotonic)-2:1;
 if(!(writerRemaining>0))throw new Error('NO_WRITER_DEADLINE_REMAINING');
 const w=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s "+Math.min(3,writerRemaining).toFixed(3)+"s /usr/bin/python3 -B - <<'PY'\nfrom pathlib import Path\nimport json\nv=json.loads("+JSON.stringify(JSON.stringify(result))+")\np=Path('"+fsroot+"')/'ACTUAL-ROOT-AUDIT-RECEIPT03.json'\nwith p.open('x') as f:json.dump(v,f,indent=2)\np.chmod(0o600)\nprint({'phases':len(v['phases']),'exits':[x['actualNativeExit'] for x in v['phases']],'primary':v['primary'],'scope':v['scope']})\nPY",max_output_tokens:2500,yield_time_ms:1000}));
 if(w.exit_code!==0)throw new Error('ROOT_RECEIPT_WRITER_FAILED:'+w.exit_code+':'+w.output);
 const post=await complete(await tools.exec_command({...shell,cmd:"/usr/bin/timeout --signal=TERM --kill-after=2s 2s /usr/bin/python3 -B -c 'import time; print(time.monotonic())'",max_output_tokens:1000,yield_time_ms:1000}));
 if(post.exit_code!==0||!Number.isFinite(Number(post.output.trim())))throw new Error('POST_WRITER_CLOCK_UNKNOWN');
 const elapsed=state?.startedMonotonic?Number(post.output.trim())-state.startedMonotonic:null;
 if(elapsed===null||elapsed>60)throw new Error('POST_WRITER_LATE_OR_UNCONFIRMED');
 text(w);text({actualPostWriterElapsedSeconds:elapsed,postWriterDeadlineVerified:true,scope:result.scope,nativeFamilyClosure:false,RCQualified:false});
}catch(e){primary=primary?new AggregateError([primary,e],'original launch and receipt writer failures'):e;}
if(primary)throw primary;
