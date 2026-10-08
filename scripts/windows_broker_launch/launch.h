#pragma once
#include <windows.h>
#include <array>
#include <string>

namespace broker_probe {
enum class Fault {
    None, NullImage, FileIdQuery, HashQuery, Wait, Continue,
    PreTimeout, PreCancel, PostTimeout, PostCancel
};
enum class Reason {
    None, Manifest, Identity, NullImage, FileIdQuery, HashQuery,
    Wait, Continue, Timeout, Cancel, Native
};
struct ImageIdentity {
    ULONGLONG volume = 0;
    std::array<BYTE, 16> file_id{};
    std::array<BYTE, 32> sha256{};
    ULONGLONG size = 0;
};
struct LaunchRequest {
    // Caller retains this noninheritable, manifest-checked handle until safe retirement.
    HANDLE retained = nullptr;
    ImageIdentity expected;
    std::wstring application;
    std::wstring cwd;
    std::wstring system_root;
    Fault fault = Fault::None;
};
struct LaunchResult {
    Reason reason = Reason::None;
    DWORD error = 0;
    DWORD cleanup_error = 0;
    DWORD native_query_error = 0;
    DWORD stdout_peek_error = 0;
    DWORD stderr_peek_error = 0;
    DWORD exit_code = STILL_ACTIVE;
    DWORD pid = 0;
    DWORD event_count = 0;
    bool created = false;
    bool create_event = false;
    bool raw_hfile_present = false;
    bool raw_identity_ok = false;
    bool identity_match = false;
    bool no_marker_before = false;
    bool deferred_closed_pipe_observation = false;
    bool no_pipe_output_after_retirement = false;
    bool fault_applied = false;
    bool admitted = false;
    bool admission_continued = false;
    bool initial_breakpoint = false;
    bool termination_requested = false;
    bool exit_event = false;
    bool exit_continued = false;
    bool process_signaled = false;
    bool stdout_eof = false;
    bool stderr_eof = false;
    bool readers_joined = false;
    bool cleanup_allowed = false;
    ImageIdentity observed;
    std::string stdout_bytes;
    std::string stderr_bytes;
};
// Both errors are sticky. Failed closes are not retried or hidden.
bool close_owned(HANDLE& handle, DWORD& cleanup_error);
bool fingerprint(HANDLE handle, ImageIdentity& identity,
                 DWORD& error, DWORD& cleanup_error);
bool same_identity(const ImageIdentity& left, const ImageIdentity& right);
// On uncertain death/join, returns failure with ownership retained until harness exit.
LaunchResult run_launch(const LaunchRequest& request);
} // namespace broker_probe
