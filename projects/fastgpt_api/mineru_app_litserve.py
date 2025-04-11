import gc
import os
import time
from base64 import b64encode

import litserve as ls
import torch
from fastapi import HTTPException

from magic_pdf.config.enums import SupportedPdfParseMethod
from magic_pdf.config.make_content_config import DropMode, MakeMode
from magic_pdf.data.data_reader_writer import FileBasedDataWriter
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.operators.pipes import PipeResult

MinerU_OUTPUT_DIR = os.getenv("MinerU_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "output"))


def clean_memory():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    gc.collect()


class MinerUAPI(ls.LitAPI):
    def __init__(self):
        self.doc_parse = None
        self.output_dir = MinerU_OUTPUT_DIR

    def setup(self, device):
        if device.startswith('cuda'):
            os.environ['CUDA_VISIBLE_DEVICES'] = device.split(':')[-1]
            if torch.cuda.device_count() > 1:
                raise RuntimeError("Remove any CUDA actions before setting 'CUDA_VISIBLE_DEVICES'.")

        from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
        from magic_pdf.model.doc_analyze_by_custom_model import ModelSingleton

        self.doc_parse = doc_analyze

        model_manager = ModelSingleton()
        model_manager.get_model(True, False)
        model_manager.get_model(False, False)
        print(f'Model initialization complete on {device}!')

    def decode_request(self, request: ls.Request, **kwargs):
        file = request['file']
        file_content = file.file.read()
        opts = request.get('kwargs', {})
        opts.setdefault('file_name', file.filename)
        opts.setdefault('debug_able', False)
        opts.setdefault('parse_method', 'auto')
        return file_content, opts

    def predict(self, inputs):

        try:
            result = self.pdf_parse(inputs[0], **inputs[1])
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            clean_memory()

    def encode_response(self, response, **kwargs):
        return {"success": True, "message": "", "data": response}

    def pdf_parse(self, file_content: bytes, **kwargs):
        start_time = time.time()
        pdf_name = kwargs['file_name'].split(".")[0]
        md_content, page_count = self.process_file_with_multiprocessing(file_content, pdf_name)

        end_time = time.time()
        duration = end_time - start_time
        print(f"==================【{pdf_name}】 解析完成，开始时间: {start_time}, 解析耗时: {duration}==================")
        return {
            "markdown": md_content,
            "page": page_count,
            "duration": duration
        }

    def process_file_with_multiprocessing(self, pdf_bytes: bytes, pdf_name: str):

        output_dir = os.path.join(self.output_dir, pdf_name)
        output_image_dir = os.path.join(output_dir, "images")
        if not os.path.exists(output_image_dir):
            os.makedirs(output_image_dir)

        md_writer = FileBasedDataWriter(output_dir)
        image_writer = FileBasedDataWriter(output_image_dir)

        # 读取并解析pdf文件
        ds = PymuDocDataset(pdf_bytes)
        pipe_result: PipeResult = None
        if ds.classify() == SupportedPdfParseMethod.OCR:
            infer_result = ds.apply(self.doc_parse, ocr=True)
            pipe_result = infer_result.pipe_ocr_mode(image_writer)
        else:
            infer_result = ds.apply(self.doc_parse, ocr=False)
            pipe_result = infer_result.pipe_txt_mode(image_writer)

        md_content = pipe_result.get_markdown("images", DropMode.NONE, MakeMode.MM_MD)
        embed_md_content = self.embed_images_as_base64(md_content, output_image_dir)
        md_writer.write_string(os.path.join(output_dir, f"{pdf_name}.md"), embed_md_content)
        return embed_md_content, len(ds)

    @staticmethod
    def encode_image(image_path: str) -> str:
        """Encode image using base64"""
        with open(image_path, "rb") as f:
            return b64encode(f.read()).decode('utf-8')

    def embed_images_as_base64(self, md_content, image_dir):
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
                    img_base64 = self.encode_image(img_path)
                    new_line = f'{line[:start_idx]}data:image/png;base64,{img_base64}{line[end_idx:]}'
                    new_lines.append(new_line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        return '\n'.join(new_lines)


if __name__ == '__main__':
    server = ls.LitServer(
        MinerUAPI(),
        api_path='/v2/parse/file',
        accelerator='cuda',
        devices='auto',
        workers_per_device=1,
        timeout=False
    )
    server.run(port=8000, generate_client_file=False)
