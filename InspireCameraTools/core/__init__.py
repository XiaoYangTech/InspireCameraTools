# -*- coding: utf-8 -*-
"""亿方展台管家（InspireCameraTools）核心包。

本包内模块均只依赖 Python 标准库（``ttkbootstrap`` 等第三方库只在 ``app/`` 层使用），
以保证补丁引擎 / 自动更新模块可被 PyInstaller 打包、也便于单元测试。
"""

from __future__ import annotations

__all__ = ["APP_NAME", "APP_NAME_EN", "__version__"]

APP_NAME = "亿方展台管家"
APP_NAME_EN = "InspireCameraTools"
__version__ = "0.1.0"
