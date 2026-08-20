"""
数据拉取模块 - 方案一核心
主数据源：AKShare（免费、全覆盖）
备用：Baostock
"""
from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.utils.calendar import get_latest_trading_day, is_trading_day
from src.utils.config import load_config
from src.utils.logger import setup_logger

logger = setup_logger("data.fetcher")


class DataFetcher:
    def __init__(self, config: Optional[Dict] = None):
        self.cfg = config or load_config()
        self.retry_times = self.cfg.get("data", {}).get("retry_times", 2)
        self.retry_sleep = self.cfg.get("data", {}).get("retry_sleep", 1.5)
        self.indices_cfg = self.cfg.get("data", {}).get("indices", [])

    def _retry(self, func, *args, timeout: float = 25.0, **kwargs):
        """带简单超时的重试（使用信号量在部分环境可能受限，这里用循环+sleep）"""
        last_err = None
        for i in range(self.retry_times):
            try:
                # 部分 akshare 接口内部无超时，这里靠重试次数控制总时间
                return func(*args, **kwargs)
            except Exception as e:
                last_err = e
                logger.warning(f"调用失败 (第{i+1}/{self.retry_times}次): {type(e).__name__}: {e}")
                if i < self.retry_times - 1:
                    time.sleep(self.retry_sleep * (i + 1))
        raise RuntimeError(f"重试{self.retry_times}次后仍失败: {last_err}")

    def is_trading_day(self, d: Optional[str | date] = None) -> bool:
        return is_trading_day(d)

    def get_trade_date(self, d: Optional[str] = None) -> str:
        """返回 YYYY-MM-DD 格式的交易日"""
        if d:
            dt = datetime.strptime(d[:10], "%Y-%m-%d").date()
        else:
            dt = get_latest_trading_day()
        return dt.strftime("%Y-%m-%d")

    # -------------------- 指数 --------------------
    def fetch_indices(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        拉取主要指数当日行情。
        优先新浪接口（较稳定），失败再尝试东方财富。
        返回列：name, code, close, change_pct, open, high, low, volume, amount, trade_date
        """
        trade_date = self.get_trade_date(trade_date)
        logger.info(f"拉取指数数据 @ {trade_date}")

        df = pd.DataFrame()
        # 1) 新浪
        try:
            df = self._retry(ak.stock_zh_index_spot_sina)
            logger.info("指数数据来自新浪")
        except Exception as e:
            logger.warning(f"新浪指数接口失败: {e}")

        # 2) 东方财富兜底
        if df is None or df.empty:
            try:
                df = self._retry(ak.stock_zh_index_spot_em)
                logger.info("指数数据来自东方财富")
            except Exception as e:
                logger.warning(f"东方财富指数接口失败: {e}")
                return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # 统一列名
        col_map = {
            "代码": "code",
            "名称": "name",
            "最新价": "close",
            "涨跌幅": "change_pct",
            "涨跌额": "change",
            "今开": "open",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "昨收": "pre_close",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        rows = []
        for item in self.indices_cfg:
            code = item["code"]  # e.g. sh000001
            pure = code.replace("sh", "").replace("sz", "")
            mask = (
                (df["code"].astype(str) == code)
                | (df["code"].astype(str) == pure)
                | (df["code"].astype(str).str.endswith(pure))
            )
            sub = df.loc[mask]
            if not sub.empty:
                row = sub.iloc[0].to_dict()
                row["name"] = item["name"]
                row["code"] = code
                row["trade_date"] = trade_date
                rows.append(row)
            else:
                logger.warning(f"未找到指数: {item['name']} ({code})")

        result = pd.DataFrame(rows)
        logger.info(f"成功获取 {len(result)} 个指数")
        return result

    # -------------------- 全市场快照 --------------------
    def fetch_market_snapshot(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        全A股实时/当日快照（收盘后即为当日数据）。
        注意：依赖东方财富接口，网络不稳定时可能失败；失败时返回空 DataFrame，不影响其他模块。
        """
        trade_date = self.get_trade_date(trade_date)
        logger.info(f"拉取全市场快照 @ {trade_date}")

        try:
            df = self._retry(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                logger.warning("全市场快照返回空")
                return pd.DataFrame()

            rename_map = {
                "代码": "code",
                "名称": "name",
                "最新价": "close",
                "涨跌幅": "change_pct",
                "涨跌额": "change",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "最高": "high",
                "最低": "low",
                "今开": "open",
                "昨收": "pre_close",
                "量比": "volume_ratio",
                "换手率": "turnover_rate",
                "市盈率-动态": "pe",
                "市净率": "pb",
                "总市值": "total_mv",
                "流通市值": "circ_mv",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            df["trade_date"] = trade_date
            logger.info(f"全市场快照共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"fetch_market_snapshot 失败（可忽略，后续用备用数据）: {e}")
            return pd.DataFrame()

    # -------------------- 涨停 / 跌停 / 炸板 / 昨日涨停 --------------------
    def fetch_limit_up_down(self, trade_date: Optional[str] = None) -> Dict[str, Any]:
        """
        情绪核心数据：涨停池、跌停池、炸板池、昨日涨停今日表现。
        用于连板高度、晋级率、炸板率等「有吸引力」指标。
        """
        trade_date = self.get_trade_date(trade_date)
        date_str = trade_date.replace("-", "")
        logger.info(f"拉取涨停/跌停/炸板/昨日涨停 @ {trade_date}")

        result: Dict[str, Any] = {
            "trade_date": trade_date,
            "limit_up": pd.DataFrame(),
            "limit_down": pd.DataFrame(),
            "zhaban": pd.DataFrame(),
            "previous_zt": pd.DataFrame(),
            "strong": pd.DataFrame(),
            "limit_up_count": 0,
            "limit_down_count": 0,
            "zhaban_count": 0,
            "max_board": 0,
            "board_ladder": {},  # {连板数: 家数}
        }

        # 涨停池
        try:
            df_up = self._retry(ak.stock_zt_pool_em, date=date_str)
            if df_up is not None and not df_up.empty:
                result["limit_up"] = df_up
                result["limit_up_count"] = len(df_up)
                if "连板数" in df_up.columns:
                    result["max_board"] = int(df_up["连板数"].max())
                    result["board_ladder"] = (
                        df_up["连板数"].value_counts().sort_index(ascending=False).to_dict()
                    )
                logger.info(
                    f"涨停 {result['limit_up_count']} 家，最高连板 {result['max_board']}"
                )
        except Exception as e:
            logger.warning(f"涨停池获取失败: {e}")

        # 跌停池
        try:
            df_down = self._retry(ak.stock_zt_pool_dtgc_em, date=date_str)
            if df_down is not None and not df_down.empty:
                result["limit_down"] = df_down
                result["limit_down_count"] = len(df_down)
                logger.info(f"跌停家数: {result['limit_down_count']}")
        except Exception as e:
            logger.warning(f"跌停池获取失败: {e}")

        # 炸板池
        try:
            df_zb = self._retry(ak.stock_zt_pool_zbgc_em, date=date_str)
            if df_zb is not None and not df_zb.empty:
                result["zhaban"] = df_zb
                result["zhaban_count"] = len(df_zb)
                logger.info(f"炸板家数: {result['zhaban_count']}")
        except Exception as e:
            logger.warning(f"炸板池获取失败: {e}")

        # 昨日涨停今日表现（算晋级率）
        try:
            df_prev = self._retry(ak.stock_zt_pool_previous_em, date=date_str)
            if df_prev is not None and not df_prev.empty:
                result["previous_zt"] = df_prev
                logger.info(f"昨日涨停今日可跟踪: {len(df_prev)} 家")
        except Exception as e:
            logger.warning(f"昨日涨停池获取失败: {e}")

        # 强势股池
        try:
            df_strong = self._retry(ak.stock_zt_pool_strong_em, date=date_str)
            if df_strong is not None and not df_strong.empty:
                result["strong"] = df_strong
                logger.info(f"强势股池: {len(df_strong)} 家")
        except Exception as e:
            logger.warning(f"强势股池获取失败: {e}")

        return result

    # -------------------- 龙虎榜 --------------------
    def fetch_lhb(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        当日龙虎榜明细（东方财富）。
        含解读、上榜原因、净买额等，是「超预期/游资/机构」内容的核心来源。
        """
        trade_date = self.get_trade_date(trade_date)
        date_str = trade_date.replace("-", "")
        logger.info(f"拉取龙虎榜 @ {trade_date}")
        try:
            df = self._retry(ak.stock_lhb_detail_em, start_date=date_str, end_date=date_str)
            if df is None or df.empty:
                return pd.DataFrame()
            logger.info(f"龙虎榜上榜记录: {len(df)} 条")
            return df
        except Exception as e:
            logger.warning(f"龙虎榜获取失败: {e}")
            return pd.DataFrame()

    def fetch_lhb_seats(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        当日龙虎榜营业部（游资席位）买卖排行。
        用于「谁在买、买了什么」的故事性内容。
        """
        trade_date = self.get_trade_date(trade_date)
        date_str = trade_date.replace("-", "")
        logger.info(f"拉取龙虎榜营业部席位 @ {trade_date}")
        try:
            df = self._retry(ak.stock_lhb_hyyyb_em, start_date=date_str, end_date=date_str)
            if df is None or df.empty:
                return pd.DataFrame()
            logger.info(f"营业部席位记录: {len(df)} 条")
            return df
        except Exception as e:
            logger.warning(f"营业部席位获取失败: {e}")
            return pd.DataFrame()

    # -------------------- 板块表现 --------------------
    def fetch_sector_performance(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """行业/概念板块涨跌幅"""
        trade_date = self.get_trade_date(trade_date)
        logger.info(f"拉取板块表现 @ {trade_date}")

        try:
            # 行业板块
            df = self._retry(ak.stock_board_industry_name_em)
            if df is None or df.empty:
                return pd.DataFrame()

            rename_map = {
                "板块名称": "name",
                "涨跌幅": "change_pct",
                "总市值": "total_mv",
                "换手率": "turnover_rate",
                "上涨家数": "up_count",
                "下跌家数": "down_count",
                "领涨股票": "leader",
                "领涨股票-涨跌幅": "leader_pct",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            df["trade_date"] = trade_date
            df["board_type"] = "industry"
            logger.info(f"行业板块 {len(df)} 个")
            return df
        except Exception as e:
            logger.error(f"fetch_sector_performance 失败: {e}")
            return pd.DataFrame()

    # -------------------- 概念板块（可选） --------------------
    def fetch_concept_performance(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        trade_date = self.get_trade_date(trade_date)
        try:
            df = self._retry(ak.stock_board_concept_name_em)
            if df is None or df.empty:
                return pd.DataFrame()
            rename_map = {
                "板块名称": "name",
                "涨跌幅": "change_pct",
                "总市值": "total_mv",
                "换手率": "turnover_rate",
                "上涨家数": "up_count",
                "下跌家数": "down_count",
                "领涨股票": "leader",
                "领涨股票-涨跌幅": "leader_pct",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            df["trade_date"] = trade_date
            df["board_type"] = "concept"
            return df
        except Exception as e:
            logger.warning(f"概念板块获取失败: {e}")
            return pd.DataFrame()

    # -------------------- 一站式每日拉取 --------------------
    def run_daily_fetch(self, trade_date: Optional[str] = None) -> Dict[str, Any]:
        """
        执行完整每日数据拉取，返回结构化字典。
        各子模块独立 try，单点失败不影响整体。
        """
        trade_date = self.get_trade_date(trade_date)
        logger.info(f"========== 开始每日数据拉取 @ {trade_date} ==========")

        if not self.is_trading_day(trade_date):
            logger.warning(f"{trade_date} 非交易日，跳过拉取")
            return {"trade_date": trade_date, "is_trading_day": False}

        data: Dict[str, Any] = {
            "trade_date": trade_date,
            "is_trading_day": True,
            "fetch_time": datetime.now().isoformat(),
        }

        # 指数（核心，优先保证）
        try:
            data["indices"] = self.fetch_indices(trade_date)
        except Exception as e:
            logger.error(f"指数拉取异常: {e}")
            data["indices"] = pd.DataFrame()

        # 涨停/跌停/炸板/昨日涨停/强势（核心情绪 + 吸引力素材）
        try:
            data["limit_up_down"] = self.fetch_limit_up_down(trade_date)
        except Exception as e:
            logger.error(f"涨停跌停异常: {e}")
            data["limit_up_down"] = {
                "trade_date": trade_date,
                "limit_up": pd.DataFrame(),
                "limit_down": pd.DataFrame(),
                "zhaban": pd.DataFrame(),
                "previous_zt": pd.DataFrame(),
                "strong": pd.DataFrame(),
                "limit_up_count": 0,
                "limit_down_count": 0,
                "zhaban_count": 0,
                "max_board": 0,
                "board_ladder": {},
            }

        # 龙虎榜（高吸引力：游资/机构/解读）
        try:
            data["lhb"] = self.fetch_lhb(trade_date)
        except Exception as e:
            logger.error(f"龙虎榜异常: {e}")
            data["lhb"] = pd.DataFrame()

        # 营业部/游资席位排行
        try:
            data["lhb_seats"] = self.fetch_lhb_seats(trade_date)
        except Exception as e:
            logger.error(f"营业部席位异常: {e}")
            data["lhb_seats"] = pd.DataFrame()

        skip_heavy = self.cfg.get("data", {}).get("skip_heavy_endpoints", False)

        if skip_heavy:
            logger.info("已开启 skip_heavy_endpoints，跳过行业/概念/全市场快照")
            data["industry"] = pd.DataFrame()
            data["concept"] = pd.DataFrame()
            data["market_snapshot"] = pd.DataFrame()
        else:
            # 行业板块
            try:
                data["industry"] = self.fetch_sector_performance(trade_date)
            except Exception as e:
                logger.error(f"行业板块异常: {e}")
                data["industry"] = pd.DataFrame()

            # 概念板块
            try:
                data["concept"] = self.fetch_concept_performance(trade_date)
            except Exception as e:
                logger.error(f"概念板块异常: {e}")
                data["concept"] = pd.DataFrame()

            # 全市场快照（较重，失败可容忍）
            try:
                data["market_snapshot"] = self.fetch_market_snapshot(trade_date)
            except Exception as e:
                logger.error(f"全市场快照异常: {e}")
                data["market_snapshot"] = pd.DataFrame()

        # 简单统计（有快照用快照，否则用涨停跌停近似）
        snap = data.get("market_snapshot", pd.DataFrame())
        lud = data.get("limit_up_down", {})
        if not snap.empty and "change_pct" in snap.columns:
            up = int((snap["change_pct"] > 0).sum())
            down = int((snap["change_pct"] < 0).sum())
            flat = int((snap["change_pct"] == 0).sum())
            data["market_stats"] = {
                "total": len(snap),
                "up": up,
                "down": down,
                "flat": flat,
                "up_ratio": round(up / len(snap) * 100, 2) if len(snap) else 0,
            }
        else:
            data["market_stats"] = {
                "total": 0,
                "up": 0,
                "down": 0,
                "flat": 0,
                "up_ratio": 0,
                "note": "无全市场快照，仅有涨停跌停数据",
            }

        lhb = data.get("lhb", pd.DataFrame())
        seats = data.get("lhb_seats", pd.DataFrame())
        logger.info(
            f"市场摘要: 涨停{lud.get('limit_up_count', 0)} "
            f"跌停{lud.get('limit_down_count', 0)} "
            f"炸板{lud.get('zhaban_count', 0)} "
            f"最高连板{lud.get('max_board', 0)} "
            f"龙虎榜{len(lhb) if isinstance(lhb, pd.DataFrame) else 0}条 "
            f"席位{len(seats) if isinstance(seats, pd.DataFrame) else 0}条 "
            f"快照行数{len(snap)}"
        )
        logger.info("========== 每日数据拉取完成 ==========")
        return data
