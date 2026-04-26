import requests
import os
import const


def download_pic(pic_url, path):
    # 确保目录存在
    dir_path = os.path.dirname(path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    
    # 每次下载时动态获取 headers
    headers = const.get_header()
    if not headers:
        print("Warning: headers is empty, download may fail")
    
    response = requests.get(pic_url, headers=headers)
    with open(path, 'wb') as f:
        f.write(response.content)
    # 删除机制
    file_size = os.path.getsize(path)
    if file_size < 10000:
        os.remove(path)
        print('predictable error')
        return False, 'predictable error'
    else:
        print(f'downloading')
        return True, f'downloading'