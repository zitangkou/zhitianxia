"""
数据存储模块
- Parquet：行情历史（按日期）
- SQLite：运行日志、复盘摘要、配置
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.utils.config import get_project_root, load_config
from src.utils.logger import setup_logger

logger = setup_logger("data.storage")


class DataStorage:
    def __init__(self, config: Optional[Dict] = None):
        self.cfg = config or load_config()
        root = get_project_root()
        self.parquet_dir = Path(self.cfg["paths"].get("data_parquet", root / "data" / "parquet"))
        self.db_path = Path(self.cfg["paths"].get("data_db", root / "data" / "db")) / "review.db"

        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    run_time TEXT NOT NULL,
                    status TEXT,
                    message TEXT,
                    stats_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_summary (
                    trade_date TEXT PRIMARY KEY,
                    created_at TEXT,
                    summary_json TEXT,
                    llm_text TEXT
                )
                """
            )
            conn.commit()

    def _date_path(self, trade_date: str, category: str) -> Path:
        """data/parquet/{category}/YYYY/MM/DD.parquet"""
        y, m, d = trade_date.split("-")
        p = self.parquet_dir / category / y / m
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{d}.parquet"

    def save_dataframe(self, df: pd.DataFrame, trade_date: str, category: str) -> Path:
        if df is None or df.empty:
            logger.warning(f"空 DataFrame，跳过保存: {category} @ {trade_date}")
            return Path()
        path = self._date_path(trade_date, category)
        df.to_parquet(path, index=False)
        logger.info(f"已保存 {category}: {path} ({len(df)} 行)")
        return path

    def load_dataframe(self, trade_date: str, category: str) -> pd.DataFrame:
        path = self._date_path(trade_date, category)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def save_daily_data(self, data: Dict[str, Any]) -> None:
        """把 run_daily_fetch 的结果完整落盘"""
        trade_date = data.get("trade_date")
        if not trade_date:
            logger.error("缺少 trade_date，无法保存")
            return

        if "indices" in data and isinstance(data["indices"], pd.DataFrame):
            self.save_dataframe(data["indices"], trade_date, "indices")

        if "market_snapshot" in data and isinstance(data["market_snapshot"], pd.DataFrame):
            self.save_dataframe(data["market_snapshot"], trade_date, "market_snapshot")

        if "industry" in data and isinstance(data["industry"], pd.DataFrame):
            self.save_dataframe(data["industry"], trade_date, "industry")

        if "concept" in data and isinstance(data["concept"], pd.DataFrame):
            self.save_dataframe(data["concept"], trade_date, "concept")

        # 涨停/跌停/炸板/昨日涨停/强势/龙虎榜
        lud = data.get("limit_up_down", {})
        for key, cat in [
            ("limit_up", "limit_up"),
            ("limit_down", "limit_down"),
            ("zhaban", "zhaban"),
            ("previous_zt", "previous_zt"),
            ("strong", "strong"),
        ]:
            df = lud.get(key)
            if isinstance(df, pd.DataFrame) and not df.empty:
                self.save_dataframe(df, trade_date, cat)

        lhb = data.get("lhb")
        if isinstance(lhb, pd.DataFrame) and not lhb.empty:
            self.save_dataframe(lhb, trade_date, "lhb")

        seats = data.get("lhb_seats")
        if isinstance(seats, pd.DataFrame) and not seats.empty:
            self.save_dataframe(seats, trade_date, "lhb_seats")

        # 统计信息写入 SQLite
        stats = data.get("market_stats", {})
        self.log_run(
            trade_date=trade_date,
            status="success",
            message="daily fetch completed",
            stats=stats,
        )
        logger.info(f"每日数据已全部落盘 @ {trade_date}")

    def log_run(
        self,
        trade_date: str,
        status: str,
        message: str = "",
        stats: Optional[Dict] = None,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO run_log (trade_date, run_time, status, message, stats_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    trade_date,
                    datetime.now().isoformat(),
                    status,
                    message,
                    json.dumps(stats or {}, ensure_ascii=False),
                ),
            )
            conn.commit()

    def save_review_summary(
        self,
        trade_date: str,
        summary: Dict[str, Any],
        llm_text: str = "",
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO review_summary
                (trade_date, created_at, summary_json, llm_text)
                VALUES (?, ?, ?, ?)
                """,
                (
                    trade_date,
                    datetime.now().isoformat(),
                    json.dumps(summary, ensure_ascii=False, default=str),
                    llm_text,
                ),
            )
            conn.commit()
        logger.info(f"复盘摘要已写入 DB @ {trade_date}")
