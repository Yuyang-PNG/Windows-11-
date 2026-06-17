import sys
import os
import time
import threading

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class ProcessPriorityService(win32serviceutil.ServiceFramework):
    """Windows服务封装类 - 将进程优先级管理器封装为Windows服务"""
    
    _svc_name_ = "ProcessPriorityManager"
    _svc_display_name_ = "Process Priority Manager"
    _svc_description_ = "智能进程优先级管理器 - 自动优化系统性能"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = False
        self.main_thread = None
        self.process_manager = None
    
    def SvcStop(self):
        """停止服务"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.hWaitStop)
        
        if self.process_manager:
            try:
                self.process_manager.stop()
            except Exception as e:
                self._log(f"停止管理器失败: {e}")
    
    def SvcDoRun(self):
        """运行服务"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, "")
        )
        
        self.running = True
        self._start_manager()
    
    def _start_manager(self):
        """启动进程优先级管理器"""
        try:
            import process_priority_manager
            
            self.process_manager = process_priority_manager.ProcessPriorityManager()
            self.process_manager.start()
            
            while self.running:
                time.sleep(1)
                win32event.WaitForSingleObject(self.hWaitStop, 1000)
                
        except Exception as e:
            self._log(f"服务启动失败: {e}")
            self.running = False
    
    def _log(self, message):
        """记录日志"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_INFO,
            (self._svc_name_, message)
        )


class ServiceInstaller:
    """Windows服务安装器"""
    
    @staticmethod
    def install():
        """安装服务"""
        if not WIN32_AVAILABLE:
            print("错误: 需要安装 pywin32 库")
            return False
        
        try:
            win32serviceutil.InstallService(
                pythonClassString='windows_service.ProcessPriorityService',
                serviceName=ProcessPriorityService._svc_name_,
                displayName=ProcessPriorityService._svc_display_name_,
                description=ProcessPriorityService._svc_description_,
                startType=win32service.SERVICE_AUTO_START
            )
            print(f"服务 '{ProcessPriorityService._svc_display_name_}' 安装成功")
            return True
        except Exception as e:
            print(f"服务安装失败: {e}")
            return False
    
    @staticmethod
    def uninstall():
        """卸载服务"""
        if not WIN32_AVAILABLE:
            print("错误: 需要安装 pywin32 库")
            return False
        
        try:
            win32serviceutil.UninstallService(ProcessPriorityService._svc_name_)
            print(f"服务 '{ProcessPriorityService._svc_display_name_}' 卸载成功")
            return True
        except Exception as e:
            print(f"服务卸载失败: {e}")
            return False
    
    @staticmethod
    def start():
        """启动服务"""
        if not WIN32_AVAILABLE:
            print("错误: 需要安装 pywin32 库")
            return False
        
        try:
            win32serviceutil.StartService(ProcessPriorityService._svc_name_)
            print(f"服务 '{ProcessPriorityService._svc_display_name_}' 启动成功")
            return True
        except Exception as e:
            print(f"服务启动失败: {e}")
            return False
    
    @staticmethod
    def stop():
        """停止服务"""
        if not WIN32_AVAILABLE:
            print("错误: 需要安装 pywin32 库")
            return False
        
        try:
            win32serviceutil.StopService(ProcessPriorityService._svc_name_)
            print(f"服务 '{ProcessPriorityService._svc_display_name_}' 停止成功")
            return True
        except Exception as e:
            print(f"服务停止失败: {e}")
            return False
    
    @staticmethod
    def status():
        """查询服务状态"""
        if not WIN32_AVAILABLE:
            print("错误: 需要安装 pywin32 库")
            return None
        
        try:
            status = win32serviceutil.QueryServiceStatus(ProcessPriorityService._svc_name_)
            status_codes = {
                win32service.SERVICE_STOPPED: '已停止',
                win32service.SERVICE_START_PENDING: '启动中',
                win32service.SERVICE_STOP_PENDING: '停止中',
                win32service.SERVICE_RUNNING: '运行中',
                win32service.SERVICE_CONTINUE_PENDING: '继续中',
                win32service.SERVICE_PAUSE_PENDING: '暂停中',
                win32service.SERVICE_PAUSED: '已暂停'
            }
            return {
                'name': ProcessPriorityService._svc_display_name_,
                'status': status_codes.get(status[1], '未知'),
                'pid': status[2]
            }
        except Exception as e:
            print(f"查询服务状态失败: {e}")
            return None
    
    @staticmethod
    def is_installed():
        """检查服务是否已安装"""
        if not WIN32_AVAILABLE:
            return False
        
        try:
            win32serviceutil.QueryServiceStatus(ProcessPriorityService._svc_name_)
            return True
        except:
            return False


def run_as_service():
    """以服务模式运行"""
    if not WIN32_AVAILABLE:
        print("错误: 需要安装 pywin32 库")
        sys.exit(1)
    
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ProcessPriorityService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(ProcessPriorityService)


def run_as_console():
    """以控制台模式运行"""
    try:
        import process_priority_manager
        
        print("启动进程优先级管理器 (控制台模式)...")
        manager = process_priority_manager.ProcessPriorityManager()
        manager.start()
        
        print("按 Ctrl+C 停止...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n正在停止...")
        if 'manager' in locals():
            manager.stop()
        print("已停止")


def main():
    """主入口"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'install':
            ServiceInstaller.install()
        elif command == 'uninstall':
            ServiceInstaller.uninstall()
        elif command == 'start':
            ServiceInstaller.start()
        elif command == 'stop':
            ServiceInstaller.stop()
        elif command == 'status':
            status = ServiceInstaller.status()
            if status:
                print(f"服务: {status['name']}")
                print(f"状态: {status['status']}")
                print(f"进程ID: {status['pid']}")
        elif command == 'service':
            run_as_service()
        elif command == 'console':
            run_as_console()
        else:
            print(f"未知命令: {command}")
            print("可用命令: install, uninstall, start, stop, status, service, console")
    else:
        run_as_console()


if __name__ == '__main__':
    main()