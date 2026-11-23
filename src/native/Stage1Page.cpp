// Stage 1 native navigation experiment for exact Gongzheng PrintExp x64 build.
// The native PrintExp page list receives the 3D entry using its own AddPage method.
// Printing, lamps, Z movement and vendor config writes are intentionally absent.
#define WIN32_LEAN_AND_MEAN
#if !defined(_WIN64)
#error "PrintExp 3D integration requires Windows x64."
#endif
#include <windows.h>
#include <commctrl.h>
#include <string>
#include <cstdint>
#include <cstring>

#pragma comment(lib, "User32.lib")
#pragma comment(lib, "Gdi32.lib")
#pragma comment(lib, "Comctl32.lib")

static HMODULE g_module = nullptr;
static HWND g_host = nullptr;
static HWND g_page = nullptr;
static void* g_frame = nullptr;
static void* g_nativeWnd = nullptr;
static int g_nativeIndex = -1;
static int g_attempts = 0;
static size_t g_previousCount = 0;
static int g_stableCountTicks = 0;
static bool g_ready = false;
static bool g_usesOwnMfcWnd = false;
static bool g_lastActive = false;
static UINT_PTR kTimer = 0x3D2990;
static constexpr UINT_PTR kSubclass = 0x3D2026;
static const wchar_t* kPageClass = L"UV3D_PrintExp_Registered_Page";

static std::wstring AddonRoot() {
    wchar_t module[MAX_PATH] = {};
    if (!GetModuleFileNameW(g_module, module, MAX_PATH)) return L"";
    std::wstring folder(module);
    for (int n = 0; n < 3; ++n) {
        const size_t slash = folder.find_last_of(L"\\/");
        if (slash == std::wstring::npos) return L"";
        folder.resize(slash);
    }
    return folder;
}

static void Log(const std::wstring& value) {
    const std::wstring root = AddonRoot();
    if (root.empty()) return;
    const std::wstring dir = root + L"\\diagnostics";
    CreateDirectoryW(dir.c_str(), nullptr);
    const std::wstring path = dir + L"\\native-page.log";
    HANDLE handle = CreateFileW(path.c_str(), FILE_APPEND_DATA,
       FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) return;
    SYSTEMTIME now = {};
    GetLocalTime(&now);
    wchar_t timestamp[90] = {};
    swprintf_s(timestamp, L"[%04u-%02u-%02u %02u:%02u:%02u] ",
       now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond);
    std::wstring line = timestamp + value + L"\r\n";
    const int n = WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (n > 1) {
        std::string bytes(static_cast<size_t>(n), '\0');
        WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1, &bytes[0], n, nullptr, nullptr);
        DWORD written = 0;
        WriteFile(handle, bytes.data(), static_cast<DWORD>(n-1), &written, nullptr);
    }
    CloseHandle(handle);
}

