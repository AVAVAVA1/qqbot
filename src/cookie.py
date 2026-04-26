import pickle
import json
from selenium import webdriver
import time


def save_cookies(driver, file_path="cookies.pkl"):
    """保存当前会话的Cookie"""
    cookies = driver.get_cookies()
    with open(file_path, 'wb') as file:
        pickle.dump(cookies, file)
    print(f"Cookie已保存到 {file_path}")


def load_cookies(driver, file_path="cookies.pkl"):
    """加载Cookie到当前会话"""
    with open(file_path, 'rb') as file:
        cookies = pickle.load(file)

    # 先访问网站域名，才能设置Cookie
    driver.get("https://example.com")
    time.sleep(2)

    # 删除旧的Cookie
    driver.delete_all_cookies()

    # 添加Cookie
    for cookie in cookies:
        # 处理特殊字符
        if 'expiry' in cookie:
            cookie['expiry'] = int(cookie['expiry'])
        driver.add_cookie(cookie)

    print("Cookie已加载")
    return driver


# 完整示例：获取并保存Cookie
def get_and_save_cookies(driver):


    # 手动登录
    driver.get("https://accounts.pixiv.net/login?return_to=https%3A%2F%2Fwww.pixiv.net%2F&lang=zh&source=pc&view_type=page")
    print("请手动登录...")
    time.sleep(30)  # 给足够时间手动登录


    save_cookies(driver, "cookies.pkl")





# 使用保存的Cookie访问需要登录的页面
def access_with_cookies(driver, path):


    try:
        # 加载Cookie
        driver = load_cookies(driver, "cookies.pkl")

        # 刷新页面使Cookie生效
        driver.refresh()

        # 访问需要登录的页面
        driver.get(path)

        # 检查是否成功访问
        if "需要登录" not in driver.page_source:
            print("成功访问受保护页面")
            return driver.page_source
        else:
            print("Cookie可能已过期")
            return None

    except Exception as e:
        print(f"访问失败: {e}")
        return None


# 使用JSON格式保存Cookie（更易读）
def save_cookies_json(driver, file_path="cookies.json"):
    cookies = driver.get_cookies()
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(cookies, file, ensure_ascii=False, indent=2)


def load_cookies_json(driver, file_path="cookies.json"):
    with open(file_path, 'r', encoding='utf-8') as file:
        cookies = json.load(file)

    driver.get("https://example.com")
    driver.delete_all_cookies()

    for cookie in cookies:
        driver.add_cookie(cookie)

    return driver


def set_cookies_from_string(driver, cookie_string, domain=None):
    """
    从字符串设置Cookie

    Args:
        driver: WebDriver实例
        cookie_string: 完整的Cookie字符串
        domain: 域名（可选，自动从当前URL提取）
    """
    if not domain:
        # 从当前URL提取域名
        current_url = driver.current_url
        domain = current_url.split('/')[2]
        # 如果是顶级域名，添加点前缀
        if domain.startswith('www.'):
            domain = '.' + domain[4:]

    # 删除旧Cookie
    driver.delete_all_cookies()

    # 解析Cookie字符串
    cookies = cookie_string.split('; ')

    success_count = 0
    fail_count = 0

    for cookie in cookies:
        if '=' in cookie:
            try:
                name, value = cookie.split('=', 1)

                cookie_dict = {
                    'name': name.strip(),
                    'value': value.strip(),
                    'domain': domain
                }

                # 添加一些常见属性
                cookie_dict['path'] = '/'

                # 特殊Cookie处理
                if name.strip() in ['PHPSESSID', 'session', 'sessionid']:
                    cookie_dict['httpOnly'] = True

                driver.add_cookie(cookie_dict)
                success_count += 1

            except Exception as e:
                print(f"处理Cookie失败: {cookie[:50]}... 错误: {str(e)[:50]}")
                fail_count += 1

    print(f"Cookie设置完成: 成功 {success_count}, 失败 {fail_count}")
    return success_count > 0