// Stage 1: purely visual in-process page. Does not load/call PrintExp printer APIs.
// The DLL is loaded only by a targeted WH_GETMESSAGE hook for an exact, SHA-pinned build.
#define WIN32_LEAN_AND_MEAN
#if !defined(_WIN64)
#error "PrintExp 3D Stage 1 must be compiled for Windows x64."
#endif
#include <windows.h>
#include <commctrl.h>
#include <string>
#include <vector>

#pragma comment(lib, "User32.lib")
#pragma comment(lib, "Gdi32.lib")
#pragma comment(lib, "Comctl32.lib")

static HINSTANCE g_module = nullptr;
static HWND g_host = nullptr;
static HWND g_tab = nullptr;
static HWND g_page = nullptr;
static bool g_active = false;
static int g_tabTop = 54;
static int g_contentTop = 111;
static constexpr UINT_PTR kSubclassId = 0x3D2026;
static const wchar_t* kTabClass = L"UV3D_PrintExp_Tab_Stage1";
static const wchar_t* kPageClass = L"UV3D_PrintExp_Page_Stage1";

// Log to the installed add-on (not to the user profile of the elevated account).
static std::wstring AddonRoot() {
    wchar_t name[MAX_PATH] = {};
    if (!GetModuleFileNameW(g_module, name, MAX_PATH)) return L"";
    std::wstring dir(name);
    for (int i = 0; i < 3; ++i) { // module filename, windows, dist
        size_t slash = dir.find_last_of(L"\\/");
        if (slash == std::wstring::npos) return L"";
        dir.erase(slash);
    }
    return dir;
}

static void StageLog(const std::wstring& message) {
    std::wstring root = AddonRoot();
    if (root.empty()) return;
    std::wstring folder = root + L"\\diagnostics";
    CreateDirectoryW(folder.c_str(), nullptr);
    const std::wstring file = folder + L"\\stage1.log";
    HANDLE handle = CreateFileW(file.c_str(), FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) return;
    SYSTEMTIME now = {};
    GetLocalTime(&now);
    wchar_t stamp[80] = {};
    swprintf_s(stamp, L"[%04u-%02u-%02u %02u:%02u:%02u] PID=%lu ",
        now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute,
        now.wSecond, GetCurrentProcessId());
    std::wstring line = std::wstring(stamp) + message + L"\r\n";
    const int count = WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1,
        nullptr, 0, nullptr, nullptr);
    if (count > 1) {
        std::vector<char> encoded(static_cast<size_t>(count));
        WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1,
            encoded.data(), count, nullptr, nullptr);
        DWORD written = 0;
        WriteFile(handle, encoded.data(), static_cast<DWORD>(count - 1), &written, nullptr);
    }
    CloseHandle(handle);
}

static std::wstring ConfigFile() {
    const std::wstring root = AddonRoot();
    if (root.empty()) return L"";
    const std::wstring local = root + L"\\config\\local-stage1.ini";
    if (GetFileAttributesW(local.c_str()) != INVALID_FILE_ATTRIBUTES) return local;
    return root + L"\\config\\stage1.ini";
}

static void RectPaint(HDC dc, RECT r, COLORREF fill) {
    HBRUSH b = CreateSolidBrush(fill);
    FillRect(dc, &r, b);
    DeleteObject(b);
}

static void Position();

