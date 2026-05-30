#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XServer GAME 自动登录和续期脚本 (内存拼装报告 + HTML安全推送 + Xray代理)
"""

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

IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"
USE_HEADLESS = IS_GITHUB_ACTIONS or os.getenv("USE_HEADLESS", "false").lower() == "true"
WAIT_TIMEOUT = 15000     
PAGE_LOAD_DELAY = 2      

XSERVER_ACCOUNTS_JSON = os.getenv("XSERVER_ACCOUNTS", "[]")
TARGET_URL = "https://secure.xserver.ne.jp/xapanel/login/xmgame"

# =====================================================================
#                        XServer 自动登录类
# =====================================================================

class XServerAutoLogin:
    
    def __init__(self, email, password, account_index):
        self.browser = None
        self.context = None
        self.page = None
        self.headless = USE_HEADLESS
        
        self.email = email
        self.password = password
        self.account_index = account_index
        
        self.target_url = TARGET_URL
        self.wait_timeout = WAIT_TIMEOUT
        self.page_load_delay = PAGE_LOAD_DELAY
        self.screenshot_count = 0 
        
        self.old_expiry_time = None      
        self.new_expiry_time = None      
        self.renewal_status = "Unknown"  
        
    async def setup_browser(self):
        try:
            playwright = await async_playwright().start()
            
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-notifications',
                '--window-size=1920,1080',
                '--lang=ja-JP',
                '--accept-lang=ja-JP,ja,en-US,en'
            ]
            
            launch_options = {
                "headless": self.headless,
                "args": browser_args
            }
            
            # 🌐 代理配置：注入 Xray-core 本地 HTTP 代理
            if IS_GITHUB_ACTIONS:
                launch_options["proxy"] = {
                    "server": "http://127.0.0.1:10808"
                }
                print(f"✅ [账号{self.account_index}] 已挂载 Xray HTTP 代理 (10808)")

            self.browser = await playwright.chromium.launch(**launch_options)
            
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = await self.context.new_page()
            await stealth_async(self.page)
            print(f"✅ [账号{self.account_index}] Stealth 插件已应用，浏览器初始化成功")
            return True
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] Playwright 初始化失败: {e}")
            return False
    
    async def take_screenshot(self, step_name=""):
        try:
            if self.page:
                self.screenshot_count += 1
                beijing_time = datetime.datetime.now(timezone(timedelta(hours=8)))
                timestamp = beijing_time.strftime("%H%M%S")
                filename = f"acc{self.account_index}_step_{self.screenshot_count:02d}_{timestamp}_{step_name}.png"
                filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                await self.page.screenshot(path=filename, full_page=True)
                print(f"📸 [账号{self.account_index}] 截图已保存: {filename}")
        except Exception as e:
            print(f"⚠️ [账号{self.account_index}] 截图失败: {e}")
    
    def validate_config(self):
        if not self.email or not self.password:
            print(f"❌ [账号{self.account_index}] 邮箱或密码未设置！")
            return False
        return True
    
    async def cleanup(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            print(f"🧹 [账号{self.account_index}] 浏览器已关闭")
        except Exception as e:
            pass
    
    async def navigate_to_login(self):
        try:
            print(f"🌐 [账号{self.account_index}] 正在访问: {self.target_url}")
            await self.page.goto(self.target_url, wait_until='load', timeout=30000)
            await self.page.wait_for_selector("body", timeout=self.wait_timeout)
            print(f"✅ [账号{self.account_index}] 页面加载成功")
            return True
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 导航失败: {e}")
            return False
    
    async def find_login_form(self):
        try:
            await asyncio.sleep(self.page_load_delay)
            email_selector = "input[name='memberid']"
            await self.page.wait_for_selector(email_selector, timeout=self.wait_timeout)
            password_selector = "input[name='user_password']"
            await self.page.wait_for_selector(password_selector, timeout=self.wait_timeout)
            login_button_selector = "input[value='ログインする']"
            await self.page.wait_for_selector(login_button_selector, timeout=self.wait_timeout)
            return email_selector, password_selector, login_button_selector
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 查找表单出错: {e}")
            return None, None, None
    
    async def human_type(self, selector, text):
        for char in text:
            await self.page.type(selector, char, delay=100)
            await asyncio.sleep(0.05)
    
    async def perform_login(self):
        try:
            email_selector, password_selector, login_button_selector = await self.find_login_form()
            if not email_selector:
                return False
            
            await self.page.fill(email_selector, "")
            await self.human_type(email_selector, self.email)
            await asyncio.sleep(1)
            
            await self.page.fill(password_selector, "")
            await self.human_type(password_selector, self.password)
            await asyncio.sleep(1)
            
            if login_button_selector:
                await self.page.click(login_button_selector)
            else:
                await self.page.press(password_selector, "Enter")
            print(f"✅ [账号{self.account_index}] 登录表单已提交")
            
            try:
                print(f"⏳ [账号{self.account_index}] 等待页面跳转响应...")
                await self.page.wait_for_url("**/xapanel/xmgame/index**", timeout=20000)
            except Exception:
                print(f"⚠️ [账号{self.account_index}] 智能等待跳转超时，将交由后续逻辑校验...")
                
            return True
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 登录操作失败: {e}")
            return False
    
    async def handle_login_result(self):
        try:
            current_url = self.page.url
            success_url = "https://secure.xserver.ne.jp/xapanel/xmgame/index"
            
            if current_url == success_url:
                print(f"✅ [账号{self.account_index}] 登录成功！")
                
                try:
                    game_button_selector = "a:has-text('ゲーム管理')"
                    await self.page.wait_for_selector(game_button_selector, timeout=self.wait_timeout)
                    await self.page.click(game_button_selector)
                    
                    await self.page.wait_for_url("**/xmgame/game**", timeout=15000)
                    print(f"✅ [账号{self.account_index}] 跳转到游戏管理页面")
                    
                    await self.get_server_time_info()
                    
                except Exception as e:
                    print(f"❌ [账号{self.account_index}] 查找ゲーム管理按钮或跳转失败: {e}")
                    await self.take_screenshot("game_button_error")
                return True
            else:
                print(f"❌ [账号{self.account_index}] 登录失败！实际URL: {current_url}")
                return False
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 检查登录结果出错: {e}")
            return False
            
    async def get_server_time_info(self):
        try:
            await asyncio.sleep(2)
            elements = await self.page.locator("text=/残り\\d+時間\\d+分/").all()
            for element in elements:
                element_text = await element.text_content()
                element_text = element_text.strip() if element_text else ""
                
                if element_text and len(element_text) < 200 and "残り" in element_text and "時間" in element_text:
                    expiry_match = re.search(r'\((\d{4}-\d{2}-\d{2})まで\)', element_text)
                    if expiry_match:
                        self.old_expiry_time = expiry_match.group(1)
                        print(f"📅 [账号{self.account_index}] 记录到期时间: {self.old_expiry_time}")
                    break
                    
            await self.click_upgrade_button()
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 获取服务器时间信息失败: {e}")
    
    async def click_upgrade_button(self):
        try:
            upgrade_selector = "a:has-text('アップグレード・期限延長')"
            await self.page.wait_for_selector(upgrade_selector, timeout=self.wait_timeout)
            await self.page.click(upgrade_selector)
            
            await self.page.wait_for_url("**/xmgame/game/freeplan/extend/index**", timeout=15000)
            await self.verify_upgrade_page()
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 点击升级按钮失败: {e}")
    
    async def verify_upgrade_page(self):
        try:
            if "extend/index" in self.page.url:
                await self.check_extension_restriction()
            else:
                print(f"❌ [账号{self.account_index}] 升级页面跳转失败")
        except Exception as e:
            pass
    
    async def check_extension_restriction(self):
        try:
            restriction_selector = "text=/残り契約時間が24時間を切るまで、期限の延長は行えません/"
            try:
                element = await self.page.wait_for_selector(restriction_selector, timeout=3000)
                print(f"✅ [账号{self.account_index}] 发现限制信息：24小时内方可续期。")
                self.renewal_status = "Unexpired"
                return True
            except Exception:
                print(f"ℹ️ [账号{self.account_index}] 未见限制，开始续期...")
                await self.perform_extension_operation()
                return False
        except Exception as e:
            return True
    
    async def perform_extension_operation(self):
        try:
            extension_selector = "a:has-text('期限を延長する')"
            await self.page.wait_for_selector(extension_selector, timeout=self.wait_timeout)
            await self.page.click(extension_selector)
            
            await self.page.wait_for_url("**/extend/input**", timeout=10000)
            
            confirmation_selector = "button[type='submit']:has-text('確認画面に進む')"
            await self.page.wait_for_selector(confirmation_selector, timeout=self.wait_timeout)
            await self.page.click(confirmation_selector)
            
            await self.page.wait_for_url("**/extend/conf**", timeout=10000)
            
            time_selector = "tr:has(th:has-text('延長後の期限')) td"
            try:
                time_element = await self.page.wait_for_selector(time_selector, timeout=5000)
                self.new_expiry_time = (await time_element.text_content()).strip()
            except Exception:
                pass

            final_button_selector = "button[type='submit']:has-text('期限を延長する')"
            await self.page.wait_for_selector(final_button_selector, timeout=self.wait_timeout)
            await self.page.click(final_button_selector)
            
            await self.page.wait_for_url("**/extend/do**", timeout=15000)
            self.renewal_status = "Success"
            print(f"🎉 [账号{self.account_index}] 续期成功！")
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 续期流程中断: {e}")
            self.renewal_status = "Failed"
    
    def append_readme(self):
        """保留此函数仅用于写入仓库状态，TG通知不再使用此文件"""
        try:
            beijing_time = datetime.datetime.now(timezone(timedelta(hours=8)))
            current_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
            masked_email = self.email.split('@')[0][:3] + "***@" + self.email.split('@')[-1]
            
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
            else:
                readme_content += "📊续期结果：❌Failed<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
            
            readme_content += "\n---\n\n"
            
            with open("README.md", "a", encoding="utf-8") as f:
                f.write(readme_content)
        except Exception as e:
            pass
    
    async def run(self):
        """
        运行结束后，返回一个包含关键结果信息的字典，供 TG 内存拼装使用
        """
        try:
            print(f"\n🚀 [账号{self.account_index}] 开始处理: {self.email}")
            if await self.validate_config() and \
               await self.setup_browser() and \
               await self.navigate_to_login() and \
               await self.perform_login():
                await self.handle_login_result()
            
            self.append_readme() # 写入文件用于GitHub展示
            
        except Exception as e:
            print(f"❌ [账号{self.account_index}] 发生异常: {e}")
            self.append_readme()
            
        finally:
            await self.cleanup()
            
            # 返回结果字典
            masked_email = self.email.split('@')[0][:3] + "***@" + self.email.split('@')[-1]
            return {
                "index": self.account_index,
                "email": masked_email,
                "status": self.renewal_status,
                "old_expiry": self.old_expiry_time or 'Unknown',
                "new_expiry": self.new_expiry_time or 'Unknown'
            }

# =====================================================================
#                          Telegram 推送模块 (HTML 模式 + 内存直拼)
# =====================================================================
def send_telegram_notification(results_list):
    """直接接收包含结果的列表，组装成安全的 HTML 发送"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("ℹ️ 未配置 Telegram Token，跳过通知推送")
        return

    try:
        beijing_time = datetime.datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        
        # 组装 HTML 格式消息体
        message = f"🐢 <b>Xserver 多账号续期通知</b>\n"
        message += f"📅 执行时间：{beijing_time}\n\n"
        
        for res in results_list:
            message += f"<b>账号 {res['index']}</b>: <code>{res['email']}</code>\n"
            message += "🖥️ 服务器：<code>🇯🇵Xserver(Mc)</code>\n"
            
            if res['status'] == "Success":
                message += "📊 续期结果：✅Success\n"
                message += f"🕛️ 旧到期时间: <code>{res['old_expiry']}</code>\n"
                message += f"🕡️ 新到期时间: <code>{res['new_expiry']}</code>\n"
            elif res['status'] == "Unexpired":
                message += "📊 续期结果：ℹ️Unexpired\n"
                message += f"🕛️ 旧到期时间: <code>{res['old_expiry']}</code>\n"
            else:
                message += "📊 续期结果：❌Failed\n"
                message += f"🕛️ 旧到期时间: <code>{res['old_expiry']}</code>\n"
            
            message += "\n" # 账号之间的空行分隔

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML", # 改为安全的 HTML 解析模式
            "disable_web_page_preview": True
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram 通知推送成功！")
        else:
            print(f"❌ Telegram 推送失败: {response.text}")
            
    except Exception as e:
        print(f"❌ 发送 Telegram 通知出错: {e}")

