from bs4 import BeautifulSoup
import time
import cookie
import re
import download_pic_fun
import const


def download_pic_from_single_page(page_url, driver, pic_folder, pic_num):
    headers = const.get_header()
    
    if not headers:
        print("Warning: cookie.json 为空，可能无法下载 Pixiv 图片")
        return []

    cookie_str = headers.get('cookie', '')
    if not cookie_str:
        print("Warning: cookie 为空，可能无法下载 Pixiv 图片")
    
    driver.get('https://www.pixiv.net/')
    cookie.set_cookies_from_string(driver, cookie_string=cookie_str)
    page_url = f'https://www.pixiv.net/artworks/{page_url}'
    driver.get(page_url)

    time.sleep(2)

    html = driver.page_source

    soup = BeautifulSoup(html, 'lxml')
    
    pattern = r'https://i\.pximg\.net/img-original/img/(\d{4}/\d{1,2}/\d{1,2}/\d{1,2}/\d{1,2}/\d{1,2}/\d+)_p0\.(png|jpg)'
    text = str(soup.prettify())
    match = re.search(pattern, text)

    if not match:
        print(f"未找到图片信息: {page_url}")
        return []

    part1 = match.group(1)
    part2 = match.group(2)
    print(f"日期数字部分: {part1}")
    print(f"文件扩展名: {part2}")
    
    part_name = part1.replace('/', '_')
    counter = 0
    path_ls = []
    
    while counter < pic_num:
        pic_url = f'https://i.pximg.net/img-original/img/{part1}_p{counter}.{part2}'
        path = f'../pic/{pic_folder}/{part_name}_p{counter}.{part2}'
        print(f"尝试下载: {pic_url}")
        
        status, text = download_pic_fun.download_pic(pic_url, path=path)
        
        if not status:
            if counter == 0 and part2 == 'png':
                part2 = 'jpg'
                pic_url = f'https://i.pximg.net/img-original/img/{part1}_p{counter}.{part2}'
                path = f'../pic/{pic_folder}/{part_name}_p{counter}.{part2}'
                print(f'png失败，尝试jpg: {pic_url}')
                status, text = download_pic_fun.download_pic(pic_url, path=path)
            
            if not status:
                print(f'下载完成或失败，共下载 {len(path_ls)} 张')
                break
        
        if status:
            path_ls.append(path)
            print(f"成功下载第 {len(path_ls)} 张图片")
        
        counter += 1
    
    print(f"作品下载完成，共 {len(path_ls)} 张图片")
    return path_ls