static LRESULT CALLBACK TabProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch(msg) {
        case WM_SETCURSOR: SetCursor(LoadCursorW(nullptr, IDC_HAND)); return TRUE;
        case WM_LBUTTONUP:
            if (g_page) {
                g_active = !g_active;
                StageLog(g_active ? L"3D tab clicked: showing page" : L"3D tab clicked: hiding page");
                ShowWindow(g_page, g_active ? SW_SHOWNOACTIVATE : SW_HIDE);
                Position();
                InvalidateRect(hwnd, nullptr, TRUE);
            }
            return 0;
        case WM_PAINT: {
            PAINTSTRUCT ps = {};
            HDC dc = BeginPaint(hwnd, &ps);
            RECT r = {};
            GetClientRect(hwnd, &r);
            RectPaint(dc, r, g_active ? RGB(42,125,165) : RGB(46,56,69));
            SetBkMode(dc, TRANSPARENT);
            SetTextColor(dc, RGB(255,255,255));
            HFONT font = CreateFontW(-17,0,0,0,FW_SEMIBOLD,FALSE,FALSE,FALSE,
                                    DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
            HGDIOBJ old = SelectObject(dc, font);
            DrawTextW(dc,L"3D",-1,&r,DT_CENTER|DT_VCENTER|DT_SINGLELINE);
            SelectObject(dc,old);
            DeleteObject(font);
            EndPaint(hwnd,&ps);
            return 0;
        }
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}

static LRESULT CALLBACK PageProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps = {};
        HDC dc = BeginPaint(hwnd, &ps);
        RECT r = {}; GetClientRect(hwnd, &r);
        RectPaint(dc,r,RGB(23,32,43));
        RECT title = {32,32,r.right-16,85};
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc,RGB(246,249,252));
        HFONT big = CreateFontW(-29,0,0,0,FW_SEMIBOLD,FALSE,FALSE,FALSE,
                                DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        HGDIOBJ old = SelectObject(dc,big);
        DrawTextW(dc,L"PrintExp 3D",-1,&title,DT_LEFT|DT_VCENTER|DT_SINGLELINE);
        SelectObject(dc,old); DeleteObject(big);
        HFONT regular = CreateFontW(-18,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
                                    DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        old = SelectObject(dc,regular);
        RECT note1 = {32,100,r.right-24,165};
        RECT note2 = {32,168,r.right-24,245};
        RECT note3 = {32,260,r.right-24,330};
        SetTextColor(dc,RGB(181,205,220));
        DrawTextW(dc,L"Stage 1 — native in-process page integration test.",-1,
                  &note1,DT_LEFT|DT_WORDBREAK);
        DrawTextW(dc,L"Printing, motors, UV lamps and RIP controls are DISABLED in this test.\n"
                     L"This view uses no Hoson DLL functions.",-1,
                  &note2,DT_LEFT|DT_WORDBREAK);
        SetTextColor(dc,RGB(138,213,237));
        DrawTextW(dc,L"Click the 3D tab again to return to the original PrintExp page.",-1,
                  &note3,DT_LEFT|DT_WORDBREAK);
        SelectObject(dc,old);DeleteObject(regular);
        EndPaint(hwnd,&ps);
        return 0;
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}

static void Position() {
    if (!g_host || !IsWindow(g_host)) return;
    if (!g_tab || !IsWindow(g_tab) || !g_page || !IsWindow(g_page)) return;
    // Owned popup windows are in the SAME PrintExp process, remain attached
    // to its main window and cannot be clipped/covered by its MFC child panes.
    // This is a Stage 1 UI feasibility overlay, not native MFC page registration.
    if (IsIconic(g_host) || !IsWindowVisible(g_host)) {
        ShowWindow(g_page, SW_HIDE);
        ShowWindow(g_tab, SW_HIDE);
        return;
    }
    RECT rect = {};
    GetClientRect(g_host, &rect);
    POINT origin = {0, 0};
    ClientToScreen(g_host, &origin);
    const int width = rect.right - rect.left;
    const int height = rect.bottom - rect.top;
    if (!IsWindowVisible(g_tab)) ShowWindow(g_tab, SW_SHOWNOACTIVATE);
    SetWindowPos(g_page, HWND_TOP, origin.x, origin.y + g_contentTop,
        width > 0 ? width : 1,
        height > g_contentTop ? height - g_contentTop : 1,
        SWP_NOACTIVATE | SWP_NOOWNERZORDER);
    if (g_active) ShowWindow(g_page, SW_SHOWNOACTIVATE);
    SetWindowPos(g_tab, HWND_TOP, origin.x + (width > 126 ? width-126 : 0),
        origin.y + g_tabTop, 108, 38, SWP_NOACTIVATE | SWP_NOOWNERZORDER);
}

static LRESULT CALLBACK HostSubclass(HWND hwnd, UINT message, WPARAM wp, LPARAM lp,
                                     UINT_PTR id, DWORD_PTR ref) {
    if (message == WM_NCDESTROY) {
        StageLog(L"Host main window closed; removing UI overlay");
        if (g_page && IsWindow(g_page)) DestroyWindow(g_page);
        if (g_tab && IsWindow(g_tab)) DestroyWindow(g_tab);
        RemoveWindowSubclass(hwnd, HostSubclass, id);
        g_host = nullptr; g_tab = nullptr; g_page = nullptr; g_active = false;
        return DefSubclassProc(hwnd, message, wp, lp);
    }
    LRESULT value = DefSubclassProc(hwnd, message, wp, lp);
    if (message == WM_SIZE || message == WM_MOVE ||
        message == WM_WINDOWPOSCHANGED || message == WM_SHOWWINDOW) {
        Position();
    }
    return value;
}

static bool Create3DPage(HWND host) {
    if (!IsWindow(host) || GetAncestor(host, GA_ROOT) != host) return false;
    DWORD pid = 0;
    DWORD thread = GetWindowThreadProcessId(host, &pid);
    if (pid != GetCurrentProcessId() || thread != GetCurrentThreadId()) return false;
    // No search for the first visible window! The launcher posts WM_NULL to
    // the chosen main window, and the hook receives that EXACT HWND.
    HMODULE pin = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                            reinterpret_cast<LPCWSTR>(&Create3DPage), &pin)) {
        StageLog(L"FAILED: GetModuleHandleEx PIN");
        return false;
    }
    const std::wstring ini = ConfigFile();
    if (!ini.empty()) {
        g_tabTop = GetPrivateProfileIntW(L"Stage1", L"tab_y", 54, ini.c_str());
        g_contentTop = GetPrivateProfileIntW(L"Stage1", L"page_y", 111, ini.c_str());
    }
    WNDCLASSW cls = {};
    cls.hInstance = g_module;
    cls.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    cls.lpfnWndProc = TabProc;
    cls.lpszClassName = kTabClass;
    if (!RegisterClassW(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        StageLog(L"FAILED: RegisterClass tab Windows error " + std::to_wstring(GetLastError()));
        return false;
    }
    cls.lpfnWndProc = PageProc;
    cls.lpszClassName = kPageClass;
    if (!RegisterClassW(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        StageLog(L"FAILED: RegisterClass page Windows error " + std::to_wstring(GetLastError()));
        return false;
    }
    if (!SetWindowSubclass(host, HostSubclass, kSubclassId, 0)) {
        StageLog(L"FAILED: SetWindowSubclass");
        return false;
    }
    g_host = host;
    // WS_POPUP with an owner (the PrintExp main frame) stays visually above
    // its child widgets without creating a second user-facing application.
    g_page = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        kPageClass, L"UV3D Stage 1", WS_POPUP,
        0, 0, 600, 400, g_host, nullptr, g_module, nullptr);
    g_tab = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        kTabClass, L"3D", WS_POPUP | WS_VISIBLE,
        0, 0, 108, 38, g_host, nullptr, g_module, nullptr);
    if (!g_page || !g_tab) {
        StageLog(L"FAILED: CreateWindowEx Windows error " + std::to_wstring(GetLastError()));
        if (g_tab) DestroyWindow(g_tab);
        if (g_page) DestroyWindow(g_page);
        RemoveWindowSubclass(g_host, HostSubclass, kSubclassId);
        g_host = nullptr; g_tab = nullptr; g_page = nullptr;
        return false;
    }
    Position();
    StageLog(L"SUCCESS: UI overlay created on host HWND=" +
        std::to_wstring(reinterpret_cast<UINT_PTR>(host)) +
        L"; screen tab visible=" + std::to_wstring(IsWindowVisible(g_tab)));
    std::wstring signal = L"Local\\UV3D_PageReady_" + std::to_wstring(GetCurrentProcessId());
    HANDLE event = OpenEventW(EVENT_MODIFY_STATE, FALSE, signal.c_str());
    if (event) { SetEvent(event); CloseHandle(event); }
    else StageLog(L"FAILED: OpenEvent page-ready; error=" + std::to_wstring(GetLastError()));
    return true;
}

extern "C" __declspec(dllexport) LRESULT CALLBACK UV3D_GetMessageHook(int code,WPARAM wp,LPARAM lp) {
    // This callback is intentionally limited to UI setup; no machine command path exists.
    if (code == HC_ACTION && lp && !g_host) {
        const MSG* msg = reinterpret_cast<const MSG*>(lp);
        if (msg->message == WM_NULL && msg->hwnd) {
            Create3DPage(msg->hwnd);
        }
    }
    return CallNextHookEx(nullptr,code,wp,lp);
}

BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) {g_module=module;DisableThreadLibraryCalls(module);}
    return TRUE;
}
