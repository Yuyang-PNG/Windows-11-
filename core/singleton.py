import threading
from typing import Type, Dict, Any


class Singleton(type):
    """
    线程安全的单例元类
    
    用法:
        class MyClass(metaclass=Singleton):
            pass
    """
    
    _instances: Dict[Type, Any] = {}
    _lock: threading.RLock = threading.RLock()

    def __call__(cls, *args, **kwargs) -> Any:
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def get_instance(mcs, cls: Type) -> Any:
        """获取单例实例，如果不存在则创建"""
        with mcs._lock:
            if cls not in mcs._instances:
                mcs._instances[cls] = cls()
            return mcs._instances[cls]

    @classmethod
    def has_instance(mcs, cls: Type) -> bool:
        """检查单例实例是否已创建"""
        with mcs._lock:
            return cls in mcs._instances

    @classmethod
    def clear_instance(mcs, cls: Type) -> None:
        """清除指定类的单例实例"""
        with mcs._lock:
            mcs._instances.pop(cls, None)

    @classmethod
    def clear_all(mcs) -> None:
        """清除所有单例实例"""
        with mcs._lock:
            mcs._instances.clear()