// Targeted x64 WH_GETMESSAGE hook launcher. The vendor PrintExp binary is never patched.
#define WIN32_LEAN_AND_MEAN
#if !defined(_WIN64)
#error "PrintExp 3D Stage 1 must be compiled for Windows x64."
#endif
#include <windows.h>
#include <bcrypt.h>
#include <shellapi.h>
#include <string>
#include <vector>

#pragma comment(lib,"Bcrypt.lib")
#pragma comment(lib,"User32.lib")
#pragma comment(lib,"Shell32.lib")

static constexpr wchar_t kSupportedSha[] = L"af1dbed5532ff4262fcc4d38e288940ece3c9f45ab1e803230d85e6092bbacf1";

static void Error(const wchar_t* reason) {
    MessageBoxW(nullptr,reason,L"PrintExp 3D Stage 1",MB_OK|MB_ICONERROR);
}

static void ErrorWin32(const wchar_t* operation, DWORD errorCode) {
    std::wstring message = operation;
    message += L"\nWindows error code: " + std::to_wstring(errorCode);
    wchar_t* systemMessage = nullptr;
    const DWORD count = FormatMessageW(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr, errorCode, 0, reinterpret_cast<LPWSTR>(&systemMessage), 0, nullptr);
    if (count && systemMessage) {
        message += L"\n";
        message += systemMessage;
    }
    if (systemMessage) LocalFree(systemMessage);
    message += L"\n\nThe printer executable was not patched. ";
    message += L"If error 5 persists after Update from main repairs permissions, ";
    message += L"Windows security rules or process elevation may be blocking the extension.";
    Error(message.c_str());
}

static std::wstring Folder(const std::wstring& path) {
    size_t slash = path.find_last_of(L"\\/");
    return slash==std::wstring::npos ? L"." : path.substr(0,slash);
}

static void StageLog(const std::wstring& message) {
    wchar_t module[MAX_PATH] = {};
    if (!GetModuleFileNameW(nullptr, module, MAX_PATH)) return;
    std::wstring folder = Folder(module);
    // Launcher lives in UV3DAddOn\\dist\\windows.
    folder = Folder(Folder(folder));
    if (folder.empty()) return;
    const std::wstring logFolder = folder + L"\\diagnostics";
    CreateDirectoryW(logFolder.c_str(), nullptr);
    const std::wstring logFile = logFolder + L"\\stage1.log";
    HANDLE handle = CreateFileW(logFile.c_str(), FILE_APPEND_DATA,
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
    int count = WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1,
        nullptr, 0, nullptr, nullptr);
    if (count > 1) {
        std::vector<char> bytes(static_cast<size_t>(count));
        WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1,
            bytes.data(), count, nullptr, nullptr);
        DWORD written = 0;
        WriteFile(handle, bytes.data(), static_cast<DWORD>(count-1), &written, nullptr);
    }
    CloseHandle(handle);
}

static std::wstring Hex(const UCHAR* bytes,size_t count) {
    static const wchar_t* dig=L"0123456789abcdef";
    std::wstring result;
    result.reserve(count*2);
    for(size_t i=0;i<count;i++) {result+=dig[bytes[i]>>4];result+=dig[bytes[i]&15];}
    return result;
}

static std::wstring FileSha256(const std::wstring& path) {
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,
                            FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) return L"";
    BCRYPT_ALG_HANDLE algorithm=nullptr;
    BCRYPT_HASH_HANDLE hash=nullptr;
    std::wstring answer;
    DWORD objectLength=0,got=0;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0 &&
       BCryptGetProperty(algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&objectLength),
                         sizeof(objectLength),&got,0)>=0) {
        std::vector<UCHAR> obj(objectLength);
        if(BCryptCreateHash(algorithm,&hash,obj.data(),objectLength,nullptr,0,0)>=0) {
            std::vector<UCHAR> chunk(1024*1024);
            DWORD read=0;
            bool okay=true;
            while(ReadFile(file,chunk.data(),static_cast<DWORD>(chunk.size()),&read,nullptr) && read) {
                if(BCryptHashData(hash,chunk.data(),read,0)<0) {okay=false;break;}
            }
            if(GetLastError()!=ERROR_SUCCESS && read==0) { /* EOF may leave last error unchanged */ }
            UCHAR digest[32]={};
            if(okay && BCryptFinishHash(hash,digest,32,0)>=0) answer=Hex(digest,32);
        }
    }
    if(hash) BCryptDestroyHash(hash);
    if(algorithm) BCryptCloseAlgorithmProvider(algorithm,0);
    CloseHandle(file);
    return answer;
}


