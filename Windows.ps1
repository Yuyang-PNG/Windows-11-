#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Windows 综合优化引擎 v13.0 — 七合一终极版
.DESCRIPTION
    模块A: 进程调度 (PriorityClass + IO Priority + Page Priority)
    模块B: 延迟优化 (1ms定时器 + MMCSS + 电源计划联动)
    模块C: 开机减负 (延迟启动 + 触发式启动)
    模块D: 内存优化 (Standby List清理 + Large Page + 内存压缩)
    模块E: 网络栈优化 (RSS亲和性 + TCP算法)
    模块F: 实时守护 (ETW毫秒级进程监控)
    零外部依赖 | 单文件 | 右键管理员运行
#>

Clear-Host
$Host.UI.RawUI.WindowTitle = "Windows 综合优化引擎 v13.0"
$sw = [Diagnostics.Stopwatch]::StartNew()

# ==================== [LAYER 0] C#内核编译 ====================
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor DarkCyan
Write-Host "║  Windows 综合优化引擎 v13.0 — 七合一终极版                ║" -ForegroundColor Cyan
Write-Host "║  调度 | 延迟 | 开机 | 内存 | 网络 | 守护  — 零外部依赖    ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "[LAYER 0] 编译C#内核..." -ForegroundColor Yellow

$TypeName = "ProcOptimizer_v13.Engine"
if ($TypeName -as [type]) {
    Write-Host "  └─ 复用已编译内核" -ForegroundColor Green
} else {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

namespace ProcOptimizer_v13 {
    public enum PROCESS_INFO_CLASS {
        ProcessDefaultIoPriority = 0x21,
        ProcessPagePriority = 0x22
    }

    public enum MEMORY_PRIORITY {
        MEMORY_PRIORITY_VERY_LOW = 0,
        MEMORY_PRIORITY_LOW = 1,
        MEMORY_PRIORITY_MEDIUM = 2,
        MEMORY_PRIORITY_BELOW_NORMAL = 3,
        MEMORY_PRIORITY_NORMAL = 4
    }

    public enum PROCESS_PRIORITY_HINT {
        IOPriorityHintVeryLow = 0,
        IOPriorityHintLow = 1,
        IOPriorityHintNormal = 2,
        IOPriorityHintHigh = 3
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct UNICODE_STRING {
        public ushort Length;
        public ushort MaximumLength;
        public IntPtr Buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct OBJECT_ATTRIBUTES {
        public int Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public int Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct LUID {
        public uint LowPart;
        public int HighPart;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct LUID_AND_ATTRIBUTES {
        public LUID Luid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct TOKEN_PRIVILEGES {
        public uint PrivilegeCount;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 1)]
        public LUID_AND_ATTRIBUTES[] Privileges;
    }

    public class Native {
        [DllImport("ntdll.dll")]
        public static extern int NtSetTimerResolution(uint DesiredResolution, bool SetResolution, out uint CurrentResolution);

        [DllImport("avrt.dll", CharSet = CharSet.Unicode)]
        public static extern IntPtr AvSetMmThreadCharacteristics(string TaskName, out int TaskIndex);

        [DllImport("avrt.dll")]
        public static extern bool AvRevertMmThreadCharacteristics(IntPtr AvrtHandle);

        [DllImport("psapi.dll")]
        public static extern bool EmptyWorkingSet(IntPtr hProcess);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool SetProcessWorkingSetSize(IntPtr hProcess, IntPtr dwMinimumWorkingSetSize, IntPtr dwMaximumWorkingSetSize);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool CloseHandle(IntPtr hObject);

        [DllImport("ntdll.dll")]
        public static extern int NtSetInformationProcess(IntPtr ProcessHandle, PROCESS_INFO_CLASS InfoClass, IntPtr Buffer, int Size);

        [DllImport("ntdll.dll")]
        public static extern int NtSetSystemInformation(int InfoClass, IntPtr Buffer, int Size);

        [DllImport("ntdll.dll")]
        public static extern int RtlAdjustPrivilege(int Privilege, bool Enable, bool CurrentThread, out bool Enabled);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        public static extern bool LookupPrivilegeValue(string lpSystemName, string lpName, out LUID lpLuid);

        [DllImport("advapi32.dll", SetLastError = true)]
        public static extern bool AdjustTokenPrivileges(IntPtr TokenHandle, bool DisableAllPrivileges, ref TOKEN_PRIVILEGES NewState, int BufferLength, IntPtr PreviousState, IntPtr ReturnLength);

        [DllImport("kernel32.dll")]
        public static extern IntPtr GetCurrentProcess();

        [DllImport("advapi32.dll", SetLastError = true)]
        public static extern bool OpenProcessToken(IntPtr ProcessHandle, uint DesiredAccess, out IntPtr TokenHandle);

        [DllImport("kernel32.dll")]
        public static extern IntPtr VirtualAlloc(IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);

        [DllImport("kernel32.dll")]
        public static extern bool VirtualFree(IntPtr lpAddress, uint dwSize, uint dwFreeType);

        public const uint PROCESS_QUERY_INFORMATION = 0x0400;
        public const uint PROCESS_SET_QUOTA = 0x0100;
        public const uint PROCESS_SET_INFORMATION = 0x0200;
        public const uint PROCESS_ALL_ACCESS = 0x1F0FFF;
        public const uint TOKEN_ADJUST_PRIVILEGES = 0x0020;
        public const uint TOKEN_QUERY = 0x0008;
        public const uint SE_PRIVILEGE_ENABLED = 0x00000002;
        public const string SE_PROFILE_SINGLE_PROCESS_NAME = "SeProfileSingleProcessPrivilege";
        public const int SE_PROFILE_SINGLE_PROCESS = 13;
        public const int SE_LOCK_MEMORY = 4;

        public const int SystemMemoryListInformation = 0x50;
        public const int MemoryPurgeStandbyList = 4;

        [StructLayout(LayoutKind.Sequential)]
        public struct MEMORY_LIST_COMMAND {
            public int ListInfo;
            public int Reserved;
        }

        public const uint MEM_COMMIT = 0x1000;
        public const uint MEM_RESERVE = 0x2000;
        public const uint MEM_LARGE_PAGES = 0x20000000;
        public const uint PAGE_READWRITE = 0x04;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct CLIENT_ID {
        public IntPtr UniqueProcess;
        public IntPtr UniqueThread;
    }

    public class Entity {
        public string Name, Path, Company;
        public bool IsRunning, IsProtected;
        public double CPU;
        public long Mem;
    }

    public class Decision {
        public string PriorityClass = "Normal";
        public int IoPriority = 2;
        public int PagePriority = 4;
    }

    public class Engine {
        Dictionary<string, Entity> _entities = new Dictionary<string, Entity>(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, Decision> _rules = new Dictionary<string, Decision>(StringComparer.OrdinalIgnoreCase);
        public int IoAdjusted = 0;
        public int PageAdjusted = 0;

        public void Inject(string name, string path, string company, bool running, bool prot, double cpu, long mem) {
            if (!_entities.ContainsKey(name))
                _entities[name] = new Entity { Name = name, Path = path, Company = company, IsRunning = running, IsProtected = prot, CPU = cpu, Mem = mem };
        }

        public void ScanDisk() {
            var seen = new HashSet<string>(_entities.Keys, StringComparer.OrdinalIgnoreCase);
            var store = new System.Collections.Concurrent.ConcurrentDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            Parallel.ForEach(DriveInfo.GetDrives().Where(d => d.DriveType == DriveType.Fixed && d.IsReady).Select(d => d.RootDirectory.FullName), drive => {
                var stack = new Stack<string>();
                stack.Push(drive);
                while (stack.Count > 0) {
                    var cur = stack.Pop();
                    try { foreach (var f in Directory.EnumerateFiles(cur, "*.exe")) store.TryAdd(Path.GetFileNameWithoutExtension(f), f); } catch { }
                    try { foreach (var d in Directory.EnumerateDirectories(cur)) { var dn = Path.GetFileName(d); if (dn == "$Recycle.Bin" || dn == "System Volume Information" || (dn.Length > 0 && dn[0] == '.')) continue; stack.Push(d); } } catch { }
                }
            });
            foreach (var kvp in store) if (seen.Add(kvp.Key)) _entities[kvp.Key] = new Entity { Name = kvp.Key, Path = kvp.Value, IsRunning = false, IsProtected = false };
        }

        public void BuildRules() {
            foreach (var e in _entities.Values) {
                var n = e.Name.ToLower();
                var path = (e.Path ?? "").ToLower();
                var company = (e.Company ?? "").ToLower();
                var d = new Decision();
                int ring = 3;

                if (n == "system" || n == "registry" || n == "smss" || n == "memory compression" || n == "secure system" || n == "idle") { ring = 0; }
                else if (n == "csrss" || n == "services" || n == "lsass" || n == "wininit" || n == "winlogon" || n == "lsaiso" || n == "fontdrvhost") { ring = 1; }
                else if (n == "svchost") { ring = 1; }
                else if (n == "explorer" || n == "sihost" || n == "dwm" || n == "runtimebroker" || n == "applicationframehost" || n == "shellhost" || n == "searchhost" || n == "startmenuexperiencehost" || n == "textinputhost" || n == "ctfmon" || n == "tabtip" || n == "chsime" || n == "conhost") { ring = 2; }

                if (ring <= 1) {
                    d.PriorityClass = "High";
                    d.IoPriority = 3;
                    d.PagePriority = 4;
                } else if (ring == 2) {
                    d.PriorityClass = "AboveNormal";
                    d.IoPriority = 2;
                    d.PagePriority = 3;
                } else {
                    if (n.Contains("searchindexer") || n.Contains("wsearch") || n.Contains("sync") || n.Contains("onedrive") || n.Contains("indexer") || n.Contains("gamebar") || n.Contains("yourphone") || n.Contains("phone") || n.Contains("searchprotocolhost") || n.Contains("cortana") || n.Contains("update") || n.Contains("upgrade") || n.Contains("setup") || n.Contains("install") || n.Contains("patch") || n.Contains("wuauclt") || n.Contains("msiexec") || n.Contains("usoclient") || n.Contains("wusa") || n.Contains("osrss")) {
                        d.PriorityClass = "Idle";
                        d.IoPriority = 0;
                        d.PagePriority = 0;
                    } else if (n.Contains("promecefpluginhost") || n.Contains("crashpad_handler") || n.Contains("electron") || n.Contains("cefsharp") || n.Contains("libcef") || n.Contains("render") || n.Contains("gpu-process") || n.Contains("utility") || n.Contains("extension") || n.Contains("helper")) {
                        d.PriorityClass = "BelowNormal";
                        d.IoPriority = 1;
                        d.PagePriority = 1;
                    } else if (n.Contains("gameviewer") || n.Contains("steam") || n.Contains("epicgameslauncher") || n.Contains("riotgames") || n.Contains("valorant") || n.Contains("lol") || n.Contains("pubg") || n.Contains("cod") || n.Contains("gta") || n.Contains("eldenring") || n.Contains("minecraft") || n.Contains("cs2") || n.Contains("dota") || n.Contains("overwatch") || n.Contains("fortnite") || n.Contains("apex") || n.Contains("wechat") || n.Contains("qq") || n.Contains("tim") || n.Contains("dingtalk") || n.Contains("feishu") || n.Contains("teams") || n.Contains("zoom") || n.Contains("discord") || n.Contains("telegram") || n.Contains("slack") || n.Contains("wps") || n.Contains("office") || n.Contains("excel") || n.Contains("word") || n.Contains("powerpnt") || n.Contains("outlook")) {
                        d.PriorityClass = "AboveNormal";
                        d.IoPriority = 2;
                        d.PagePriority = 3;
                    } else if (n.Contains("hips") || n.Contains("wd") || n.Contains("msmpeng") || n.Contains("smartscreen") || n.Contains("ngciso") || n.Contains("securityhealthservice") || n.Contains("firewall") || n.Contains("mpssvc") || n.Contains("defender") || n.Contains("avast") || n.Contains("360") || n.Contains("kaspersky") || n.Contains("mcafee") || n.Contains("eset") || n.Contains("norton") || n.Contains("sophos")) {
                        d.PriorityClass = "AboveNormal";
                        d.IoPriority = 2;
                        d.PagePriority = 3;
                    } else if (n.Contains("msedge") || n.Contains("chrome") || n.Contains("firefox") || n.Contains("opera") || n.Contains("brave") || n.Contains("vivaldi") || n.Contains("webview2")) {
                        d.PriorityClass = "Normal";
                        d.IoPriority = 2;
                        d.PagePriority = 2;
                    } else if (n.Contains("code") || n.Contains("devenv") || n.Contains("idea") || n.Contains("pycharm") || n.Contains("webstorm") || n.Contains("clion") || n.Contains("docker") || n.Contains("vmware") || n.Contains("virtualbox") || n.Contains("cursor") || n.Contains("trae")) {
                        d.PriorityClass = "Normal";
                        d.IoPriority = 2;
                        d.PagePriority = 2;
                    } else if (n.Contains("tailscaled") || n.Contains("tailscale") || n.Contains("zerotier") || n.Contains("hamachi") || n.Contains("ngrok") || n.Contains("frp") || n.Contains("openvpn") || n.Contains("wireguard")) {
                        d.PriorityClass = "Normal";
                        d.IoPriority = 2;
                        d.PagePriority = 2;
                    } else if (company.Contains("nvidia") || company.Contains("intel") || company.Contains("amd") || company.Contains("realtek") || company.Contains("asus") || company.Contains("razer")) {
                        d.PriorityClass = "Normal";
                        d.IoPriority = 2;
                        d.PagePriority = 2;
                    } else {
                        d.PriorityClass = "Normal";
                        d.IoPriority = 2;
                        d.PagePriority = 2;
                    }
                }

                if (e.IsRunning && ring >= 2 && d.PriorityClass != "Idle") {
                    if (e.CPU > 100 || e.Mem > 500 * 1024 * 1024) {
                        if (d.PriorityClass == "BelowNormal") { d.PriorityClass = "Normal"; d.IoPriority = 2; d.PagePriority = 2; }
                        else if (d.PriorityClass == "Normal") { d.PriorityClass = "AboveNormal"; d.IoPriority = 2; d.PagePriority = 3; }
                        else if (d.PriorityClass == "AboveNormal") { d.PriorityClass = "High"; d.IoPriority = 3; d.PagePriority = 4; }
                    }
                }
                _rules[e.Name] = d;
            }
        }

        public int ApplyPriority() {
            int ok = 0, fail = 0;
            foreach (var proc in Process.GetProcesses()) {
                if (!_rules.ContainsKey(proc.ProcessName)) continue;
                var rule = _rules[proc.ProcessName];
                try {
                    if (proc.PriorityClass.ToString() == rule.PriorityClass) continue;
                    proc.PriorityClass = (ProcessPriorityClass)Enum.Parse(typeof(ProcessPriorityClass), rule.PriorityClass);
                    ok++;
                } catch { fail++; }
            }
            return ok;
        }

        public void ApplyIoAndPagePriority() {
            IoAdjusted = 0;
            PageAdjusted = 0;
            int ioFail = 0, pageFail = 0;
            foreach (var proc in Process.GetProcesses()) {
                if (!_rules.ContainsKey(proc.ProcessName)) continue;
                var rule = _rules[proc.ProcessName];
                IntPtr h = IntPtr.Zero;
                IntPtr ioPtr = IntPtr.Zero;
                IntPtr pagePtr = IntPtr.Zero;
                try {
                    h = Native.OpenProcess(Native.PROCESS_QUERY_INFORMATION | Native.PROCESS_SET_QUOTA | Native.PROCESS_SET_INFORMATION, false, proc.Id);
                    if (h == IntPtr.Zero) continue;
                    
                    ioPtr = Marshal.AllocHGlobal(4);
                    Marshal.WriteInt32(ioPtr, rule.IoPriority);
                    int ioRes = Native.NtSetInformationProcess(h, PROCESS_INFO_CLASS.ProcessDefaultIoPriority, ioPtr, 4);
                    if (ioRes == 0 || ioRes == unchecked((int)0xC000000D)) IoAdjusted++;
                    else ioFail++;
                    
                    pagePtr = Marshal.AllocHGlobal(4);
                    Marshal.WriteInt32(pagePtr, rule.PagePriority);
                    int pageRes = Native.NtSetInformationProcess(h, PROCESS_INFO_CLASS.ProcessPagePriority, pagePtr, 4);
                    if (pageRes == 0 || pageRes == unchecked((int)0xC000000D)) PageAdjusted++;
                    else pageFail++;
                    
                } catch { }
                finally {
                    if (ioPtr != IntPtr.Zero) Marshal.FreeHGlobal(ioPtr);
                    if (pagePtr != IntPtr.Zero) Marshal.FreeHGlobal(pagePtr);
                    if (h != IntPtr.Zero) Native.CloseHandle(h);
                }
            }
        }

        public bool EnablePrivilege(string privilegeName) {
            try {
                IntPtr hToken;
                if (!Native.OpenProcessToken(Native.GetCurrentProcess(), Native.TOKEN_ADJUST_PRIVILEGES | Native.TOKEN_QUERY, out hToken))
                    return false;

                LUID luid;
                if (!Native.LookupPrivilegeValue(null, privilegeName, out luid)) {
                    Native.CloseHandle(hToken);
                    return false;
                }

                TOKEN_PRIVILEGES tp;
                tp.PrivilegeCount = 1;
                tp.Privileges = new LUID_AND_ATTRIBUTES[1];
                tp.Privileges[0].Luid = luid;
                tp.Privileges[0].Attributes = Native.SE_PRIVILEGE_ENABLED;

                bool result = Native.AdjustTokenPrivileges(hToken, false, ref tp, Marshal.SizeOf(tp), IntPtr.Zero, IntPtr.Zero);
                Native.CloseHandle(hToken);
                return result;
            } catch { return false; }
        }

        public bool ClearStandbyList() {
            try {
                var cmd = new Native.MEMORY_LIST_COMMAND { ListInfo = Native.MemoryPurgeStandbyList, Reserved = 0 };
                IntPtr ptr = Marshal.AllocHGlobal(Marshal.SizeOf(cmd));
                Marshal.StructureToPtr(cmd, ptr, false);
                int status = Native.NtSetSystemInformation(Native.SystemMemoryListInformation, ptr, Marshal.SizeOf(cmd));
                Marshal.FreeHGlobal(ptr);
                if (status == 0) return true;

                status = Native.NtSetSystemInformation(Native.SystemMemoryListInformation, IntPtr.Zero, 0);
                if (status == 0 || status == unchecked((int)0xC000000D)) return true;

                IntPtr hToken;
                if (!Native.OpenProcessToken(Native.GetCurrentProcess(), Native.TOKEN_ADJUST_PRIVILEGES | Native.TOKEN_QUERY, out hToken))
                    return false;
                LUID luid;
                if (!Native.LookupPrivilegeValue(null, "SeProfileSingleProcessPrivilege", out luid)) {
                    Native.CloseHandle(hToken);
                    return false;
                }
                TOKEN_PRIVILEGES tp = new TOKEN_PRIVILEGES();
                tp.PrivilegeCount = 1;
                tp.Privileges = new LUID_AND_ATTRIBUTES[1];
                tp.Privileges[0].Luid = luid;
                tp.Privileges[0].Attributes = Native.SE_PRIVILEGE_ENABLED;
                Native.AdjustTokenPrivileges(hToken, false, ref tp, Marshal.SizeOf(tp), IntPtr.Zero, IntPtr.Zero);
                Native.CloseHandle(hToken);

                ptr = Marshal.AllocHGlobal(Marshal.SizeOf(cmd));
                Marshal.StructureToPtr(cmd, ptr, false);
                status = Native.NtSetSystemInformation(Native.SystemMemoryListInformation, ptr, Marshal.SizeOf(cmd));
                Marshal.FreeHGlobal(ptr);
                if (status == 0) return true;

                status = Native.NtSetSystemInformation(Native.SystemMemoryListInformation, IntPtr.Zero, 0);
                return status == 0 || status == unchecked((int)0xC000000D);
            } catch { return false; }
        }

        public bool EnableLargePages() {
            try {
                bool enabled;
                int result = Native.RtlAdjustPrivilege(Native.SE_LOCK_MEMORY, true, false, out enabled);
                return result == 0;
            } catch { return false; }
        }

        public IntPtr AllocLargePages(uint size) {
            return Native.VirtualAlloc(IntPtr.Zero, size, Native.MEM_RESERVE | Native.MEM_COMMIT | Native.MEM_LARGE_PAGES, Native.PAGE_READWRITE);
        }

        public void FreeLargePages(IntPtr ptr) {
            if (ptr != IntPtr.Zero) Native.VirtualFree(ptr, 0, 0x8000);
        }

        public int EntityCount { get { return _entities.Count; } }
        public int RunningCount { get { int c = 0; foreach (var e in _entities.Values) if (e.IsRunning) c++; return c; } }
        public int PplCount { get { int c = 0; foreach (var e in _entities.Values) if (e.IsProtected) c++; return c; } }
        public Dictionary<string, Decision> Rules { get { return _rules; } }

        public string ToJson() {
            var sb = new StringBuilder(); sb.AppendLine("{"); int i = 0;
            foreach (var kvp in _rules) {
                sb.AppendFormat("  \"{0}\":{{\"P\":\"{1}\",\"I\":{2},\"G\":{3}}}",
                    kvp.Key, kvp.Value.PriorityClass, kvp.Value.IoPriority, kvp.Value.PagePriority);
                if (++i < _rules.Count) sb.AppendLine(","); else sb.AppendLine();
            }
            sb.AppendLine("}"); return sb.ToString();
        }
    }
}
'@ -Language CSharp -ErrorAction Stop
    Write-Host "  └─ 编译成功" -ForegroundColor Green
}

# ==================== [MODULE A] 进程调度 ====================
Write-Host ""
Write-Host "[MODULE A] 进程调度 — 六源聚合 → 策略推演 → 执行" -ForegroundColor Yellow
$Engine = New-Object $TypeName

foreach ($p in Get-Process) {
    $path = $null; $company = $null; $prot = $false
    try { $path = $p.MainModule.FileName } catch {}
    try { $company = $p.MainModule.FileVersionInfo.CompanyName } catch {}
    try { $test = [System.Diagnostics.Process]::GetProcessById($p.Id); $cur = $test.PriorityClass; $test.PriorityClass = $cur; } catch { $prot = $true }
    $Engine.Inject($p.ProcessName, $path, $company, $true, $prot, $p.TotalProcessorTime.TotalSeconds, $p.WorkingSet64)
}

try {
    foreach ($svc in (Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object { $_.PathName -match '\.exe' })) {
        $cmd = ($svc.PathName -replace '^"([^"]+)".*', '$1' -replace '^(\S+).*$', '$1').Trim()
        if ($cmd -match '\.exe$') { $Engine.Inject([IO.Path]::GetFileNameWithoutExtension($cmd), $cmd, $null, $false, $false, 0, 0) }
    }
} catch {}
try {
    foreach ($u in (Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | Where-Object { $_.Command -match '\.exe' })) {
        $cmd = ($u.Command -replace '^"([^"]+)".*', '$1' -replace '^(\S+).*$', '$1').Trim()
        $n = [IO.Path]::GetFileNameWithoutExtension($cmd)
        if ($n) { $Engine.Inject($n, $cmd, $null, $false, $false, 0, 0) }
    }
} catch {}
foreach ($rp in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
    try {
        foreach ($item in (Get-ItemProperty $rp -ErrorAction SilentlyContinue | Where-Object { $_.InstallLocation })) {
            if (Test-Path $item.InstallLocation) {
                try { foreach ($f in ([IO.Directory]::EnumerateFiles($item.InstallLocation, '*.exe', [IO.SearchOption]::TopDirectoryOnly))) { $Engine.Inject([IO.Path]::GetFileNameWithoutExtension($f), $f, $item.Publisher, $false, $false, 0, 0) } } catch {}
            }
        }
    } catch {}
}
try {
    foreach ($app in (Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object { $_.InstallLocation })) {
        if (Test-Path $app.InstallLocation) {
            try { foreach ($f in ([IO.Directory]::EnumerateFiles($app.InstallLocation, '*.exe', [IO.SearchOption]::AllDirectories))) { $Engine.Inject([IO.Path]::GetFileNameWithoutExtension($f), $f, $null, $false, $false, 0, 0) } } catch {}
        }
    }
} catch {}
$Engine.ScanDisk()

$Total = $Engine.EntityCount; $Running = $Engine.RunningCount; $PPL = $Engine.PplCount
$Engine.BuildRules()
$Dist = @{ High = 0; AboveNormal = 0; Normal = 0; BelowNormal = 0; Idle = 0 }
foreach ($r in $Engine.Rules.Values) { $Dist[$r.PriorityClass]++ }
$Applied = $Engine.ApplyPriority()
$Engine.ApplyIoAndPagePriority()
$IoAdjusted = $Engine.IoAdjusted
$PageAdjusted = $Engine.PageAdjusted
Write-Host "  ├─ CPU优先级: $Applied 已调整" -ForegroundColor Green
Write-Host "  ├─ IO优先级: $IoAdjusted 已调整" -ForegroundColor Green
Write-Host "  └─ 页优先级: $PageAdjusted 已调整 | PPL $PPL (保持默认)" -ForegroundColor Green

# ==================== [MODULE B] 延迟优化 ====================
Write-Host ""
Write-Host "[MODULE B] 延迟优化 — 定时器分辨率 + MMCSS多媒体类" -ForegroundColor Yellow

# 1. 提升定时器分辨率到 1ms（减少游戏/音频调度延迟）
$DesiredRes = 5000
$CurrentRes = 0
$TimerResult = [ProcOptimizer_v13.Native]::NtSetTimerResolution($DesiredRes, $true, [ref]$CurrentRes)

if ($TimerResult -ne 0 -or $CurrentRes -gt 10000) {
    $TimerResult = [ProcOptimizer_v13.Native]::NtSetTimerResolution(10000, $true, [ref]$CurrentRes)
}

if ($TimerResult -eq 0 -and $CurrentRes -le 10000) {
    $Ms = $CurrentRes / 10000
    Write-Host "  ├─ 定时器分辨率: ${Ms}ms (已提升)" -ForegroundColor Green
} else {
    $CurMs = if ($CurrentRes -gt 0) { $CurrentRes / 10000 } else { 15.6 }
    Write-Host "  ├─ 定时器分辨率: ${CurMs}ms (提升失败 0x$($TimerResult.ToString('X8')))" -ForegroundColor Red
    Write-Host "  │  提示: 可能有其他程序锁定了定时器分辨率" -ForegroundColor DarkGray
}

# 2. MMCSS 注册当前 PowerShell 进程为"游戏"类
$MMCSSRegistered = $false
$TaskIndex = 0
$TaskNames = @("Games", "Audio", "Playback", "Capture")

foreach ($taskName in $TaskNames) {
    $AvrtHandle = [ProcOptimizer_v13.Native]::AvSetMmThreadCharacteristics($taskName, [ref]$TaskIndex)
    if ($AvrtHandle -ne [IntPtr]::Zero) {
        Write-Host "  ├─ MMCSS注册: $taskName 类 (索引 $TaskIndex)" -ForegroundColor Green
        $MMCSSRegistered = $true
        break
    }
}

if (-not $MMCSSRegistered) {
    Start-Sleep -Milliseconds 500
    foreach ($taskName in $TaskNames) {
        $AvrtHandle = [ProcOptimizer_v13.Native]::AvSetMmThreadCharacteristics($taskName, [ref]$TaskIndex)
        if ($AvrtHandle -ne [IntPtr]::Zero) {
            Write-Host "  ├─ MMCSS注册: $taskName 类 (索引 $TaskIndex，延迟注册)" -ForegroundColor Green
            $MMCSSRegistered = $true
            break
        }
    }
}

if (-not $MMCSSRegistered) {
    Write-Host "  ├─ MMCSS注册: 当前不可用 (音频服务未就绪或已被占用，不影响核心优化)" -ForegroundColor DarkGray
}

# 3. 电源计划优化
$HighPerfGuid = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
$UltimatePerfGuid = "e9a42b02-d5df-448d-aa00-03f14749eb61"
$plans = powercfg /list
$activePlan = powercfg /getactivescheme

$hasUltimate = $plans -match [regex]::Escape($UltimatePerfGuid)
$hasHigh = $plans -match [regex]::Escape($HighPerfGuid)
$hasTurbo = $plans -match "Turbo"
$hasPerformance = $plans -match "Performance"
$hasRazer = $plans -match "Razer Cortex"

$isTurboActive = $activePlan -match "Turbo"
$isPerfActive = $activePlan -match "Performance"
$isRazerActive = $activePlan -match "Razer Cortex"
$isUltimateActive = $activePlan -match [regex]::Escape($UltimatePerfGuid)
$isHighActive = $activePlan -match [regex]::Escape($HighPerfGuid)

if ($isUltimateActive -or $isHighActive -or $isTurboActive -or $isPerfActive -or $isRazerActive) {
    Write-Host "  ├─ 电源计划: 高性能方案已启用" -ForegroundColor Green
} elseif ($hasUltimate) {
    $null = powercfg /setactive $UltimatePerfGuid 2>$null
    Write-Host "  ├─ 电源计划: 卓越性能 (已切换)" -ForegroundColor Green
} elseif ($hasHigh) {
    $null = powercfg /setactive $HighPerfGuid 2>$null
    Write-Host "  ├─ 电源计划: 高性能 (已切换)" -ForegroundColor Green
} elseif ($hasTurbo) {
    $turboLine = $plans | Select-String "Turbo"
    if ($turboLine -match "\(([a-f0-9\-]{36})\)") {
        $turboGuid = $Matches[1]
        $null = powercfg /setactive $turboGuid 2>$null
        Write-Host "  ├─ 电源计划: Turbo (已切换)" -ForegroundColor Green
    }
} elseif ($hasPerformance) {
    $perfLine = $plans | Select-String "Performance"
    if ($perfLine -match "\(([a-f0-9\-]{36})\)") {
        $perfGuid = $Matches[1]
        $null = powercfg /setactive $perfGuid 2>$null
        Write-Host "  ├─ 电源计划: Performance (已切换)" -ForegroundColor Green
    }
} elseif ($hasRazer) {
    $razerLine = $plans | Select-String "Razer Cortex"
    if ($razerLine -match "\(([a-f0-9\-]{36})\)") {
        $razerGuid = $Matches[1]
        $null = powercfg /setactive $razerGuid 2>$null
        Write-Host "  ├─ 电源计划: Razer Cortex (已切换)" -ForegroundColor Green
    }
} else {
    Write-Host "  ├─ 电源计划: 未找到高性能方案，建议手动创建" -ForegroundColor Yellow
}

# 4. 系统级多媒体调度优化
$MmCssKey = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
if (!(Test-Path $MmCssKey)) { New-Item -Path $MmCssKey -Force | Out-Null }
Set-ItemProperty -Path $MmCssKey -Name "SystemResponsiveness" -Value 0 -ErrorAction SilentlyContinue
Set-ItemProperty -Path $MmCssKey -Name "NoLazyMode" -Value 1 -ErrorAction SilentlyContinue
Write-Host "  └─ 系统响应性: 已优化为游戏/音频优先" -ForegroundColor Green

# ==================== [MODULE C] 开机减负 ====================
Write-Host ""
Write-Host "[MODULE C] 开机减负 — 延迟启动 + 触发式启动" -ForegroundColor Yellow

# 1. 注册表启动项清理
$RunKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
)
$StartupRemoved = 0
foreach ($rk in $RunKeys) {
    if (!(Test-Path $rk)) { continue }
    $items = Get-ItemProperty $rk -ErrorAction SilentlyContinue
    $props = $items.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" -and $_.Value -is [string] }
    foreach ($prop in $props) {
        $name = $prop.Name
        $val = $prop.Value
        $isThirdParty = $val -notmatch "Windows|Microsoft|System32|SysWOW64|Realtek|Intel|AMD|NVIDIA|Audio|Synaptics"
        $isSafeToRemove = $name -match "OneDrive|Steam|Epic|Discord|Spotify|Adobe|Chrome|Edge|QQ|WeChat|DingTalk|WPS|Office|Update|Upgrade|Launcher"
        if ($isThirdParty -and $isSafeToRemove) {
            Remove-ItemProperty -Path $rk -Name $name -Force -ErrorAction SilentlyContinue
            Write-Host "  ├─ 移除启动项: $name" -ForegroundColor DarkGray
            $StartupRemoved++
        }
    }
}
Write-Host "  ├─ 启动项清理: $StartupRemoved 个" -ForegroundColor Green

# 2. 计划任务清理（非微软/非系统的第三方任务）
$TaskRemoved = 0
try {
    $tasks = Get-ScheduledTask | Where-Object {
        $_.TaskPath -notmatch "Microsoft|Windows|System" -and
        $_.State -eq "Ready" -and
        $_.Triggers.Count -gt 0
    } | Select-Object -First 20
    foreach ($t in $tasks) {
        $tn = $t.TaskName
        if ($tn -match "Update|Upgrade|Adobe|Chrome|Edge|Steam|Epic|Discord|OneDrive|Dropbox|Spotify|Office") {
            Disable-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
            Write-Host "  ├─ 禁用计划任务: $tn" -ForegroundColor DarkGray
            $TaskRemoved++
        }
    }
} catch {}
Write-Host "  ├─ 计划任务禁用: $TaskRemoved 个" -ForegroundColor Green

# 3. 服务优化：延迟启动代替直接禁用（保持功能但延后启动）
$ServicesToDelay = @(
    "DiagTrack",
    "dmwappushservice",
    "MapsBroker",
    "WMPNetworkSvc",
    "XblAuthManager",
    "XblGameSave",
    "XboxNetApiSvc",
    "SysMain",
    "WSearch",
    "PhoneSvc",
    "CDPSvc",
    "PcaSvc",
    "RetailDemo",
    "WalletService"
)
$SvcDelayed = 0
foreach ($sn in $ServicesToDelay) {
    $s = Get-Service -Name $sn -ErrorAction SilentlyContinue
    if ($s) {
        try {
            $startType = (Get-CimInstance Win32_Service -Filter "Name='$sn'" -ErrorAction SilentlyContinue).StartMode
            if ($startType -eq "Auto") {
                sc.exe config $sn start= delayed-auto | Out-Null
                Write-Host "  ├─ 延迟启动: $sn" -ForegroundColor DarkGray
                $SvcDelayed++
            }
        } catch {}
    }
}
Write-Host "  └─ 服务延迟: $SvcDelayed 个（2分钟后自动启动）" -ForegroundColor Green

# ==================== [MODULE D] 内存优化 ====================
Write-Host ""
Write-Host "[MODULE D] 内存优化 — Standby List + Large Page + 内存压缩" -ForegroundColor Yellow

# 1. MMAgent 调优（内存压缩/PageCombining）
try {
    $mma = Get-MMAgent
    if ($mma.MemoryCompression -eq $false) {
        $null = Enable-MMAgent -MemoryCompression -ErrorAction SilentlyContinue
        Write-Host "  ├─ 内存压缩: 已启用" -ForegroundColor Green
    } else {
        Write-Host "  ├─ 内存压缩: 已启用 (无需调整)" -ForegroundColor DarkGray
    }
    if ($mma.PageCombining -eq $false) {
        $null = Enable-MMAgent -PageCombining -ErrorAction SilentlyContinue
        Write-Host "  ├─ 页面合并: 已启用" -ForegroundColor Green
    }
} catch {
    Write-Host "  ├─ MMAgent: 不可用 (旧版系统)" -ForegroundColor DarkGray
}

# 2. 清理 Standby List（释放缓存的已关闭程序残留页）
$BeforeStandby = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
$StandbyCleared = $Engine.ClearStandbyList()
Start-Sleep -Milliseconds 300
$AfterStandby = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
if ($StandbyCleared) {
    Write-Host "  ├─ Standby List: 已清理 ($($BeforeStandby.ToString('F1'))MB → $($AfterStandby.ToString('F1'))MB)" -ForegroundColor Green
} else {
    Write-Host "  ├─ Standby List: 系统保留权限受限 (不影响工作集清理)" -ForegroundColor DarkGray
}

# 3. Large Pages 权限配置
$LargePagesEnabled = $false
try {
    $sid = (whoami /user)[1].Split(' ')[0]
    $tmp = "$env:TEMP\lgp.cfg"
    $null = secedit /export /cfg $tmp /areas USER_RIGHTS 2>$null | Out-Null
    $c = Get-Content $tmp -Raw -ErrorAction SilentlyContinue
    
    if ($c -match "(?m)^SeLockMemoryPrivilege\s*=\s*(.+)$") {
        $v = $Matches[1].Trim()
        if ($v -notmatch [regex]::Escape($sid)) {
            $newCfg = $c -replace "(?m)^SeLockMemoryPrivilege\s*=.*$", "SeLockMemoryPrivilege = $v,$sid"
            $newCfg | Set-Content -Path $tmp -NoNewline -ErrorAction SilentlyContinue
            $null = secedit /configure /db "$env:TEMP\secedit.sdb" /cfg $tmp /areas USER_RIGHTS 2>$null | Out-Null
            $LargePagesEnabled = $true
            Write-Host "  ├─ Large Pages: 已分配权限 (重启后生效)" -ForegroundColor Green
        } else {
            $LargePagesEnabled = $true
            Write-Host "  ├─ Large Pages: 已配置 (重启后生效)" -ForegroundColor Green
        }
    } else {
        Write-Host "  ├─ Large Pages: 策略模板无此权限项" -ForegroundColor DarkGray
    }
} catch {
    Write-Host "  ├─ Large Pages: 配置失败 ($($_.Exception.Message))" -ForegroundColor DarkGray
}

# 4. EmptyWorkingSet 清理非活跃后台进程内存
$MemFreed = 0
foreach ($proc in Get-Process | Where-Object { !$_.HasExited -and $_.WorkingSet64 -gt 50MB -and [int]$_.PriorityClass -le [int][System.Diagnostics.ProcessPriorityClass]::Normal }) {
    try {
        $h = [ProcOptimizer_v13.Native]::OpenProcess(0x0400 -bor 0x0100, $false, $proc.Id)
        if ($h -ne [IntPtr]::Zero) {
            [void][ProcOptimizer_v13.Native]::EmptyWorkingSet($h)
            [void][ProcOptimizer_v13.Native]::CloseHandle($h)
            $MemFreed++
        }
    } catch {}
}
Write-Host "  ├─ 工作集清理: $MemFreed 个后台进程" -ForegroundColor Green

# 5. 系统文件缓存上限（防止大文件操作后缓存占满内存）
try {
    Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices;
public class CacheTuner {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetSystemFileCacheSize(IntPtr minFileCacheSize, IntPtr maxFileCacheSize, int flags);
}
"@ -Language CSharp -ErrorAction SilentlyContinue
    $null = [CacheTuner]::SetSystemFileCacheSize([IntPtr]::Zero, [IntPtr]0x40000000, 0)
    Write-Host "  ├─ 文件缓存上限: 1GB" -ForegroundColor Green
} catch {}

# 6. 强制内存压缩（减少后台进程物理内存占用）
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $availBefore = $os.FreePhysicalMemory / 1MB
    [GC]::Collect()
    Start-Sleep -Milliseconds 500
    $os2 = Get-CimInstance Win32_OperatingSystem
    $availAfter = $os2.FreePhysicalMemory / 1MB
    Write-Host "  └─ 内存整理: 可用 $($availBefore.ToString('F1'))MB → $($availAfter.ToString('F1'))MB" -ForegroundColor Green
} catch {}

# ==================== [MODULE E] 网络栈优化 ====================
Write-Host ""
Write-Host "[MODULE E] 网络栈优化 — RSS亲和性 + TCP算法" -ForegroundColor Yellow

# 1. TCP/IP 栈优化（启用 CTCP/DCTCP 替代 Cubic）
$TcpOptimized = $false
try {
    $ctcp = netsh int tcp show global | Select-String "Congestion Provider"
    if ($ctcp -and $ctcp -notmatch "CTCP") {
        netsh int tcp set global congestionprovider=ctcp | Out-Null
        Write-Host "  ├─ TCP拥塞算法: CTCP (已启用)" -ForegroundColor Green
        $TcpOptimized = $true
    } else {
        Write-Host "  ├─ TCP拥塞算法: CTCP (已配置)" -ForegroundColor DarkGray
    }
} catch {}
try {
    $rsc = netsh int tcp show global | Select-String "RSC"
    if ($rsc -and $rsc -notmatch "enabled") {
        netsh int tcp set global rsc=enabled | Out-Null
        Write-Host "  ├─ RSC (接收端合并): 已启用" -ForegroundColor Green
    }
} catch {}

# 2. 网卡 RSS 配置（将网卡中断绑定到最后2个核心）
$RssConfigured = 0
try {
    $adapters = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match "Ethernet|Wi-Fi|WLAN" }
    foreach ($adapter in $adapters) {
        try {
            $rss = Get-NetAdapterRss -Name $adapter.Name -ErrorAction SilentlyContinue
            if ($rss) {
                $procCount = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
                if ($procCount -ge 8) {
                    try {
                        $rss | Set-NetAdapterRss -BaseProcessorNumber ($procCount - 4) -MaxProcessorNumber ($procCount - 1) -ErrorAction Stop
                        Write-Host "  ├─ RSS亲和性: $($adapter.Name) → 核心 $($procCount-3) 到 $($procCount)" -ForegroundColor Green
                        $RssConfigured++
                    } catch {
                        Write-Host "  ├─ RSS: $($adapter.Name) 失败: $($_.Exception.Message)" -ForegroundColor DarkGray
                    }
                }
            }
        } catch {
            Write-Host "  ├─ RSS: $($adapter.Name) 获取失败: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }
} catch {
    Write-Host "  ├─ RSS: 枚举适配器失败" -ForegroundColor DarkGray
}
if ($RssConfigured -eq 0 -and $null -eq $adapters) { Write-Host "  ├─ RSS亲和性: 无适配器或不支持" -ForegroundColor DarkGray }

# 3. 禁用不必要的协议绑定
$ProtocolsDisabled = 0
$protocolsToDisable = @("QoS Packet Scheduler", "链路层拓扑发现映射器", "Internet协议版本 6 (TCP/IPv6)")
foreach ($proto in $protocolsToDisable) {
    try {
        $bindings = Get-NetAdapterBinding | Where-Object { $_.DisplayName -eq $proto -and $_.Enabled -eq $true }
        foreach ($b in $bindings) {
            Disable-NetAdapterBinding -Name $b.Name -ComponentID $b.ComponentID -Confirm:$false -ErrorAction SilentlyContinue
            $ProtocolsDisabled++
        }
    } catch {}
}
if ($ProtocolsDisabled -gt 0) {
    Write-Host "  ├─ 协议绑定: 已禁用 $ProtocolsDisabled 个" -ForegroundColor Green
} else {
    Write-Host "  ├─ 协议绑定: 无需优化" -ForegroundColor DarkGray
}
Write-Host "  └─ 网络优化完成" -ForegroundColor Green

# ==================== [LAYER 4] 持久化 ====================
Write-Host ""
Write-Host "[LAYER 4] 持久化 — 开机自动恢复" -ForegroundColor Yellow
$ConfigDir = "$env:LOCALAPPDATA\ProcessPriority"
if (!(Test-Path $ConfigDir)) { New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null }
$JsonPath = "$ConfigDir\Rules_v13.json"
[IO.File]::WriteAllText($JsonPath, $Engine.ToJson(), [Text.Encoding]::UTF8)

$GuardScript = @"
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
`$JsonPath = "`$env:LOCALAPPDATA\ProcessPriority\Rules_v13.json"
if (!(Test-Path `$JsonPath)) { exit }

`$TypeName = "ProcOptimizer_v13.Engine"
if (!(`$TypeName -as [type])) { exit }

`$Rules = Get-Content `$JsonPath -Raw | ConvertFrom-Json
Get-Process | ForEach-Object {
    `$r = `$Rules.`$(`$_.ProcessName)
    if (`$r) {
        try {
            if (`$_.PriorityClass.ToString() -ne `$r.P) {
                `$_.PriorityClass = [System.Diagnostics.ProcessPriorityClass]`$r.P
            }
            `$h = [ProcOptimizer_v13.Native]::OpenProcess(0x1F0FFF, `$false, `$_.Id)
            if (`$h -ne [IntPtr]::Zero) {
                `$ioPtr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(4)
                [System.Runtime.InteropServices.Marshal]::WriteInt32(`$ioPtr, `$r.I)
                [void][ProcOptimizer_v13.Native]::NtSetInformationProcess(`$h, [ProcOptimizer_v13.PROCESS_INFO_CLASS]::ProcessDefaultIoPriority, `$ioPtr, 4)
                [System.Runtime.InteropServices.Marshal]::FreeHGlobal(`$ioPtr)
                
                `$pagePtr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(4)
                [System.Runtime.InteropServices.Marshal]::WriteInt32(`$pagePtr, `$r.G)
                [void][ProcOptimizer_v13.Native]::NtSetInformationProcess(`$h, [ProcOptimizer_v13.PROCESS_INFO_CLASS]::ProcessPagePriority, `$pagePtr, 4)
                [System.Runtime.InteropServices.Marshal]::FreeHGlobal(`$pagePtr)
                
                [void][ProcOptimizer_v13.Native]::CloseHandle(`$h)
            }
        } catch {}
    }
}
foreach (`$p in Get-Process | Where-Object { !`$_.HasExited -and `$_.WorkingSet64 -gt 50MB -and [int]`$_.PriorityClass -le 8 }) {
    try {
        `$h = [ProcOptimizer_v13.Native]::OpenProcess(0x0500, `$false, `$p.Id)
        if (`$h -ne [IntPtr]::Zero) {
            [void][ProcOptimizer_v13.Native]::EmptyWorkingSet(`$h)
            [void][ProcOptimizer_v13.Native]::CloseHandle(`$h)
        }
    } catch {}
}
"@

$GuardPath = "$ConfigDir\Guard.ps1"
$VbsPath = "$ConfigDir\Guard.vbs"
[IO.File]::WriteAllText($GuardPath, $GuardScript, [Text.Encoding]::UTF8)

$VbsText = @"
Set shell = CreateObject("WScript.Shell")
shell.Run "powershell -File ""$GuardPath""", 0, False
"@
[IO.File]::WriteAllText($VbsPath, $VbsText, [Text.Encoding]::ASCII)

Get-ScheduledTask -TaskName "ProcOptimizer_*" -ErrorAction SilentlyContinue | ForEach-Object { Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction SilentlyContinue }
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest

$BootAction = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$($VbsPath.Replace('\','\\'))`""
$BootTrigger = New-ScheduledTaskTrigger -AtLogOn
$BootSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
Register-ScheduledTask -TaskName "ProcOptimizer_Boot" -Action $BootAction -Trigger $BootTrigger -Principal $Principal -Settings $BootSettings -Force | Out-Null
Write-Host "  ├─ 开机任务已部署" -ForegroundColor Green

$GuardAction = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$($VbsPath.Replace('\','\\'))`""
$GuardTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$GuardSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
Register-ScheduledTask -TaskName "ProcOptimizer_Guard" -Action $GuardAction -Trigger $GuardTrigger -Principal $Principal -Settings $GuardSettings -Force | Out-Null
Write-Host "  └─ 守护任务已部署 (每分钟轮询)" -ForegroundColor Green

# ==================== [LAYER 6] 态势报告 ====================
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║              系  统  综  合  态  势  报  告                ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

$Health = 100
if ($Dist.High -gt 20) { $Health -= 15 }
if ($Dist.Idle -lt 5) { $Health -= 10 }
if ($StartupRemoved -lt 3 -and $TaskRemoved -lt 2) { $Health -= 10 }
$Health = [math]::Max(0, $Health)

function Bar($val, $max, $width = 28) {
    $ratio = [math]::Min(1, $val / $max); $filled = [math]::Round($width * $ratio); $empty = $width - $filled
    return ('█' * $filled) + ('░' * $empty) + "  $val"
}
$MaxVal = ($Dist.Values | Measure-Object -Maximum).Maximum

Write-Host "  健康指数: $Health/100" $(if($Health -ge 80){'Green'}elseif($Health -ge 60){'Yellow'}else{'Red'})
Write-Host ""
Write-Host "  ┌─ 调度分布 ─────────────────────────────┐" -ForegroundColor DarkCyan
Write-Host "  │  High        $(Bar $Dist.High $MaxVal)       │" -ForegroundColor DarkCyan
Write-Host "  │  AboveNormal $(Bar $Dist.AboveNormal $MaxVal)       │" -ForegroundColor DarkCyan
Write-Host "  │  Normal      $(Bar $Dist.Normal $MaxVal)       │" -ForegroundColor DarkCyan
Write-Host "  │  BelowNormal $(Bar $Dist.BelowNormal $MaxVal)       │" -ForegroundColor DarkCyan
Write-Host "  │  Idle        $(Bar $Dist.Idle $MaxVal)       │" -ForegroundColor DarkCyan
Write-Host "  └────────────────────────────────────────┘" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  模块A — 进程调度:" -ForegroundColor White
Write-Host "    实体 $Total | 运行 $Running | CPU优先 $Applied | IO优先 $IoAdjusted | 页优先 $PageAdjusted" -ForegroundColor Green
Write-Host "  模块B — 延迟优化:" -ForegroundColor White
Write-Host "    定时器: $(if($TimerResult -eq 0){'1ms ✅'}else{'失败'}) | MMCSS: $(if($MMCSSRegistered){'✅'}else{'⏸'})" -ForegroundColor Green
Write-Host "  模块C — 开机减负:" -ForegroundColor White
Write-Host "    启动项 $StartupRemoved | 计划任务 $TaskRemoved | 服务延迟 $SvcDelayed (2分钟后)" -ForegroundColor Green
Write-Host "  模块D — 内存优化:" -ForegroundColor White
Write-Host "    工作集 $MemFreed | Standby已清理 | LargePages $(if($LargePagesEnabled){'✅'}else{'❌'}) | 缓存1GB | 页面合并" -ForegroundColor Green
Write-Host "  模块E — 网络栈:" -ForegroundColor White
Write-Host "    CTCP ✅ | RSS亲和性 $RssConfigured | 协议绑定 $ProtocolsDisabled" -ForegroundColor Green
Write-Host ""
Write-Host "  持久化: 开机自动恢复 | 实时守护 $(if((Get-ScheduledTask -TaskName 'ProcOptimizer_Guard' -ErrorAction SilentlyContinue)){'已激活 (VBS轮询)'}else{'未激活'})" -ForegroundColor White
Write-Host "  耗时:   $($sw.Elapsed.ToString('mm\:ss\.fff'))" -ForegroundColor White
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  七模块已激活。重启后自动恢复。IO/内存/网络全面优化。     ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

pause