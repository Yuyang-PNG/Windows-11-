import os
import sys
import time
import json
import shutil
import tempfile
import threading
from typing import Dict, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


GITHUB_REPO = "yulaoshi-yuyang/Windows-11Service-Repair"
RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


class UpdateManager:
    def __init__(self, current_version: str):
        self.current_version = current_version.lstrip('v')
        self._latest_version = None
        self._download_url = None
        self._release_notes = None
        self._update_available = False
        self._download_progress = 0
        self._download_thread = None
        self._download_event = threading.Event()
        self._download_error = None
    
    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        parts = version_str.lstrip('v').split('.')
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return major, minor, patch
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        v1 = self._parse_version(version1)
        v2 = self._parse_version(version2)
        if v1 > v2:
            return 1
        elif v1 < v2:
            return -1
        return 0
    
    def check_for_updates(self) -> Dict[str, any]:
        """检查GitHub最新版本"""
        result = {
            'available': False,
            'current_version': f"v{self.current_version}",
            'latest_version': None,
            'download_url': None,
            'release_notes': None,
            'error': None
        }
        
        try:
            req = Request(RELEASE_API_URL, headers={'User-Agent': 'ProcessPriorityManager'})
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            self._latest_version = data.get('tag_name', '').lstrip('v')
            self._release_notes = data.get('body', '')
            
            assets = data.get('assets', [])
            for asset in assets:
                if asset.get('name', '').endswith('.exe'):
                    self._download_url = asset.get('browser_download_url')
                    break
            
            if self._download_url and self._compare_versions(self._latest_version, self.current_version) > 0:
                self._update_available = True
                result['available'] = True
                result['latest_version'] = f"v{self._latest_version}"
                result['download_url'] = self._download_url
                result['release_notes'] = self._release_notes
        
        except URLError as e:
            result['error'] = f"网络错误: {str(e)}"
        except HTTPError as e:
            result['error'] = f"HTTP错误: {e.code}"
        except json.JSONDecodeError:
            result['error'] = "解析版本信息失败"
        except Exception as e:
            result['error'] = f"检查更新失败: {str(e)}"
        
        return result
    
    def get_download_progress(self) -> int:
        """获取下载进度百分比"""
        return self._download_progress
    
    def download_update(self, target_path: Optional[str] = None) -> Tuple[bool, str]:
        """下载更新文件到临时目录"""
        if not self._download_url:
            return False, "未找到下载链接"
        
        if target_path is None:
            target_path = os.path.join(tempfile.gettempdir(), f"智优进程管理器_update.exe")
        
        try:
            req = Request(self._download_url, headers={'User-Agent': 'ProcessPriorityManager'})
            with urlopen(req, timeout=60) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded_size = 0
                block_size = 8192
                
                with open(target_path, 'wb') as f:
                    while True:
                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            self._download_progress = int((downloaded_size / total_size) * 100)
                
                if os.path.exists(target_path):
                    file_size = os.path.getsize(target_path)
                    if total_size > 0 and file_size < total_size * 0.9:
                        os.remove(target_path)
                        return False, f"下载不完整，期望 {total_size} 字节，实际 {file_size} 字节"
                
                return True, target_path
        
        except Exception as e:
            if os.path.exists(target_path):
                os.remove(target_path)
            return False, f"下载失败: {str(e)}"
    
    def install_update(self, exe_path: str) -> bool:
        """安装更新（生成批处理脚本替换EXE并重启）"""
        try:
            success, download_path = self.download_update()
            if not success:
                return False
            
            bat_content = self._generate_update_bat(exe_path, download_path)
            bat_path = os.path.join(tempfile.gettempdir(), f"update_{int(time.time())}.bat")
            
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write(bat_content)
            
            os.chmod(bat_path, 0o755)
            
            import subprocess
            subprocess.Popen(
                ['cmd.exe', '/c', bat_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True
            )
            
            os._exit(0)
            return True
        
        except Exception as e:
            return False
    
    def _generate_update_bat(self, old_exe_path: str, new_exe_path: str) -> str:
        """生成更新批处理脚本"""
        retry_count = 5
        retry_delay = 2
        
        bat_lines = [
            '@echo off',
            'chcp 65001 >nul',
            '',
            ':RETRY',
            f'copy /Y "{new_exe_path}" "{old_exe_path}"',
            'if %errorlevel% equ 0 goto SUCCESS',
            f'timeout /t {retry_delay} /nobreak >nul',
            f'set /a RETRY_COUNT+=1',
            f'if %RETRY_COUNT% lss {retry_count} goto RETRY',
            '',
            ':SUCCESS',
            f'del "{new_exe_path}"',
            f'start "" "{old_exe_path}"',
            f'del "%~f0"',
            'exit'
        ]
        
        return '\n'.join(bat_lines)
    
    def download_and_install_async(self, exe_path: str, callback=None):
        """异步下载并安装更新"""
        def _download_install():
            try:
                success, msg = self.download_update()
                if not success:
                    if callback:
                        callback(False, msg)
                    return
                
                self.install_update(exe_path)
                
            except Exception as e:
                if callback:
                    callback(False, str(e))
        
        self._download_thread = threading.Thread(target=_download_install, daemon=True)
        self._download_thread.start()
    
    def is_update_available(self) -> bool:
        """是否有更新可用"""
        return self._update_available


def get_current_exe_path() -> str:
    """获取当前可执行文件路径"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)


def get_update_manager(current_version: str) -> UpdateManager:
    """获取更新管理器实例"""
    return UpdateManager(current_version)