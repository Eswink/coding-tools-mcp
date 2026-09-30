"""Exact-base one-shot assembly; excluded from clean product commits."""
from pathlib import Path
import hashlib
import re

BASE_BLOBS = {
 'src-tauri/src/mcp/listener.rs': 'd016c27f57ae57da537f453e4b2a3d25816b1e7d',
 'src-tauri/src/runtime/supervisor.rs': '9bc9be6ab9b56b9bff9a44d9eb2ed9752f6f41d2',
 'src-tauri/src/mcp/mod.rs': 'd6409b1b4b3e8635b02dbebb433f552d35a3e3e2',
 'src-tauri/src/tools/mod.rs': 'bd30dc30486b5e9d46f9313da59a74f0d0eabe11',
}
texts = {}
for name, expected in BASE_BLOBS.items():
 data = Path(name).read_bytes()
 actual = hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
 if actual != expected: raise RuntimeError(f'Wrong base {name}: {actual}')
 texts[name] = data.decode('utf-8')

def once(text, old, new):
 if text.count(old) != 1: raise RuntimeError(f'Expected one anchor ({text.count(old)}): {old[:100]}')
 return text.replace(old, new, 1)

path = 'src-tauri/src/mcp/listener.rs'
text = texts[path]
anchor = '#[allow(clippy::too_many_arguments)]\nfn spawn_listener_with_binding('
start = text.index(anchor)
end = text.index('\nasync fn serve(', start)
original = text[start:end]
params = original.split('fn spawn_listener_with_binding(\n',1)[1].split('    bind: impl FnOnce()',1)[0]
arguments = ''.join('        '+line.strip().split(':',1)[0]+',\n' for line in params.splitlines() if line.strip())
bindparam = '    bind: impl FnOnce() -> Result<tokio::net::TcpListener, String>,\n'
triple = '(ShutdownSender, tauri::async_runtime::JoinHandle<()>, Arc<crate::runtime::WorkspaceExecutionGate>)'
quad = '(ShutdownSender, tauri::async_runtime::JoinHandle<()>, Arc<crate::runtime::WorkspaceExecutionGate>, crate::tools::listener_context::ListenerContextLease)'
core = once(original, 'fn spawn_listener_with_binding(', 'fn spawn_listener_with_lease_binding(')
core = once(core, f') -> Result<{triple}, String>', f') -> Result<{quad}, String>')
core = once(core, '    let listener = bind()?;\n', '''    let listener = bind()?;
    // Guard construction precedes spawn, including cancellation before first poll.
    // The lease shares the exact context; it never creates execution authority.
    let context_lease = crate::tools::listener_context::ListenerContextLease::new(state.mcp.clone());
    let lifetime = context_lease.lifetime_guard();
''')
core = once(core, '    let handle = tauri::async_runtime::spawn(async move {\n', '    let handle = tauri::async_runtime::spawn(async move {\n        let _lifetime = lifetime;\n')
core = once(core, '    Ok((shutdown_tx, handle, execution_gate))', '    Ok((shutdown_tx, handle, execution_gate, context_lease))')
compat = ('#[cfg(test)]\n#[allow(clippy::too_many_arguments)]\nfn spawn_listener_with_binding(\n'+params+bindparam+f') -> Result<{triple}, String> {{\n'+'    spawn_listener_with_lease_binding(\n'+arguments+'        bind,\n    ).map(|(shutdown, handle, gate, _lease)| (shutdown, handle, gate))\n}\n\n')
public = ('#[allow(clippy::too_many_arguments)]\npub(crate) fn spawn_listener_with_origin_and_context_lease(\n'+params+f') -> Result<{quad}, String> {{\n'+'    spawn_listener_with_lease_binding(\n'+arguments+'        || bind_listener(port),\n    )\n}\n\n')
text = text[:start]+compat+public+core+text[end:]
text = once(text, '#[allow(clippy::too_many_arguments)]\npub(crate) fn spawn_listener_with_origin_and_execution_gate(', '#[cfg(test)]\n#[allow(clippy::too_many_arguments)]\npub(crate) fn spawn_listener_with_origin_and_execution_gate(')
texts[path] = text+'\n#[cfg(test)]\n#[path = "listener_context_tests.rs"]\nmod context_lease_tests;\n'
path = 'src-tauri/src/mcp/mod.rs'
texts[path] = once(texts[path], 'pub(crate) use listener::{spawn_listener_with_origin_and_execution_gate, ShutdownSender};', '#[cfg(test)]\npub(crate) use listener::spawn_listener_with_origin_and_execution_gate;\npub(crate) use listener::{spawn_listener_with_origin_and_context_lease, ShutdownSender};')
path = 'src-tauri/src/tools/mod.rs'
texts[path] = once(texts[path], 'pub mod context;\n', 'pub mod context;\npub mod listener_context;\n')
path = 'src-tauri/src/runtime/supervisor.rs'
text = texts[path]
text = once(text, '    execution_gate: Option<Arc<WorkspaceExecutionGate>>,\n', '    execution_gate: Option<Arc<WorkspaceExecutionGate>>,\n    context_lease: Option<crate::tools::listener_context::ListenerContextLease>,\n')
text = once(text, '    /// True when the service for this workspace is currently running.\n', '''    /// Exact listener-owned context; never a new gate or execution permission.
    pub fn mcp_context_lease(&self, workspace_id: &str) -> Option<crate::tools::listener_context::ListenerContextLease> {
        self.entries.get(&(workspace_id.to_string(), ServiceKind::Mcp))
            .filter(|entry| entry.phase == RuntimePhase::Running)
            .and_then(|entry| entry.context_lease.as_ref())
            .filter(|lease| lease.is_live())
            .cloned()
    }

    /// True when the service for this workspace is currently running.
''')
text = once(text, '            Some(RuntimePhase::Running)\n        )\n    }\n\n    pub fn refresh_mcp', '            Some(RuntimePhase::Running)\n        ) && (kind != ServiceKind::Mcp || self.mcp_context_lease(workspace_id).is_some())\n    }\n\n    pub fn refresh_mcp')
text = once(text, '        entry.phase = RuntimePhase::Stopping;\n', '        entry.phase = RuntimePhase::Stopping;\n        if let Some(lease) = entry.context_lease.as_ref() { lease.close(); }\n')
text = once(text, '        self.entries.remove(&(workspace_id.to_string(), kind));\n    }\n\n    fn status', '''        if let Some(entry) = self.entries.remove(&(workspace_id.to_string(), kind)) {
            if let Some(lease) = entry.context_lease { lease.close(); }
        }
    }

    fn status''')