# =====================================================================
#                          主程序入口
# =====================================================================

async def main():
    print("=" * 60)
    print("XServer GAME 自动续期 - Xray & Playwright (内存变量组装版)")
    print("=" * 60)
    
    try:
        accounts = json.loads(XSERVER_ACCOUNTS_JSON)
        if not accounts:
            raise ValueError("账号列表为空")
    except Exception as e:
        print("❌ 账号配置无效，请确保 XSERVER_ACCOUNTS 环境变量格式为 JSON 数组。")
        return

    # 初始化本地 README (仅供 GitHub Repo 查看)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write("## 🇯🇵 XServer GAME 多账号状态报告\n\n")

    all_success = True
    all_results = [] # 初始化空列表，用于收集每个账号的执行结果
    
    for index, acc in enumerate(accounts, start=1):
        email = acc.get("email")
        password = acc.get("password")
        
        if not email or not password:
            print(f"⚠️ 账号 {index} 缺失字段，跳过。")
            continue
            
        auto_login = XServerAutoLogin(email, password, index)
        
        # 捕获 run() 传回的结果字典
        result_dict = await auto_login.run()
        all_results.append(result_dict)
        
        if result_dict['status'] not in ["Success", "Unexpired"]:
            all_success = False
            
        if index < len(accounts):
            await asyncio.sleep(2)

    # 统一触发 Telegram 通知，直接将内存中的列表传进去！
    send_telegram_notification(all_results)

    if all_success:
        print("\n✅ 所有账号流程执行完毕！")
        exit(0)
    else:
        print("\n⚠️ 流程执行完毕，部分账号存在异常。")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
