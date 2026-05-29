#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XServer GAME 自动登录和续期脚本 (多账户版)
"""

# =====================================================================
#                          导入依赖
# =====================================================================

import asyncio
import time
import re
import datetime
from datetime import timezone, timedelta
import os
import json
import requests
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_async

# =====================================================================
#                          配置区域
# =====================================================================

# 浏览器配置
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"
USE_HEADLESS = IS_GITHUB_ACTIONS or os.getenv("USE_HEADLESS", "false").lower() == "true"
WAIT_TIMEOUT = 15000     # 页面元素等待超时时间（毫秒）
PAGE_LOAD_DELAY = 6      # 页面加载延迟时间（秒）

# XServer多账户配置
# 期望的环境变量格式: [{"email": "1@example.com", "password": "pwd1"}, {"email": "2@example.com", "password": "pwd2"}]
XSERVER_ACCOUNTS_JSON = os.getenv("XSERVER_ACCOUNTS", "[]")
TARGET_URL = "https://secure.xserver.ne.jp/xapanel/login/xmgame"

# =====================================================================
#                        XServer 自动登录类
# =====================================================================

class XServerAutoLogin:
    """XServer GAME 自动登录主类 - Playwright版本"""
    
    def __init__(self, email, password, account_index):
        """
        初始化 XServer GAME 自动登录器
        """
        self.browser = None
        self.context = None
        self.page = None
        self.headless = USE_HEADLESS
        
        # 接收传入的账号信息
        self.email = email
        self.password = password
        self.account_index = account_index
        
        self.target_url = TARGET_URL
        self.wait_timeout = WAIT_TIMEOUT
        self.page_load_delay = PAGE_LOAD_DELAY
        self.screenshot_count = 0  # 截图计数器
        
        # 续期状态跟踪
        self.old_expiry_time = None      # 原到期时间
        self.new_expiry_time = None      # 新到期时间
        self.renewal_status = "Unknown"  # 续期状态: Success/Unexpired/Failed/Unknown
    
    
    # =================================================================
    #                       1. 浏览器管理模块
    # =================================================================
        
    async def setup_browser(self):
        """设置并启动 Playwright 浏览器"""
        try:
            playwright = await async_playwright().start()
            
            # 配置浏览器选项
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-notifications',
                '--window-size=1920,1080',
                '--lang=ja-JP',
                '--accept-lang=ja-JP,ja,en-US,en'
            ]
            
            # 启动浏览器
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=browser_args
            )
            
            # 创建浏览器上下文
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # 创建页面
            self.page = await self.context.new_page()
            
            # 应用stealth插件
            await stealth_async(self.page)
            print(f"✅ [账号{self.account_index}] Stealth 插件已应用")
            
            print(f"✅ [账号{self.account_index}] Playwright 浏览器初始化成功")
            return True
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] Playwright 浏览器初始化失败: {e}")
            return False
    
    async def take_screenshot(self, step_name=""):
        """截图功能 - 用于可视化调试"""
        try:
            if self.page:
                self.screenshot_count += 1
                # 使用北京时间（UTC+8）
                beijing_time = datetime.datetime.now(timezone(timedelta(hours=8)))
                timestamp = beijing_time.strftime("%H%M%S")
                # 在文件名中加入账号索引，防止多账号互相覆盖
                filename = f"acc{self.account_index}_step_{self.screenshot_count:02d}_{timestamp}_{step_name}.png"
                
                # 确保文件名安全
                filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                
                await self.page.screenshot(path=filename, full_page=True)
                print(f"📸 [账号{self.account_index}] 截图已保存: {filename}")
                
        except Exception as e:
            print(f"⚠️ [账号{self.account_index}] 截图失败: {e}")
    
    def validate_config(self):
        """验证配置信息"""
        if not self.email or not self.password:
            print(f"❌ [账号{self.account_index}] 邮箱或密码未设置！")
            return False
        
        print(f"✅ [账号{self.account_index}] 配置信息验证通过")
        return True
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            print(f"🧹 [账号{self.account_index}] 浏览器已关闭")
        except Exception as e:
            print(f"⚠️ [账号{self.account_index}] 清理资源时出错: {e}")
    
    # =================================================================
    #                       2. 页面导航模块
    # =================================================================
    
    async def navigate_to_login(self):
        """导航到登录页面"""
        try:
            print(f"🌐 [账号{self.account_index}] 正在访问: {self.target_url}")
            await self.page.goto(self.target_url, wait_until='load')
            
            # 等待页面加载
            await self.page.wait_for_selector("body", timeout=self.wait_timeout)
            
            print(f"✅ [账号{self.account_index}] 页面加载成功")
            await self.take_screenshot("login_page_loaded")
            return True
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 导航失败: {e}")
            return False
    
    
    # =================================================================
    #                       3. 登录表单处理模块
    # =================================================================
    
    async def find_login_form(self):
        """查找登录表单元素"""
        try:
            print(f"🔍 [账号{self.account_index}] 正在查找登录表单...")
            
            # 等待页面加载完成
            await asyncio.sleep(self.page_load_delay)
            
            # 查找邮箱输入框
            email_selector = "input[name='memberid']"
            await self.page.wait_for_selector(email_selector, timeout=self.wait_timeout)
            print(f"✅ [账号{self.account_index}] 找到邮箱输入框")

            # 查找密码输入框
            password_selector = "input[name='user_password']"
            await self.page.wait_for_selector(password_selector, timeout=self.wait_timeout)
            print(f"✅ [账号{self.account_index}] 找到密码输入框")

            # 查找登录按钮
            login_button_selector = "input[value='ログインする']"
            await self.page.wait_for_selector(login_button_selector, timeout=self.wait_timeout)
            print(f"✅ [账号{self.account_index}] 找到登录按钮")
            
            return email_selector, password_selector, login_button_selector
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 查找登录表单时出错: {e}")
            return None, None, None
    
    async def human_type(self, selector, text):
        """模拟人类输入行为"""
        for char in text:
            await self.page.type(selector, char, delay=100)  # 100ms delay between characters
            await asyncio.sleep(0.05)  # Additional small delay
    
    async def perform_login(self):
        """执行登录操作"""
        try:
            print(f"🎯 [账号{self.account_index}] 开始执行登录操作...")
            
            # 查找登录表单元素
            email_selector, password_selector, login_button_selector = await self.find_login_form()
            
            if not email_selector or not password_selector:
                return False
            
            print(f"📝 [账号{self.account_index}] 正在填写登录信息...")
            
            # 模拟人类行为：慢速输入邮箱
            await self.page.fill(email_selector, "")  # 清空
            await self.human_type(email_selector, self.email)
            print(f"✅ [账号{self.account_index}] 邮箱已填写")
            
            # 等待一下，模拟人类思考时间
            await asyncio.sleep(2)
            
            # 模拟人类行为：慢速输入密码
            await self.page.fill(password_selector, "")  # 清空
            await self.human_type(password_selector, self.password)
            print(f"✅ [账号{self.account_index}] 密码已填写")
            
            # 等待一下，模拟人类操作
            await asyncio.sleep(2)
            
            # 提交表单
            if login_button_selector:
                print(f"🖱️ [账号{self.account_index}] 点击登录按钮...")
                await self.page.click(login_button_selector)
            else:
                print(f"⌨️ [账号{self.account_index}] 使用回车键提交...")
                await self.page.press(password_selector, "Enter")
            
            print(f"✅ [账号{self.account_index}] 登录表单已提交")
            
            # 等待页面响应
            await asyncio.sleep(20)
            return True
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 登录操作失败: {e}")
            return False
    
    
    # =================================================================
    #                       5. 登录结果处理模块
    # =================================================================
    
    async def handle_login_result(self):
        """处理登录结果"""
        try:
            print(f"🔍 [账号{self.account_index}] 正在检查登录结果...")
            
            # 等待页面加载
            await asyncio.sleep(10)
            
            current_url = self.page.url
            print(f"📍 [账号{self.account_index}] 当前URL: {current_url}")
            
            # 简单直接：只判断是否跳转到成功页面
            success_url = "https://secure.xserver.ne.jp/xapanel/xmgame/index"
            
            if current_url == success_url:
                print(f"✅ [账号{self.account_index}] 登录成功！已跳转到XServer GAME管理页面")
                
                # 等待页面加载完成
                print(f"⏰ [账号{self.account_index}] 等待页面加载完成...")
                await asyncio.sleep(3)
                
                # 查找并点击"ゲーム管理"按钮
                print(f"🔍 [账号{self.account_index}] 正在查找ゲーム管理按钮...")
                try:
                    game_button_selector = "a:has-text('ゲーム管理')"
                    await self.page.wait_for_selector(game_button_selector, timeout=self.wait_timeout)
                    print(f"✅ [账号{self.account_index}] 找到ゲーム管理按钮")
                    
                    # 点击ゲーム管理按钮
                    print(f"🖱️ [账号{self.account_index}] 正在点击ゲーム管理按钮...")
                    await self.page.click(game_button_selector)
                    print(f"✅ [账号{self.account_index}] 已点击ゲーム管理按钮")
                    
                    # 等待页面跳转
                    await asyncio.sleep(5)
                    
                    # 验证是否跳转到游戏管理页面
                    final_url = self.page.url
                    print(f"📍 [账号{self.account_index}] 最终页面URL: {final_url}")
                    
                    expected_game_url = "https://secure.xserver.ne.jp/xmgame/game"
                    if expected_game_url in final_url:
                        print(f"✅ [账号{self.account_index}] 成功点击ゲーム管理按钮并跳转到游戏管理页面")
                        await self.take_screenshot("game_page_loaded")
                        
                        # 获取服务器时间信息
                        await self.get_server_time_info()
                    else:
                        print(f"⚠️ [账号{self.account_index}] 跳转到游戏页面可能失败")
                        print(f"   预期包含: {expected_game_url}")
                        print(f"   实际URL: {final_url}")
                        await self.take_screenshot("game_page_redirect_failed")
                        
                except Exception as e:
                    print(f"❌ [账号{self.account_index}] 查找或点击ゲーム管理按钮时出错: {e}")
                    await self.take_screenshot("game_button_error")
                
                return True
            else:
                print(f"❌ [账号{self.account_index}] 登录失败！当前URL不是预期的成功页面")
                print(f"   预期URL: {success_url}")
                print(f"   实际URL: {current_url}")
                return False
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 检查登录结果时出错: {e}")
            return False
            
    # =================================================================
    #                    6A. 服务器信息获取模块
    # =================================================================
    
    async def get_server_time_info(self):
        """获取服务器时间信息"""
        try:
            print(f"🕒 [账号{self.account_index}] 正在获取服务器时间信息...")
            
            # 等待页面加载完成
            await asyncio.sleep(3)
            
            # 使用已验证有效的选择器
            try:
                elements = await self.page.locator("text=/残り\\d+時間\\d+分/").all()
                
                for element in elements:
                    element_text = await element.text_content()
                    element_text = element_text.strip() if element_text else ""
                    
                    # 只处理包含时间信息且文本不太长的元素
                    if element_text and len(element_text) < 200 and "残り" in element_text and "時間" in element_text:
                        print(f"✅ [账号{self.account_index}] 找到时间元素: {element_text}")
                        
                        # 提取剩余时间
                        remaining_match = re.search(r'残り(\d+時間\d+分)', element_text)
                        if remaining_match:
                            remaining_raw = remaining_match.group(1)
                            remaining_formatted = self.format_remaining_time(remaining_raw)
                            print(f"⏰ [账号{self.account_index}] 剩余时间: {remaining_formatted}")
                        
                        # 提取到期时间
                        expiry_match = re.search(r'\((\d{4}-\d{2}-\d{2})まで\)', element_text)
                        if expiry_match:
                            expiry_raw = expiry_match.group(1)
                            expiry_formatted = self.format_expiry_date(expiry_raw)
                            print(f"📅 [账号{self.account_index}] 到期时间: {expiry_formatted}")
                            # 记录原到期时间
                            self.old_expiry_time = expiry_formatted
                        
                        break
                        
            except Exception as e:
                print(f"❌ [账号{self.account_index}] 获取时间信息时出错: {e}")
            
            # 点击升级按钮
            await self.click_upgrade_button()
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 获取服务器时间信息失败: {e}")
    
    def format_remaining_time(self, time_str):
        """格式化剩余时间"""
        return time_str
    
    def format_expiry_date(self, date_str):
        """格式化到期时间"""
        return date_str
    
    # =================================================================
    #                    6B. 续期页面导航模块
    # =================================================================
    
    async def click_upgrade_button(self):
        """点击升级延长按钮"""
        try:
            print(f"🔄 [账号{self.account_index}] 正在查找アップグレード・期限延長按钮...")
            
            upgrade_selector = "a:has-text('アップグレード・期限延長')"
            await self.page.wait_for_selector(upgrade_selector, timeout=self.wait_timeout)
            print(f"✅ [账号{self.account_index}] 找到アップグレード・期限延長按钮")
            
            # 点击按钮
            await self.page.click(upgrade_selector)
            print(f"✅ [账号{self.account_index}] 已点击アップグレード・期限延長按钮")
            
            # 等待页面跳转
            await asyncio.sleep(5)
            
            # 验证URL和检查限制信息
            await self.verify_upgrade_page()
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 点击升级按钮失败: {e}")
    
    async def verify_upgrade_page(self):
        """验证升级页面"""
        try:
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/index"
            
            print(f"📍 [账号{self.account_index}] 升级页面URL: {current_url}")
            
            if expected_url in current_url:
                print(f"✅ [账号{self.account_index}] 成功跳转到升级页面")
                
                # 检查延长限制信息
                await self.check_extension_restriction()
            else:
                print(f"❌ [账号{self.account_index}] 升级页面跳转失败")
                print(f"   预期URL: {expected_url}")
                print(f"   实际URL: {current_url}")
                
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 验证升级页面失败: {e}")
    
    async def check_extension_restriction(self):
        """检查期限延长限制信息"""
        try:
            print(f"🔍 [账号{self.account_index}] 正在检测期限延长限制提示...")
            
            # 查找限制信息
            restriction_selector = "text=/残り契約時間が24時間を切るまで、期限の延長は行えません/"
            
            try:
                element = await self.page.wait_for_selector(restriction_selector, timeout=5000)
                restriction_text = await element.text_content()
                print(f"✅ [账号{self.account_index}] 找到期限延长限制信息")
                print(f"📝 [账号{self.account_index}] 限制信息: {restriction_text}")
                # 设置状态为未到期
                self.renewal_status = "Unexpired"
                return True  # 有限制，不能续期
                
            except Exception:
                print(f"ℹ️ [账号{self.account_index}] 未找到期限延长限制信息，可以进行延长操作")
                # 没有限制信息，执行续期操作
                await self.perform_extension_operation()
                return False  # 无限制，可以续期
                
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 检测期限延长限制失败: {e}")
            return True  # 出错时默认认为有限制
    
    # =================================================================
    #                    6C. 续期操作执行模块
    # =================================================================
    
    async def perform_extension_operation(self):
        """执行期限延长操作"""
        try:
            print(f"🔄 [账号{self.account_index}] 开始执行期限延长操作...")
            await self.click_extension_button()
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 执行期限延长操作失败: {e}")
    
    async def click_extension_button(self):
        """点击期限延长按钮"""
        try:
            print(f"🔍 [账号{self.account_index}] 正在查找'期限を延長する'按钮...")
            extension_selector = "a:has-text('期限を延長する')"
            await self.page.wait_for_selector(extension_selector, timeout=self.wait_timeout)
            print(f"✅ [账号{self.account_index}] 找到'期限を延長する'按钮")
            
            await self.page.click(extension_selector)
            print(f"✅ [账号{self.account_index}] 已点击'期限を延長する'按钮")
            
            print(f"⏰ [账号{self.account_index}] 等待页面跳转...")
            await asyncio.sleep(5)
            
            await self.verify_extension_input_page()
            return True
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 点击期限延长按钮失败: {e}")
            return False
    
    async def verify_extension_input_page(self):
        """验证是否成功跳转到期限延长输入页面"""
        try:
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/input"
            
            print(f"📍 [账号{self.account_index}] 当前页面URL: {current_url}")
            
            if expected_url in current_url:
                print(f"🎉 [账号{self.account_index}] 成功跳转到期限延长输入页面！")
                await self.take_screenshot("extension_input_page")
                await self.click_confirmation_button()
                return True
            else:
                print(f"❌ [账号{self.account_index}] 页面跳转失败")
                return False
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 验证期限延长输入页面失败: {e}")
            return False
            
    async def click_confirmation_button(self):
        """点击確認画面に進む按钮"""
        try:
            print(f"🔍 [账号{self.account_index}] 正在查找'確認画面に進む'按钮...")
            confirmation_selector = "button[type='submit']:has-text('確認画面に進む')"
            await self.page.wait_for_selector(confirmation_selector, timeout=self.wait_timeout)
            
            await self.page.click(confirmation_selector)
            print(f"✅ [账号{self.account_index}] 已点击'確認画面に進む'按钮")
            
            await asyncio.sleep(5)
            await self.verify_extension_conf_page()
            return True
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 点击確認画面に進む按钮失败: {e}")
            return False
            
    async def verify_extension_conf_page(self):
        """验证是否成功跳转到期限延长确认页面"""
        try:
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/conf"
            
            if expected_url in current_url:
                print(f"🎉 [账号{self.account_index}] 成功跳转到期限延长确认页面！")
                await self.take_screenshot("extension_conf_page")
                await self.record_extension_time()
                await self.find_final_extension_button()
                return True
            else:
                print(f"❌ [账号{self.account_index}] 页面跳转失败")
                return False
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 验证期限延长确认页面失败: {e}")
            return False
    
    async def record_extension_time(self):
        """记录续期后的时间信息"""
        try:
            print(f"📅 [账号{self.account_index}] 正在获取续期后的时间信息...")
            time_selector = "tr:has(th:has-text('延長後の期限'))"
            time_element = await self.page.wait_for_selector(time_selector, timeout=self.wait_timeout)
            
            td_element = await time_element.query_selector("td")
            if td_element:
                extension_time = await td_element.text_content()
                extension_time = extension_time.strip()
                print(f"📅 [账号{self.account_index}] 续期后的期限: {extension_time}")
                self.new_expiry_time = extension_time
            else:
                print(f"❌ [账号{self.account_index}] 未找到时间内容")
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 记录续期后时间失败: {e}")
    
    async def find_final_extension_button(self):
        """查找并点击最终的期限延长按钮"""
        try:
            print(f"🔍 [账号{self.account_index}] 正在查找最终的'期限を延長する'按钮...")
            final_button_selector = "button[type='submit']:has-text('期限を延長する')"
            await self.page.wait_for_selector(final_button_selector, timeout=self.wait_timeout)
            
            await self.page.click(final_button_selector)
            print(f"✅ [账号{self.account_index}] 已点击最终续期按钮")
            
            await asyncio.sleep(5)
            await self.verify_extension_success()
            return True
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 执行最终期限延长操作失败: {e}")
            return False
            
    async def verify_extension_success(self):
        """验证续期操作是否成功"""
        try:
            print(f"🔍 [账号{self.account_index}] 正在验证续期操作结果...")
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/do"
            
            url_success = expected_url in current_url
            text_success = False
            
            try:
                success_text_selector = "p:has-text('期限を延長しました。')"
                await self.page.wait_for_selector(success_text_selector, timeout=5000)
                success_text = await self.page.query_selector(success_text_selector)
                if success_text:
                    text_content = await success_text.text_content()
                    print(f"✅ [账号{self.account_index}] 找到成功提示文字: {text_content.strip()}")
                    text_success = True
            except Exception:
                print(f"ℹ️ [账号{self.account_index}] 未找到成功提示文字")
            
            if url_success or text_success:
                print(f"🎉 [账号{self.account_index}] 续期操作成功！")
                self.renewal_status = "Success"
                await self.take_screenshot("extension_success")
                return True
            else:
                print(f"❌ [账号{self.account_index}] 续期操作可能失败")
                self.renewal_status = "Failed"
                await self.take_screenshot("extension_failed")
                return False
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 验证续期结果失败: {e}")
            self.renewal_status = "Failed"
            return False
        
    # =================================================================
    #                    6D. 结果记录与报告模块
    # =================================================================
    
    def append_readme(self):
        """追加记录到README.md文件"""
        try:
            print(f"📝 [账号{self.account_index}] 正在更新 README.md 文件...")
            
            # 使用北京时间（UTC+8）
            beijing_time = datetime.datetime.now(timezone(timedelta(hours=8)))
            current_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 隐藏完整邮箱以保护隐私
            masked_email = self.email.split('@')[0][:3] + "***@" + self.email.split('@')[-1]
            
            # 根据状态生成不同的内容
            readme_content = f"### 账号 {self.account_index}: {masked_email}\n"
            readme_content += f"**运行时间**: `{current_time}`<br>\n"
            readme_content += "🖥️服务器：`🇯🇵Xserver(Mc)`<br>\n"
            
            if self.renewal_status == "Success":
                readme_content += "📊续期结果：✅Success<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
                readme_content += f"🕡️新到期时间: `{self.new_expiry_time or 'Unknown'}`<br>\n"
            elif self.renewal_status == "Unexpired":
                readme_content += "📊续期结果：ℹ️Unexpired<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
            elif self.renewal_status == "Failed":
                readme_content += "📊续期结果：❌Failed<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
            else:
                readme_content += "📊续期结果：❓Unknown<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
            
            readme_content += "\n---\n\n"
            
            # 使用追加模式 'a' 写入 README.md
            with open("README.md", "a", encoding="utf-8") as f:
                f.write(readme_content)
            
            print(f"✅ [账号{self.account_index}] README.md 追加成功")
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 更新 README.md 文件失败: {e}")
    
    # =================================================================
    #                       7. 主流程控制模块
    # =================================================================
    
    async def run(self):
        """运行自动登录流程"""
        try:
            print(f"🚀 [账号{self.account_index}] 开始自动登录流程: {self.email}")
            
            if not self.validate_config():
                return False
            if not await self.setup_browser():
                return False
            if not await self.navigate_to_login():
                return False
            if not await self.perform_login():
                return False
            if not await self.handle_login_result():
                print(f"⚠️ [账号{self.account_index}] 登录可能失败，请检查邮箱和密码是否正确")
                return False
            
            print(f"🎉 [账号{self.account_index}] 自动登录与续期流程完成！")
            await self.take_screenshot("login_completed")
            self.append_readme()
            
            print(f"⏰ [账号{self.account_index}] 浏览器即将关闭...")
            await asyncio.sleep(2)
            
            return True
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 自动登录流程出错: {e}")
            self.append_readme()
            return False
    
        finally:
            await self.cleanup()


# =====================================================================
#                          主程序入口
# =====================================================================

async def main():
    """主函数"""
    print("=" * 60)
    print("XServer GAME 自动登录脚本 - Playwright版本 (多账户)")
    print("=" * 60)
    print()
    
    # 解析账号 JSON
    try:
        accounts = json.loads(XSERVER_ACCOUNTS_JSON)
        if not isinstance(accounts, list) or len(accounts) == 0:
            print("❌ 未检测到有效的账号配置，或配置为空列表。")
            print("请确保设置了正确的 XSERVER_ACCOUNTS 环境变量，例如:")
            print('[{"email": "1@example.com", "password": "pwd"}, {"email": "2@example.com", "password": "pwd"}]')
            return
    except json.JSONDecodeError:
        print("❌ 账号配置格式错误！请确保环境变量 XSERVER_ACCOUNTS 传入的是合法的 JSON 数组。")
        return

    # 初始化 README 文件
    with open("README.md", "w", encoding="utf-8") as f:
        f.write("# XServer GAME 多账号自动续期报告\n\n")

    print(f"📋 共检测到 {len(accounts)} 个待处理账号。")
    print(f"   无头模式: {USE_HEADLESS}")
    print("🚀 开始依次执行...")
    
    all_success = True
    
    # 循环执行每个账号
    for index, acc in enumerate(accounts, start=1):
        email = acc.get("email")
        password = acc.get("password")
        
        print(f"\n" + "="*50)
        print(f"▶️ 正在处理第 {index}/{len(accounts)} 个账号")
        print("="*50)
        
        if not email or not password:
            print(f"⚠️ 账号 {index} 缺失邮箱或密码字段，跳过执行。")
            all_success = False
            continue
            
        auto_login = XServerAutoLogin(email, password, index)
        success = await auto_login.run()
        
        if not success:
            all_success = False
            
        # 账号之间稍微等待一下，防止请求过快被拦截
        if index < len(accounts):
            print(f"⏳ 等待 5 秒后继续处理下一个账号...")
            await asyncio.sleep(5)

    print("\n" + "="*60)
    if all_success:
        print("✅ 所有账号流程执行成功！")
        exit(0)
    else:
        print("⚠️ 部分或全部账号流程执行存在异常，请查看上方日志。")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
