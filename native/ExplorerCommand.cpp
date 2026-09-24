#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shobjidl.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <wrl/client.h>
#include <string>
#include <vector>
#include <new>
#include "ShellStrings.h"

using Microsoft::WRL::ComPtr;
static HMODULE moduleHandle;
static LONG objects = 0, serverLocks = 0;
static const CLSID commandIds[] = {
    {0x71bc7f3a,0x9d38,0x4ad1,{0xb7,0x6c,0x9b,0x3e,0x1e,0xa4,0x50,0x01}},
    {0x71bc7f3a,0x9d38,0x4ad1,{0xb7,0x6c,0x9b,0x3e,0x1e,0xa4,0x50,0x02}},
    {0x71bc7f3a,0x9d38,0x4ad1,{0xb7,0x6c,0x9b,0x3e,0x1e,0xa4,0x50,0x03}}
};
static const wchar_t* actions[] = {L"merge", L"convert", L"summary"};

static HRESULT appPath(std::wstring& value) {
    wchar_t path[32768];
    DWORD length = GetModuleFileNameW(moduleHandle, path, ARRAYSIZE(path));
    if (!length || length >= ARRAYSIZE(path)) return HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER);
    value.assign(path, length);
    auto separator = value.find_last_of(L"\\/");
    if (separator == std::wstring::npos) return E_UNEXPECTED;
    value.resize(separator + 1);
    value += L"EoingPDF.exe";
    return S_OK;
}

static HRESULT selection(IShellItemArray* items, std::vector<std::wstring>& paths, bool verifyFiles) {
    if (!items) return E_INVALIDARG;
    DWORD count = 0;
    HRESULT hr = items->GetCount(&count);
    if (FAILED(hr)) return hr;
    if (!count || count > 1000) return E_INVALIDARG;
    static const wchar_t* extensions[] = {L".pdf",L".jpg",L".jpeg",L".png",L".webp",L".bmp",L".tif",L".tiff",
        L".doc",L".docx",L".rtf",L".xls",L".xlsx",L".xlsm",L".ppt",L".pptx",L".pptm",L".hwp",L".hwpx",L".txt",L".csv",L".md"};
    for (DWORD index = 0; index < count; ++index) {
        ComPtr<IShellItem> item;
        hr = items->GetItemAt(index, &item);
        if (FAILED(hr)) return hr;
        SFGAOF kind = 0;
        hr = item->GetAttributes(SFGAO_FOLDER | SFGAO_FILESYSTEM, &kind);
        if (FAILED(hr)) return hr;
        if (!(kind & SFGAO_FILESYSTEM) || (kind & SFGAO_FOLDER)) return E_INVALIDARG;
        PWSTR name = nullptr;
        hr = item->GetDisplayName(SIGDN_FILESYSPATH, &name);
        if (FAILED(hr)) return hr;
        if (!name) return E_UNEXPECTED;
        std::wstring path;
        try { path = name; } catch (...) { CoTaskMemFree(name); throw; }
        CoTaskMemFree(name);
        if (path.empty() || path.find_first_of(L"\r\n") != std::wstring::npos || PathIsRelativeW(path.c_str())) return E_INVALIDARG;
        bool supported = false;
        for (const auto extension : extensions) {
            if (!_wcsicmp(PathFindExtensionW(path.c_str()), extension)) { supported = true; break; }
        }
        if (!supported) return E_INVALIDARG;
        if (verifyFiles) {
            DWORD attributes = GetFileAttributesW(path.c_str());
            if (attributes == INVALID_FILE_ATTRIBUTES) return HRESULT_FROM_WIN32(GetLastError());
            if (attributes & FILE_ATTRIBUTE_DIRECTORY) return E_INVALIDARG;
        }
        paths.push_back(std::move(path));
    }
    return S_OK;
}

