#include "launch.h"
#include <algorithm>
#include <cstring>
#include <cwchar>
#include <set>
#include <sstream>

using namespace broker_probe;
namespace {
struct Case {
    const char* id;
    unsigned kind;
    Fault fault;
    Reason expected_reason;
    std::wstring root;
    HANDLE retained = nullptr;
    ImageIdentity expected, alternate;
    LaunchResult result;
    DWORD setup_error = 0, cleanup_error = 0, mutation_error = 0, marker_error = 0;
    bool started = false, setup_ok = false, launch_called = false, mutation_attempted = false;
    bool mutation_first = false, mutation_second = false, mutation_denied = false;
    bool redirected = false, mutation_ok = true, marker_present = false;
    bool marker_valid = false, retired = false, passed = false;
};
void note_failure(DWORD& sticky, DWORD error) {
    if (!sticky) sticky = error ? error : ERROR_GEN_FAILURE;
}
std::string hex_bytes(const BYTE* bytes, size_t length) {
    static const char digits[] = "0123456789abcdef";
    std::string text;
    for (size_t i = 0; i < length; ++i) {
        text += digits[bytes[i] >> 4]; text += digits[bytes[i] & 15];
    }
    return text;
}
bool hash_matches(const ImageIdentity& image, const wchar_t* manifest) {
    if (wcslen(manifest) != 64) return false;
    const auto actual = hex_bytes(image.sha256.data(), image.sha256.size());
    for (size_t i = 0; i < actual.size(); ++i) {
        wchar_t ch = manifest[i];
        if (ch >= L'A' && ch <= L'F') ch += L'a' - L'A';
        if (ch != actual[i]) return false;
    }
    return true;
}
bool copy_image(const std::wstring& from, const std::wstring& to, DWORD& error) {
    if (CopyFileW(from.c_str(), to.c_str(), TRUE)) return true;
    note_failure(error, GetLastError()); return false;
}
bool prepare_case(Case& c, const std::wstring& run, const wchar_t* good,
                  const wchar_t* bad) {
    c.root = run + L"\\cases\\" + std::wstring(c.id, c.id + std::strlen(c.id));
    for (const auto suffix : {L"", L"\\image-a", L"\\image-b", L"\\cwd"}) {
        const auto path = c.root + suffix;
        if (c.kind != 4 && !CreateDirectoryW(path.c_str(), nullptr)) {
            note_failure(c.setup_error, GetLastError()); return false;
        }
        DWORD attr = GetFileAttributesW(path.c_str());
        if (attr == INVALID_FILE_ATTRIBUTES) {
            note_failure(c.setup_error, GetLastError()); return false;
        }
        if (!(attr & FILE_ATTRIBUTE_DIRECTORY) ||
            (attr & FILE_ATTRIBUTE_REPARSE_POINT)) {
            note_failure(c.setup_error, ERROR_INVALID_DATA); return false;
        }
    }
    const auto a = c.root + L"\\image-a\\image.exe";
    const auto b = c.root + L"\\image-b\\image.exe";
    if (!copy_image(run + L"\\trusted\\good.exe", a, c.setup_error) ||
        !copy_image(run + (c.kind == 2 ? L"\\trusted\\good.exe" : L"\\trusted\\bad.exe"),
                    b, c.setup_error)) return false;
    c.retained = CreateFileW(a.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                             OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (c.retained == INVALID_HANDLE_VALUE) {
        c.retained = nullptr; note_failure(c.setup_error, GetLastError()); return false;
    }
    DWORD flags = 0;
    if (!GetHandleInformation(c.retained, &flags)) {
        note_failure(c.setup_error, GetLastError()); return false;
    }
    if ((flags & HANDLE_FLAG_INHERIT) ||
        !fingerprint(c.retained, c.expected, c.setup_error, c.cleanup_error) ||
        !hash_matches(c.expected, good)) {
        note_failure(c.setup_error, ERROR_INVALID_DATA); return false;
    }
    HANDLE other = CreateFileW(b.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (other == INVALID_HANDLE_VALUE) {
        note_failure(c.setup_error, GetLastError()); return false;
    }
    bool valid = fingerprint(other, c.alternate, c.setup_error, c.cleanup_error) &&
        hash_matches(c.alternate, c.kind == 2 ? good : bad);
    close_owned(other, c.cleanup_error);
    valid = valid && (c.expected.volume != c.alternate.volume ||
                     c.expected.file_id != c.alternate.file_id);
    valid = valid && ((c.expected.sha256 == c.alternate.sha256) == (c.kind == 2));
    if (!valid) note_failure(c.setup_error, ERROR_INVALID_DATA);
    if (valid && c.kind == 4) {
        for (unsigned i = 0; i < 2; ++i) {
            const auto link = c.root + (i ? L"\\spare" : L"\\active");
            DWORD attr = GetFileAttributesW(link.c_str());
            if (attr == INVALID_FILE_ATTRIBUTES) {
                note_failure(c.setup_error, GetLastError()); return false;
            }
            if (!(attr & FILE_ATTRIBUTE_DIRECTORY) || !(attr & FILE_ATTRIBUTE_REPARSE_POINT)) {
                note_failure(c.setup_error, ERROR_INVALID_DATA); return false;
            }
            HANDLE image = CreateFileW((link + L"\\image.exe").c_str(), GENERIC_READ,
                FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (image == INVALID_HANDLE_VALUE) {
                note_failure(c.setup_error, GetLastError()); return false;
            }
            ImageIdentity target;
            valid = fingerprint(image, target, c.setup_error, c.cleanup_error) &&
                    same_identity(target, i ? c.alternate : c.expected);
            close_owned(image, c.cleanup_error);
            if (!valid) { note_failure(c.setup_error, ERROR_INVALID_DATA); return false; }
        }
    }
    return valid && !c.setup_error && !c.cleanup_error;
}
void mutate_case(Case& c) {
    const auto image = c.root + L"\\image-a\\image.exe";
    if (c.kind < 3 || c.kind > 7) return;
    c.mutation_attempted = true;
    if (c.kind == 3 || c.kind == 4) {
        const auto active = c.root + (c.kind == 3 ? L"\\image-a" : L"\\active");
        const auto spare = c.root + (c.kind == 3 ? L"\\image-b" : L"\\spare");
        c.mutation_first = MoveFileExW(active.c_str(), (c.root + L"\\displaced").c_str(), 0) != 0;
        if (!c.mutation_first) c.mutation_error = GetLastError();
        else {
            c.mutation_second = MoveFileExW(spare.c_str(), active.c_str(), 0) != 0;
            if (!c.mutation_second) c.mutation_error = GetLastError();
        }
        c.redirected = c.mutation_first && c.mutation_second;
        c.mutation_ok = c.redirected; // A blocked rename is not a redirected-image comparison.
    } else {
        if (c.kind == 5) {
            HANDLE writer = CreateFileW(image.c_str(), GENERIC_WRITE, FILE_SHARE_READ,
                nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            c.mutation_first = writer != INVALID_HANDLE_VALUE;
            if (!c.mutation_first) c.mutation_error = GetLastError();
            else close_owned(writer, c.cleanup_error); // Never write any bytes.
        } else if (c.kind == 6) {
            c.mutation_first = DeleteFileW(image.c_str()) != 0;
            if (!c.mutation_first) c.mutation_error = GetLastError();
        } else {
            c.mutation_first = MoveFileExW(image.c_str(),
                (c.root + L"\\image-a\\renamed.exe").c_str(), 0) != 0;
            if (!c.mutation_first) c.mutation_error = GetLastError();
        }
        c.mutation_denied = !c.mutation_first &&
            (c.mutation_error == ERROR_SHARING_VIOLATION || c.mutation_error == ERROR_ACCESS_DENIED);
        c.mutation_ok = c.mutation_denied;
    }
}
bool marker_absent(Case& c) {
    HANDLE file = CreateFileW((c.root + L"\\cwd\\marker.txt").c_str(), GENERIC_READ,
        FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        DWORD error = GetLastError();
        if (error != ERROR_FILE_NOT_FOUND) note_failure(c.marker_error, error);
        return error == ERROR_FILE_NOT_FOUND;
    }
    c.marker_present = true;
    char bytes[3] = {}; DWORD count = 0;
    if (!ReadFile(file, bytes, sizeof(bytes), &count, nullptr))
        note_failure(c.marker_error, GetLastError());
    c.marker_valid = count == 2 && bytes[0] == 'A' && bytes[1] == '\n';
    close_owned(file, c.cleanup_error); return false;
}
bool run_case(Case& c, const std::wstring& run, const wchar_t* good,
              const wchar_t* bad, const std::wstring& system_root) {
    c.started = true;
    c.setup_ok = prepare_case(c, run, good, bad);
    if (c.setup_ok) {
        mutate_case(c);
        LaunchRequest request;
        request.retained = c.retained; request.expected = c.expected;
        request.application = c.root + (c.kind == 1 || c.kind == 2 ?
            L"\\image-b\\image.exe" : c.kind == 4 ? L"\\active\\image.exe" : L"\\image-a\\image.exe");
        request.cwd = c.root + L"\\cwd"; request.system_root = system_root; request.fault = c.fault;
        if (c.kind == 8) request.expected.sha256[0] ^= 1;
        if (!c.cleanup_error) { c.launch_called = true; c.result = run_launch(request); }
    }
    const auto& r = c.result;
    // Artifacts remain on disk. Uncertain lifetime also keeps the pin until harness exit.
    if (c.cleanup_error || (c.launch_called && !r.cleanup_allowed)) return false;
    if (c.setup_ok) marker_absent(c);
    if (c.cleanup_error || !close_owned(c.retained, c.cleanup_error)) return false;
    c.retired = true;
    const bool post = c.fault == Fault::PostTimeout || c.fault == Fault::PostCancel;
    const bool admit = c.expected_reason == Reason::None || post;
    bool valid = c.setup_ok && c.launch_called && c.mutation_ok && !c.marker_error &&
        !c.cleanup_error && !r.cleanup_error && r.reason == c.expected_reason &&
        ((r.error == 0) == (c.expected_reason == Reason::None)) &&
        r.admitted == admit && r.admission_continued == admit && r.cleanup_allowed;
    if (c.kind == 8) {
        valid = valid && !r.created && !r.create_event && !r.pid && !r.fault_applied &&
            !c.marker_present && r.stdout_bytes.empty() && r.stderr_bytes.empty();
    } else {
        valid = valid && r.created && r.pid && r.create_event && r.raw_hfile_present &&
            r.raw_identity_ok && !r.native_query_error && r.no_marker_before &&
            r.exit_event && r.exit_continued && r.process_signaled &&
            r.stdout_eof && r.stderr_eof && r.readers_joined;
        valid = valid && (r.fault_applied == (c.fault != Fault::None));
        if (!admit) valid = valid && r.termination_requested && !c.marker_present &&
            r.stdout_bytes.empty() && r.stderr_bytes.empty();
        else if (post) valid = valid && r.termination_requested && r.initial_breakpoint &&
            c.marker_valid && r.stdout_bytes == "A\n" && r.stderr_bytes == "E\n";
        else valid = valid && r.initial_breakpoint && !r.termination_requested &&
            r.exit_code == 0 && c.marker_valid && r.stdout_bytes == "A\n" && r.stderr_bytes == "E\n";
        if (c.kind >= 1 && c.kind <= 4) valid = valid &&
            !same_identity(c.expected, r.observed) && same_identity(c.alternate, r.observed) &&
            !r.identity_match;
        else valid = valid && same_identity(c.expected, r.observed) && r.identity_match;
    }
    c.passed = valid; return true;
}
bool write_result(HANDLE output, const Case& c, DWORD& error) {
    const auto& r = c.result;
    std::ostringstream o;
    o << std::boolalpha << "{\"id\":\"" << c.id << "\",\"expected_reason\":" << unsigned(c.expected_reason)
      << ",\"observed_reason\":" << unsigned(r.reason) << ",\"fault\":" << unsigned(c.fault)
      << ",\"passed\":" << c.passed << ",\"status\":\"" << (!c.started ? "not_run" :
          !c.setup_ok ? "setup_failed" : !c.retired ? "unknown_retained" : c.passed ? "passed" : "failed")
      << "\",\"launch_called\":" << c.launch_called << ",\"setup_ok\":" << c.setup_ok
      << ",\"setup_error\":" << c.setup_error << ",\"cleanup_error\":" << c.cleanup_error
      << ",\"marker_error\":" << c.marker_error << ",\"launch_error\":" << r.error
      << ",\"launch_cleanup_error\":" << r.cleanup_error << ",\"native_query_error\":" << r.native_query_error
      << ",\"mutation_attempted\":" << c.mutation_attempted << ",\"mutation_first\":" << c.mutation_first
      << ",\"mutation_second\":" << c.mutation_second << ",\"mutation_error\":" << c.mutation_error
      << ",\"mutation_denied\":" << c.mutation_denied << ",\"redirected\":" << c.redirected
      << ",\"redirect_blocked\":" << ((c.kind == 3 || c.kind == 4) && c.mutation_attempted && !c.mutation_first)
      << ",\"marker_present\":" << c.marker_present << ",\"marker_valid\":" << c.marker_valid;
    o << ",\"created\":" << r.created << ",\"pid\":" << r.pid << ",\"create_event\":" << r.create_event
      << ",\"raw_hfile_present\":" << r.raw_hfile_present << ",\"raw_identity_ok\":" << r.raw_identity_ok
      << ",\"identity_match\":" << r.identity_match << ",\"no_marker_before\":" << r.no_marker_before
      << ",\"fault_applied\":" << r.fault_applied << ",\"admitted\":" << r.admitted
      << ",\"admission_continued\":" << r.admission_continued << ",\"initial_breakpoint\":" << r.initial_breakpoint
      << ",\"termination_requested\":" << r.termination_requested << ",\"exit_event\":" << r.exit_event
      << ",\"exit_continued\":" << r.exit_continued << ",\"process_signaled\":" << r.process_signaled
      << ",\"stdout_eof\":" << r.stdout_eof << ",\"stderr_eof\":" << r.stderr_eof
      << ",\"readers_joined\":" << r.readers_joined << ",\"cleanup_allowed\":" << r.cleanup_allowed
      << ",\"retained_handle_retired\":" << c.retired << ",\"exit_code\":" << r.exit_code
      << ",\"event_count\":" << r.event_count << ",\"stdout_bytes\":" << r.stdout_bytes.size()
      << ",\"stderr_bytes\":" << r.stderr_bytes.size() << ",\"stdout_prefix_hex\":\""
      << hex_bytes(reinterpret_cast<const BYTE*>(r.stdout_bytes.data()), (std::min)(size_t(16), r.stdout_bytes.size()))
      << "\",\"stderr_prefix_hex\":\""
      << hex_bytes(reinterpret_cast<const BYTE*>(r.stderr_bytes.data()), (std::min)(size_t(16), r.stderr_bytes.size())) << '"';
    const ImageIdentity* identities[] = {&c.expected, &c.alternate, &r.observed};
    const char* names[] = {"retained", "alternate", "observed"};
    for (unsigned i = 0; i < 3; ++i) {
        const auto& value = *identities[i];
        o << ",\"" << names[i] << "\":{\"volume\":" << value.volume << ",\"file_id\":\""
          << hex_bytes(value.file_id.data(), value.file_id.size()) << "\",\"sha256\":\""
          << hex_bytes(value.sha256.data(), value.sha256.size()) << "\",\"size\":" << value.size << '}';
    }
    o << "}\n"; const auto line = o.str(); DWORD count = 0;
    if (line.size() > 8192) { note_failure(error, ERROR_BUFFER_OVERFLOW); return false; }
    if (!WriteFile(output, line.data(), DWORD(line.size()), &count, nullptr)) {
        note_failure(error, GetLastError()); return false;
    }
    if (count != line.size()) { note_failure(error, ERROR_WRITE_FAULT); return false; }
    if (!FlushFileBuffers(output)) { note_failure(error, GetLastError()); return false; }
    return true;
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 4) return 2;
    const std::wstring root = argv[1]; wchar_t full[MAX_PATH] = {}, system[MAX_PATH] = {};
    DWORD length = GetFullPathNameW(root.c_str(), MAX_PATH, full, nullptr);
    if (root.size() < 3 || root.size() > 160 || root[1] != L':' || root[2] != L'\\' ||
        !length || length >= MAX_PATH || root != full || root.back() == L'\\') return 2;
    length = GetWindowsDirectoryW(system, MAX_PATH);
    if (!length || length >= MAX_PATH) return 2;
    for (const auto suffix : {L"", L"\\trusted", L"\\cases", L"\\evidence"}) {
        DWORD attr = GetFileAttributesW((root + suffix).c_str());
        if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY) ||
            (attr & FILE_ATTRIBUTE_REPARSE_POINT)) return 2;
    }
    Case cases[] = {
        {"native_correct_image", 0, Fault::None, Reason::None},
        {"native_different_image", 1, Fault::None, Reason::Identity},
        {"native_identical_bytes_new_id", 2, Fault::None, Reason::Identity},
        {"native_ancestor_redirect", 3, Fault::None, Reason::Identity},
        {"native_junction_redirect", 4, Fault::None, Reason::Identity},
        {"native_pin_write_denied", 5, Fault::None, Reason::None},
        {"native_pin_delete_denied", 6, Fault::None, Reason::None},
        {"native_pin_rename_denied", 7, Fault::None, Reason::None},
        {"manifest_rejected", 8, Fault::None, Reason::Manifest},
        {"fault_null_image_decision", 9, Fault::NullImage, Reason::NullImage},
        {"fault_file_id_query", 9, Fault::FileIdQuery, Reason::FileIdQuery},
        {"fault_hash_query", 9, Fault::HashQuery, Reason::HashQuery},
        {"fault_debug_wait", 9, Fault::Wait, Reason::Wait},
        {"fault_debug_continue", 9, Fault::Continue, Reason::Continue},
        {"fault_preadmission_timeout", 9, Fault::PreTimeout, Reason::Timeout},
        {"fault_preadmission_cancel", 9, Fault::PreCancel, Reason::Cancel},
        {"fault_postadmission_timeout", 9, Fault::PostTimeout, Reason::Timeout},
        {"fault_postadmission_cancel", 9, Fault::PostCancel, Reason::Cancel}
    };
    static_assert(sizeof(cases) / sizeof(cases[0]) == 18, "Required case count changed");
    std::set<std::string> seen;
    for (const auto& c : cases) if (!c.id || !*c.id || !seen.insert(c.id).second) return 2;
    HANDLE output = CreateFileW((root + L"\\evidence\\results.jsonl").c_str(), GENERIC_WRITE,
        FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (output == INVALID_HANDLE_VALUE) return 2;
    DWORD evidence_error = 0; unsigned executed = 0, passed = 0, rows = 0;
    bool continue_cases = true;
    for (auto& c : cases) {
        if (continue_cases) {
            continue_cases = run_case(c, root, argv[2], argv[3], system);
            ++executed; if (c.passed) ++passed;
        }
        if (!write_result(output, c, evidence_error)) break;
        ++rows;
    }
    close_owned(output, evidence_error);
    bool all = rows == 18 && executed == 18 && passed == 18 && seen.size() == 18 && !evidence_error;
    HANDLE summary = CreateFileW((root + L"\\evidence\\summary.json").c_str(), GENERIC_WRITE,
        FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (summary == INVALID_HANDLE_VALUE) return 1;
    const auto text = std::string("{\"schema\":1,\"required_count\":18,\"executed_count\":") + std::to_string(executed) +
        ",\"passed_count\":" + std::to_string(passed) + ",\"passed\":" + (all ? "true" : "false") +
        ",\"fixtures_retained\":true,\"evidence_error\":" + std::to_string(evidence_error) + "}\n";
    DWORD count = 0;
    if (!WriteFile(summary, text.data(), DWORD(text.size()), &count, nullptr))
        note_failure(evidence_error, GetLastError());
    else if (count != text.size()) note_failure(evidence_error, ERROR_WRITE_FAULT);
    if (!FlushFileBuffers(summary)) note_failure(evidence_error, GetLastError());
    close_owned(summary, evidence_error);
    return all && !evidence_error ? 0 : 1;
}
