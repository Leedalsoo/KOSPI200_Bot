# -*- coding: utf-8 -*-
import os
import sys
import inspect
import importlib
import logging
from typing import Dict, Type
from core.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class PluginLoader:
    """전략 플러그인 동적 검사 및 샌드박스 적재 로더"""
    
    def __init__(self, plugins_dir: str) -> None:
        self.plugins_dir: str = plugins_dir

    def discover_and_load(self) -> Dict[str, Type[BaseAgent]]:
        """[목표 A, B, C] 디렉토리 스캔, 추상 클래스 배제, 예외 격리 후 전략 클래스 반환"""
        loaded_strategies: Dict[str, Type[BaseAgent]] = {}
        
        # 1. 디렉토리 존재 확인
        if not os.path.isdir(self.plugins_dir):
            logger.warning(f"Plugins directory not found: {self.plugins_dir}")
            return loaded_strategies

        # 2. 동적 임포트를 위한 sys.path 기준 경로 계산 및 prefix 도출
        abs_plugins_dir = os.path.abspath(self.plugins_dir)
        base_path = None
        for p in sys.path:
            if not p:
                continue
            abs_p = os.path.abspath(p)
            if abs_plugins_dir.startswith(abs_p):
                if base_path is None or len(abs_p) > len(base_path):
                    base_path = abs_p

        added_to_path = False
        if base_path is None:
            sys.path.insert(0, abs_plugins_dir)
            base_path = abs_plugins_dir
            added_to_path = True

        try:
            rel_path = os.path.relpath(abs_plugins_dir, base_path)
            if rel_path == ".":
                module_prefix = ""
            else:
                module_prefix = rel_path.replace(os.sep, ".").strip(".") + "."

            # 3. self.plugins_dir 내부의 .py 파일 순회
            for filename in sorted(os.listdir(abs_plugins_dir)):
                # 확장자 검사 및 __init__.py 배제
                if not filename.endswith(".py") or filename == "__init__.py":
                    continue

                module_name_without_ext = filename[:-3]
                module_full_name = f"{module_prefix}{module_name_without_ext}"

                # 4. 모듈 임포트 (try-except 샌드박싱)
                try:
                    module = importlib.import_module(module_full_name)
                except Exception as e:
                    logger.error(
                        f"Failed to import strategy plugin module {module_full_name} from {filename}: {e}",
                        exc_info=True
                    )
                    continue

                # 5. inspect.getmembers 로 클래스 탐색
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # BaseAgent 상속 검사
                    if not issubclass(obj, BaseAgent):
                        continue
                    
                    # 🛡️ [목표 B] 최상위 베이스 클래스 자체인 경우 배제 (유령 주문 원천 차단)
                    if obj is BaseAgent:
                        continue

                    # 🛡️ [목표 B] 추상 클래스 배제 (not inspect.isabstract)
                    if inspect.isabstract(obj):
                        continue

                    loaded_strategies[name] = obj
                    logger.info(f"Successfully loaded strategy plugin class: {name}")

        finally:
            if added_to_path:
                try:
                    sys.path.remove(abs_plugins_dir)
                except ValueError:
                    pass

        return loaded_strategies
