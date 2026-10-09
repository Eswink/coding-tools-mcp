"""External built-in-fixture lifecycle only; never a production permission.

Import is effect-free. Construction/import of the compiled bridge is Stage II,
requiring a separately reviewed, sealed invocation. Original SUT is not used.
"""
import time
import types

READY_SECONDS = .2
READ_SECONDS = 5.0
STOP_SECONDS = 2.0
FINISH_SECONDS = 2.0
LOG_LIMIT = 2 * 1024 * 1024


def parse_protocol(raw, phase):
    """Only the private native B/E channel, including split frames."""
    if type(raw) is not bytes or type(phase) is not int or not 0 <= phase <= 4:
        raise ValueError("invalid_protocol_input")
    expected = b"B\nE\n"
    for byte in raw:
        if phase == 4 or byte != expected[phase]:
            raise ValueError("unexpected_native_protocol")
        phase += 1
    return phase


def raise_preserved(primary, errors):
    """Keep each original primary/cancel object after real cleanup attempts."""
    causes = [] if primary is None else [primary]
    for error in errors:
        if not isinstance(error, BaseException):
            raise TypeError("cleanup_error_must_be_original_exception")
        if not any(error is existing for existing in causes):
            causes.append(error)
    if not causes:
        return
    if len(causes) == 1:
        raise causes[0]
    raise BaseExceptionGroup("native fixture primary and cleanup", causes)


class NativeOwnerAdapter:
    """A genuine bridge-created opaque record, not a PID/Popen reconstruction.

    This prototype has no command-result protocol. B means collector boot;
    E means local native family/IO retirement. Neither is original READY/DONE,
    an installation lease, publisher authorization or release qualification.
    """

    def __init__(self):
        # The only bridge import is explicit construction (forbidden Stage I).
        import _rc_native_birth
        factory = _rc_native_birth.create
        if (type(factory) is not types.BuiltinFunctionType or
                factory.__self__ is not _rc_native_birth or factory.__name__ != "create"):
            raise TypeError("reviewed_native_factory_required")
        self.created_at = time.monotonic()
        self.record = factory()
        if type(self.record) is not _rc_native_birth.CreatedRoot:
            raise TypeError("actual_created_native_type_required")
        self.phase = 0
        self.total_bytes = 0
        self.sticky_errors = []
        self.stop_started = None
        self.finish_started = None
        self.launch_attempted = False

    def _pump(self):
        # Attempt BOTH actual reads even when one raises/cancels. No close yet.
        errors = []
        for method, protocol in ((self.record.read, True),
                                 (self.record.exec_error, False)):
            try:
                raw = method()
                if raw is None:
                    continue
                self.total_bytes += len(raw)
                if self.total_bytes > LOG_LIMIT:
                    raise ValueError("combined_transport_limit")
                if protocol:
                    self.phase = parse_protocol(raw, self.phase)
                elif raw:
                    raise OSError("actual_native_exec_error_bytes")
            except BaseException as error:
                errors.append(error)
        raise_preserved(None, errors)

    def _send(self, frame, deadline):
        if frame[:1] == b"L":
            self.launch_attempted = True  # before ANY actual first-byte attempt
        offset = 0
        while offset != len(frame):
            if time.monotonic() >= deadline:
                raise TimeoutError("bounded_native_frame_write")
            try:
                count = self.record.send(frame[offset:])
            except (BlockingIOError, InterruptedError):
                time.sleep(.001)
                continue
            if not 0 < count <= len(frame) - offset:
                raise OSError("native_frame_write_no_progress")
            self.total_bytes += count
            if self.total_bytes > LOG_LIMIT:
                raise ValueError("combined_transport_limit")
            offset += count

    def start(self, mode=None):
        deadline = self.created_at + READY_SECONDS  # never reset at B
        while self.phase < 2:
            if time.monotonic() >= deadline:
                raise TimeoutError("shared_birth_collector_boot_deadline")
            self._pump()
            self.record.observe()
            time.sleep(.001)
        if mode is not None:
            if type(mode) is not int or not 0 <= mode <= 7:
                raise ValueError("builtin_fixture_mode_only")
            self._send(b"L " + bytes([48 + mode]) + b"\n", deadline)
        # No fixture READY is exposed. Do NOT report original READY coverage.
        return self.record.snapshot()

    def _finish(self, errors):
        if self.finish_started is None:
            self.finish_started = time.monotonic()
        deadline = self.finish_started + FINISH_SECONDS
        while time.monotonic() < deadline:
            try:
                self._pump()
            except BaseException as error:
                errors.append(error)
            try:
                terminal = self.record.observe()
                if terminal is not None:
                    self.record.reap()
                    break
            except BaseException as error:
                errors.append(error)
                break
            time.sleep(.001)
        else:
            errors.append(TimeoutError("actual_root_terminal_unknown"))
        # Real reads after terminal/reap, then actual once-close attempts.
        try:
            self._pump()
        except BaseException as error:
            errors.append(error)
        try:
            status = self.record.retire()
        except BaseException as error:
            errors.append(error)
            return None
        if not status["native_closed"]:
            errors.append(RuntimeError("native_local_closure_unknown"))
        return status

    def stop(self, primary=None):
        errors = []
        if self.stop_started is None:
            self.stop_started = time.monotonic()
        deadline = self.stop_started + STOP_SECONDS
        try:
            self._send(b"S\n", deadline)
            while self.phase < 4:
                if time.monotonic() >= deadline:
                    raise TimeoutError("native_family_empty_unknown")
                self._pump()
                if self.record.observe() is not None:
                    raise RuntimeError("root_died_before_empty")
                time.sleep(.001)
            self._send(b"C\n", deadline)
        except BaseException as error:
            errors.append(error)
        # NO group kill or abort after a possible first LAUNCH byte.
        status = self._finish(errors)
        raise_preserved(primary, errors)
        return status

    def abort_no_launch(self, primary=None):
        errors = []
        try:
            # Native private sticky state independently rejects after LAUNCH.
            self.record.abort_before_launch()
        except BaseException as error:
            errors.append(error)
        status = self._finish(errors)
        raise_preserved(primary, errors)
        return status
