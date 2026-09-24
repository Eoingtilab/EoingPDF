#define UNICODE
#define _UNICODE
#include <windows.h>
#include <string>
#include <fstream>
#include <sstream>

static HMODULE moduleHandle;
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) moduleHandle = instance;
    return TRUE;
}

// Hancom's documented callback. Allow only this job's exact input/output paths.
extern "C" __declspec(dllexport) BOOL __stdcall IsAccessiblePath(HWND, LONG, LPCWSTR file, LPCWSTR) {
    if (!file || !*file) return FALSE;
    wchar_t modulePath[32768], fullPath[32768];
    DWORD moduleLength = GetModuleFileNameW(moduleHandle, modulePath, 32768);
    DWORD pathLength = GetFullPathNameW(file, 32768, fullPath, NULL);
    if (!moduleLength || moduleLength >= 32768 || !pathLength || pathLength >= 32768) return FALSE;
    std::wstring config(modulePath);
    config = config.substr(0, config.find_last_of(L"\\/")) + L"\\allowed.txt";
    HANDLE stream = CreateFileW(config.c_str(), GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (stream == INVALID_HANDLE_VALUE) return FALSE;
    DWORD size = GetFileSize(stream, NULL);
    if (!size || size > 131072 || size % 2) { CloseHandle(stream); return FALSE; }
    std::wstring content(size / 2, L'\0');
    DWORD read;
    BOOL success = ReadFile(stream, &content[0], size, &read, NULL);
    CloseHandle(stream);
    if (!success || read != size) return FALSE;
    std::wistringstream lines(content);
    std::wstring line;
    while (std::getline(lines, line)) {
        if (!line.empty() && line.back() == L'\r') line.pop_back();
        if (_wcsicmp(line.c_str(), fullPath) == 0) return TRUE;
    }
    return FALSE;
}
