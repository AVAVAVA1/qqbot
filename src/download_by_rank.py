from bs4 import BeautifulSoup
import time
import download_pic_fun
import re

'''
https://www.pixiv.net/ranking.php?mode=daily&content=illust
https://i.pximg.net/img-original/img/2025/03/04/00/00/11/127839312_p0.png
daily, weekly, monthly, rookie
'''


def download_pic_from_ranking_page(selected_time, driver, pic_folder, pic_num):
    time_ls = ['daily', 'weekly', 'monthly', 'rookie']
    if selected_time not in time_ls:
        print('time error')
        return []
    
    page_url = f'https://www.pixiv.net/ranking.php?mode={selected_time}&content=illust'
    driver.get(page_url)

    time.sleep(2)

    html = driver.page_source
    soup = BeautifulSoup(html, 'lxml')
    
    image_tag = soup.find_all('script', id='__NEXT_DATA__')
    pic_idANDdate_ls = []
    path_ls = []
    
    if image_tag is not None:
        for image in image_tag:
            ls = str(image).split(',')
            ls_image = []
            for i in ls:
                if i[1:4] == 'url':
                    ls_image.append(i)
            
            for element in ls_image:
                try:
                    match = re.search(r'/(\d{4}/\d{2}/\d{2}/\d{2}/\d{2}/\d{2}/\d+)_', element)
                    if match:
                        data = match.group(1)
                        if data not in pic_idANDdate_ls:
                            pic_idANDdate_ls.append(data)
                except:
                    continue
        
        print(f"找到 {len(pic_idANDdate_ls)} 个作品")
        
        downloaded_count = 0
        for pic in pic_idANDdate_ls:
            if downloaded_count >= pic_num:
                break
            
            pic_id = pic.split('/')[-1]
            style = 'png'
            page_counter = 0
            
            while True:
                if downloaded_count >= pic_num:
                    break
                    
                path = f'../pic/{pic_folder}/{pic.replace("/", "_")}_p{page_counter}.{style}'
                pic_url = f'https://i.pximg.net/img-original/img/{pic}_p{page_counter}.{style}'
                print(f"尝试下载: {pic_url}")
                
                status, text = download_pic_fun.download_pic(pic_url=pic_url, path=path)
                
                if not status:
                    if page_counter == 0:
                        style = 'jpg'
                        print('png失败，尝试jpg')
                        path = f'../pic/{pic_folder}/{pic.replace("/", "_")}_p{page_counter}.{style}'
                        pic_url = f'https://i.pximg.net/img-original/img/{pic}_p{page_counter}.{style}'
                        status, text = download_pic_fun.download_pic(pic_url=pic_url, path=path)
                    
                    if not status:
                        print(f'作品 {pic_id} 下载完成或失败')
                        break
                
                if status:
                    path_ls.append(path)
                    downloaded_count += 1
                    print(f"成功下载第 {downloaded_count} 张图片")
                
                page_counter += 1

    else:
        print('未找到图片数据')
    
    print(f"总共下载 {len(path_ls)} 张图片")
    return path_ls
