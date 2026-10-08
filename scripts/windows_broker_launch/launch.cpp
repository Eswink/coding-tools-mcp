#include "launch.h"
#include <bcrypt.h>
#include <algorithm>
#include <atomic>
#include <memory>
#include <new>
#include <process.h>
#include <vector>

namespace broker_probe {
bool close_owned(HANDLE& handle, DWORD& error) {
    if (!handle || handle == INVALID_HANDLE_VALUE) return true;
    HANDLE owned = handle;
    handle = nullptr; // Never retry an uncertain close or double-close a reused value.
    if (CloseHandle(owned)) return true;
    DWORD last = GetLastError();
    if (!error) error = last ? last : ERROR_GEN_FAILURE;
    return false;
}
bool same_identity(const ImageIdentity& a, const ImageIdentity& b) {
    return a.volume == b.volume && a.file_id == b.file_id &&
           a.sha256 == b.sha256 && a.size == b.size;
}
bool fingerprint(HANDLE handle, ImageIdentity& identity, DWORD& error, DWORD& cleanup) {
    FILE_ID_INFO id{};
    LARGE_INTEGER size{}, zero{};
    if (!GetFileInformationByHandleEx(handle, FileIdInfo, &id, sizeof(id)) ||
        !GetFileSizeEx(handle, &size) || !SetFilePointerEx(handle, zero, nullptr, FILE_BEGIN)) {
        if (!error) error = GetLastError();
        return false;
    }
    if (size.QuadPart <= 0 || size.QuadPart > 16 * 1024 * 1024) {
        if (!error) error = ERROR_FILE_TOO_LARGE;
        return false;
    }
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    NTSTATUS status = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0);
    if (status >= 0) status = BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0);
    BYTE block[16384];
    LONGLONG total = 0;
    while (status >= 0 && total < size.QuadPart) {
        DWORD received = 0;
        DWORD wanted = static_cast<DWORD>(std::min<LONGLONG>(sizeof(block), size.QuadPart - total));
        BOOL read_ok = ReadFile(handle, block, wanted, &received, nullptr);
        if (!read_ok || !received) {
            if (!error) error = read_ok ? ERROR_READ_FAULT : GetLastError();
            break;
        }
        total += received;
        status = BCryptHashData(hash, block, received, 0);
    }
    if (status >= 0 && !error) status = BCryptFinishHash(hash, identity.sha256.data(), 32, 0);
    if (status < 0 && !error) error = static_cast<DWORD>(status);
    NTSTATUS destroyed = hash ? BCryptDestroyHash(hash) : 0;
    NTSTATUS closed = algorithm ? BCryptCloseAlgorithmProvider(algorithm, 0) : 0;
    if (destroyed < 0 && !cleanup) cleanup = static_cast<DWORD>(destroyed);
    if (closed < 0 && !cleanup) cleanup = static_cast<DWORD>(closed);
    identity.volume = id.VolumeSerialNumber;
    std::copy_n(id.FileId.Identifier, 16, identity.file_id.begin());
    identity.size = static_cast<ULONGLONG>(size.QuadPart);
    return !error && !cleanup && total == size.QuadPart;
}
struct PipeReader {
    HANDLE pipe = nullptr;
    std::atomic<bool> stop{false}, seen{false};
    BYTE bytes[65536]{};
    DWORD used = 0, error = 0;
    bool eof = false;
};
static unsigned __stdcall read_pipe(void* context) {
    auto& reader = *static_cast<PipeReader*>(context);
    while (!reader.stop.load()) {
        DWORD available = 0;
        if (!PeekNamedPipe(reader.pipe, nullptr, 0, nullptr, &available, nullptr)) {
            DWORD error = GetLastError();
            reader.eof = error == ERROR_BROKEN_PIPE;
            reader.error = reader.eof ? 0 : error;
            return 0;
        }
        if (!available) { Sleep(10); continue; }
        reader.seen.store(true); // Publish before consuming bytes, including before admission.
        DWORD room = static_cast<DWORD>(sizeof(reader.bytes)) - reader.used;
        if (!room) { reader.error = ERROR_BUFFER_OVERFLOW; return 0; }
        DWORD received = 0, wanted = std::min<DWORD>(available, std::min<DWORD>(room, 4096));
        if (!ReadFile(reader.pipe, reader.bytes + reader.used, wanted, &received, nullptr)) {
            DWORD error = GetLastError();
            reader.eof = error == ERROR_BROKEN_PIPE;
            reader.error = reader.eof ? 0 : error;
            return 0;
        }
        if (!received) { reader.error = ERROR_READ_FAULT; return 0; }
        reader.used += received;
    }
    reader.error = ERROR_CANCELLED; // A joined stopped reader is not EOF evidence.
    return 0;
}
static void note_failure(LaunchResult& result, Reason reason, DWORD error) {
    if (result.reason == Reason::None) {
        result.reason = reason;
        result.error = error ? error : ERROR_GEN_FAILURE;
    }
}
static bool marker_absent(const std::wstring& path) {
    if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) return false;
    DWORD error = GetLastError();
    return error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND;
}
static void pump_debug(const LaunchRequest& request, const std::wstring& marker,
                       PROCESS_INFORMATION& process, PipeReader& output, PipeReader& errors,
                       LaunchResult& result) {
    ULONGLONG admission_end = GetTickCount64() + 5000, execution_end = 0, drain_end = 0, fault_at = 0;
    auto native_failure = [&](DWORD error) {
        if (!result.cleanup_error) result.cleanup_error = error ? error : ERROR_GEN_FAILURE;
        note_failure(result, Reason::Native, error);
    };
    auto terminate = [&]() {
        if (result.termination_requested || result.process_signaled) return true;
        DWORD wait = WaitForSingleObject(process.hProcess, 0);
        if (wait == WAIT_OBJECT_0) { result.process_signaled = true; return true; }
        if (wait == WAIT_FAILED) native_failure(GetLastError());
        if (TerminateProcess(process.hProcess, 125)) {
            result.termination_requested = true;
            return true;
        }
        DWORD error = GetLastError();
        if (WaitForSingleObject(process.hProcess, 0) == WAIT_OBJECT_0) {
            result.process_signaled = true;
            return true;
        }
        native_failure(error);
        return false;
    };
    if (result.cleanup_error) note_failure(result, Reason::Native, result.cleanup_error);
    while (result.event_count < 256) {
        ULONGLONG now = GetTickCount64();
        if (request.fault == Fault::Wait && !result.fault_applied) {
            result.fault_applied = true;
            note_failure(result, Reason::Wait, ERROR_GEN_FAILURE);
        }
        bool post = request.fault == Fault::PostTimeout || request.fault == Fault::PostCancel;
        if (result.reason == Reason::None && result.admission_continued && post) {
            if (!fault_at && output.seen.load() && errors.seen.load() &&
                GetFileAttributesW(marker.c_str()) != INVALID_FILE_ATTRIBUTES)
                fault_at = now + (request.fault == Fault::PostTimeout ? 250 : 100);
            if (fault_at && now >= fault_at) {
                result.fault_applied = true;
                note_failure(result, request.fault == Fault::PostTimeout ? Reason::Timeout : Reason::Cancel,
                             request.fault == Fault::PostTimeout ? WAIT_TIMEOUT : ERROR_CANCELLED);
            }
        }
        if (result.reason == Reason::None && now >=
            (result.admission_continued ? execution_end : admission_end)) {
            note_failure(result, Reason::Timeout, WAIT_TIMEOUT);
        }
        if (result.reason != Reason::None) {
            if (!drain_end) drain_end = now + 10000;
            if (!terminate() || now >= drain_end) break;
        }
        DEBUG_EVENT event{};
        if (!WaitForDebugEvent(&event, 50)) {
            DWORD error = GetLastError();
            if (error != ERROR_SEM_TIMEOUT) native_failure(error);
            continue;
        }
        ++result.event_count;
        if (event.dwProcessId != process.dwProcessId) {
            native_failure(ERROR_INVALID_DATA);
            break; // Never continue an event attributed to another process.
        }
        if (!result.create_event && event.dwDebugEventCode != CREATE_PROCESS_DEBUG_EVENT)
            native_failure(ERROR_INVALID_DATA);
        DWORD continuation = DBG_CONTINUE;
        switch (event.dwDebugEventCode) {
        case CREATE_PROCESS_DEBUG_EVENT: {
            if (result.create_event || event.dwThreadId != process.dwThreadId)
                native_failure(ERROR_INVALID_DATA);
            result.create_event = true;
            HANDLE image = event.u.CreateProcessInfo.hFile;
            result.raw_hfile_present = image && image != INVALID_HANDLE_VALUE;
            if (result.raw_hfile_present)
                result.raw_identity_ok = fingerprint(image, result.observed,
                    result.native_query_error, result.cleanup_error);
            result.identity_match = result.raw_identity_ok && same_identity(request.expected, result.observed);
            DWORD out_available = 0, err_available = 0;
            bool peek_ok = PeekNamedPipe(output.pipe, nullptr, 0, nullptr, &out_available, nullptr) &&
                           PeekNamedPipe(errors.pipe, nullptr, 0, nullptr, &err_available, nullptr);
            if (!peek_ok) native_failure(GetLastError());
            result.no_marker_before = peek_ok && !out_available && !err_available &&
                marker_absent(marker) && !output.seen.load() && !errors.seen.load();
            close_owned(image, result.cleanup_error);
            if (!result.no_marker_before) native_failure(ERROR_INVALID_DATA);
            if (!result.raw_hfile_present) note_failure(result, Reason::NullImage, ERROR_INVALID_HANDLE);
            else if (!result.raw_identity_ok) native_failure(result.native_query_error);
            else if (!result.identity_match) note_failure(result, Reason::Identity, ERROR_FILE_INVALID);
            if (result.cleanup_error) native_failure(result.cleanup_error);
            if (result.reason == Reason::None && request.fault != Fault::None &&
                request.fault != Fault::PostTimeout && request.fault != Fault::PostCancel) {
                result.fault_applied = true;
                Reason reason = Reason::Native;
                switch (request.fault) {
                case Fault::NullImage: reason = Reason::NullImage; break;
                case Fault::FileIdQuery: reason = Reason::FileIdQuery; break;
                case Fault::HashQuery: reason = Reason::HashQuery; break;
                case Fault::Continue: reason = Reason::Continue; break;
                case Fault::PreCancel: reason = Reason::Cancel; break;
                case Fault::PreTimeout: {
                    ULONGLONG deadline = GetTickCount64() + 100;
                    while (GetTickCount64() < deadline) Sleep(10);
                    reason = Reason::Timeout;
                    break;
                }
                default: break;
                }
                note_failure(result, reason, reason == Reason::Timeout ? WAIT_TIMEOUT : ERROR_CANCELLED);
            }
            break;
        }
        case LOAD_DLL_DEBUG_EVENT: {
            HANDLE dll = event.u.LoadDll.hFile;
            if (!close_owned(dll, result.cleanup_error)) native_failure(result.cleanup_error);
            break;
        }
        case EXCEPTION_DEBUG_EVENT:
            continuation = DBG_EXCEPTION_NOT_HANDLED;
            if (event.u.Exception.dwFirstChance && result.admission_continued &&
                !result.initial_breakpoint && event.u.Exception.ExceptionRecord.ExceptionCode == EXCEPTION_BREAKPOINT) {
                result.initial_breakpoint = true;
                continuation = DBG_CONTINUE;
            } else if (!event.u.Exception.dwFirstChance) {
                native_failure(event.u.Exception.ExceptionRecord.ExceptionCode);
            }
            break;
        case EXIT_PROCESS_DEBUG_EVENT:
            result.exit_event = true;
            result.exit_code = event.u.ExitProcess.dwExitCode;
            if (result.reason == Reason::None && (!result.admission_continued || result.exit_code))
                native_failure(ERROR_PROCESS_ABORTED);
            break;
        case CREATE_THREAD_DEBUG_EVENT:
        case EXIT_THREAD_DEBUG_EVENT:
        case UNLOAD_DLL_DEBUG_EVENT:
        case OUTPUT_DEBUG_STRING_EVENT:
            break; // Event process/thread handles belong to Windows; never close them here.
        default:
            native_failure(ERROR_INVALID_DATA);
            break;
        }
        if (event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT && result.reason == Reason::None) {
            if (GetTickCount64() >= admission_end) note_failure(result, Reason::Timeout, WAIT_TIMEOUT);
            else result.admitted = true;
        }
        if (result.reason != Reason::None && !terminate()) break;
        bool continued = ContinueDebugEvent(event.dwProcessId, event.dwThreadId, continuation) != FALSE;
        if (!continued) {
            native_failure(GetLastError()); // Sticky even if termination-only retry succeeds.
            if (terminate()) continued = ContinueDebugEvent(event.dwProcessId, event.dwThreadId, continuation) != FALSE;
            if (!continued) { native_failure(GetLastError()); break; }
        }
        if (event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT && result.reason == Reason::None) {
            result.admission_continued = true;
            execution_end = GetTickCount64() + 10000;
        }
        if (event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT) {
            result.exit_continued = true;
            break;
        }
    }
    if (!result.exit_continued) {
        native_failure(WAIT_TIMEOUT);
        terminate();
    }
}
LaunchResult run_launch(const LaunchRequest& request) {
    LaunchResult result;
    ImageIdentity retained;
    DWORD query_error = 0;
    if (!fingerprint(request.retained, retained, query_error, result.cleanup_error) ||
        !same_identity(retained, request.expected)) {
        note_failure(result, Reason::Manifest, query_error ? query_error : ERROR_INVALID_DATA);
        result.readers_joined = true;
        result.cleanup_allowed = !result.cleanup_error;
        return result;
    }
    auto output = std::unique_ptr<PipeReader>(new (std::nothrow) PipeReader);
    auto errors = std::unique_ptr<PipeReader>(new (std::nothrow) PipeReader);
    if (!output || !errors) {
        note_failure(result, Reason::Native, ERROR_NOT_ENOUGH_MEMORY);
        result.readers_joined = result.cleanup_allowed = true;
        return result;
    }
    HANDLE input_read = nullptr, input_write = nullptr, output_write = nullptr, error_write = nullptr;
    HANDLE output_thread = nullptr, error_thread = nullptr;
    PROCESS_INFORMATION process{};
    STARTUPINFOEXW startup{};
    std::vector<BYTE> attributes;
    bool attributes_ready = false;
    try {
        std::wstring command = L"\"" + request.application + L"\" --marker";
        std::wstring marker = request.cwd + L"\\marker.txt";
        std::wstring environment = L"DOT_HOLD=";
        environment += (request.fault == Fault::PostTimeout || request.fault == Fault::PostCancel) ? L"1" : L"0";
        environment.push_back(L'\0');
        environment += L"PATH=" + request.system_root + L"\\System32";
        environment.push_back(L'\0');
        environment += L"SystemRoot=" + request.system_root;
        environment.append(2, L'\0');
        SIZE_T bytes = 0;
        InitializeProcThreadAttributeList(nullptr, 1, 0, &bytes);
        if (!bytes) throw GetLastError();
        attributes.resize(bytes);
        startup.lpAttributeList = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attributes.data());
        if (!InitializeProcThreadAttributeList(startup.lpAttributeList, 1, 0, &bytes)) throw GetLastError();
        attributes_ready = true;
        SECURITY_ATTRIBUTES security{sizeof(security), nullptr, TRUE};
        if (!CreatePipe(&input_read, &input_write, &security, 0) ||
            !CreatePipe(&output->pipe, &output_write, &security, 0) ||
            !CreatePipe(&errors->pipe, &error_write, &security, 0) ||
            !SetHandleInformation(output->pipe, HANDLE_FLAG_INHERIT, 0) ||
            !SetHandleInformation(errors->pipe, HANDLE_FLAG_INHERIT, 0) ||
            !SetHandleInformation(input_write, HANDLE_FLAG_INHERIT, 0)) throw GetLastError();
        close_owned(input_write, result.cleanup_error);
        HANDLE inherited[]{input_read, output_write, error_write};
        if (!UpdateProcThreadAttribute(startup.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            inherited, sizeof(inherited), nullptr, nullptr)) throw GetLastError();
        startup.StartupInfo.cb = sizeof(startup);
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = input_read;
        startup.StartupInfo.hStdOutput = output_write;
        startup.StartupInfo.hStdError = error_write;
        output_thread = reinterpret_cast<HANDLE>(_beginthreadex(nullptr, 0, read_pipe, output.get(), 0, nullptr));
        if (!output_thread) throw static_cast<DWORD>(ERROR_NOT_ENOUGH_MEMORY);
        error_thread = reinterpret_cast<HANDLE>(_beginthreadex(nullptr, 0, read_pipe, errors.get(), 0, nullptr));
        if (!error_thread) throw static_cast<DWORD>(ERROR_NOT_ENOUGH_MEMORY);
        if (result.cleanup_error) throw result.cleanup_error;
        DWORD flags = DEBUG_ONLY_THIS_PROCESS | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT;
        if (!CreateProcessW(request.application.c_str(), command.data(), nullptr, nullptr, TRUE,
            flags, environment.data(), request.cwd.c_str(), &startup.StartupInfo, &process)) throw GetLastError();
        result.created = true;
        result.pid = process.dwProcessId;
        close_owned(process.hThread, result.cleanup_error);
        close_owned(input_read, result.cleanup_error);
        close_owned(output_write, result.cleanup_error);
        close_owned(error_write, result.cleanup_error);
        pump_debug(request, marker, process, *output, *errors, result);
    } catch (DWORD error) {
        note_failure(result, Reason::Native, error);
    } catch (...) {
        note_failure(result, Reason::Native, ERROR_NOT_ENOUGH_MEMORY);
    }
    if (attributes_ready) DeleteProcThreadAttributeList(startup.lpAttributeList);
    close_owned(input_read, result.cleanup_error);
    close_owned(input_write, result.cleanup_error);
    close_owned(output_write, result.cleanup_error);
    close_owned(error_write, result.cleanup_error);
    if (result.created) {
        DWORD wait = WaitForSingleObject(process.hProcess, result.exit_continued ? 1000 : 0);
        result.process_signaled = wait == WAIT_OBJECT_0;
        if (!result.process_signaled && !result.cleanup_error)
            result.cleanup_error = wait == WAIT_FAILED ? GetLastError() : WAIT_TIMEOUT;
    }
    auto join_reader = [&](std::unique_ptr<PipeReader>& reader, HANDLE& thread, bool& eof,
                           std::string& captured) {
        DWORD waited = thread ? WaitForSingleObject(thread, 1000) : WAIT_OBJECT_0;
        if (waited == WAIT_FAILED && !result.cleanup_error) result.cleanup_error = GetLastError();
        bool joined = waited == WAIT_OBJECT_0;
        if (!joined) {
            reader->stop.store(true);
            waited = WaitForSingleObject(thread, 1000);
            if (waited == WAIT_FAILED && !result.cleanup_error) result.cleanup_error = GetLastError();
            joined = waited == WAIT_OBJECT_0;
        }
        if (!joined) {
            if (!result.cleanup_error) result.cleanup_error = WAIT_TIMEOUT;
            reader.release(); // Its active thread still owns this state until harness exit.
            return false;
        }
        eof = thread && reader->eof;
        if (reader->error && !result.cleanup_error) result.cleanup_error = reader->error;
        try {
            captured.assign(reinterpret_cast<const char*>(reader->bytes), reader->used);
        } catch (...) {
            if (!result.cleanup_error) result.cleanup_error = ERROR_NOT_ENOUGH_MEMORY;
        } // Always join the other reader, even when evidence allocation fails.
        close_owned(thread, result.cleanup_error);
        close_owned(reader->pipe, result.cleanup_error);
        return true;
    };
    bool output_joined = join_reader(output, output_thread, result.stdout_eof, result.stdout_bytes);
    bool error_joined = join_reader(errors, error_thread, result.stderr_eof, result.stderr_bytes);
    result.readers_joined = output_joined && error_joined;
    bool completed = !result.created || (result.exit_continued && result.process_signaled &&
                                        result.stdout_eof && result.stderr_eof);
    result.cleanup_allowed = completed && result.readers_joined && !result.cleanup_error;
    if (result.cleanup_allowed) {
        close_owned(process.hThread, result.cleanup_error);
        close_owned(process.hProcess, result.cleanup_error);
        result.cleanup_allowed = !result.cleanup_error;
    } // Unknown process/thread ownership is retained until harness exit; never detach.
    return result;
}
} // namespace broker_probe
