"""交易日判断工具"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import chinese_calendar as calendar


def is_trading_day(d: date | datetime | str | None = None) -> bool:
    """
    判断是否为A股交易日（排除周末和中国法定节假日）。
    注意：不包含临时休市，极端情况需人工覆盖。
    """
    if d is None:
        d = date.today()
    if isinstance(d, str):
        d = datetime.strptime(d[:10], "%Y-%m-%d").date()
    if isinstance(d, datetime):
        d = d.date()

    # 周末直接 False
    if d.weekday() >= 5:
        return False

    # 法定节假日
    try:
        return calendar.is_workday(d)
    except Exception:
        # 兜底：仅排除周末
        return d.weekday() < 5


def get_latest_trading_day(ref: date | datetime | str | None = None) -> date:
    """获取不晚于 ref 的最近一个交易日"""
    if ref is None:
        ref = date.today()
    if isinstance(ref, str):
        ref = datetime.strptime(ref[:10], "%Y-%m-%d").date()
    if isinstance(ref, datetime):
        ref = ref.date()

    d = ref
    for _ in range(15):  # 最多往前找15天
        if is_trading_day(d):
            return d
        d -= timedelta(days=1)
    return ref  # 理论上不会走到这里