static bool RelaunchAsAdministrator(const std::wstring& launcherPath,
                                    const std::wstring& printExpPath) {
    // PrintExp's embedded manifest requests highestAvailable. CreateProcess
    // cannot display a UAC dialog, but ShellExecuteEx with "runas" can.
    std::wstring arguments = L"\"" + printExpPath + L"\" --elevated";
    std::wstring workingDir = Folder(launcherPath);
    SHELLEXECUTEINFOW info = {};
    info.cbSize = sizeof(info);
    info.fMask = SEE_MASK_NOCLOSEPROCESS;
    info.lpVerb = L"runas";
    info.lpFile = launcherPath.c_str();
    info.lpParameters = arguments.c_str();
    info.lpDirectory = workingDir.c_str();
    info.nShow = SW_SHOWNORMAL;
    if (!ShellExecuteExW(&info)) {
        const DWORD code = GetLastError();
        if (code == ERROR_CANCELLED) {
            Error(L"Administrator approval was cancelled. PrintExp was not started.");
        } else {
            ErrorWin32(L"Windows could not elevate the PrintExp 3D launcher.", code);
        }
        return false;
    }
    if (info.hProcess) CloseHandle(info.hProcess);
    return true;
}

struct FindData { DWORD pid; HWND hwnd; DWORD tid; long long score; };
static BOOL CALLBACK CountChildWindows(HWND, LPARAM data) {
    ++(*reinterpret_cast<int*>(data));
    return TRUE;
}
static BOOL CALLBACK FindPrintExp(HWND w, LPARAM lp) {
    FindData* f = reinterpret_cast<FindData*>(lp);
    DWORD p = 0;
    DWORD thread = GetWindowThreadProcessId(w, &p);
    if (p != f->pid || GetWindow(w, GW_OWNER) || !IsWindowVisible(w)) return TRUE;
    RECT rect = {};
    GetWindowRect(w, &rect);
    const int width = rect.right - rect.left;
    const int height = rect.bottom - rect.top;
    if (width < 640 || height < 420) return TRUE;
    int children = 0;
    EnumChildWindows(w, CountChildWindows, reinterpret_cast<LPARAM>(&children));
    // PrintExp's real MFC frame has substantial child UI. Splash windows usually
    // have fewer widgets and lack the resizable frame style.
    const LONG_PTR style = GetWindowLongPtrW(w, GWL_STYLE);
    const long long score = static_cast<long long>(children) * 10000000 +
        (style & WS_THICKFRAME ? 30000000 : 0) +
        (style & WS_MAXIMIZEBOX ? 10000000 : 0) +
        static_cast<long long>(width) * height;
    if (score > f->score) {
        f->hwnd = w;
        f->tid = thread;
        f->score = score;
    }
    return TRUE;
}

