# 역할: 자동매매 실행 중 Windows 절전 진입을 방지합니다.
import ctypes
import platform
import threading


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


class KeepAwakeManager:
    def __init__(self) -> None:
        self._enabled = False
        self._lock = threading.Lock()

    @property
    def supported(self) -> bool:
        return platform.system() == "Windows"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> tuple[bool, str]:
        if not self.supported:
            return False, "절전 방지는 Windows에서만 지원됩니다."
        with self._lock:
            flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
            if result == 0:
                fallback = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                if fallback == 0:
                    self._enabled = False
                    return False, "Windows 절전 방지 설정 실패"
            self._enabled = True
            return True, "자동매매 중 Windows 절전 방지 ON"

    def disable(self) -> tuple[bool, str]:
        if not self.supported:
            return False, "절전 방지는 Windows에서만 지원됩니다."
        with self._lock:
            result = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            self._enabled = False
            if result == 0:
                return False, "Windows 절전 방지 해제 실패"
            return True, "Windows 절전 방지 OFF"


keep_awake = KeepAwakeManager()
