/// GMaps Scraper Launcher — pure C, zero CRT dependency.
/// Always starts (kernel32 + user32 + shell32 only), checks VC++,
/// launches the real Flutter app or shows a friendly download dialog.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

// ── No-CRT helpers ───────────────────────────────────────────────

// Compiler replaces loops with memset — stub it out
__declspec(noinline) static void _memset_stub(void *d, int c, size_t n) {
    BYTE *b = (BYTE*)d;
    while (n--) *b++ = (BYTE)c;
}

#pragma function(memset)
void * __cdecl memset(void *d, int c, size_t n) {
    _memset_stub(d, c, n);
    return d;
}

// ── VC++ check ──────────────────────────────────────────────────

static int IsVCRedistAvailable(void) {
    HMODULE h = LoadLibraryW(L"vcruntime140.dll");
    if (h) { FreeLibrary(h); return 1; }
    return 0;
}

static void ShowMissingVCRedistDialog(void) {
    MessageBoxW(
        NULL,
        L"Visual C++ Redistributable tidak ditemukan.\n\n"
        L"Aplikasi ini membutuhkan Microsoft Visual C++ Redistributable.\n"
        L"Silakan download dan install dari link yang akan terbuka di browser.\n\n"
        L"Setelah install, jalankan ulang aplikasi ini.",
        L"GMaps Scraper — Missing Dependency",
        MB_OK | MB_ICONWARNING);
    ShellExecuteW(NULL, L"open",
                  L"https://aka.ms/vs/17/release/vc_redist.x64.exe",
                  NULL, NULL, SW_SHOW);
}

// ── Launch real app ──────────────────────────────────────────────

static int LaunchRealApp(LPWSTR exeDir) {
    WCHAR path[MAX_PATH];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    BYTE *bp;
    DWORD n;

    lstrcpyW(path, exeDir);
    lstrcatW(path, L"\\gmaps_app.exe");

    // Zero out structs manually (no CRT memset)
    for (bp = (BYTE*)&si, n = 0; n < sizeof(si); n++) bp[n] = 0;
    for (bp = (BYTE*)&pi, n = 0; n < sizeof(pi); n++) bp[n] = 0;

    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_SHOW;

    if (!CreateProcessW(path, GetCommandLineW(), NULL, NULL,
                        FALSE, 0, NULL, exeDir, &si, &pi)) {
        return 0;
    }
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 1;
}

// ── Entry point ──────────────────────────────────────────────────

int WINAPI wWinMainCRTStartup(void) {
    WCHAR exePath[MAX_PATH];
    LPWSTR lastSlash;
    LPWSTR p;

    // Get directory of this launcher
    GetModuleFileNameW(NULL, exePath, MAX_PATH);
    lastSlash = exePath;
    for (p = exePath; *p; p++) {
        if (*p == L'\\' || *p == L'/') lastSlash = p;
    }
    *lastSlash = L'\0';

    // Check VC++
    if (!IsVCRedistAvailable()) {
        ShowMissingVCRedistDialog();
        return 1;
    }

    // Launch real app
    if (!LaunchRealApp(exePath)) {
        MessageBoxW(NULL,
                    L"Gagal menjalankan gmaps_app.exe.\n"
                    L"Pastikan file tersebut ada di folder yang sama.",
                    L"GMaps Scraper — Launch Error",
                    MB_OK | MB_ICONERROR);
        return 1;
    }

    return 0;
}

// Dummy WinMain for /SUBSYSTEM:WINDOWS linker happiness
int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR lpCmd, int nShow) {
    (void)hInst; (void)hPrev; (void)lpCmd; (void)nShow;
    return wWinMainCRTStartup();
}