text, n = re.subn(r'(?m)^(\s*)execution_gate: None,\n', r'\1execution_gate: None,\n\1context_lease: None,\n', text)
if n != 2: raise RuntimeError(f'Expected 2 production initializer fields, got {n}')
text = once(text, '            execution_gate: if phase == RuntimePhase::Running {', '            context_lease: None,\n            execution_gate: if phase == RuntimePhase::Running {')
text = once(text, 'mcp::spawn_listener_with_origin_and_execution_gate(', 'mcp::spawn_listener_with_origin_and_context_lease(')
text = once(text, ').map(|(shutdown, handle, execution_gate)| (shutdown, handle, Some(execution_gate)))', ').map(|(shutdown, handle, execution_gate, context_lease)| (shutdown, handle, Some(execution_gate), Some(context_lease)))')
text = once(text, ').map(|(shutdown, handle)| (shutdown, handle, None))', ').map(|(shutdown, handle)| (shutdown, handle, None, None))')
text = once(text, '            Ok((shutdown, handle, execution_gate)) => {', '            Ok((shutdown, handle, execution_gate, context_lease)) => {')
text = once(text, '                        execution_gate,\n', '                        execution_gate,\n                        context_lease,\n')
text = once(text, '                if should_mark_runtime_error(entry, listening) {\n', '                if should_mark_runtime_error(entry, listening) {\n                    if let Some(lease) = entry.context_lease.as_ref() { lease.close(); }\n')
texts[path] = text+'\n#[cfg(test)]\n#[path = "supervisor_context_tests.rs"]\nmod context_lease_tests;\n'
for name, text in texts.items(): Path(name).write_bytes(text.encode('utf-8'))
print('Applied exact reviewed four-file integration; authorization/sandbox method bodies unchanged.')
