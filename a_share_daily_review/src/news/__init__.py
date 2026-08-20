"""盘前资讯：采集 → 过滤 → 打分 → 帖子草稿（人工审核后发布）"""

from .pipeline import run_morning_pipeline

__all__ = ["run_morning_pipeline"]
