# -*- coding: utf-8 -*-
"""
日志管理服务模块

功能:
- 读取应用日志和错误日志
- 按级别和时间范围筛选
- 关键词搜索
- 日志文件下载
- 清空日志
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from app.config import settings
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str
    logger_name: str
    message: str
    raw_line: str


@dataclass
class LogFile:
    """日志文件信息"""
    name: str
    path: str
    size: int
    modified: str


class LogService:
    """日志管理服务"""
    
    # 日志级别
    LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    # 日志行解析正则
    LOG_PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*(\S+)\s*\|\s*(.*)$'
    )
    
    def __init__(self):
        self._log_dir = self._get_log_dir()
    
    def _get_log_dir(self) -> str:
        """获取日志目录"""
        log_dir = settings.LOGS_DIR
        if not os.path.isabs(log_dir):
            # 相对路径转绝对路径
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            log_dir = os.path.join(base_dir, log_dir)
        os.makedirs(log_dir, exist_ok=True)
        return log_dir
    
    def get_log_files(self) -> List[LogFile]:
        """获取所有日志文件"""
        files = []
        
        if not os.path.exists(self._log_dir):
            return files
        
        for filename in os.listdir(self._log_dir):
            if filename.endswith('.log'):
                filepath = os.path.join(self._log_dir, filename)
                try:
                    stat = os.stat(filepath)
                    files.append(LogFile(
                        name=filename,
                        path=filepath,
                        size=stat.st_size,
                        modified=datetime.fromtimestamp(
                            stat.st_mtime, 
                            tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M:%S")
                    ))
                except OSError:
                    continue
        
        return sorted(files, key=lambda x: x.modified, reverse=True)
    
    def read_log(
        self,
        filename: str = "app.log",
        lines: int = 100,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[LogEntry]:
        """读取日志文件
        
        Args:
            filename: 日志文件名
            lines: 返回行数限制
            level: 日志级别筛选
            keyword: 关键词搜索
            start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
            
        Returns:
            List[LogEntry]: 日志条目列表
        """
        filepath = os.path.join(self._log_dir, filename)
        
        if not os.path.exists(filepath):
            return []
        
        entries = []
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            # 从后往前读取
            for raw_line in reversed(all_lines):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                
                entry = self._parse_log_line(raw_line)
                if not entry:
                    continue
                
                # 级别筛选
                if level and entry.level != level.upper():
                    continue
                
                # 关键词搜索
                if keyword and keyword.lower() not in entry.message.lower():
                    continue
                
                # 时间范围筛选
                if start_time and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp > end_time:
                    continue
                
                entries.append(entry)
                
                if len(entries) >= lines:
                    break
            
            # 恢复时间顺序
            entries.reverse()
            
        except Exception as e:
            logger.exception("读取日志文件失败: %s", str(e))
        
        return entries
    
    def _read_all_filtered_entries(
        self,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[LogEntry]:
        """从所有日志文件中读取并筛选条目（按时间倒序）"""
        all_entries = []
        
        for log_file in self.get_log_files():
            filepath = log_file.path
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                
                for raw_line in lines:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    
                    entry = self._parse_log_line(raw_line)
                    if not entry:
                        continue
                    
                    if level and entry.level != level.upper():
                        continue
                    if keyword and keyword.lower() not in entry.message.lower():
                        continue
                    if start_time and entry.timestamp < start_time:
                        continue
                    if end_time and entry.timestamp > end_time:
                        continue
                    
                    all_entries.append(entry)
            except Exception as e:
                logger.exception("读取日志文件失败: %s", str(e))
        
        # 按时间倒序排列（最新的在前）
        all_entries.sort(key=lambda e: e.timestamp, reverse=True)
        return all_entries

    def read_log_paginated(
        self,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple:
        """分页读取日志
        
        Returns:
            tuple: (entries, total)
        """
        all_entries = self._read_all_filtered_entries(
            level=level,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
        )
        
        total = len(all_entries)
        start = (page - 1) * page_size
        end = start + page_size
        page_entries = all_entries[start:end]
        
        return page_entries, total

    def _parse_log_line(self, line: str) -> Optional[LogEntry]:
        """解析日志行"""
        match = self.LOG_PATTERN.match(line)
        if match:
            return LogEntry(
                timestamp=match.group(1),
                level=match.group(2).strip(),
                logger_name=match.group(3).strip(),
                message=match.group(4).strip(),
                raw_line=line
            )
        
        # 简单格式日志
        simple_pattern = re.compile(
            r'^(\d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*(.*)$'
        )
        match = simple_pattern.match(line)
        if match:
            return LogEntry(
                timestamp=match.group(1),
                level=match.group(2).strip(),
                logger_name="",
                message=match.group(3).strip(),
                raw_line=line
            )
        
        return None
    
    def get_log_content(self, filename: str = "app.log") -> str:
        """获取日志文件完整内容（用于下载）
        
        Args:
            filename: 日志文件名
            
        Returns:
            str: 日志文件内容
        """
        filepath = os.path.join(self._log_dir, filename)
        
        if not os.path.exists(filepath):
            return ""
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.exception("读取日志文件失败: %s", str(e))
            return ""
    
    def clear_log(self, filename: str = "app.log") -> bool:
        """清空日志文件
        
        Args:
            filename: 日志文件名
            
        Returns:
            bool: 是否成功
        """
        filepath = os.path.join(self._log_dir, filename)
        
        if not os.path.exists(filepath):
            return True
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("")
            logger.info("日志文件已清空: %s", filename)
            return True
        except Exception as e:
            logger.exception("清空日志文件失败: %s", str(e))
            return False
    
    def clear_all_logs(self) -> int:
        """清空所有日志文件
        
        Returns:
            int: 清空的文件数量
        """
        cleared = 0
        
        for log_file in self.get_log_files():
            if self.clear_log(log_file.name):
                cleared += 1
        
        return cleared
    
    @property
    def log_dir(self) -> str:
        """获取日志目录"""
        return self._log_dir


# 全局单例
_log_service: Optional[LogService] = None


def get_log_service() -> LogService:
    """获取日志服务单例"""
    global _log_service
    if _log_service is None:
        _log_service = LogService()
    return _log_service
