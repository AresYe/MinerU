import asyncio
import multiprocessing as mp
import os
import time
from base64 import b64encode
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
import shutil
import hashlib
import pypdfium2 as pdfium
import torch
import uvicorn
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from loguru import logger

from mineru.cli.common import read_fn, do_parse
from mineru.utils.config_reader import get_device

process_variables = {}
my_pool = None
MinerU_OUTPUT_BASE_DIR = os.getenv("MinerU_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "output"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI应用的生命周期管理函数，在应用启动和关闭时执行相应的资源管理操作。

    该函数使用异步上下文管理器模式，负责初始化和清理多进程资源，包括设置多进程启动方法、
    创建进程池执行器以及在应用关闭时清理资源。

    参数:
        app (FastAPI): FastAPI应用实例，由FastAPI框架自动传入

    返回值:
        无直接返回值，但通过yield将控制权交还给FastAPI框架，实现生命周期管理
    """
    try:
        # 设置多进程启动方法为'spawn'，强制覆盖可能存在的其他设置
        # spawn方法在不同平台上行为更一致，避免fork方法可能带来的问题
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        # 当尝试重复设置启动方法时抛出异常，提示用户重新运行脚本
        raise RuntimeError(
            "Set start method to spawn twice. This may be a temporary issue with the script. Please try running it again.")

    # 声明使用全局变量my_pool来存储进程池执行器实例
    global my_pool

    # 创建多进程管理器，用于在进程间共享数据
    manager = mp.Manager()

    # 创建共享的工作者计数器和锁，用于进程间同步
    worker_counter = manager.Value('i', 0)
    worker_lock = manager.Lock()

    # 获取可用GPU数量，用于计算进程池大小
    gpu_count = torch.cuda.device_count()

    # 根据GPU数量和环境变量设置创建进程池执行器
    # 进程池大小 = GPU数量 × 每个GPU的进程数(默认为1)
    my_pool = ProcessPoolExecutor(max_workers=gpu_count * int(os.environ.get('PROCESSES_PER_GPU', 1)),
                                  initializer=worker_init, initargs=(worker_counter, worker_lock))

    # 将控制权交还给FastAPI框架，此时应用开始正常运行
    yield

    # 应用关闭阶段：如果进程池存在则关闭并等待所有任务完成
    if my_pool:
        my_pool.shutdown(wait=True)

    # 打印应用关闭和资源清理完成的信息
    logger.info("Application shutdown, cleaning up...")

app = FastAPI(lifespan=lifespan)


def worker_init(counter, lock):
    """
    初始化工作进程的函数，用于设置GPU设备分配和模型加载

    参数:
        counter: 多进程计数器对象，用于为每个工作进程分配唯一的ID
        lock: 多进程锁对象，用于保护计数器访问的线程安全

    返回值:
        无返回值

    功能说明:
        1. 根据GPU数量和环境变量设置为当前工作进程分配合适的GPU设备
        2. 初始化模型转换器并存储到全局变量中供后续使用
        3. 确保多进程环境下的设备分配不会冲突
    """
    # 获取系统中可用的GPU数量
    num_gpus = torch.cuda.device_count()
    processes_per_gpu = int(os.environ.get('PROCESSES_PER_GPU', 1))

    # 使用锁保护计数器访问，为当前工作进程分配唯一ID
    with lock:
        worker_id = counter.value
        counter.value += 1

    # 根据GPU数量和工作进程ID确定设备分配
    if num_gpus == 0:
        device = 'cpu'
    else:
        device_id = worker_id // processes_per_gpu
        if device_id >= num_gpus:
            raise ValueError(f"Worker ID {worker_id} exceeds available GPUs ({num_gpus}).")
        device = f'cuda:{device_id}'

    # 配置模型转换器参数
    config = {
        "parse_method": "auto",
        "ADDITIONAL_KEY": "VALUE"
    }

    # 初始化模型转换器并将其与当前进程ID关联存储
    converter = init_converter(config, device_id)
    pid = os.getpid()
    process_variables[pid] = converter

    logger.info(f"Worker {worker_id}: Models loaded successfully on [{device}]. PID=[{pid}]!")

def init_converter(config, device_id):
    """
    初始化转换器配置函数

    该函数用于设置转换器运行所需的环境变量配置，包括CUDA设备、运行模式和模型源等参数

    参数:
        config: 转换器配置对象，用于存储和传递配置信息
        device_id: 设备ID，指定要使用的CUDA设备编号

    返回值:
        返回更新后的配置对象
    """
    # 设置CUDA可见设备ID
    os.environ["CUDA_VISIBLE_DEVICES"] = str(device_id)

    # 设置运行设备模式
    os.environ['MINERU_DEVICE_MODE'] = get_device()

    # 设置模型源，默认为本地模式
    os.environ["MINERU_MODEL_SOURCE"] = os.environ.get('MINERU_MODEL_SOURCE', "local")

    return config

def process_pdf(
        doc_path: str,
        output_dir,
        lang="ch",
        backend="pipeline",
        method="auto",
        server_url=None,
        interval_page=100,
        total_pages=None
):
    """
    处理PDF文档，将其按指定页数分块解析并保存到输出目录中。

    参数:
        doc_path (str): PDF文档的路径。
        output_dir: 解析结果输出的根目录。
        lang (str): 文档语言，默认为"ch"（中文）。
        backend (str): 使用的解析后端，默认为"pipeline"。
        method (str): 解析方法，默认为"auto"。
        server_url (str or None): 服务器地址，用于远程解析，默认为None。
        interval_page (int): 每次处理的页数间隔，默认为100页。
        total_pages (int or None): 需要处理的总页数，若为None则可能默认处理全部页面。

    返回:
        dict: 包含处理状态、信息和输出路径等的结果字典。
              成功时返回：
                  {
                      "status": "success",
                      "text": "",
                      "output_path": [分块输出目录列表],
                      "images": "images"
                  }
              失败时返回：
                  {
                      "status": "error",
                      "message": 错误信息,
                      "file": 出错文件路径
                  }
    """
    try:
        file_name_list = []
        pdf_bytes_list = []
        lang_list = []
        file_name = str(Path(doc_path).stem)
        pdf_bytes = read_fn(doc_path)
        file_name_list.append(file_name)
        pdf_bytes_list.append(pdf_bytes)
        lang_list.append(lang)

        # 分块解析输出目录
        output_dirs = []
        end_page = None

        # 将PDF按指定页数分块进行解析
        for i in range(-1, total_pages, interval_page):
            start_page = i + 1
            if total_pages >= interval_page:
                end_page = min(start_page + interval_page - 1, total_pages - 1)
            # 分块解析输出目录
            chunk_output_dir = os.path.join(output_dir, f"{start_page}_{end_page}")
            do_parse(
                output_dir=chunk_output_dir,
                pdf_file_names=file_name_list,
                pdf_bytes_list=pdf_bytes_list,
                p_lang_list=lang_list,
                backend=backend,
                parse_method=method,
                server_url=server_url,
                start_page_id=start_page,
                end_page_id=end_page,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
                f_dump_middle_json=False,
                f_dump_model_output=False,
                f_dump_orig_pdf=False,
                f_dump_content_list=False
            )
            output_dirs.append(chunk_output_dir)
        return {
            "status": "success",
            "text": "",
            "output_path": output_dirs,
            "images": "images"
        }
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "file": doc_path[0]
        }



def encode_image(image_path: str) -> str:
    """
    将指定路径的图片文件进行Base64编码并返回编码后的字符串

    参数:
        image_path (str): 图片文件的路径

    返回值:
        str: 图片文件的Base64编码字符串
    """
    # 以二进制模式读取图片文件内容并进行Base64编码
    with open(image_path, "rb") as f:
        return b64encode(f.read()).decode('utf-8')



def embed_images_as_base64(md_content, image_dir):
    """
    将Markdown内容中的图片引用替换为base64编码的内嵌图片

    参数:
        md_content (str): 包含图片引用的Markdown文本内容
        image_dir (str): 图片文件所在的目录路径

    返回:
        str: 处理后的Markdown内容，其中存在的图片已被替换为base64编码
    """
    lines = md_content.split('\n')
    new_lines = []
    for line in lines:
        # 检查当前行是否包含Markdown图片语法: ![alt](src)
        if line.startswith("![") and "](" in line and ")" in line:
            # 提取图片相对路径
            start_idx = line.index("](") + 2
            end_idx = line.index(")", start_idx)
            img_rel_path = line[start_idx:end_idx]

            # 构造图片完整路径
            img_name = os.path.basename(img_rel_path)
            img_path = os.path.join(image_dir, img_name)

            # 如果图片文件存在，则替换为base64编码
            if os.path.exists(img_path):
                img_base64 = encode_image(str(img_path))
                new_line = f'{line[:start_idx]}data:image/png;base64,{img_base64}{line[end_idx:]}'
                new_lines.append(new_line)
            else:
                # 图片文件不存在，保留原行
                new_lines.append(line)
        else:
            # 非图片行直接保留
            new_lines.append(line)
    return '\n'.join(new_lines)



count = 0


@app.post("/v2/parse/file")
async def process_pdfs(file: UploadFile = File(...)):
    """
    异步处理上传的PDF文件，进行解析并返回Markdown格式结果。

    参数:
        file (UploadFile): 通过POST请求上传的PDF文件对象。

    返回:
        dict 或 JSONResponse: 成功时返回包含解析结果的字典，失败时返回错误信息的JSON响应。
    """
    s_time = time.time()
    global count
    count = count + 1
    logger.info(f"==========计数: {count}")

    # 读取文件内容
    file_content = await file.read()
    # 计算文件的MD5哈希值，基于MD5创建输出目录路径
    file_hash = hashlib.md5(file_content).hexdigest()
    file_name_stem = Path(file.filename).stem
    output_dir = os.path.join(MinerU_OUTPUT_BASE_DIR, f"{file_hash}_{file_name_stem}")
    # 解析结果是否已经存在
    parsed_md_file_result = os.path.join(output_dir, f"{file_name_stem}.md")
    # 原始文件保存路径
    origin_file_path = os.path.join(output_dir, file.filename)

    # 判断是否已经解析过该文件
    has_parsed = os.path.exists(parsed_md_file_result)
    try:
        # 如果未解析过，则写入原始文件到指定路径
        if not has_parsed:
            Path(origin_file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(str(origin_file_path), "wb") as buffer:
                buffer.write(file_content)
        # 获取PDF文件总页数
        pdf_document = pdfium.PdfDocument(str(origin_file_path))
        total_pages = len(pdf_document)
    except Exception as e:
        total_pages = 0
        logger.error(f"Error Count PDF Pages: {str(e)}")

    try:
        # 如果结果没有解析过，则进行解析
        if not has_parsed:
            # 使用线程池异步执行PDF解析任务
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                my_pool,
                process_pdf,
                origin_file_path,
                output_dir,
                "ch",
                "pipeline",
                "auto",
                None,
                100,
                total_pages
            )
            # 解析失败，直接返回错误信息
            if results.get("status") == "error":
                # 删除输出目录
                shutil.rmtree(output_dir, ignore_errors=True)
                logger.error(f"Error processing PDF: {results.get('message')}")
                return JSONResponse(content={
                    "success": False,
                    "message": "",
                    "error": f"【{file.filename}】解析失败：{results.get('message')}"
                }, status_code=500)

            # 合并分块的解析结果
            for chunk_output_dir in results.get("output_path"):
                # 获取当前分块的解析结果文件路径和图片目录路径
                parsed_md_file_chunk = os.path.join(chunk_output_dir,file_name_stem, "auto", f"{file_name_stem}.md")
                image_dir = os.path.join(chunk_output_dir, file_name_stem, "auto", "images")
                # 读取分块解析结果，并将其中的图片转为base64嵌入格式
                with open(parsed_md_file_chunk, "r", encoding="utf-8") as f:
                    md_content_chunk = f.read()
                    md_content_chunk_with_base64 = embed_images_as_base64(md_content_chunk, image_dir)
                # 将处理后的分块内容追加到最终结果文件中
                with open(parsed_md_file_result, "a", encoding="utf-8") as f:
                    f.write(md_content_chunk_with_base64)

        # 读取最终解析结果文件内容
        with open(parsed_md_file_result, "r", encoding="utf-8") as f:
            finally_result = f.read()

        e_time = time.time()
        logger.info(f"【{origin_file_path}】解析完成。耗时: {e_time - s_time}，是否使用缓存: {has_parsed}")
        return {
            "success": True,
            "message": "",
            "markdown": finally_result,
            "pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error in process_pdfs: {str(e)}")
        return JSONResponse(content={
            "success": False,
            "message": "",
            "error": f"【{file.filename}】Internal server error: {str(e)}"
        }, status_code=500)



if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8888, reload=False)