static HRESULT launch(const std::vector<std::wstring>& paths, int action) {
    std::wstring executable;
    HRESULT hr = appPath(executable);
    if (FAILED(hr)) return hr;
    DWORD attributes = GetFileAttributesW(executable.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY)) return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
    PWSTR local = nullptr;
    hr = SHGetKnownFolderPath(FOLDERID_LocalAppData, KF_FLAG_DEFAULT, nullptr, &local);
    if (FAILED(hr)) return hr;
    std::wstring directory;
    try { directory = std::wstring(local) + L"\\EoingPDF\\queue"; }
    catch (...) { CoTaskMemFree(local); throw; }
    CoTaskMemFree(local);
    int error = SHCreateDirectoryExW(nullptr, directory.c_str(), nullptr);
    if (error != ERROR_SUCCESS && error != ERROR_ALREADY_EXISTS && error != ERROR_FILE_EXISTS) return HRESULT_FROM_WIN32(error);
    GUID id;
    hr = CoCreateGuid(&id);
    if (FAILED(hr)) return hr;
    wchar_t identifier[40];
    if (!StringFromGUID2(id, identifier, ARRAYSIZE(identifier))) return E_UNEXPECTED;
    std::wstring manifest = directory + L"\\" + identifier + L".files";
    std::wstring text;
    for (const auto& path : paths) { text += path; text += L'\n'; }
    if (text.size() > 2 * 1024 * 1024) return HRESULT_FROM_WIN32(ERROR_FILE_TOO_LARGE);
    int bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    if (!bytes || bytes > 2 * 1024 * 1024) return HRESULT_FROM_WIN32(ERROR_FILE_TOO_LARGE);
    std::string utf8(bytes, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), utf8.data(), bytes, nullptr, nullptr)) return HRESULT_FROM_WIN32(GetLastError());
    // Construct all allocating objects before creating the queue file.
    std::wstring command = L"\"" + executable + L"\" --quick " + actions[action] + L" --manifest \"" + manifest + L"\"";
    HANDLE file = CreateFileW(manifest.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return HRESULT_FROM_WIN32(GetLastError());
    DWORD written = 0;
    BOOL saved = WriteFile(file, utf8.data(), bytes, &written, nullptr);
    DWORD writeError = saved ? ERROR_WRITE_FAULT : GetLastError();
    CloseHandle(file);
    if (!saved || written != static_cast<DWORD>(bytes)) {
        DeleteFileW(manifest.c_str());
        return HRESULT_FROM_WIN32(writeError);
    }
    STARTUPINFOW startup = {sizeof(startup)};
    startup.dwFlags = STARTF_USESHOWWINDOW;
    startup.wShowWindow = SW_SHOWNORMAL;
    PROCESS_INFORMATION process = {};
    if (!CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
                        nullptr, nullptr, &startup, &process)) {
        DWORD lastError = GetLastError();
        DeleteFileW(manifest.c_str());
        return HRESULT_FROM_WIN32(lastError);
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return S_OK;
}

