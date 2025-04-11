import requests
import time

import numpy as np
import requests
from joblib import Parallel, delayed
from loguru import logger


def do_parse(file_path, url='http://127.0.0.1:8000/api', **kwargs):
    try:
        start_time = time.time()
        with open(file_path, 'rb') as f:
            files = {'file': f}
            # 准备其他参数
            data = kwargs

            # 发送POST请求
            response = requests.post(url, files=files, data=data)
        end_time = time.time()
        duration = end_time - start_time
        print(f'File: {file_path} -开始时间: {start_time}s -结束时间: {end_time}s - Duration: {duration}s')
        if response.status_code == 200:
            output = response.json()
            output['file_path'] = file_path
            return output
        else:
            raise Exception(response.text)
    except Exception as e:
        logger.error(f'File: {file_path} - Info: {e}')


if __name__ == '__main__':
    dir_path = "E:/GitLab/OpenCode/AI/MinerU/MinerU/demo"
    files = [f'{dir_path}/small_ocr.pdf',f'{dir_path}/demo1.pdf',f'{dir_path}/demo2.pdf']
    # files = [f'{dir_path}/small_ocr.pdf']
    n_jobs = np.clip(len(files), 1, 8)
    results = Parallel(n_jobs, prefer='threads', verbose=10)(
        delayed(do_parse)(p) for p in files
    )
    # print(results)
