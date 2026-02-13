# -*- coding: utf-8 -*-
"""
性能监控服务模块 - 追踪API调用耗时、向量检索性能等

功能:
- 性能指标收集
- 统计平均响应时间、成功率等
- P50、P95、P99百分位数计算
- 支持性能报告导出
"""

import time
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from threading import Lock
from contextlib import contextmanager

from app.utils.time import utcnow

logger = logging.getLogger(__name__)


@dataclass
class MetricRecord:
    """性能指标记录"""
    name: str
    duration: float  # 耗时（秒）
    success: bool
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


@dataclass
class MetricStats:
    """指标统计结果"""
    name: str
    count: int = 0
    success_rate: float = 0.0
    avg_duration: float = 0.0
    min_duration: float = 0.0
    max_duration: float = 0.0
    p50_duration: float = 0.0
    p95_duration: float = 0.0
    p99_duration: float = 0.0
    total_count: int = 0
    total_success: int = 0


class MetricCollector:
    """性能指标收集器"""
    
    def __init__(self, name: str, max_records: int = 1000):
        self.name = name
        self._max_records = max_records
        self._records: deque = deque(maxlen=max_records)
        self._lock = Lock()
        
        # 累计统计
        self._total_count = 0
        self._success_count = 0
        self._total_duration = 0.0
    
    def record(self, duration: float, success: bool = True, metadata: dict = None):
        """记录一次指标"""
        record = MetricRecord(
            name=self.name,
            duration=duration,
            success=success,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._records.append(record)
            self._total_count += 1
            if success:
                self._success_count += 1
            self._total_duration += duration
    
    @contextmanager
    def measure(self, metadata: dict = None):
        """测量代码块执行时间的上下文管理器"""
        start = time.perf_counter()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            duration = time.perf_counter() - start
            self.record(duration, success, metadata)
    
    def get_stats(self, last_n: int = None) -> MetricStats:
        """获取统计信息
        
        Args:
            last_n: 只统计最近N条记录，None表示全部
        """
        with self._lock:
            if last_n:
                records = list(self._records)[-last_n:]
            else:
                records = list(self._records)
        
        if not records:
            return MetricStats(name=self.name)
        
        durations = [r.duration for r in records]
        success_count = sum(1 for r in records if r.success)
        
        durations_sorted = sorted(durations)
        n = len(durations_sorted)
        
        return MetricStats(
            name=self.name,
            count=len(records),
            success_rate=success_count / len(records),
            avg_duration=sum(durations) / len(durations),
            min_duration=min(durations),
            max_duration=max(durations),
            p50_duration=durations_sorted[n // 2],
            p95_duration=durations_sorted[int(n * 0.95)] if n >= 20 else durations_sorted[-1],
            p99_duration=durations_sorted[int(n * 0.99)] if n >= 100 else durations_sorted[-1],
            total_count=self._total_count,
            total_success=self._success_count
        )
    
    def clear(self):
        """清空记录"""
        with self._lock:
            self._records.clear()
            self._total_count = 0
            self._success_count = 0
            self._total_duration = 0.0


class PerformanceService:
    """性能监控服务（单例）"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 各类指标收集器
        self._collectors: Dict[str, MetricCollector] = {
            "chat_api": MetricCollector("chat_api"),
            "embedding_api": MetricCollector("embedding_api"),
            "vector_search": MetricCollector("vector_search"),
            "keyword_search": MetricCollector("keyword_search"),
            "knowledge_add": MetricCollector("knowledge_add"),
            "knowledge_update": MetricCollector("knowledge_update"),
            "product_add": MetricCollector("product_add"),
            "product_update": MetricCollector("product_update"),
        }
        
        self._start_time = time.time()
        logger.info("性能监控服务初始化完成")
    
    def get_collector(self, name: str) -> MetricCollector:
        """获取或创建指标收集器"""
        if name not in self._collectors:
            self._collectors[name] = MetricCollector(name)
        return self._collectors[name]
    
    @contextmanager
    def measure(self, metric_name: str, metadata: dict = None):
        """测量代码块执行时间"""
        collector = self.get_collector(metric_name)
        with collector.measure(metadata):
            yield
    
    def record(
        self, 
        metric_name: str, 
        duration: float, 
        success: bool = True, 
        metadata: dict = None
    ):
        """记录指标"""
        collector = self.get_collector(metric_name)
        collector.record(duration, success, metadata)
    
    def get_all_stats(self, last_n: int = None) -> Dict[str, MetricStats]:
        """获取所有指标统计"""
        return {
            name: collector.get_stats(last_n) 
            for name, collector in self._collectors.items()
        }
    
    def get_summary(self) -> dict:
        """获取性能摘要"""
        uptime = time.time() - self._start_time
        
        stats = self.get_all_stats(last_n=100)
        
        # 计算总体指标
        total_requests = sum(s.count for s in stats.values())
        total_success = sum(s.count * s.success_rate for s in stats.values())
        
        return {
            "uptime_seconds": uptime,
            "uptime_formatted": self._format_duration(uptime),
            "total_requests": total_requests,
            "overall_success_rate": total_success / total_requests if total_requests > 0 else 0.0,
            "start_time": datetime.fromtimestamp(
                self._start_time, 
                tz=timezone.utc
            ).isoformat(),
        }
    
    def _format_duration(self, seconds: float) -> str:
        """格式化时长"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        elif minutes > 0:
            return f"{minutes}分钟{secs}秒"
        else:
            return f"{secs}秒"
    
    def export_report(self) -> str:
        """导出性能报告"""
        summary = self.get_summary()
        stats = self.get_all_stats(last_n=100)
        
        lines = [
            "=" * 60,
            "性能监控报告",
            f"生成时间: {utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"运行时长: {summary['uptime_formatted']}",
            "=" * 60,
            "",
            f"总请求数: {summary['total_requests']}",
            f"总体成功率: {summary['overall_success_rate']:.1%}",
            "",
            "-" * 60,
            "各指标详情:",
            "-" * 60,
        ]
        
        for name, stat in stats.items():
            if stat.count > 0:
                lines.extend([
                    f"\n【{name}】",
                    f"  请求数: {stat.count}",
                    f"  成功率: {stat.success_rate:.1%}",
                    f"  平均耗时: {stat.avg_duration*1000:.1f}ms",
                    f"  最小耗时: {stat.min_duration*1000:.1f}ms",
                    f"  最大耗时: {stat.max_duration*1000:.1f}ms",
                    f"  P50耗时: {stat.p50_duration*1000:.1f}ms",
                    f"  P95耗时: {stat.p95_duration*1000:.1f}ms",
                    f"  P99耗时: {stat.p99_duration*1000:.1f}ms",
                ])
        
        lines.append("\n" + "=" * 60)
        
        return "\n".join(lines)
    
    def clear_all(self):
        """清空所有记录"""
        for collector in self._collectors.values():
            collector.clear()
        self._start_time = time.time()
        logger.info("性能监控数据已清空")


# 全局单例
_performance_service: Optional[PerformanceService] = None


def get_performance_service() -> PerformanceService:
    """获取性能监控服务单例"""
    global _performance_service
    if _performance_service is None:
        _performance_service = PerformanceService()
    return _performance_service


def timed(metric_name: str):
    """性能计时装饰器"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            service = get_performance_service()
            start = time.perf_counter()
            success = True
            try:
                return await func(*args, **kwargs)
            except Exception:
                success = False
                raise
            finally:
                duration = time.perf_counter() - start
                service.record(metric_name, duration, success)
        
        def sync_wrapper(*args, **kwargs):
            service = get_performance_service()
            start = time.perf_counter()
            success = True
            try:
                return func(*args, **kwargs)
            except Exception:
                success = False
                raise
            finally:
                duration = time.perf_counter() - start
                service.record(metric_name, duration, success)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
