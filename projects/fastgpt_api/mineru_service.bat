@chcp 65001 >nul
@echo off
setlocal enabledelayedexpansion
rem 设置控制台代码页为UTF-8
chcp 65001 >nul

rem ================================
rem 配置区域 - 可根据需要修改
rem ================================

rem 指定具体python解释器路径
set "PYTHON_PATH=D:\SysEnvRun\Anaconda\envs\MinerU-New\python.exe"
set "SCRIPT_PATH=%~dp0main.py"
set "DEFAULT_OUTPUT_DIR=%~dp0output"
set "DEFAULT_HOST=0.0.0.0"
set "DEFAULT_PORT=8888"
set "LOG_DIR=%~dp0logs"
set "LOG_FILE=%LOG_DIR%\mineru_service.log"

rem 设置环境变量
set "MinerU_OUTPUT_DIR=%DEFAULT_OUTPUT_DIR%"
set "PROCESSES_PER_GPU=1"
set "MINERU_MODEL_SOURCE=local"

rem 创建日志目录
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
)

rem 记录脚本启动日志
echo "[%date% %time%] ========开始执行脚本========脚本命令: %0 %*" >> "%LOG_FILE%"

rem 检查参数
if "%1"=="" (
    echo "用法: %0 [start^|stop]"
    echo "[%date% %time%] 错误: 缺少参数" >> "%LOG_FILE%"
    exit /b 1
)

if "%1"=="start" (
    call :stop_service
    call :start_service
) else if "%1"=="stop" (
    call :stop_service
) else (
    echo "错误: 无效参数 %1。请使用 start 或 stop"。
    echo "[%date% %time%] 错误: 无效参数 %1" >> "%LOG_FILE%"
    exit /b 1
)

echo "[%date% %time%] ===========脚本执行完成=========" >> "%LOG_FILE%"
goto :eof

:start_service
    echo "[%date% %time%] 开始启动服务" >> "%LOG_FILE%"

    rem 创建输出目录
    if not exist "%MinerU_OUTPUT_DIR%" (
        mkdir "%MinerU_OUTPUT_DIR%"
        echo "创建输出目录: %MinerU_OUTPUT_DIR%"
        echo "[%date% %time%] 创建输出目录: %MinerU_OUTPUT_DIR%" >> "%LOG_FILE%"
    )

    echo "启动服务..."
    echo "[%date% %time%] 启动服务" >> "%LOG_FILE%"
    echo "主机: %DEFAULT_HOST%"
    echo "端口: %DEFAULT_PORT%"
    echo "输出目录: %MinerU_OUTPUT_DIR%"

    echo "[%date% %time%] 主机: %DEFAULT_HOST%" >> "%LOG_FILE%"
    echo "[%date% %time%] 端口: %DEFAULT_PORT%" >> "%LOG_FILE%"
    echo "[%date% %time%] 输出目录: %MinerU_OUTPUT_DIR%" >> "%LOG_FILE%"

    rem 启动服务并将输出重定向到日志文件
    echo "[%date% %time%] 启动FastAPI服务进程" >> "%LOG_FILE%"

    rem 生成带时间戳的日志文件名
    for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
    set "timestamp=%dt:~0,4%%dt:~4,2%%dt:~6,2%_%dt:~8,2%%dt:~10,2%%dt:~12,2%"
    set "FASTAPI_LOG_FILE=%LOG_DIR%\fastapi_stdout_%timestamp%.log"

    rem 使用start命令启动服务，/b参数使窗口不显示
    start "MinerU FastAPI Service" /D "%~dp0" /b cmd /c ""%PYTHON_PATH%" "%SCRIPT_PATH%"" > "%FASTAPI_LOG_FILE%" 2>&1

    rem 等待5秒后再检查服务启动是否完成。
    timeout /t 30 /nobreak >nul

    rem 查找占用指定端口的进程PID
    set "use_pid="
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%DEFAULT_PORT%.*LISTENING') do (
        set "use_pid=%%a"
    )
    echo "%DEFAULT_PORT% 端口正在使用的进程PID: !use_pid!"
    if defined use_pid (
        echo "[%date% %time%] 启动FastAPI服务进程成功" >> "%LOG_FILE%"
        echo "服务启动成功 (PID: !use_pid!)。请查看日志文件确认服务是否正常启动。"
        echo "[%date% %time%] 服务启动成功 (PID: !use_pid!), 日志文件: %FASTAPI_LOG_FILE%" >> "%LOG_FILE%"
    ) else (
        echo "未找到监听端口 %DEFAULT_PORT% 的进程，启动失败。"
        echo "[%date% %time%] 未找到监听端口 %DEFAULT_PORT% 的进程，启动失败。" >> "%LOG_FILE%"
        exit /b 1
    )

    timeout /t 3 /nobreak >nul
    goto :eof

:stop_service
    echo "[%date% %time%] 开始停止服务。" >> "%LOG_FILE%"
    echo "停止服务..."

    rem 查找占用指定端口的进程PID
    set "found_pid="
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%DEFAULT_PORT%.*LISTENING') do (
        set "found_pid=%%a"
    )

    rem 如果找到了PID，强制终止进程及子进程
    if defined found_pid (
        echo "[%date% %time%] 尝试终止进程 (PID: !found_pid!)及子进程。" >> "%LOG_FILE%"

        rem 强制终止进程及子进程
        taskkill /f /T /pid !found_pid! >nul 2>&1

        rem 等待一小段时间
        timeout /t 10 /nobreak >nul

        rem 检查进程是否已经关闭
        tasklist /fi "PID eq !found_pid!" 2>nul | findstr /i "!found_pid!" >nul
        if errorlevel 1 (
            echo "服务已停止。"
            echo "[%date% %time%] 进程(PID: !found_pid!)及子进程已强制关闭 。" >> "%LOG_FILE%"
        ) else (
            echo "服务停止失败 (PID: !found_pid!)。"
            echo "[%date% %time%] 进程关闭失败 (PID: !found_pid!)。" >> "%LOG_FILE%"
        )

    ) else (
        echo "未找到监听端口 %DEFAULT_PORT% 的进程。"
        echo "[%date% %time%] 未找到监听端口 %DEFAULT_PORT% 的进程。" >> "%LOG_FILE%"
    )
    timeout /t 2 /nobreak >nul
    goto :eof

