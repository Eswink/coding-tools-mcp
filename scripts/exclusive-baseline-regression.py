"""Inject the approved no-new-pending assertion into an isolated pre-feature checkout.
The expected failure is a test assertion, never a compiler/infrastructure error.
"""
import argparse, pathlib, subprocess, sys
parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--evidence',required=True);args=parser.parse_args()
root=pathlib.Path(args.root).resolve(); evidence=pathlib.Path(args.evidence).resolve();evidence.mkdir(parents=True,exist_ok=True)
expected='a0551c447712104e2c2cb253d3d8a5a966518580'
actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
if actual!=expected:raise RuntimeError('Failure-first checkout must be the pinned pre-feature base')
path=root/'src-tauri/src/auth/聊天授权v1.rs'
original=path.read_text(encoding='utf-8')
fixture=r'''
#[cfg(test)]
mod exclusive_failure_first {
    use super::*;
    #[test]
    fn occupied_owner_must_not_create_another_pending_record() {
        let service=Arc::new(ChatAuthorizer::default()); service.set_exclusive("failure-first",true);
        let raw=crate::auth::principal::issue("https://fixture.example","https://fixture.example/mcp","fixture-key","fixture-client",3600).unwrap();
        let principal=crate::auth::principal::verify(&raw,"fixture-key","https://fixture.example","https://fixture.example/mcp").unwrap();
        let a=RemoteRequest::verified("failure-first","workspace",principal.clone(),&json!({"openai/session":"A"}),"fixture-key");
        let b=RemoteRequest::verified("failure-first","workspace",principal,&json!({"openai/session":"B"}),"fixture-key");
        let first=service.request(&a,&json!({"scopes":["files.read"]}));
        service.decide("failure-first",first["authorization"]["id"].as_str().unwrap(),true,&["files.read".into()]).unwrap();
        let other=service.request(&b,&json!({}));
        assert_eq!(other["ok"],false,"occupied workspace must not create B pending");
    }
}
'''
try:
    path.write_text(original+fixture,encoding='utf-8')
    result=subprocess.run(['cargo','test','--locked','--lib','--manifest-path','src-tauri/Cargo.toml','exclusive_failure_first::occupied_owner_must_not_create_another_pending_record','--','--nocapture'],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (evidence/'failure-first.txt').write_text(result.stdout,encoding='utf-8')
    valid=result.returncode==101 and 'occupied workspace must not create B pending' in result.stdout and '1 failed' in result.stdout and 'error[E' not in result.stdout
    if not valid:print(result.stdout);raise RuntimeError('Pinned base did not produce the expected assertion failure')
    (evidence/'baseline-sha.txt').write_text(actual+'\n',encoding='utf-8');print('Verified expected pre-feature assertion failure; this is not a passing baseline test.')
finally:path.write_text(original,encoding='utf-8')
