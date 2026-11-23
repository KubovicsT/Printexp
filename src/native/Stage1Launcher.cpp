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

struct FindData { DWORD pid; HWND hwnd; DWORD tid; };
static BOOL CALLBACK FindPrintExp(HWND w,LPARAM lp) {
    FindData* f=reinterpret_cast<FindData*>(lp);
    DWORD p=0;DWORD t=GetWindowThreadProcessId(w,&p);
    if(p!=f->pid || GetWindow(w,GW_OWNER) || !IsWindowVisible(w)) return TRUE;
    RECT r={};GetWindowRect(w,&r);
    if(r.right-r.left<500 || r.bottom-r.top<360) return TRUE;
    f->hwnd=w;f->tid=t;return FALSE;
}

int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    int argc=0;
    LPWSTR* args=CommandLineToArgvW(GetCommandLineW(),&argc);
    if(!args || argc!=2) {
        Error(L"This launcher requires the absolute path of PrintExp_X64.exe.");
        if(args)LocalFree(args);
        return 2;
    }
    std::wstring executable=args[1];LocalFree(args);
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
        ErrorWin32(L"Could not start PrintExp. Check its permissions and elevation requirements.", code);
        FreeLibrary(localDll);return 7;
    }
    WaitForInputIdle(pi.hProcess,15000);
    FindData f={pi.dwProcessId,nullptr,0};
    for(int i=0;i<160 && !f.hwnd;i++) {
        EnumWindows(FindPrintExp,reinterpret_cast<LPARAM>(&f));
        if(!f.hwnd) Sleep(125);
    }
    if(!f.hwnd) {
        Error(L"PrintExp launched, but its main window was not detected.\n"
              L"PrintExp is still running normally without the 3D page.");
        CloseHandle(pi.hThread);CloseHandle(pi.hProcess);FreeLibrary(localDll);return 8;
    }
    std::wstring eventName=L"Local\\UV3D_PageReady_"+std::to_wstring(pi.dwProcessId);
    HANDLE ready=CreateEventW(nullptr,TRUE,FALSE,eventName.c_str());
    HHOOK hook=SetWindowsHookExW(WH_GETMESSAGE,hookproc,localDll,f.tid);
    if(!hook) {
        const DWORD code = GetLastError();
        ErrorWin32(L"Windows blocked the experimental 3D module hook.\n"
                     L"PrintExp is running unchanged.", code);
        if(ready)CloseHandle(ready);
        CloseHandle(pi.hThread);CloseHandle(pi.hProcess);FreeLibrary(localDll);return 9;
    }
    bool success=false;
    for(int i=0;i<80;i++) {
        if(ready && WaitForSingleObject(ready,125)==WAIT_OBJECT_0) {success=true;break;}
        PostMessageW(f.hwnd,WM_NULL,0,0); // Trigger the PrintExp UI thread's hook.
        if(WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0) break;
    }
    UnhookWindowsHookEx(hook);
    if(ready)CloseHandle(ready);
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
    FreeLibrary(localDll);
    if(!success) {
        Error(L"3D tab did not initialize. PrintExp is still running normally.\n"
              L"No printer commands were issued, and no PrintExp files were changed.");
        return 10;
    }
    return 0;
}
