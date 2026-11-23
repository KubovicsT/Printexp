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
#include <cwchar>
#include <cstdlib>

#pragma comment(lib, "User32.lib")
#pragma comment(lib, "Gdi32.lib")
#pragma comment(lib, "Comctl32.lib")

static HINSTANCE g_module = nullptr;
static HWND g_host = nullptr;
static HWND g_tab = nullptr;
static HWND g_page = nullptr;
static HHOOK g_navHook = nullptr;
static bool g_active = false;
static int g_tabTop = 7;
static int g_tabLeft = -1;
static int g_fallbackTabX = 1348;
static int g_contentTop = 76;
static int g_bottomReserve = 46;
static constexpr int kTabWidth = 144;
static constexpr int kTabHeight = 62;
static bool g_dragging = false;
static bool g_dragged = false;
static bool g_positionCustomized = false;
static bool g_visionAnchorReported = false;
static POINT g_dragStart = {};
static int g_dragStartLeft = 0;
static int g_dragStartTop = 0;
static constexpr UINT_PTR kRepositionTimer = 0x3D21;
static unsigned g_probeTicks = 0;
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
    const std::wstring local = root + L"\\config\\native-page.ini";
    if (GetFileAttributesW(local.c_str()) != INVALID_FILE_ATTRIBUTES) return local;
    return root + L"\\config\\stage1.ini";
}

static void RectPaint(HDC dc, RECT r, COLORREF fill) {
    HBRUSH b = CreateSolidBrush(fill);
    FillRect(dc, &r, b);
    DeleteObject(b);
}

static void Position();
static void DumpNativeUi(const wchar_t* reason);

static void SaveTabLocation() {
    const std::wstring root = AddonRoot();
    if (root.empty()) return;
    const std::wstring path = root + L"\\config\\local-stage1.ini";
    const std::wstring x = std::to_wstring(g_tabLeft);
    const std::wstring y = std::to_wstring(g_tabTop);
    if (!WritePrivateProfileStringW(L"Stage1", L"tab_x", x.c_str(), path.c_str()) ||
        !WritePrivateProfileStringW(L"Stage1", L"tab_y", y.c_str(), path.c_str())) {
        StageLog(L"WARNING: Could not save 3D tab coordinates, Win32=" +
                 std::to_wstring(GetLastError()));
    } else {
        StageLog(L"Saved 3D tab position: x=" + x + L", y=" + y);
    }
}

struct VisionAnchor { HWND host; bool found; int right; int top; int score; };
static BOOL CALLBACK FindVisionControl(HWND child, LPARAM param) {
    auto* anchor = reinterpret_cast<VisionAnchor*>(param);
    if (!IsWindowVisible(child)) return TRUE;
    wchar_t label[160] = {};
    GetWindowTextW(child, label, 160);
    if (!wcsstr(label, L"Vision") &&
        !wcsstr(label, L"VISION") &&
        !wcsstr(label, L"vision")) return TRUE;
    RECT bounds = {};
    if (!GetWindowRect(child, &bounds)) return TRUE;
    POINT point = {bounds.left, bounds.top};
    if (!ScreenToClient(anchor->host, &point)) return TRUE;
    const int width = bounds.right - bounds.left;
    const int height = bounds.bottom - bounds.top;
    if (point.x < 0 || point.y < 0 || point.y > 140 ||
        width < 25 || width > 260 || height < 20 || height > 100) return TRUE;
    const int score = point.y * 1000 + width;
    if (!anchor->found || score < anchor->score) {
        anchor->found = true;
        anchor->right = point.x + width;
        anchor->top = point.y;
        anchor->score = score;
    }
    return TRUE;
}

static void Deactivate3D(const wchar_t* reason) {
    if (!g_active) return;
    g_active = false;
    if (g_page && IsWindow(g_page)) ShowWindow(g_page, SW_HIDE);
    if (g_tab && IsWindow(g_tab)) InvalidateRect(g_tab, nullptr, TRUE);
    StageLog(std::wstring(L"3D child page closed: ") + reason);
}

