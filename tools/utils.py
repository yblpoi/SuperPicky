"""
工具函数模块
提供日志记录和CSV报告功能
"""
import os
import csv
from datetime import datetime
from .file_utils import ensure_hidden_directory

# 跟踪当前活跃的工作目录，供 sys.excepthook 写入错误日志使用
_active_log_directory: str = None


def get_active_log_directory() -> str:
    """返回当前活跃的工作目录路径（用于错误日志定位）"""
    return _active_log_directory


def log_message(message: str, directory: str = None, file_only: bool = False):
    """
    记录日志消息到控制台和日志文件

    Args:
        message: 日志消息
        directory: 工作目录（可选，如果提供则写入该目录/superpicky.log）
        file_only: 仅写入文件，不打印到控制台（避免重复输出）
    """
    global _active_log_directory

    # 打印到控制台（除非指定只写文件）
    if not file_only:
        print(message)

    # 如果提供了目录，写入日志文件到根目录（可见文件，方便排查问题）
    if directory:
        _active_log_directory = directory  # 记录当前活跃目录
        log_file = os.path.join(directory, "superpicky.log")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")


def write_to_csv(data: dict, directory: str, header: bool = False):
    """
    将数据写入CSV报告文件

    Args:
        data: 要写入的数据字典（如果为None且header=True，则只创建文件并写表头）
        directory: 工作目录
        header: 是否写入表头（第一次写入时为True）
    """
    # 确保_tmp目录存在并隐藏（Windows 下设置 Hidden 属性）
    tmp_dir = os.path.join(directory, ".superpicky")
    ensure_hidden_directory(tmp_dir)

    report_file = os.path.join(tmp_dir, "report.csv")

    # V3.4: 全英文列名，添加飞版检测字段
    fieldnames = [
        "filename",        # 文件名（不含扩展名）
        "has_bird",        # 是否有鸟 (yes/no)
        "confidence",      # AI置信度 (0-1)
        "head_sharp",      # 头部区域锐度
        "left_eye",        # 左眼可见性 (0-1)
        "right_eye",       # 右眼可见性 (0-1)
        "beak",            # 喙可见性 (0-1)
        "nima_score",      # NIMA美学评分 (0-10)
        "is_flying",       # V3.4: 是否飞行 (yes/no/-)
        "flight_conf",     # V3.4: 飞行置信度 (0-1)
        "rating"           # 最终评分 (-1/0/1/2/3)
    ]

    try:
        # 如果是初始化表头（data为None）
        if data is None and header:
            with open(report_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
            return

        file_exists = os.path.exists(report_file)
        mode = 'a' if file_exists else 'w'

        with open(report_file, mode, newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            # 如果文件不存在或者明确要求写表头，则写入表头
            if not file_exists or header:
                writer.writeheader()

            if data:
                writer.writerow(data)
    except Exception as e:
        log_message(f"Warning: Could not write to CSV file: {e}", directory)
