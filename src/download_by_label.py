from bs4 import BeautifulSoup
import time
import download_by_special_page


def download_pic_from_label(label, driver, pic_folder, pic_num):
    page_url = f'https://www.pixiv.net/tags/{label}/illustrations'

    driver.get(page_url)

    time.sleep(3)

    html = driver.page_source

    soup = BeautifulSoup(html, 'lxml')

    result_tuples = []

    for element in soup.find_all(attrs={'data-gtm-value': True}):
        gtm_value = element.get('data-gtm-value')
        href_value = element.get('href')

        if gtm_value and href_value:
            result_tuples.append((gtm_value, href_value))
        elif gtm_value:
            result_tuples.append((gtm_value, None))

    tem_ls = []
    for item in result_tuples:
        if item[1] is None:
            continue
        art_or_user_id = item[1].split('/')[1] if len(item[1].split('/')) > 1 else ''
        if art_or_user_id == 'artworks':
            tem_ls.append(item)
    
    if not tem_ls:
        return []
    
    res_ls = []
    seen = set()
    for item in tem_ls:
        if item[0] not in seen:
            seen.add(item[0])
            res_ls.append(item)
    
    print(f"找到 {len(res_ls)} 个作品")
    
    path_ls = []
    downloaded_count = 0
    
    for ele in res_ls:
        if downloaded_count >= pic_num:
            break
        
        pic_id = ele[0]
        remaining = pic_num - downloaded_count
        print(f"下载作品 {pic_id}，还需下载 {remaining} 张")
        
        paths = download_by_special_page.download_pic_from_single_page(pic_id, driver, pic_folder, remaining)
        
        for path in paths:
            if downloaded_count >= pic_num:
                break
            path_ls.append(path)
            downloaded_count += 1
            print(f"成功下载第 {downloaded_count} 张图片")
    
    print(f"总共下载 {len(path_ls)} 张图片")
    return path_ls