static LRESULT CALLBACK NativeNavHook(int code, WPARAM wp, LPARAM lp) {
    // The vendor receives every original navigation click unchanged.
    if (code == HC_ACTION && lp && g_active && g_host && IsWindow(g_host)) {
        const MSG* msg = reinterpret_cast<const MSG*>(lp);
        if (msg->message == WM_LBUTTONDOWN) {
            POINT screenPoint = msg->pt;
            RECT ownTab = {};
            if (g_tab && IsWindow(g_tab)) GetWindowRect(g_tab, &ownTab);
            if (!PtInRect(&ownTab, screenPoint)) {
                POINT pt = screenPoint;
                ScreenToClient(g_host, &pt);
                RECT client = {};
                GetClientRect(g_host, &client);
                if (pt.x >= 0 && pt.x < client.right &&
                    pt.y >= 0 && pt.y <= g_contentTop) {
                    Deactivate3D(L"original top navigation clicked");
                }
            }
        }
    }
    return CallNextHookEx(g_navHook, code, wp, lp);
}

static LRESULT CALLBACK TabProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch(msg) {
        case WM_SETCURSOR: SetCursor(LoadCursorW(nullptr, IDC_HAND)); return TRUE;
        case WM_LBUTTONUP:
            if (g_page) {
                g_active = !g_active;
                StageLog(g_active ? L"3D child page selected" : L"3D child page deselected");
                ShowWindow(g_page, g_active ? SW_SHOW : SW_HIDE);
                Position();
                InvalidateRect(hwnd, nullptr, TRUE);
            }
            return 0;
        case WM_PAINT: {
            PAINTSTRUCT ps = {};
            HDC dc = BeginPaint(hwnd, &ps);
            RECT r = {};
            GetClientRect(hwnd, &r);
            RectPaint(dc, r, g_active ? RGB(52,52,52) : RGB(96,96,96));
            SetBkMode(dc, TRANSPARENT);
            SetTextColor(dc, RGB(255,255,255));
            HFONT font = CreateFontW(-23,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
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
    if (msg == WM_ERASEBKGND) return 1;
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps = {};
        HDC dc = BeginPaint(hwnd, &ps);
        RECT rect = {};
        GetClientRect(hwnd, &rect);
        const int width = rect.right;
        const int height = rect.bottom;
        const int sideWidth = width > 900 ? 350 : 270;
        const int dividerX = width > sideWidth + 250 ? width - sideWidth : width - 250;

        RectPaint(dc, rect, RGB(243,244,246));
        // Existing PrintExp pages have a gray command strip immediately
        // beneath their top navigation. The Stage 1 toolbar is read-only.
        RECT toolbar = {0,0,width,76};
        RectPaint(dc, toolbar, RGB(97,97,97));
        SetBkMode(dc, TRANSPARENT);
        HFONT regular = CreateFontW(-19,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
            DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        HFONT big = CreateFontW(-28,0,0,0,FW_SEMIBOLD,FALSE,FALSE,FALSE,
            DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        HGDIOBJ old = SelectObject(dc, regular);
        SetTextColor(dc, RGB(236,236,236));
        const wchar_t* actions[] = {L"Model",L"Slice",L"Supports",L"Gantry",L"Preview"};
        int x = 34;
        for (int i=0; i<5; ++i) {
            RECT area = {x,15,x+120,62};
            DrawTextW(dc, actions[i], -1, &area, DT_LEFT|DT_VCENTER|DT_SINGLELINE);
            x += 143;
        }

        if (width > 400 && height > 180) {
            RECT canvas = {20,96,dividerX-18,height-18};
            RectPaint(dc, canvas, RGB(255,255,255));
            HBRUSH border = CreateSolidBrush(RGB(199,204,208));
            FrameRect(dc, &canvas, border);
            DeleteObject(border);

            SelectObject(dc, big);
            SetTextColor(dc, RGB(47,55,64));
            RECT title = {canvas.left+28,canvas.top+25,canvas.right-18,canvas.top+72};
            DrawTextW(dc,L"3D workspace",-1,&title,DT_LEFT|DT_VCENTER|DT_SINGLELINE);
            SelectObject(dc,regular);
            SetTextColor(dc,RGB(93,105,116));
            RECT message = {canvas.left+28,canvas.top+100,canvas.right-28,canvas.top+240};
            DrawTextW(dc,
                L"Embedded inside PrintExp. This stage tests the navigation and workspace.\n"
                L"Model import, slicing, UV curing and motor control are not connected yet.\n"
                L"Select Print, Settings, Adjust or Vision to switch to the original pages.",
                -1,&message,DT_WORDBREAK);

            RECT side = {dividerX,76,width,height};
            RectPaint(dc,side,RGB(77,77,77));
            const wchar_t* sections[] = {L"3D job",L"Model",L"Slice settings",L"Supports",
                                          L"Gantry",L"Simulation"};
            SetTextColor(dc,RGB(244,244,244));
            for (int i=0; i<6; ++i) {
                RECT line = {dividerX+22,96+i*78,width-18,140+i*78};
                DrawTextW(dc,sections[i],-1,&line,DT_LEFT|DT_VCENTER|DT_SINGLELINE);
                if (i<5) {
                    HPEN pen = CreatePen(PS_SOLID,1,RGB(112,112,112));
                    HGDIOBJ savedPen = SelectObject(dc,pen);
                    MoveToEx(dc,dividerX+20,157+i*78,nullptr);
                    LineTo(dc,width-18,157+i*78);
                    SelectObject(dc,savedPen);
                    DeleteObject(pen);
                }
            }
        }
        SelectObject(dc,old);
        DeleteObject(regular);
        DeleteObject(big);
        EndPaint(hwnd,&ps);
        return 0;
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}

static void Position() {
    if (!g_host || !IsWindow(g_host)) return;
    if (!g_tab || !IsWindow(g_tab) || !g_page || !IsWindow(g_page)) return;
    RECT rect = {};
    GetClientRect(g_host, &rect);
    const int width = rect.right - rect.left;
    const int height = rect.bottom - rect.top;
    if (!g_positionCustomized && !g_dragging) {
        VisionAnchor vision = {g_host, false, 0, 0, 0};
        EnumChildWindows(g_host, FindVisionControl,
                         reinterpret_cast<LPARAM>(&vision));
        if (vision.found) {
            g_tabLeft = vision.right + 7;
            g_tabTop = vision.top;
            if (!g_visionAnchorReported) {
                StageLog(L"3D child tab positioned after Vision");
                g_visionAnchorReported = true;
            }
        }
    }
    const int preferredX = g_tabLeft >= 0 ? g_tabLeft : g_fallbackTabX;
    const int x = preferredX > width - kTabWidth ?
          (width > kTabWidth ? width - kTabWidth : 0) :
          (preferredX > 0 ? preferredX : 0);
    const int contentHeight = height - g_contentTop - g_bottomReserve;
    // Child page follows the PrintExp main frame. It cannot float above
    // unrelated applications and moves/minimizes with the host.
    SetWindowPos(g_page, HWND_TOP, 0, g_contentTop,
                 width > 0 ? width : 1,
                 contentHeight > 0 ? contentHeight : 1,
                 SWP_NOACTIVATE | SWP_NOOWNERZORDER);
    if (!g_active) ShowWindow(g_page, SW_HIDE);
    SetWindowPos(g_tab, HWND_TOP, x, g_tabTop, kTabWidth, kTabHeight,
                 SWP_NOACTIVATE | SWP_NOOWNERZORDER);
    ShowWindow(g_tab, SW_SHOW);
}

static LRESULT CALLBACK HostSubclass(HWND hwnd, UINT message, WPARAM wp, LPARAM lp,
                                     UINT_PTR id, DWORD_PTR ref) {
    if (message == WM_NCDESTROY) {
        StageLog(L"Host main window closed; removing UI overlay");
        KillTimer(hwnd, kRepositionTimer);
        if (g_navHook) { UnhookWindowsHookEx(g_navHook); g_navHook = nullptr; }
        if (g_page && IsWindow(g_page)) DestroyWindow(g_page);
        if (g_tab && IsWindow(g_tab)) DestroyWindow(g_tab);
        RemoveWindowSubclass(hwnd, HostSubclass, id);
        g_host = nullptr; g_tab = nullptr; g_page = nullptr; g_active = false;
        return DefSubclassProc(hwnd, message, wp, lp);
    }
    if (message == WM_TIMER && wp == kRepositionTimer) {
        Position(); // Vision can appear after PrintExp startup.
        ++g_probeTicks;
        if (g_probeTicks == 3) DumpNativeUi(L"1.8 seconds after registration");
        if (g_probeTicks == 15) DumpNativeUi(L"9 seconds after registration");
        if (g_probeTicks == 40) DumpNativeUi(L"24 seconds after registration");
        return 0;
    }
    if (message == WM_COMMAND) {
        StageLog(L"native-nav event: WM_COMMAND id=" +
            std::to_wstring(LOWORD(wp)) + L" code=" +
            std::to_wstring(HIWORD(wp)));
    }
    if (message == WM_NOTIFY) {
        StageLog(L"native-nav event: WM_NOTIFY id=" + std::to_wstring(wp));
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
        g_tabTop = GetPrivateProfileIntW(L"Stage1", L"tab_y", 7, ini.c_str());
        g_tabLeft = GetPrivateProfileIntW(L"Stage1", L"tab_x", -1, ini.c_str());
        g_positionCustomized = g_tabLeft >= 0;
        g_fallbackTabX = GetPrivateProfileIntW(L"Stage1", L"fallback_tab_x", 1348, ini.c_str());
        g_contentTop = GetPrivateProfileIntW(L"Stage1", L"page_y", 76, ini.c_str());
        g_bottomReserve = GetPrivateProfileIntW(L"Stage1", L"bottom_bar_height", 46, ini.c_str());
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
    // Both are child controls in the native PrintExp main frame.
    g_page = CreateWindowExW(0, kPageClass, L"UV3D Stage 1",
                            WS_CHILD | WS_CLIPSIBLINGS | WS_CLIPCHILDREN,
                            0, g_contentTop, 600, 400,
                            g_host, nullptr, g_module, nullptr);
    g_tab = CreateWindowExW(0, kTabClass, L"3D",
                           WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS,
                           g_fallbackTabX, g_tabTop, kTabWidth, kTabHeight,
                           g_host, nullptr, g_module, nullptr);
    if (!g_page || !g_tab) {
        StageLog(L"FAILED: CreateWindowEx Windows error " + std::to_wstring(GetLastError()));
        if (g_tab) DestroyWindow(g_tab);
        if (g_page) DestroyWindow(g_page);
        RemoveWindowSubclass(g_host, HostSubclass, kSubclassId);
        g_host = nullptr; g_tab = nullptr; g_page = nullptr;
        return false;
    }
    g_navHook = SetWindowsHookExW(WH_GETMESSAGE, NativeNavHook, g_module, GetCurrentThreadId());
    if (!g_navHook) StageLog(L"WARNING: navigation watcher unavailable, Win32=" +
                                    std::to_wstring(GetLastError()));
    SetTimer(g_host, kRepositionTimer, 600, nullptr);
    Position();
    StageLog(L"SUCCESS: embedded 3D child page created on host HWND=" +
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
