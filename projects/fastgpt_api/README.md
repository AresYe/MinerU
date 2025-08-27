# 项目介绍

本项目是基于MinerU实现的适用于Fastgpt将PDF文档或图片解析 Markdown 格式文本的API。

# 快速开始

参考链接[MinerU快速开始](https://github.com/opendatalab/MinerU/blob/master/README_zh-CN.md)

## 基础环境配置

### 安装Anaconda并创建虚拟环境

python 版本 **3.10-3.13**

```bash
conda create -n mineru python=3.12.5
conda activate mineru
```

### 使用pip或uv安装MinerU

```bash
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple
pip install uv -i https://mirrors.aliyun.com/pypi/simple
uv pip install -U "mineru[core]" -i https://mirrors.aliyun.com/pypi/simple
```

### 解析模型源配置

模型相关配置参考链接[模型配置](https://github.com/opendatalab/MinerU/blob/master/docs/zh/usage/model_source.md)

```bash
mineru-models-download
```

> [!NOTE]
>- 下载完成后，模型路径会在当前终端窗口输出，并自动写入用户目录下的 `mineru.json`。
>- 您也可以通过将[配置模板文件](https://github.com/opendatalab/MinerU/blob/master/mineru.template.json)复制到用户目录下并重命名为
   `mineru.json` 来创建配置文件。(Linux为~/.mineru.json，Windows为C:\Users\用户名\.mineru.json)
>- 模型下载到本地后，您可以自由移动模型文件夹到其他位置，同时需要在 `mineru.json` 中更新模型路径。
>- 如您将模型文件夹部署到其他服务器上，请确保将 `mineru.json`文件一同移动到新设备的用户目录中并正确配置模型路径。
>- 如您需要更新模型文件，可以再次运行 `mineru-models-download`
   命令，模型更新暂不支持自定义路径，如您没有移动本地模型文件夹，模型文件会增量更新；如您移动了模型文件夹，模型文件会重新下载到默认位置并更新
   `mineru.json`。
>- 建议直接复制已下载好的模型文件到生产环境，避免模型文件重复下载。

## 使用说明
**前置条件：完成基础环境配置及解析模型源配置**
1. 复制fastgpt_api文件夹到指定目录，并进入该目录；
2. 修改启动脚本中的python解释器路径;*(Windows: mineru_service.bat;Linux: mineru_service.sh)*
3. 命令窗口运行脚本启动停止命令进行服务启动或停止；*(Windows: mineru_service.bat start|stop；Linux: sh mineru_service.sh start|stop)*

# 使用问题记录

## CUDA加速

nvidia-smi查看显卡信息，显卡驱动要与CUDA版本兼容，否则需要重新安装torch以来版本。

[cuda版本对应torch版本](https://pytorch.org/get-started/previous-versions/)

```
pip install --force-reinstall torch==2.6.0 torchvision==0.21.0 "numpy<2.0.0" --index-url https://download.pytorch.org/whl/cu124
pip install --force-reinstall torch==2.3.1 torchvision==0.18.1 "numpy<2.0.0" --index-url https://download.pytorch.org/whl/cu118
```

# 配置及解析效率

| 文档说明               | Windows 解析效率<br/>(GPU:8G.CPU:32G) | Windows 解析效率<br/>(GPU:2\*48G.CPU:6\*64G) | Linux 解析效率<br/>(GPU:2\*24G.CPU:64G) | 备注     |
|:-------------------|:----------------------------------|:-----------------------------------------|:------------------------------------|--------|
| 6页英文论文+图片PDF文档     | 17s                               | 12s                                      | 11s                                 |
| 8页中文图片式PDF文档       | 12s                               | 8s                                       | 7s                                  | 纯OCR识别 |
| 10页英文论文+图片+表格PDF文档 | 24s                               | 18s                                      | 16s                                 |        |
| 13页英文论文+图片PDF文档    | 25s                               | 19s                                      | 16s                                 |        |
| 293页中文文字+图片PDF文档   | 407s                              | 281s                                     | 254s                                |        |
