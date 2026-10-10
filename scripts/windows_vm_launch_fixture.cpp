#include <windows.h>

#ifndef MARKER_BYTE
#error MARKER_BYTE must select a known self-built fixture
#endif
static_assert(MARKER_BYTE == 65 || MARKER_BYTE == 66, "Only known A/B fixtures");

// No CRT, dynamic input, descendants, or work beyond this owned marker and bounded hold.
extern "C" void marker_entry() {
    const char marker[2] = {MARKER_BYTE, '\n'};
    const char diagnostic[2] = {'E', '\n'};
    DWORD written = 0, failure = 0;
    HANDLE file = CreateFileW(L"marker.txt", GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) failure = 1;
    else {
        if (!WriteFile(file, marker, sizeof(marker), &written, nullptr) || written != sizeof(marker)) failure = 2;
        if (!CloseHandle(file) && !failure) failure = 3;
    }
    written = 0;
    if (!WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), marker, sizeof(marker), &written, nullptr) ||
        written != sizeof(marker)) { if (!failure) failure = 4; }
    written = 0;
    if (!WriteFile(GetStdHandle(STD_ERROR_HANDLE), diagnostic, sizeof(diagnostic), &written, nullptr) ||
        written != sizeof(diagnostic)) { if (!failure) failure = 5; }
    wchar_t hold[2] = {};
    if (GetEnvironmentVariableW(L"DOT_HOLD", hold, 2) == 1 && hold[0] == L'1') Sleep(20000);
    ExitProcess(failure);
}
