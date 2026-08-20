"""复盘简易图表（阶段3，Mac mini 友好：matplotlib 非交互）"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("content.charts")


def _setup_font():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # 尝试常见中文字体；失败则用默认
    for name in ("PingFang SC", "Heiti SC", "Songti SC", "SimHei", "Arial Unicode MS", "DejaVu Sans"):
        try:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            break
        except Exception:
            continue
    return plt


def make_review_charts(
    review_like: Dict[str, Any],
    out_dir: Path,
) -> List[str]:
    """
    生成 1～2 张图，返回相对文件名列表。
    review_like 可含: board_ladder, limit_up_count, limit_down_count, zhaban_count, indices
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    names: List[str] = []

    try:
        plt = _setup_font()
    except Exception as e:
        logger.warning("matplotlib 不可用: %s", e)
        return names

    # 1) 涨停/跌停/炸板柱状
    try:
        up = int(review_like.get("limit_up_count") or 0)
        down = int(review_like.get("limit_down_count") or 0)
        zb = int(review_like.get("zhaban_count") or 0)
        fig, ax = plt.subplots(figsize=(6, 3.5), dpi=120)
        labels = ["涨停", "跌停", "炸板"]
        vals = [up, down, zb]
        colors = ["#ef4444", "#22c55e", "#f59e0b"]
        ax.bar(labels, vals, color=colors)
        ax.set_title("情绪概览")
        for i, v in enumerate(vals):
            ax.text(i, v, str(v), ha="center", va="bottom", fontsize=10)
        fig.tight_layout()
        p = chart_dir / "emotion_bars.png"
        fig.savefig(p)
        plt.close(fig)
        names.append("charts/emotion_bars.png")
    except Exception as e:
        logger.warning("情绪图失败: %s", e)

    # 2) 连板梯队
    try:
        ladder = review_like.get("board_ladder") or {}
        if isinstance(ladder, dict) and ladder:
            items = sorted(
                ((int(k), int(v)) for k, v in ladder.items() if str(k).isdigit()),
                key=lambda x: x[0],
            )
            if items:
                fig, ax = plt.subplots(figsize=(6, 3.5), dpi=120)
                xs = [f"{k}板" for k, _ in items]
                ys = [v for _, v in items]
                ax.bar(xs, ys, color="#3b82f6")
                ax.set_title("连板梯队")
                for i, v in enumerate(ys):
                    ax.text(i, v, str(v), ha="center", va="bottom", fontsize=10)
                fig.tight_layout()
                p = chart_dir / "board_ladder.png"
                fig.savefig(p)
                plt.close(fig)
                names.append("charts/board_ladder.png")
    except Exception as e:
        logger.warning("连板图失败: %s", e)

    logger.info("图表生成: %s", names)
    return names
