// Stage 1: purely visual in-process page. Does not load/call PrintExp printer APIs.
// The DLL is loaded only by a targeted WH_GETMESSAGE hook for an exact, SHA-pinned build.
#define WIN32_LEAN_AND_MEAN
#if !defined(_WIN64)
#error "PrintExp 3D Stage 1 must be compiled for Windows x64."
#endif
#include <windows.h>
#include <commctrl.h>
#include <string>

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

static std::wstring ConfigFile() {
    wchar_t name[MAX_PATH] = {};
    if (!GetModuleFileNameW(g_module, name, MAX_PATH)) return L"";
    std::wstring dir(name);
    for (int i=0; i<3; ++i) { // DLL filename + 'windows' + 'dist'
        size_t idx = dir.find_last_of(L"\\/");
        if (idx == std::wstring::npos) return L"";
        dir.erase(idx);
    }
    return dir + L"\\config\\stage1.ini";
}

static void RectPaint(HDC dc, RECT r, COLORREF fill) {
    HBRUSH b = CreateSolidBrush(fill);
    FillRect(dc, &r, b);
    DeleteObject(b);
}

static LRESULT CALLBACK TabProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch(msg) {
        case WM_SETCURSOR: SetCursor(LoadCursorW(nullptr, IDC_HAND)); return TRUE;
        case WM_LBUTTONUP:
            if (g_page) {
                g_active = !g_active;
                ShowWindow(g_page, g_active ? SW_SHOW : SW_HIDE);
                if (g_active) SetWindowPos(g_page, HWND_TOP, 0,0,0,0,
                                             SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
                SetWindowPos(g_tab, HWND_TOP,0,0,0,0,
                             SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
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
    RECT r={}; GetClientRect(g_host,&r);
    int width = r.right-r.left;
    int height = r.bottom-r.top;
    if (g_tab) SetWindowPos(g_tab,HWND_TOP, width-108,g_tabTop,86,38,
                             SWP_NOACTIVATE|SWP_NOOWNERZORDER);
    if (g_page) SetWindowPos(g_page,HWND_TOP,0,g_contentTop,width,
                              height>g_contentTop ? height-g_contentTop : 1,
                              SWP_NOACTIVATE|SWP_NOOWNERZORDER);
    if (g_tab) SetWindowPos(g_tab,HWND_TOP,0,0,0,0,
                             SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);
}

static LRESULT CALLBACK HostSubclass(HWND hwnd,UINT message,WPARAM wp,LPARAM lp,
                                     UINT_PTR id,DWORD_PTR ref) {
    if (message == WM_NCDESTROY) {
        RemoveWindowSubclass(hwnd,HostSubclass,id);
        g_host = nullptr;g_tab = nullptr;g_page = nullptr;
        return DefSubclassProc(hwnd,message,wp,lp);
    }
    LRESULT value = DefSubclassProc(hwnd,message,wp,lp);
    if (message == WM_SIZE) Position();
    return value;
}

struct FindData { DWORD pid; HWND found; };
static BOOL CALLBACK FindWindowForPid(HWND hwnd,LPARAM p) {
    FindData* data = reinterpret_cast<FindData*>(p);
    DWORD pid=0;GetWindowThreadProcessId(hwnd,&pid);
    if (pid != data->pid || GetWindow(hwnd,GW_OWNER) || !IsWindowVisible(hwnd)) return TRUE;
    RECT r={};GetWindowRect(hwnd,&r);
    if (r.right-r.left<500 || r.bottom-r.top<360) return TRUE;
    data->found=hwnd;return FALSE;
}

static bool Create3DPage() {
    FindData f={GetCurrentProcessId(),nullptr};
    EnumWindows(FindWindowForPid,reinterpret_cast<LPARAM>(&f));
    if (!f.found) return false;
    // Pin only inside the matching PrintExp process. The DLL lives until PrintExp exits.
    HMODULE pin=nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
                            reinterpret_cast<LPCWSTR>(&Create3DPage),&pin)) return false;
    const std::wstring ini = ConfigFile();
    if (!ini.empty()) {
        g_tabTop = GetPrivateProfileIntW(L"Stage1",L"tab_y",54,ini.c_str());
        g_contentTop = GetPrivateProfileIntW(L"Stage1",L"page_y",111,ini.c_str());
    }
    WNDCLASSW cls={}; cls.hInstance=g_module;cls.hCursor=LoadCursorW(nullptr,IDC_ARROW);
    cls.lpfnWndProc=TabProc;cls.lpszClassName=kTabClass;
    RegisterClassW(&cls);
    cls.lpfnWndProc=PageProc;cls.lpszClassName=kPageClass;
    RegisterClassW(&cls);
    g_host=f.found;
    if (!SetWindowSubclass(g_host,HostSubclass,kSubclassId,0)) {g_host=nullptr;return false;}
    g_page=CreateWindowExW(0,kPageClass,L"UV3D Stage 1",WS_CHILD|WS_CLIPSIBLINGS|WS_CLIPCHILDREN,
                           0,111,600,400,g_host,nullptr,g_module,nullptr);
    g_tab=CreateWindowExW(0,kTabClass,L"3D",WS_CHILD|WS_VISIBLE|WS_CLIPSIBLINGS,
                          300,54,86,38,g_host,nullptr,g_module,nullptr);
    if (!g_page || !g_tab) {
        if(g_tab)DestroyWindow(g_tab);
        if(g_page)DestroyWindow(g_page);
        RemoveWindowSubclass(g_host,HostSubclass,kSubclassId);
        g_host=nullptr;g_tab=nullptr;g_page=nullptr;return false;
    }
    Position();
    std::wstring signal=L"Local\\UV3D_PageReady_"+std::to_wstring(GetCurrentProcessId());
    HANDLE event=OpenEventW(EVENT_MODIFY_STATE,FALSE,signal.c_str());
    if(event){SetEvent(event);CloseHandle(event);}
    return true;
}

extern "C" __declspec(dllexport) LRESULT CALLBACK UV3D_GetMessageHook(int code,WPARAM wp,LPARAM lp) {
    // This callback is intentionally limited to UI setup; no machine command path exists.
    if (code>=0 && !g_host) Create3DPage();
    return CallNextHookEx(nullptr,code,wp,lp);
}

BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) {g_module=module;DisableThreadLibraryCalls(module);}
    return TRUE;
}
