import os
import time
from base64 import b64encode
from typing import Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from loguru import logger

import magic_pdf.model as model_config
from magic_pdf.config.enums import SupportedPdfParseMethod
from magic_pdf.config.make_content_config import DropMode, MakeMode
from magic_pdf.data.data_reader_writer import FileBasedDataWriter
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.operators.pipes import PipeResult

model_config.__use_inside_model__ = True

app = FastAPI()
MinerU_OUTPUT_DIR = os.getenv("MinerU_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "output"))

def init_writers(
        file: UploadFile = None,
        output_path: str = None,
        output_image_path: str = None,
) -> Tuple[
    FileBasedDataWriter,
    FileBasedDataWriter,
    bytes,
]:
    """
    Initialize writers based on path type

    Args:
        file: Uploaded PDF file object
        output_path: Output directory path
        output_image_path: Image output directory path

    Returns:
        Tuple[writer, image_writer, pdf_bytes]: Returns initialized writer tuple and PDF
        file content
    """

    # 处理上传的文件
    pdf_bytes = file.file.read()
    writer = FileBasedDataWriter(output_path)
    image_writer = FileBasedDataWriter(output_image_path)
    os.makedirs(output_image_path, exist_ok=True)

    return writer, image_writer, pdf_bytes


def process_pdf(
        pdf_bytes: bytes,
        parse_method: str,
        image_writer: FileBasedDataWriter,
) -> Tuple[PipeResult, int]:
    """
    Process PDF file content

    Args:
        pdf_bytes: Binary content of PDF file
        parse_method: Parse method ('ocr', 'txt', 'auto')
        image_writer: Image writer

    Returns:
        Tuple[PipeResult,int]: Returns inference result and pipeline result and page count
    """
    ds = PymuDocDataset(pdf_bytes)
    pipe_result: PipeResult = None
    if ds.classify() == SupportedPdfParseMethod.OCR:
        infer_result = ds.apply(doc_analyze, ocr=True)
        pipe_result = infer_result.pipe_ocr_mode(image_writer)
    else:
        infer_result = ds.apply(doc_analyze, ocr=False)
        pipe_result = infer_result.pipe_txt_mode(image_writer)

    return pipe_result, len(ds)


def encode_image(image_path: str) -> str:
    """Encode image using base64"""
    with open(image_path, "rb") as f:
        return b64encode(f.read()).decode('utf-8')


def embed_images_as_base64(md_content, image_dir):
    lines = md_content.split('\n')
    new_lines = []
    for line in lines:
        if line.startswith("![") and "](" in line and ")" in line:
            start_idx = line.index("](") + 2
            end_idx = line.index(")", start_idx)
            img_rel_path = line[start_idx:end_idx]

            img_name = os.path.basename(img_rel_path)
            img_path = os.path.join(image_dir, img_name)

            if os.path.exists(img_path):
                img_base64 = encode_image(img_path)
                new_line = f'{line[:start_idx]}data:image/png;base64,{img_base64}{line[end_idx:]}'
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    return '\n'.join(new_lines)

@app.post("/v1/parse/file")
# @profile
async def pdf_parse(
        file: UploadFile = File(...),
        output_dir: str = None,
):
    """
    解析pdf文件病输出到指定目录

    Args:
        file: The PDF file to be parsed.
        output_dir: Output directory for results. A folder named after the PDF file
            will be created to store all results
    """
    output_dir = output_dir or MinerU_OUTPUT_DIR
    try:
        start_time = time.time()

        # Get PDF filename
        pdf_name = os.path.basename(file.filename).split(".")[0]
        output_path = f"{output_dir}/{pdf_name}"
        output_image_path = f"{output_path}/images"

        # Initialize readers/writers and get PDF content
        md_writer, image_writer, pdf_bytes = init_writers(
            file=file,
            output_path=output_path,
            output_image_path=output_image_path,
        )

        # Process PDF
        pipe_result, page_count = process_pdf(pdf_bytes, "auto", image_writer)

        md_content = pipe_result.get_markdown("images", DropMode.NONE, MakeMode.MM_MD)
        embed_md_content = embed_images_as_base64(md_content, output_image_path)
        md_writer.write_string(os.path.join(output_path, f"{pdf_name}.md"), embed_md_content)

        # 解析时间统计
        end_time = time.time()
        duration = end_time - start_time
        print(file.filename + " 解析完成，耗时:", duration)

        # Build return data
        data = {
            "success": True,
            "message": "",
            "data": {
                "markdown": md_content,
                "page": page_count,
                "duration": duration
            }
        }
        return data
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=f"错误信息: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888)
