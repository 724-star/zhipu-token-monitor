#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱Token监控脚本 - 依赖安装脚本
"""

import subprocess
import sys
import os

def install_dependencies():
    """安装所有依赖"""
    print("正在安装智谱Token监控脚本所需的依赖...")

    dependencies = [
        "playwright",
        "plyer"
    ]

    for dep in dependencies:
        try:
            print(f"正在安装 {dep}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            print(f"✓ {dep} 安装成功")
        except subprocess.CalledProcessError as e:
            print(f"✗ {dep} 安装失败: {e}")
            return False

    # 安装Playwright浏览器
    print("正在安装Playwright浏览器...")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("✓ Playwright浏览器安装成功")
    except subprocess.CalledProcessError as e:
        print(f"✗ Playwright浏览器安装失败: {e}")
        return False

    print("\n所有依赖安装完成！")
    return True

if __name__ == "__main__":
    if install_dependencies():
        print("\n现在可以运行启动脚本了！")
    else:
        print("\n依赖安装失败，请检查网络连接或Python环境")
        sys.exit(1)