static void PaintFill(HDC dc, RECT rect, COLORREF color) {
    HBRUSH brush = CreateSolidBrush(color);
    FillRect(dc, &rect, brush);
    DeleteObject(brush);
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
        PaintFill(dc, rect, RGB(245,246,247));
        RECT tools = {0,0,width,76};
        PaintFill(dc, tools, RGB(96,96,96));
        SetBkMode(dc, TRANSPARENT);
        HFONT normal = CreateFontW(-19,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
                                   DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        HFONT heading = CreateFontW(-29,0,0,0,FW_SEMIBOLD,FALSE,FALSE,FALSE,
                                    DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        HGDIOBJ original = SelectObject(dc, normal);
        SetTextColor(dc, RGB(245,245,245));
        const wchar_t* actions[] = {L"Model", L"Slice", L"Supports", L"Gantry", L"Preview"};
        for (int i=0; i<5; ++i) {
            RECT item = {28+i*145,12,158+i*145,64};
            DrawTextW(dc,actions[i],-1,&item,DT_LEFT|DT_VCENTER|DT_SINGLELINE);
        }
        const int side = width > 950 ? 345 : 260;
        const int split = width - side;
        RECT canvas = {20,96,split-16,height-18};
        if (canvas.right > canvas.left && canvas.bottom > canvas.top) {
            PaintFill(dc,canvas,RGB(255,255,255));
            SelectObject(dc,heading);
            SetTextColor(dc,RGB(43,51,58));
            RECT title = {canvas.left+30,canvas.top+30,canvas.right-20,canvas.top+84};
            DrawTextW(dc,L"PrintExp 3D",-1,&title,DT_LEFT|DT_VCENTER|DT_SINGLELINE);
            SelectObject(dc,normal);
            SetTextColor(dc,RGB(93,102,110));
            RECT note = {canvas.left+30,canvas.top+110,canvas.right-30,canvas.top+240};
            DrawTextW(dc,
                L"Registered through PrintExp's native page list.\n"
                L"Stage 1: user-interface integration only.\n"
                L"Printing, Z-axis motion and UV lamp commands are disabled.",
                -1,&note,DT_LEFT|DT_WORDBREAK);
        }
        RECT panel = {split,76,width,height};
        PaintFill(dc,panel,RGB(77,77,77));
        SetTextColor(dc,RGB(244,244,244));
        const wchar_t* groups[] = {L"3D job",L"Model",L"Slice settings",L"Supports",
                                    L"Gantry",L"Simulation"};
        for (int i=0; i<6; ++i) {
            RECT line = {split+18,104+i*77,width-12,144+i*77};
            DrawTextW(dc,groups[i],-1,&line,DT_LEFT|DT_VCENTER|DT_SINGLELINE);
        }
        SelectObject(dc,original);
        DeleteObject(normal);
        DeleteObject(heading);
        EndPaint(hwnd,&ps);
        return 0;
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}

using NativeAddPage = void(__fastcall*)(void*,int,void*,void*,int);
using NativeCount = size_t(__fastcall*)(void*);
using NativeInitString = void*(__fastcall*)(void*);
using NativeDestroyString = void(__fastcall*)(void*);
using NativeTranslate = void*(__fastcall*)(void*,void*,const wchar_t*);
using MfcMainWnd = void*(__cdecl*)();
using MfcFromHandle = void*(__cdecl*)(HWND);
using MfcWndCtor = void*(__fastcall*)(void*);
using MfcWndAttach = int(__fastcall*)(void*,HWND);

// SEH safety boundaries must be isolated: /EHsc forbids __try in C++
// functions that use std::wstring or other objects requiring unwinding.
static bool SafeFrameMatches(void* frame, HWND host) {
    bool hit=false;
    __try {
        const auto* bytes=static_cast<const unsigned char*>(frame);
        for (size_t i=0;i<=0x100;i+=sizeof(void*)) {
            HWND value=nullptr;
            std::memcpy(&value,bytes+i,sizeof(value));
            if (value==host) {hit=true;break;}
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {hit=false;}
    return hit;
}

static bool SafeAttachMfc(FARPROC constructor, FARPROC attach, void* storage, HWND hwnd) {
    bool done=false;
    __try {
        reinterpret_cast<MfcWndCtor>(constructor)(storage);
        done=reinterpret_cast<MfcWndAttach>(attach)(storage,hwnd)!=0;
    } __except(EXCEPTION_EXECUTE_HANDLER) {done=false;}
    return done;
}

static bool SafeFrameState(void* frame, unsigned char* image, int* vision, size_t* count) {
    bool okay=false;
    __try {
        *vision=*reinterpret_cast<int*>(static_cast<unsigned char*>(frame)+0xf76a0);
        *count=reinterpret_cast<NativeCount>(image+0x340c0)(
            static_cast<unsigned char*>(frame)+0x4cc0);
        okay=true;
    } __except(EXCEPTION_EXECUTE_HANDLER) {okay=false;}
    return okay;
}

static bool SafePageCount(void* frame, unsigned char* image, size_t* count) {
    bool okay=false;
    __try {
        *count=reinterpret_cast<NativeCount>(image+0x340c0)(
            static_cast<unsigned char*>(frame)+0x4cc0);
        okay=true;
    } __except(EXCEPTION_EXECUTE_HANDLER) {okay=false;}
    return okay;
}

static bool SafeSelectedIndex(void* frame, int* selected) {
    bool okay=false;
    __try {
        *selected=*reinterpret_cast<int*>(static_cast<unsigned char*>(frame)+0x4cbc);
        okay=true;
    } __except(EXCEPTION_EXECUTE_HANDLER) {okay=false;}
    return okay;
}

static void* FindMainFrame(HWND host) {
    HMODULE mfc = GetModuleHandleW(L"mfc100u.dll");
    if (!mfc) { Log(L"MFC runtime is not loaded"); return nullptr; }
    const char* mainNames[] = {
        "?AfxGetMainWnd@@YAPEAVCWnd@@XZ",
        "?AfxGetMainWnd@@YAPAVCWnd@@XZ"
    };
    void* frame = nullptr;
    for (const char* name : mainNames) {
        FARPROC proc = GetProcAddress(mfc, name);
        if (proc) {
            frame = reinterpret_cast<MfcMainWnd>(proc)();
            if (frame) break;
        }
    }
    if (!frame) {
        FARPROC from = GetProcAddress(mfc, "?FromHandlePermanent@CWnd@@SAPEAV1@PEAUHWND__@@@Z");
        if (from) frame = reinterpret_cast<MfcFromHandle>(from)(host);
    }
    if (!frame) {
        // VC++ 2010 MFC builds sometimes export only ordinals. Search the
        // pinned PrintExp executable's own writable static data for a pointer
        // to its permanent CMainFrame object, then verify the exact HWND.
        unsigned char* image =
            reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
        if (image) {
            constexpr size_t dataStart=0x28f000;
            constexpr size_t dataSize=0x59a8; // PE .data VirtualSize
            for (size_t offset=0;offset+sizeof(void*)<=dataSize;offset+=sizeof(void*)) {
                void* candidate=nullptr;
                std::memcpy(&candidate,image+dataStart+offset,sizeof(candidate));
                if (!candidate || candidate==image) continue;
                MEMORY_BASIC_INFORMATION region={};
                if (!VirtualQuery(candidate,&region,sizeof(region)) ||
                    region.State!=MEM_COMMIT ||
                    (region.Protect & PAGE_GUARD) ||
                    (region.Protect & PAGE_NOACCESS)) continue;
                if (SafeFrameMatches(candidate,host)) {
                    frame=candidate;
                    Log(L"Native registration: discovered MFC main frame through "
                        L"PrintExp static-data pointer RVA=" + std::to_wstring(
                        dataStart+offset));
                    break;
                }
            }
        }
    }
    if (!frame) {
        if (GetTickCount()%10000<600) Log(
            L"Native registration: MFC main-frame object not available yet");
        return nullptr;
    }
    // Check that this is the permanent wrapper for the exact selected HWND.
    if (!SafeFrameMatches(frame,host)) {
        Log(L"Native registration: MFC frame pointer did not match PrintExp HWND");
        return nullptr;
    }
    return frame;
}

static void* BuildOwnMfcWrapper(HWND page) {
    HMODULE mfc = GetModuleHandleW(L"mfc100u.dll");
    if (!mfc) return nullptr;
    FARPROC init = GetProcAddress(mfc, "??0CWnd@@QEAA@XZ");
    FARPROC attach = GetProcAddress(mfc, "?Attach@CWnd@@QEAAHPEAUHWND__@@@Z");
    if (!init || !attach) {
        Log(L"MFC CWnd constructor/Attach exports unavailable; native temporary fallback");
        return nullptr;
    }
    // The CWnd object is process-lifetime storage. Vendor page objects are
    // likewise retained for the lifetime of PrintExp.
    void* storage = VirtualAlloc(nullptr, 4096, MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    if (!storage) return nullptr;
    if (!SafeAttachMfc(init,attach,storage,page)) {
        Log(L"Could not attach MFC CWnd wrapper to the 3D content HWND");
        // Leave memory allocated; an MFC constructor may have partially run.
        return nullptr;
    }
    Log(L"3D content attached as its own native MFC CWnd");
    return storage;
}

static bool PerformNativeRegistration(unsigned char* image, void* frame,
                                      size_t index, void* pageObject) {
    // Exact RVAs extracted from the user's original SHA-pinned PrintExp_X64.exe.
    auto* initSlot = reinterpret_cast<NativeInitString*>(image+0x1f9e28);
    auto* destroySlot = reinterpret_cast<NativeDestroyString*>(image+0x1f9e30);
    if (!*initSlot || !*destroySlot) return false;
    void* label = nullptr;
    bool added = false;
    __try {
        (*initSlot)(&label);
        auto translated = reinterpret_cast<NativeTranslate>(image+0x11490)(
            image+0x292468,&label,L"3D");
        if (translated) {
            reinterpret_cast<NativeAddPage>(image+0x48530)(
                frame, static_cast<int>(index), pageObject, translated, 1);
            added = true;
        }
        (*destroySlot)(&label);
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        added = false;
    }
    return added;
}

static bool TryNativePageRegistration() {
    if (g_ready || !g_host || !g_page) return g_ready;
    ++g_attempts;
    unsigned char* image = reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
    if (!image) return false;
    // Guard the page-register function signature for the known PrintExp build.
    const unsigned char methodSignature[] = {0x4c,0x89,0x4c,0x24,0x20,0x4c,0x89,0x44,0x24,0x18};
    if (std::memcmp(image+0x48530,methodSignature,sizeof(methodSignature))!=0) {
        if (g_attempts==1) Log(L"Native page function signature mismatch; refusing to call.");
        return false;
    }
    void* frame = FindMainFrame(g_host);
    if (!frame) return false;
    size_t count = 0;
    // Only the core page list is required. Vision may not be registered
    // when there is no printer or camera connected.
    if (!SafePageCount(frame,image,&count)) return false;
    if (count<3 || count>24) {
        if (g_attempts==1 || g_attempts==12)
            Log(L"Waiting for PrintExp core navigation initialization...");
        return false;
    }
    // Avoid registering in the middle of PrintExp's normal startup sequence.
    if (count != g_previousCount) {
        g_previousCount=count;
        g_stableCountTicks=0;
        return false;
    }
    if (++g_stableCountTicks < 4) return false;

    // NEVER use Vision's CWnd as our page: it may be absent or uninitialized
    // on the offline development PC, and is not owned by the 3D extension.
    void* nativePage = BuildOwnMfcWrapper(g_page);
    if (!nativePage) {
        if (g_attempts==5 || g_attempts==20)
            Log(L"Native 3D page waiting: independent MFC CWnd wrapper unavailable");
        return false;
    }
    g_usesOwnMfcWnd = true;
    if (!PerformNativeRegistration(image,frame,count,nativePage)) {
        Log(L"ERROR: Native AddPage call did not complete");
        return false;
    }
    size_t after = 0;
    if (!SafePageCount(frame,image,&after)) return false;
    if (after != count+1) {
        Log(L"ERROR: native page-list count did not increase as expected");
        return false;
    }
    g_frame=frame;
    g_nativeWnd=nativePage;
    g_nativeIndex=static_cast<int>(count);
    g_ready=true;
    Log(L"SUCCESS: PrintExp native AddPage registered 3D at index=" +
        std::to_wstring(g_nativeIndex) + L", total=" + std::to_wstring(after));
    std::wstring eventName=L"Local\\UV3D_PageReady_"+std::to_wstring(GetCurrentProcessId());
    HANDLE ready=OpenEventW(EVENT_MODIFY_STATE,FALSE,eventName.c_str());
    if (ready) { SetEvent(ready); CloseHandle(ready); }
    return true;
}

static void Position3D() {
    if (!g_ready || !g_host || !g_page || !IsWindow(g_page)) return;
    int selected=-1;
    if (!SafeSelectedIndex(g_frame,&selected)) return;
    const bool active=selected==g_nativeIndex;
    if (active!=g_lastActive) {
        Log(active ? L"Native PrintExp navigation selected 3D" :
                     L"Native PrintExp navigation switched away from 3D");
        g_lastActive=active;
    }
    if (!active) { ShowWindow(g_page,SW_HIDE); return; }
    RECT rect={};
    GetClientRect(g_host,&rect);
    const int top=76;
    const int height=rect.bottom-top-46;
    SetWindowPos(g_page,HWND_TOP,0,top,rect.right>0?rect.right:1,
        height>0?height:1,SWP_NOACTIVATE|SWP_SHOWWINDOW);
}

static LRESULT CALLBACK HostSubclass(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp,
                                     UINT_PTR id,DWORD_PTR ref) {
    if (msg==WM_NCDESTROY) {
        KillTimer(hwnd,kTimer);
        RemoveWindowSubclass(hwnd,HostSubclass,id);
        g_host=nullptr;g_page=nullptr;g_frame=nullptr;
        return DefSubclassProc(hwnd,msg,wp,lp);
    }
    LRESULT result=DefSubclassProc(hwnd,msg,wp,lp);
    if (msg==WM_TIMER && wp==kTimer) {
        if (!g_ready) TryNativePageRegistration();
        Position3D();
    } else if (msg==WM_SIZE || msg==WM_WINDOWPOSCHANGED) {
        Position3D();
    }
    return result;
}

static bool SetupNative3D(HWND host) {
    if (!IsWindow(host) || GetAncestor(host,GA_ROOT)!=host) return false;
    DWORD process=0;
    DWORD thread=GetWindowThreadProcessId(host,&process);
    if (process!=GetCurrentProcessId() || thread!=GetCurrentThreadId()) return false;
    WNDCLASSW cls={};
    cls.hInstance=g_module;
    cls.lpfnWndProc=PageProc;
    cls.hCursor=LoadCursorW(nullptr,IDC_ARROW);
    cls.lpszClassName=kPageClass;
    if (!RegisterClassW(&cls) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS)
        return false;
    if (!SetWindowSubclass(host,HostSubclass,kSubclass,0)) return false;
    g_host=host;
    g_page=CreateWindowExW(0,kPageClass,L"PrintExp 3D",
        WS_CHILD|WS_CLIPSIBLINGS|WS_CLIPCHILDREN,
        0,76,800,600,host,nullptr,g_module,nullptr);
    if (!g_page) {
        Log(L"ERROR: Could not create 3D workspace HWND, Win32="+std::to_wstring(GetLastError()));
        RemoveWindowSubclass(host,HostSubclass,kSubclass);
        g_host=nullptr;
        return false;
    }
    // Unlike earlier experiments, no independently painted 3D tab is created.
    // Its navigation entry must come from PrintExp's own AddPage method.
    Log(L"Host attached. Waiting for stable core page initialization (no Vision dependency).");
    SetTimer(host,kTimer,550,nullptr);
    TryNativePageRegistration();
    return true;
}

extern "C" __declspec(dllexport) LRESULT CALLBACK UV3D_GetMessageHook(int code,WPARAM wp,LPARAM lp) {
    if (code==HC_ACTION && lp && !g_host) {
        const MSG* msg=reinterpret_cast<const MSG*>(lp);
        if (msg->message==WM_NULL && msg->hwnd)
            SetupNative3D(msg->hwnd);
    }
    return CallNextHookEx(nullptr,code,wp,lp);
}

BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if (reason==DLL_PROCESS_ATTACH) {
        g_module=module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}
