"""Test-only independent literals and helpers for the unified AppLocker audit."""
import ast
import hashlib
import json
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import applocker_observation_contract as contract
from cmd_observation_fixtures import completed_fixture, reseal

__all__ = ('encode', 'digest', 'fixture', 'identity', 'inspect_query',
           'inspect_pure_source', 'inspect_reader_source', 'CASE', 'BASE', 'START',
           'END', 'PATH', 'CHANNEL', 'PREDICATES', 'SELECTOR', 'QUERY', 'BRACKET')

CASE = 'cmd-relative-batch-exit23'
BASE = 'pilot/' + CASE + '/'
START, END = '2026-10-03T07:00:00.0000000Z', '2026-10-03T07:00:01.0000000Z'
PATH = (r'C:\Fixture\Local\Temp\ctm-direct-pilot-00000000000000000000000000000001'
        r'\owned-0000000000000000000000000000000b\workspace\direct.cmd')
CHANNEL = 'Microsoft-Windows-AppLocker/MSI and Script'
PREDICATES = ("@Name='Microsoft-Windows-AppLocker'", 'EventID=8005', 'EventID=8006', 'EventID=8007',
              "@SystemTime>='" + START + "'", "@SystemTime<='" + END + "'", "PolicyName='SCRIPT'",
              'TargetProcessId=4242', "FilePath='" + PATH + "'")
SELECTOR = ("*[System[Provider[" + PREDICATES[0] + "] and (" + ' or '.join(PREDICATES[1:4]) +
            ") and TimeCreated[" + ' and '.join(PREDICATES[4:6]) + "]] and UserData[RuleAndFileData[" +
            ' and '.join(PREDICATES[6:]) + "]]]")
QUERY = ('<QueryList><Query Id="0" Path="' + CHANNEL + '"><Select Path="' + CHANNEL + '">' +
         escape(SELECTOR) + '</Select></Query></QueryList>')
BRACKET = dict(Protocol='applocker-invocation-bracket-v1', StartedUtc=START, EndedUtc=END, ElapsedMilliseconds=1000)


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture():
    """Augment unchanged old synthetic fixture at the producer's actual checkpoints."""
    context, members = completed_fixture()
    source = json.loads(members[BASE + 'case.json'])['Launcher']
    numbers = {key: value for key, value in source['Numbers'].items() if key.startswith('pilot_cmd_batch_')}
    numbers.update(pilot_created_pid=4242, pilot_cmd_minimal_payload_verified=1)
    numbers.update({'pilot_cmd_batch_destination_' + key: value for key, value in
                    dict(open_error=0, desired_access=0x40000000, handle_flags=0,
                         file_type=1, links=1, length=0, attributes=32).items()})
    identities = {key: value for key, value in source['Identities'].items() if key.startswith('pilot_cmd_batch_')}
    identities.update({key: source['Identities'][key] for key in ('pilot_cmd_observation_case',
                       'pilot_cmd_observation_protocol', 'pilot_cmd_observation_command', 'pilot_cmd_observation_cwd')})
    for name, data in tuple(members.items()):
        if name.startswith('pilot/') and name.endswith('.json'):
            value = json.loads(data)
            for row in value.get('Cases', [value]):
                if row.get('Case') == CASE and (row['Launcher']['Created'] or name == BASE + 'ownership-profile.json'):
                    row['Launcher']['Numbers'].update({key: value for key, value in numbers.items()
                                                     if key != 'pilot_created_pid' or row['Launcher']['Created']})
                    row['Launcher']['Identities'].update(identities)
            members[name] = encode(value)
    members['applocker-observation/invocation.json'] = encode(BRACKET)
    raw = dict(Protocol='applocker-script-observation-raw-v1', Case=CASE, Status='raw_matched', Reason=None,
               Decision=dict(EventId=8007, Utc='2026-10-03T07:00:00.5000000Z'), QuerySha256=digest(QUERY.encode()))
    for key, name in [('Ownership', BASE + 'ownership-process.json'), ('Case', BASE + 'case.json'),
                      ('Run', 'pilot/pilot-result.json'), ('Invocation', 'applocker-observation/invocation.json')]:
        raw[key + 'Sha256'] = digest(members[name])
    members['applocker-observation/observation.json'] = encode(raw)
    return reseal(context, members)


def identity(members):
    return contract.target_identity(*(members[contract.FIXED_MEMBERS[key]] for key in ('ownership', 'case', 'run', 'payload')))


def inspect_query(query):
    root = ET.fromstring(query)
    assert [node.tag for node in root.iter()] == ['QueryList', 'Query', 'Select']
    assert root.attrib == {} and root[0].attrib == {'Id': '0', 'Path': CHANNEL}
    assert root[0][0].attrib == {'Path': CHANNEL} and root[0][0].text == SELECTOR


def inspect_pure_source(source):
    allowed = {'datetime', 'json', 'math', 're', 'xml.etree.ElementTree', 'cmd_observation_artifact', 'cmd_observation_contracts'}
    imports = {name.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for name in node.names}
    imports.update(node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom))
    assert imports == allowed


def inspect_reader_source(source):
    """Independent literal oracle, also run against deliberately weakened source."""
    selector = re.search(r'\$expected = "([^\n]+)"', source).group(1)
    for variable, literal in [('StartedUtc', START), ('EndedUtc', END), ('TargetPid', '4242'), ('TargetPath', PATH)]:
        selector = selector.replace('$($request.' + variable + ')', literal)
    assert selector == SELECTOR
    for token in ('$query.TolerateQueryErrors = $false', '$reader.BatchSize = 1',
                  '[string]::Equals($select.InnerText, $expected, [StringComparison]::Ordinal)', '$query.ChildNodes.Count -ne 1',
                  '$process.ExitCode -ne 0', '$stderrCount -ne 0', '$timer.ElapsedMilliseconds -ge 10000',
                  '$capture.Length + $count -gt 131072', '$stderrCount -gt 4096',
                  '$process.WaitForExit(1000) -and $process.HasExited', 'if (-not $closed'):
        assert token in source, token
    assert source.count('ReadEvent([TimeSpan]::FromMilliseconds(2000))') == 2
    assert source.index('$reader.BatchSize = 1') < source.index('$first = $reader.ReadEvent')
    writer = source.split('function Write-AppLockerBoundedJson {', 1)[1].split('\nfunction ', 1)[0]
    stages = ("'observation-pending.json'", '[IO.FileMode]::CreateNew', '$stream.Write($bytes, 0, $bytes.Length)',
              '$stream.Flush($true)', '$stream.Dispose()', '[IO.File]::Move($writePath, $finalPath)')
    for token in stages:
        assert writer.count(token) == 1, token
    assert [writer.index(token) for token in stages] == sorted(writer.index(token) for token in stages)
    assert writer.strip().endswith('if (-not $invocation) { [IO.File]::Move($writePath, $finalPath) }\n}')

