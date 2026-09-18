#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱Token活动自动监控脚本
持续监控并自动领取智谱官方发放的Token额度
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    import plyer
except ImportError:
    print("正在安装必需的依赖包...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "plyer"])
    print("依赖包安装完成！请重新运行脚本。")
    sys.exit(0)


class TokenMonitorConfig:
    """监控配置"""
    # 监控页面
    ACTIVITY_PAGES = [
        "https://open.bigmodel.cn/activity",
        "https://open.bigmodel.cn/user/benefits",
        "https://open.bigmodel.cn/activity/zcode"
    ]

    # 检测频率（分钟）
    CHECK_INTERVAL_NORMAL = 30  # 平时30分钟
    CHECK_INTERVAL_HIGH = 5     # 高峰期5分钟

    # 高峰期时段（周五18:00 ~ 周一10:00）
    HIGH_PEAK_FRIDAY_START = 18
    HIGH_PEAK_MONDAY_END = 10

    # 检测关键词
    CLAIM_BUTTONS = [
        "立即领取",
        "免费领取",
        "领取Token",
        "立即参与",
        "领取额度",
        "领取福利",
        "Claim",
        "Get Token"
    ]

    # 重试配置
    MAX_RETRIES = 3
    RETRY_INTERVAL = 60  # 秒

    # 浏览器配置
    BROWSER_HEADLESS = True  # 后台运行不显示窗口
    BROWSER_TIMEOUT = 30000  # 30秒

    # 日志配置
    LOG_FILE = "token_monitor.log"
    LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB

    # 通知配置
    NOTIFICATION_DURATION = 5  # 秒


class TokenMonitor:
    """Token监控器"""

    def __init__(self):
        self.config = TokenMonitorConfig()
        self.logger = self._setup_logger()
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running = False
        self.user_data_dir = os.path.join(os.path.dirname(__file__), ".browser_data")
        self.last_check_time = None
        self.claim_count = 0

    def _setup_logger(self):
        """设置日志"""
        logger = logging.getLogger("TokenMonitor")
        logger.setLevel(logging.INFO)

        # 文件处理器
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            self.config.LOG_FILE,
            maxBytes=self.config.LOG_MAX_SIZE,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    def _is_high_peak_period(self):
        """判断是否是高峰期"""
        now = datetime.now()
        weekday = now.weekday()  # 0=周一, 4=周五, 6=周日

        if weekday == 4:  # 周五
            return now.hour >= self.config.HIGH_PEAK_FRIDAY_START
        elif weekday in [5, 6]:  # 周六、周日
            return True
        elif weekday == 0:  # 周一
            return now.hour < self.config.HIGH_PEAK_MONDAY_END
        else:  # 周二~周四
            return False

    def _get_check_interval(self):
        """获取检测间隔"""
        if self._is_high_peak_period():
            return self.config.CHECK_INTERVAL_HIGH
        return self.config.CHECK_INTERVAL_NORMAL

    def _send_notification(self, title: str, message: str):
        """发送桌面通知"""
        try:
            plyer.notification.notify(
                title=title,
                message=message,
                app_name="智谱Token监控",
                timeout=self.config.NOTIFICATION_DURATION
            )
            self.logger.info(f"发送通知: {title} - {message}")
        except Exception as e:
            self.logger.error(f"发送通知失败: {e}")

    async def _initialize_browser(self):
        """初始化浏览器"""
        try:
            self.logger.info("正在启动浏览器...")

            self.playwright = await async_playwright().start()

            # 确保用户数据目录存在
            os.makedirs(self.user_data_dir, exist_ok=True)

            # 启动浏览器，使用持久化上下文保持登录状态
            self.browser = await self.playwright.chromium.launch(
                headless=self.config.BROWSER_HEADLESS,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-ssl-verify',  # 关闭SSL验证
                    '--ignore-certificate-errors',
                    '--ignore-ssl-errors',
                    '--ignore-certificate-errors-spki-list',
                    '--disable-web-security'
                ]
            )

            # 使用持久化上下文保持登录会话
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                ignore_https_errors=True,  # 忽略HTTPS错误
                accept_downloads=False
            )

            # 加载已有的会话
            cookies_file = os.path.join(self.user_data_dir, "cookies.json")
            if os.path.exists(cookies_file):
                with open(cookies_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    await self.context.add_cookies(cookies)
                    self.logger.info("加载已有登录会话")

            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.config.BROWSER_TIMEOUT)

            # 设置页面加载超时
            self.page.set_default_navigation_timeout(self.config.BROWSER_TIMEOUT)

            self.logger.info("浏览器启动成功")
            return True

        except Exception as e:
            self.logger.error(f"浏览器启动失败: {e}")
            return False

    async def _save_session(self):
        """保存会话"""
        try:
            cookies = await self.context.cookies()
            cookies_file = os.path.join(self.user_data_dir, "cookies.json")

            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)

            self.logger.info("会话保存成功")
        except Exception as e:
            self.logger.error(f"保存会话失败: {e}")

    async def _check_page_loaded(self):
        """检查页面是否加载成功"""
        try:
            # 等待页面主体加载
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            return True
        except Exception:
            # 即使networkidle超时，也可能页面已基本加载
            return await self.page.locator('body').count() > 0

    async def _find_claim_buttons(self) -> List:
        """查找可领取按钮"""
        claim_buttons = []

        try:
            # 等待页面加载
            if not await self._check_page_loaded():
                return claim_buttons

            # 搜索各种可能的可领取按钮
            for keyword in self.config.CLAIM_BUTTONS:
                try:
                    # 尝试多种选择器
                    selectors = [
                        f'button:has-text("{keyword}")',
                        f'a:has-text("{keyword}")',
                        f'div:has-text("{keyword}")',
                        f'[role="button"]:has-text("{keyword}")',
                    ]

                    for selector in selectors:
                        elements = await self.page.locator(selector).all()
                        for element in elements:
                            # 检查元素是否可见和可点击
                            if await element.is_visible() and await element.is_enabled():
                                claim_buttons.append({
                                    'element': element,
                                    'keyword': keyword,
                                    'selector': selector
                                })
                except Exception as e:
                    self.logger.debug(f"查找按钮'{keyword}'时出错: {e}")
                    continue

            # 去重
            unique_buttons = []
            seen_elements = set()

            for button in claim_buttons:
                element_str = str(button['element'])
                if element_str not in seen_elements:
                    unique_buttons.append(button)
                    seen_elements.add(element_str)

            return unique_buttons

        except Exception as e:
            self.logger.error(f"查找可领取按钮失败: {e}")
            return claim_buttons

    async def _handle_dialog(self):
        """处理弹窗"""
        try:
            # 检查是否有弹窗
            dialog_handled = False

            # 尝试处理alert/confirm弹窗
            try:
                self.page.on('dialog', lambda dialog: asyncio.create_task(dialog.accept()))
                dialog_handled = True
            except Exception:
                pass

            # 检查页面上的模态框
            try:
                # 等待可能的确认弹窗
                await asyncio.sleep(1)

                # 尝试点击确认按钮
                confirm_selectors = [
                    'button:has-text("确认")',
                    'button:has-text("确定")',
                    'button:has-text("OK")',
                    'button:has-text("同意")',
                    'button[type="submit"]',
                    '.confirm-button',
                    '.ok-button'
                ]

                for selector in confirm_selectors:
                    try:
                        element = self.page.locator(selector).first
                        if await element.is_visible() and await element.is_enabled():
                            await element.click()
                            self.logger.info("自动点击确认弹窗")
                            await asyncio.sleep(1)
                            break
                    except Exception:
                        continue

            except Exception as e:
                self.logger.debug(f"处理模态框时出错: {e}")

            return dialog_handled

        except Exception as e:
            self.logger.error(f"处理弹窗失败: {e}")
            return False

    async def _check_captcha(self) -> bool:
        """检查是否有验证码"""
        try:
            # 常见的验证码特征
            captcha_selectors = [
                '.captcha',
                '#captcha',
                '[class*="captcha"]',
                '[id*="captcha"]',
                '.geetest',
                '#geetest',
                'iframe[src*="captcha"]',
                'iframe[src*="geetest"]'
            ]

            for selector in captcha_selectors:
                try:
                    element = self.page.locator(selector).first
                    if await element.is_visible():
                        self.logger.warning("检测到验证码，需要手动处理")
                        return True
                except Exception:
                    continue

            return False

        except Exception as e:
            self.logger.error(f"检查验证码失败: {e}")
            return False

    async def _check_token_balance(self) -> dict:
        """查询Token余额"""
        try:
            self.logger.info("正在查询Token余额...")

            # 访问个人中心
            await self.page.goto("https://open.bigmodel.cn/user/benefits",
                                wait_until='domcontentloaded',
                                timeout=self.config.BROWSER_TIMEOUT)

            await asyncio.sleep(2)

            # 尝试从页面提取余额信息
            balance_info = {
                'total': '未知',
                'available': '未知',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # 常见的余额显示位置
            balance_selectors = [
                '.token-balance',
                '.balance',
                '[class*="balance"]',
                '[class*="token"]',
                '.quota',
                '.amount'
            ]

            for selector in balance_selectors:
                try:
                    element = self.page.locator(selector).first
                    if await element.is_visible():
                        text = await element.text_content()
                        if text and any(char.isdigit() for char in text):
                            balance_info['available'] = text.strip()
                            self.logger.info(f"找到余额信息: {text.strip()}")
                            break
                except Exception:
                    continue

            self.logger.info(f"当前余额: {balance_info}")
            return balance_info

        except Exception as e:
            self.logger.error(f"查询余额失败: {e}")
            return {
                'total': '查询失败',
                'available': '查询失败',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'error': str(e)
            }

    async def _claim_token(self, button_info: dict, page_url: str) -> bool:
        """领取Token"""
        try:
            element = button_info['element']
            keyword = button_info['keyword']

            self.logger.info(f"发现可领取按钮: '{keyword}'，准备点击")

            # 滚动到元素位置
            await element.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)

            # 点击按钮
            await element.click()
            self.logger.info(f"已点击 '{keyword}' 按钮")

            # 等待页面响应
            await asyncio.sleep(2)

            # 处理可能的弹窗
            await self._handle_dialog()
            await asyncio.sleep(1)

            # 检查是否有验证码
            has_captcha = await self._check_captcha()
            if has_captcha:
                self._send_notification(
                    "需要手动处理验证码",
                    f"检测到验证码，请手动处理\n页面: {page_url}"
                )
                return False

            # 检查是否成功
            success = await self._check_claim_success()

            if success:
                # 查询余额确认
                balance_info = await self._check_token_balance()
                self.claim_count += 1

                self._send_notification(
                    f"Token领取成功！",
                    f"成功领取Token\n当前余额: {balance_info.get('available', '未知')}\n本次是第 {self.claim_count} 次成功领取"
                )

                # 保存会话
                await self._save_session()

                return True
            else:
                self._send_notification(
                    "Token领取失败",
                    f"点击 '{keyword}' 按钮后未检测到成功提示\n页面: {page_url}"
                )
                return False

        except Exception as e:
            self.logger.error(f"领取Token失败: {e}")
            self._send_notification(
                "Token领取异常",
                f"领取过程中出现异常: {str(e)}\n页面: {page_url}"
            )
            return False

    async def _check_claim_success(self) -> bool:
        """检查领取是否成功"""
        try:
            # 等待页面稳定
            await asyncio.sleep(2)

            # 检查成功提示
            success_indicators = [
                "领取成功",
                "已领取",
                "成功",
                "Token已到账",
                "success",
                "已添加",
                "充值成功"
            ]

            for indicator in success_indicators:
                try:
                    # 检查页面是否包含成功提示
                    page_text = await self.page.text_content('body')
                    if page_text and indicator in page_text:
                        self.logger.info(f"检测到成功提示: '{indicator}'")
                        return True

                    # 检查特定元素
                    success_elements = await self.page.locator(f'*:has-text("{indicator}")').all()
                    for elem in success_elements:
                        if await elem.is_visible():
                            self.logger.info(f"发现成功提示元素: '{indicator}'")
                            return True

                except Exception:
                    continue

            # 检查按钮状态变化（按钮可能变为"已领取"或禁用）
            try:
                claimed_indicators = [
                    "已领取",
                    "已参与",
                    "已领取",
                    "Claimed"
                ]

                for indicator in claimed_indicators:
                    claimed_elements = await self.page.locator(f'*:has-text("{indicator}")').all()
                    if len(claimed_elements) > 0:
                        self.logger.info(f"检测到已领取状态: '{indicator}'")
                        return True

            except Exception:
                pass

            return False

        except Exception as e:
            self.logger.error(f"检查领取状态失败: {e}")
            return False

    def _is_browser_dead_error(self, error) -> bool:
        """判断异常是否为浏览器/驱动已断连（这种情况重试没有意义）"""
        keywords = [
            "Connection closed",
            "Target closed",
            "Browser has been closed",
            "Target page, context or browser has been closed",
            "Protocol error",
        ]
        text = str(error)
        return any(keyword in text for keyword in keywords)

    async def _check_page(self, url: str) -> bool:
        """检查单个页面"""
        retry_count = 0
        max_retries = self.config.MAX_RETRIES

        while retry_count < max_retries:
            try:
                self.logger.info(f"正在检查页面: {url}")

                # 访问页面
                await self.page.goto(
                    url,
                    wait_until='domcontentloaded',
                    timeout=self.config.BROWSER_TIMEOUT
                )

                # 等待页面加载
                await asyncio.sleep(2)

                # 检查是否有可领取按钮
                claim_buttons = await self._find_claim_buttons()

                if claim_buttons:
                    self.logger.info(f"发现 {len(claim_buttons)} 个可领取按钮")
                    self._send_notification(
                        "发现新的Token活动！",
                        f"在页面发现可领取按钮\n页面: {url}\n按钮数量: {len(claim_buttons)}"
                    )

                    # 尝试领取所有找到的按钮
                    success_count = 0
                    for button_info in claim_buttons:
                        if await self._claim_token(button_info, url):
                            success_count += 1
                            await asyncio.sleep(3)  # 领取间隔

                    self.logger.info(f"成功领取 {success_count}/{len(claim_buttons)} 个Token")
                    return True
                else:
                    self.logger.info("未发现可领取的Token活动")

                return True

            except Exception as e:
                # 浏览器/驱动已断连，再重试也是白等，直接抛给上层触发重建
                if self._is_browser_dead_error(e):
                    self.logger.error(f"浏览器已断连，放弃本次检查: {e}")
                    raise

                retry_count += 1
                self.logger.error(f"检查页面失败 (尝试 {retry_count}/{max_retries}): {e}")

                if retry_count < max_retries:
                    self.logger.info(f"等待 {self.config.RETRY_INTERVAL} 秒后重试...")
                    await asyncio.sleep(self.config.RETRY_INTERVAL)

        # 重试用尽仍未成功：抛出，让上层重建浏览器（不能假装"没有活动"）
        raise RuntimeError(f"检查页面 {url} 连续 {max_retries} 次失败")

    async def _monitor_cycle(self):
        """执行一次完整的监控循环"""
        self.logger.info("=" * 50)
        self.logger.info("开始新的监控周期")
        self.last_check_time = datetime.now()

        # 检查浏览器是否可用
        if not self.browser or not self.page:
            self.logger.warning("浏览器不可用，尝试重新初始化...")
            if not await self._initialize_browser():
                self.logger.error("浏览器初始化失败，跳过本次检查")
                return

        try:
            # 检查所有配置的页面
            found_activity = False
            for url in self.config.ACTIVITY_PAGES:
                try:
                    if await self._check_page(url):
                        found_activity = True
                    await asyncio.sleep(2)  # 页面间间隔
                except Exception as e:
                    self.logger.error(f"检查页面 {url} 时出错: {e}")
                    # 交给下方 except 统一处理：清理并重建浏览器
                    raise

            # 保存会话
            await self._save_session()

            if found_activity:
                self.logger.info("本次监控发现并处理了Token活动")
            else:
                self.logger.info("本次监控未发现新的Token活动")

        except Exception as e:
            self.logger.error(f"监控周期执行失败: {e}")
            # 尝试重新初始化浏览器
            await self._cleanup_browser()
            await self._initialize_browser()

        self.logger.info("监控周期完成")
        self.logger.info("=" * 50)

    async def _cleanup_browser(self):
        """清理浏览器资源"""
        try:
            if self.page:
                await self.page.close()
                self.page = None

            if self.context:
                await self.context.close()
                self.context = None

            if self.browser:
                await self.browser.close()
                self.browser = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            self.logger.info("浏览器资源已清理")

        except Exception as e:
            self.logger.error(f"清理浏览器资源失败: {e}")

    async def run(self):
        """运行监控"""
        self.is_running = True
        self.logger.info("智谱Token监控脚本启动")
        self._send_notification("Token监控启动", "智谱Token监控脚本已启动，正在后台运行")

        try:
            # 初始化浏览器
            if not await self._initialize_browser():
                self.logger.error("浏览器初始化失败，无法启动监控")
                self._send_notification("监控启动失败", "浏览器初始化失败，请检查网络连接")
                return

            # 主监控循环
            while self.is_running:
                try:
                    # 执行监控周期
                    await self._monitor_cycle()

                    # 获取下次检查时间
                    interval = self._get_check_interval()
                    next_check = datetime.now() + timedelta(minutes=interval)

                    self.logger.info(f"下次检查时间: {next_check.strftime('%Y-%m-%d %H:%M:%S')}")
                    self.logger.info(f"检测间隔: {interval} 分钟")

                    # 等待下次检查
                    wait_seconds = interval * 60
                    await asyncio.sleep(wait_seconds)

                except asyncio.CancelledError:
                    self.logger.info("监控被取消")
                    break
                except KeyboardInterrupt:
                    self.logger.info("收到键盘中断信号")
                    break
                except Exception as e:
                    self.logger.error(f"监控循环异常: {e}", exc_info=True)

                    # 发送错误通知
                    self._send_notification(
                        "监控异常",
                        f"监控过程中出现异常，将在1分钟后重启\n错误: {str(e)}"
                    )

                    # 等待后继续
                    await asyncio.sleep(60)

        finally:
            await self._cleanup_browser()
            self.logger.info("智谱Token监控脚本停止")
            self._send_notification("Token监控停止", "智谱Token监控脚本已停止")

    def stop(self):
        """停止监控"""
        self.logger.info("正在停止监控...")
        self.is_running = False


def main():
    """主函数"""
    print("=" * 60)
    print("智谱Token活动自动监控脚本")
    print("=" * 60)
    print()

    # 创建监控器
    monitor = TokenMonitor()

    try:
        # 运行监控
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\n收到停止信号，正在关闭...")
        monitor.stop()
    except Exception as e:
        print(f"\n程序异常退出: {e}")
        monitor.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()