class Command final : public IExplorerCommand {
    LONG references = 1;
    int action;
public:
    explicit Command(int value) : action(value) { InterlockedIncrement(&objects); }
    ~Command() { InterlockedDecrement(&objects); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** result) override {
        if (!result) return E_POINTER;
        *result = nullptr;
        if (iid == IID_IUnknown || iid == __uuidof(IExplorerCommand)) *result = static_cast<IExplorerCommand*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&references); }
    ULONG STDMETHODCALLTYPE Release() override { ULONG count = InterlockedDecrement(&references); if (!count) delete this; return count; }
    HRESULT STDMETHODCALLTYPE GetTitle(IShellItemArray*, PWSTR* title) override {
        if (!title) return E_POINTER;
        WORD language = PRIMARYLANGID(GetUserDefaultUILanguage());
        int locale = language == LANG_JAPANESE ? 2 : language == LANG_ENGLISH ? 1 : 0;
        return SHStrDupW(shellTitles[locale][action], title);
    }
    HRESULT STDMETHODCALLTYPE GetIcon(IShellItemArray*, PWSTR* icon) override {
        if (!icon) return E_POINTER;
        *icon = nullptr;
        try { std::wstring path; HRESULT hr = appPath(path); if (FAILED(hr)) return hr; return SHStrDupW((L"\"" + path + L"\",0").c_str(), icon); }
        catch (...) { return E_OUTOFMEMORY; }
    }
    HRESULT STDMETHODCALLTYPE GetToolTip(IShellItemArray*, PWSTR* tooltip) override { if (!tooltip) return E_POINTER; *tooltip = nullptr; return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetCanonicalName(GUID* name) override { if (!name) return E_POINTER; *name = commandIds[action]; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetState(IShellItemArray* items, BOOL slow, EXPCMDSTATE* state) override {
        if (!state) return E_POINTER;
        *state = ECS_HIDDEN;
        if (!items) return S_OK;
        DWORD count = 0;
        HRESULT hr = items->GetCount(&count);
        if (FAILED(hr)) return hr;
        if (!count || count > 1000) return S_OK;
        if (!slow) return E_PENDING;
        try { std::vector<std::wstring> paths; if (SUCCEEDED(selection(items, paths, false))) *state = ECS_ENABLED; return S_OK; }
        catch (...) { return E_OUTOFMEMORY; }
    }
    HRESULT STDMETHODCALLTYPE Invoke(IShellItemArray* items, IBindCtx*) override {
        try { std::vector<std::wstring> paths; HRESULT hr = selection(items, paths, true); return FAILED(hr) ? hr : launch(paths, action); }
        catch (const std::bad_alloc&) { return E_OUTOFMEMORY; }
        catch (...) { return E_FAIL; }
    }
    HRESULT STDMETHODCALLTYPE GetFlags(EXPCMDFLAGS* flags) override { if (!flags) return E_POINTER; *flags = ECF_DEFAULT; return S_OK; }
    HRESULT STDMETHODCALLTYPE EnumSubCommands(IEnumExplorerCommand** commands) override { if (!commands) return E_POINTER; *commands = nullptr; return E_NOTIMPL; }
};

class Factory final : public IClassFactory {
    LONG references = 1;
    int action;
public:
    explicit Factory(int value) : action(value) { InterlockedIncrement(&objects); }
    ~Factory() { InterlockedDecrement(&objects); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** result) override {
        if (!result) return E_POINTER;
        *result = nullptr;
        if (iid == IID_IUnknown || iid == IID_IClassFactory) *result = static_cast<IClassFactory*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&references); }
    ULONG STDMETHODCALLTYPE Release() override { ULONG count = InterlockedDecrement(&references); if (!count) delete this; return count; }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID iid, void** result) override {
        if (!result) return E_POINTER;
        *result = nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;
        auto value = new(std::nothrow) Command(action);
        if (!value) return E_OUTOFMEMORY;
        HRESULT hr = value->QueryInterface(iid, result);
        value->Release(); return hr;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override { if (lock) InterlockedIncrement(&serverLocks); else InterlockedDecrement(&serverLocks); return S_OK; }
};

STDAPI DllGetClassObject(REFCLSID clsid, REFIID iid, void** result) {
    if (!result) return E_POINTER;
    *result = nullptr;
    for (int index = 0; index < 3; ++index) {
        if (clsid == commandIds[index]) {
            auto factory = new(std::nothrow) Factory(index);
            if (!factory) return E_OUTOFMEMORY;
            HRESULT hr = factory->QueryInterface(iid, result);
            factory->Release(); return hr;
        }
    }
    return CLASS_E_CLASSNOTAVAILABLE;
}
STDAPI DllCanUnloadNow() {
    return !objects && !serverLocks ? S_OK : S_FALSE;
}
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) moduleHandle = instance;
    return TRUE;
}
