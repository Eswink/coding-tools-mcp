"""Fixed diagnostic cases only; no acquisition or caller-supplied command policy."""

OBSERVATIONS = (
    dict(kind='cmd-cwd', slot=8, tag='Cwd', row_flag='CmdCwdObserved',
         run_flag='CmdCwdRawObservationMatched', accepted_field='CmdCwdObservationPassed',
         status_key='CwdStatus', raw_protocol='cmd-cwd-read-raw-v1',
         command_tail=' /d /q /c cd', output_policy='cwd_ascii_crlf', expected_exit=0,
         matched_status='cmd_cwd_raw_observed', unmatched_status='cmd_cwd_raw_not_observed',
         canary='cwd_observation_did_not_attempt_runtime_canary'),
    dict(kind='cmd-read-direct', slot=9, tag='Read', row_flag='CmdReadObserved',
         run_flag='CmdReadRawObservationMatched', accepted_field='CmdReadObservationPassed',
         status_key='ReadStatus', raw_protocol='cmd-cwd-read-raw-v1',
         command_tail=' /d /q /c type direct.cmd', output_policy='minimal_batch_bytes', expected_exit=0,
         matched_status='cmd_read_direct_raw_observed', unmatched_status='cmd_read_direct_raw_not_observed',
         canary='read_observation_did_not_attempt_runtime_canary'),
    dict(kind='cmd-relative-batch-exit23', slot=10, tag='RelativeBatch', row_flag='CmdRelativeBatchExit23Observed',
         run_flag='CmdRelativeBatchRawObservationMatched', accepted_field='CmdRelativeBatchObservationPassed',
         status_key='RelativeBatchStatus', raw_protocol='cmd-relative-batch-raw-v1',
         command_tail=' /d /q /c .\\direct.cmd', output_policy='empty', expected_exit=23,
         matched_status='cmd_relative_batch_exit23_raw_observed', unmatched_status='cmd_relative_batch_exit23_raw_not_observed',
         canary='relative_batch_observation_did_not_attempt_runtime_canary'),
)


class ArtifactError(ValueError):
    def __init__(self, code, member='', case='', status='inconsistent'):
        super().__init__(code)
        self.code, self.member, self.case, self.status = code, member, case, status


def observation_case(kind):
    if type(kind) is not str:
        raise ArtifactError('identity')
    for observation in OBSERVATIONS:
        if observation['kind'] == kind:
            return observation
    raise ArtifactError('identity')


def observation_expected_bytes(kind, cwd):
    observation = observation_case(kind)
    if type(cwd) is not str:
        raise ArtifactError('identity')
    policy = observation['output_policy']
    if policy == 'cwd_ascii_crlf':
        return (cwd + '\r\n').encode('ascii') if cwd.isascii() else None
    if policy == 'minimal_batch_bytes':
        return b'exit 23\r\n'
    if policy == 'empty':
        return b''
    raise ArtifactError('identity')
