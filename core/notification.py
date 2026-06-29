import os
import sys
from typing import Optional
from core.subprocess_utils import run_powershell

try:
    if sys.platform == 'win32':
        import win32gui
        import win32con
        WIN32_AVAILABLE = True
    else:
        WIN32_AVAILABLE = False
except ImportError:
    WIN32_AVAILABLE = False


class NotificationManager:
    def __init__(self):
        self.enabled = True
        self._use_native = WIN32_AVAILABLE
    
    def notify(self, title: str, message: str, icon_type: str = "info"):
        if not self.enabled:
            return
        
        if self._use_native:
            self._show_native_notification(title, message, icon_type)
        else:
            print(f"[通知] {title}: {message}")
    
    def _show_native_notification(self, title: str, message: str, icon_type: str = "info"):
        try:
            ps_script = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
            
            $template = @"
            <toast>
                <visual>
                    <binding template="ToastText02">
                        <text id="1">{title}</text>
                        <text id="2">{message}</text>
                    </binding>
                </visual>
            </toast>
"@
            
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("智优进程管理器")
            $notifier.Show($toast)
            '''
            
            run_powershell(ps_script, timeout=5)
        except Exception as e:
            print(f"通知发送失败: {e}")
            print(f"[通知] {title}: {message}")
    
    def game_detected(self, game_name: str):
        self.notify(
            "智优进程管理器",
            f"检测到游戏: {game_name}\n已开始优化",
            "info"
        )
    
    def optimization_complete(self, adjusted_count: int, denied_count: int = 0):
        denied_text = f"\n访问被拒: {denied_count}" if denied_count > 0 else ""
        self.notify(
            "智优进程管理器",
            f"进程优化完成\n成功调整: {adjusted_count} 个进程{denied_text}",
            "info"
        )
    
    def anomaly_detected(self, process_name: str, reason: str):
        self.notify(
            "⚠️ 异常警告",
            f"{process_name}: {reason}",
            "warning"
        )
    
    def priority_restored(self, process_name: str):
        self.notify(
            "智优进程管理器",
            f"已恢复 {process_name} 的原始优先级",
            "info"
        )
    
    def error_occurred(self, error_message: str):
        self.notify(
            "❌ 错误",
            error_message,
            "error"
        )
    
    def set_enabled(self, enabled: bool):
        self.enabled = enabled
    
    def is_enabled(self) -> bool:
        return self.enabled


_notification_manager = None


def get_notification_manager() -> NotificationManager:
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager