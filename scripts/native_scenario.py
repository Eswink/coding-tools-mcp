"""Allowlisted native test entrypoints copied into the ephemeral Windows fixture."""
SCRIPTS = {'legacy': '聊天授权原生验收v6.py', 'exclusive': 'exclusive_native_acceptance.py', 'ui-refactor': 'ui_refactor_native_acceptance.py'}


def script_name(scenario: str) -> str:
    if not isinstance(scenario, str) or scenario not in SCRIPTS:
        raise ValueError('unknown native acceptance scenario')
    return SCRIPTS[scenario]