int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    int argc=0;
    LPWSTR* args=CommandLineToArgvW(GetCommandLineW(),&argc);
    if (!args || (argc!=2 && argc!=3) ||
        (argc==3 && std::wstring(args[2])!=L"--elevated")) {
        Error(L"This launcher requires the absolute path of PrintExp_X64.exe.");
        if(args)LocalFree(args);
        return 2;
    }
    const bool alreadyTriedElevation = (argc==3);
    std::wstring executable=args[1];LocalFree(args);
    StageLog(L"Launcher started; target=" + executable);
    if(FileSha256(executable)!=kSupportedSha) {
        Error(L"This PrintExp_X64.exe does not match the exact inspected build.\n"
              L"The 3D page was not loaded. Original PrintExp was not modified.");
        return 3;
    }
    wchar_t own[MAX_PATH]={};
    if(!GetModuleFileNameW(nullptr,own,MAX_PATH)) return 4;
    std::wstring dll=Folder(own)+L"\\UV3DPage.dll";
    HMODULE localDll=LoadLibraryW(dll.c_str());
    if(!localDll) {ErrorWin32(L"Could not load UV3DPage.dll.", GetLastError());return 5;}
    auto hookproc=reinterpret_cast<HOOKPROC>(GetProcAddress(localDll,"UV3D_GetMessageHook"));
    if(!hookproc) {Error(L"3D hook export missing.");FreeLibrary(localDll);return 6;}
    std::wstring command=L"\""+executable+L"\"";
    std::vector<wchar_t> cmd(command.begin(),command.end());cmd.push_back(L'\0');
    std::wstring working=Folder(executable);
    STARTUPINFOW startup={};startup.cb=sizeof(startup);
    PROCESS_INFORMATION pi={};
    if(!CreateProcessW(executable.c_str(),cmd.data(),nullptr,nullptr,FALSE,0,nullptr,
                       working.c_str(),&startup,&pi)) {
        const DWORD code = GetLastError();
        FreeLibrary(localDll);
        // The original PrintExp executable has level="highestAvailable".
        // Relaunch THIS loader elevated as well as the host, so that the
        // subsequent UI hook runs at the host's Windows integrity level.
        // Also handle access denied from an unelevated CreateProcess once;
        // persistent access denied is reported rather than bypassed.
        if (!alreadyTriedElevation &&
            (code == ERROR_ELEVATION_REQUIRED || code == ERROR_ACCESS_DENIED)) {
            return RelaunchAsAdministrator(own, executable) ? 0 : 11;
        }
        ErrorWin32(L"Could not start PrintExp. Check its permissions and elevation requirements.", code);
        return 7;
    }
    WaitForInputIdle(pi.hProcess,15000);
    // Don't attach to PrintExp's splash/startup window. Require a stable window
    // candidate for 2.5 seconds, and continue monitoring for a richer MFC frame.
    FindData f = {pi.dwProcessId, nullptr, 0, -1};
    HWND candidate = nullptr;
    DWORD stableSince = GetTickCount();
    for (int i=0; i<160; ++i) {
        FindData scan = {pi.dwProcessId, nullptr, 0, -1};
        EnumWindows(FindPrintExp, reinterpret_cast<LPARAM>(&scan));
        if (scan.hwnd != candidate) {
            candidate = scan.hwnd;
            stableSince = GetTickCount();
        }
        if (candidate && GetTickCount() - stableSince >= 2500) {
            f = scan;
            break;
        }
        if (WaitForSingleObject(pi.hProcess, 0) == WAIT_OBJECT_0) break;
        Sleep(125);
    }
    if(!f.hwnd) {
        DWORD exitCode=STILL_ACTIVE;
        const bool exited=(WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0);
        if (exited) GetExitCodeProcess(pi.hProcess,&exitCode);
        StageLog(L"FAILED: PrintExp main window unavailable; host exited=" +
                 std::to_wstring(exited?1:0) + L" exit code=" + std::to_wstring(exitCode));
        if (exited) {
            Error((L"PrintExp exited during startup before its main window appeared.\n"
                   L"Windows process exit code: " + std::to_wstring(exitCode) +
                   L"\nCheck whether offline debug mode is enabled in Project.ini.").c_str());
        } else {
            Error(L"PrintExp launched but no usable main window appeared.\n"
                  L"Check UV3DAddOn\\diagnostics\\stage1.log.");
        }
        CloseHandle(pi.hThread);CloseHandle(pi.hProcess);FreeLibrary(localDll);return 8;
    }
    wchar_t targetTitle[256] = {};
    wchar_t targetClass[256] = {};
    GetWindowTextW(f.hwnd, targetTitle, 256);
    GetClassNameW(f.hwnd, targetClass, 256);
    StageLog(L"Attaching to HWND=" + std::to_wstring(reinterpret_cast<UINT_PTR>(f.hwnd)) +
        L" title=" + targetTitle + L" class=" + targetClass +
        L" thread=" + std::to_wstring(f.tid) +
        L" score=" + std::to_wstring(f.score));
    std::wstring eventName=L"Local\\UV3D_PageReady_"+std::to_wstring(pi.dwProcessId);
    HANDLE ready=CreateEventW(nullptr,TRUE,FALSE,eventName.c_str());
    HHOOK hook=SetWindowsHookExW(WH_GETMESSAGE,hookproc,localDll,f.tid);
    if(!hook) {
        const DWORD code = GetLastError();
        StageLog(L"FAILED: SetWindowsHookEx error=" + std::to_wstring(code));
        ErrorWin32(L"Windows blocked the experimental 3D module hook.\n"
                     L"PrintExp is running unchanged.", code);
        if(ready)CloseHandle(ready);
        CloseHandle(pi.hThread);CloseHandle(pi.hProcess);FreeLibrary(localDll);return 9;
    }
    bool success=false;
    bool hostExited=false;
    DWORD hostExitCode=STILL_ACTIVE;
    for(int i=0;i<200;i++) {
        if(ready && WaitForSingleObject(ready,125)==WAIT_OBJECT_0) {success=true;break;}
        PostMessageW(f.hwnd,WM_NULL,0,0); // Trigger the PrintExp UI thread's hook.
        if(WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0) {
            hostExited=true;
            GetExitCodeProcess(pi.hProcess,&hostExitCode);
            break;
        }
    }
    UnhookWindowsHookEx(hook);
    if(ready)CloseHandle(ready);
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
    FreeLibrary(localDll);
    if(!success) {
        StageLog(L"FAILED: Native 3D registration did not signal readiness; PrintExp exited=" +
                 std::to_wstring(hostExited?1:0) +
                 L"; exit code=" + std::to_wstring(hostExitCode));
        if(hostExited) {
            Error((L"PrintExp exited before the 3D page initialized.\n"
                   L"Process exit code: " + std::to_wstring(hostExitCode) +
                   L"\nCheck offline debug configuration and diagnostics/native-page.log.").c_str());
        } else {
            Error(L"PrintExp started, but native 3D registration did not complete.\n"
                  L"Inspect UV3DAddOn\\diagnostics\\native-page.log.\n"
                  L"No printer commands were issued.");
        }
        return 10;
    }
    StageLog(L"SUCCESS: injected UI reported readiness");
    return 0;
}
