#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理器
对递归扫描到的原子目录逐个调用 PhotoProcessor.process()，
汇总统计，支持增量跳过。
"""

import os
import json
import time
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from core.recursive_scanner import scan_recursive, is_processed, count_photos


@dataclass
class BatchResult:
    """批量处理结果"""
    total_dirs: int = 0
    processed_dirs: int = 0
    skipped_dirs: int = 0
    failed_dirs: int = 0
    total_photos: int = 0
    total_time: float = 0.0
    dir_results: List[Dict] = field(default_factory=list)


class BatchProcessor:
    """
    批量处理器
    
    扫描根目录下的所有原子目录，逐个调用 PhotoProcessor 处理。
    """
    
    def __init__(
        self,
        root_dir: str,
        settings,  # ProcessingSettings
        skip_existing: bool = False,
        max_depth: int = 10,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self.root_dir = os.path.abspath(root_dir)
        self.settings = settings
        self.skip_existing = skip_existing
        self.max_depth = max_depth
        self.log = log_fn or print
    
    def scan(self) -> List[str]:
        """扫描并返回待处理的原子目录列表"""
        return scan_recursive(self.root_dir, self.max_depth)
    
    def process(
        self,
        dirs: List[str],
        organize_files: bool = True,
        cleanup_temp: bool = True,
    ) -> BatchResult:
        """
        批量处理所有目录
        
        Args:
            dirs: 原子目录列表
            organize_files: 是否移动文件到分类文件夹
            cleanup_temp: 是否清理临时文件
            
        Returns:
            BatchResult 汇总结果
        """
        from core.photo_processor import PhotoProcessor, ProcessingCallbacks
        
        result = BatchResult(total_dirs=len(dirs))
        batch_start = time.time()
        
        for i, dir_path in enumerate(dirs, 1):
            dir_name = os.path.relpath(dir_path, self.root_dir)
            photo_count = count_photos(dir_path)
            
            # 增量跳过
            if self.skip_existing and is_processed(dir_path):
                self.log(f"\n⏭️  [{i}/{len(dirs)}] 跳过已处理: {dir_name} ({photo_count} 张)")
                result.skipped_dirs += 1
                result.dir_results.append({
                    'dir': dir_name,
                    'status': 'skipped',
                    'photos': photo_count,
                })
                continue
            
            self.log(f"\n{'━' * 60}")
            self.log(f"📂 [{i}/{len(dirs)}] 处理: {dir_name} ({photo_count} 张)")
            self.log(f"{'━' * 60}")
            
            dir_start = time.time()
            
            try:
                # 创建回调
                callbacks = ProcessingCallbacks(
                    log=lambda msg, level="info": self.log(f"  {msg}"),
                    progress=None,
                )
                
                # 创建处理器并执行
                processor = PhotoProcessor(
                    dir_path=dir_path,
                    settings=self.settings,
                    callbacks=callbacks,
                )
                
                proc_result = processor.process(
                    organize_files=organize_files,
                    cleanup_temp=cleanup_temp,
                )
                
                dir_time = time.time() - dir_start
                stats = proc_result.stats
                
                self.log(f"\n  ✅ 完成 ({dir_time:.1f}s): "
                         f"3★={stats.get('star_3', 0)} "
                         f"2★={stats.get('star_2', 0)} "
                         f"1★={stats.get('star_1', 0)} "
                         f"0★={stats.get('star_0', 0)} "
                         f"无鸟={stats.get('no_bird', 0)}")
                
                result.processed_dirs += 1
                result.total_photos += stats.get('total', 0)
                result.dir_results.append({
                    'dir': dir_name,
                    'status': 'success',
                    'photos': stats.get('total', 0),
                    'star_3': stats.get('star_3', 0),
                    'star_2': stats.get('star_2', 0),
                    'star_1': stats.get('star_1', 0),
                    'star_0': stats.get('star_0', 0),
                    'no_bird': stats.get('no_bird', 0),
                    'time': round(dir_time, 1),
                })
                
            except Exception as e:
                dir_time = time.time() - dir_start
                self.log(f"\n  ❌ 失败 ({dir_time:.1f}s): {e}")
                result.failed_dirs += 1
                result.dir_results.append({
                    'dir': dir_name,
                    'status': 'failed',
                    'error': str(e),
                    'time': round(dir_time, 1),
                })
        
        result.total_time = time.time() - batch_start
        
        # 保存批量汇总报告
        self._save_batch_report(result)
        
        # 打印汇总
        self._print_summary(result)
        
        return result
    
    def _save_batch_report(self, result: BatchResult):
        """保存批量处理汇总到根目录"""
        report = {
            'version': '1.0',
            'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'root_dir': self.root_dir,
            'total_dirs': result.total_dirs,
            'processed': result.processed_dirs,
            'skipped': result.skipped_dirs,
            'failed': result.failed_dirs,
            'total_photos': result.total_photos,
            'total_time': round(result.total_time, 1),
            'dirs': result.dir_results,
        }
        
        report_path = os.path.join(self.root_dir, '.superpicky_batch.json')
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"⚠️  汇总报告保存失败: {e}")
    
    def _print_summary(self, result: BatchResult):
        """打印批量处理汇总"""
        self.log(f"\n{'═' * 60}")
        self.log(f"📊 批量处理汇总")
        self.log(f"{'═' * 60}")
        self.log(f"  目录总数: {result.total_dirs}")
        self.log(f"  已处理:   {result.processed_dirs}")
        if result.skipped_dirs > 0:
            self.log(f"  已跳过:   {result.skipped_dirs}")
        if result.failed_dirs > 0:
            self.log(f"  失败:     {result.failed_dirs}")
        self.log(f"  照片总数: {result.total_photos}")
        self.log(f"  总耗时:   {result.total_time:.1f}s")
        
        # 汇总各星级
        totals = {'star_3': 0, 'star_2': 0, 'star_1': 0, 'star_0': 0, 'no_bird': 0}
        for d in result.dir_results:
            if d.get('status') == 'success':
                for key in totals:
                    totals[key] += d.get(key, 0)
        
        self.log(f"\n  ⭐ 评分汇总:")
        self.log(f"    3★ 优选: {totals['star_3']}")
        self.log(f"    2★ 良好: {totals['star_2']}")
        self.log(f"    1★ 普通: {totals['star_1']}")
        self.log(f"    0★ 放弃: {totals['star_0']}")
        self.log(f"    无鸟:    {totals['no_bird']}")
