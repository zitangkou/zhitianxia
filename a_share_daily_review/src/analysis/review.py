"""
分析引擎 - 方案一（轻量）
重点：提炼「有吸引力、奇怪、惊讶、超预期」的信息
- 连板高度 / 连板梯队 / 高标
- 炸板率、晋级率
- 龙虎榜游资/机构/解读
- 热门/强势异动
- 指数与情绪背离等
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("analysis.review")


@dataclass
class ReviewResult:
    trade_date: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 基础
    indices: List[Dict[str, Any]] = field(default_factory=list)
    market_stats: Dict[str, Any] = field(default_factory=dict)
    limit_up_count: int = 0
    limit_down_count: int = 0
    zhaban_count: int = 0
    max_board: int = 0
    board_ladder: Dict[int, int] = field(default_factory=dict)

    # 列表素材
    limit_up_top: List[Dict[str, Any]] = field(default_factory=list)
    high_board_stocks: List[Dict[str, Any]] = field(default_factory=list)
    zhaban_top: List[Dict[str, Any]] = field(default_factory=list)
    previous_zt_stats: Dict[str, Any] = field(default_factory=dict)
    lhb_highlights: List[Dict[str, Any]] = field(default_factory=list)
    strong_top: List[Dict[str, Any]] = field(default_factory=list)
    yizi_boards: List[Dict[str, Any]] = field(default_factory=list)       # 一字板近似
    reopen_boards: List[Dict[str, Any]] = field(default_factory=list)     # 开板后回封
    ditian_boards: List[Dict[str, Any]] = field(default_factory=list)     # 地天/昨跌停今涨停
    seat_top: List[Dict[str, Any]] = field(default_factory=list)          # 游资席位
    theme_hits: List[Dict[str, Any]] = field(default_factory=list)        # 题材关键词命中
    industry_top: List[Dict[str, Any]] = field(default_factory=list)
    industry_bottom: List[Dict[str, Any]] = field(default_factory=list)

    # 核心：吸引人的惊喜点
    surprise_points: List[str] = field(default_factory=list)
    summary_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReviewEngine:
    def __init__(self, config: Optional[Dict] = None):
        self.cfg = config or {}

    def build(self, data: Dict[str, Any]) -> ReviewResult:
        trade_date = data.get("trade_date", "")
        result = ReviewResult(trade_date=trade_date)

        # 指数
        idx = data.get("indices", pd.DataFrame())
        if isinstance(idx, pd.DataFrame) and not idx.empty:
            cols = [c for c in ["name", "code", "close", "change_pct", "open", "high", "low"] if c in idx.columns]
            result.indices = idx[cols].to_dict(orient="records")

        result.market_stats = data.get("market_stats", {})

        # 涨停情绪
        lud = data.get("limit_up_down", {})
        result.limit_up_count = int(lud.get("limit_up_count", 0))
        result.limit_down_count = int(lud.get("limit_down_count", 0))
        result.zhaban_count = int(lud.get("zhaban_count", 0))
        result.max_board = int(lud.get("max_board", 0))
        result.board_ladder = {int(k): int(v) for k, v in (lud.get("board_ladder") or {}).items()}

        up_df = lud.get("limit_up", pd.DataFrame())
        if isinstance(up_df, pd.DataFrame) and not up_df.empty:
            prefer = ["代码", "名称", "涨跌幅", "最新价", "连板数", "所属行业", "炸板次数", "封板资金", "首次封板时间"]
            use_cols = [c for c in prefer if c in up_df.columns]
            result.limit_up_top = up_df[use_cols].head(20).to_dict(orient="records")
            if "连板数" in up_df.columns:
                high = up_df[up_df["连板数"] >= 2].sort_values("连板数", ascending=False)
                result.high_board_stocks = high[use_cols].head(12).to_dict(orient="records")

        zb_df = lud.get("zhaban", pd.DataFrame())
        if isinstance(zb_df, pd.DataFrame) and not zb_df.empty:
            zb_cols = [c for c in ["代码", "名称", "涨跌幅", "最新价", "涨停价", "换手率", "所属行业"] if c in zb_df.columns]
            result.zhaban_top = zb_df[zb_cols].head(10).to_dict(orient="records")

        prev_df = lud.get("previous_zt", pd.DataFrame())
        result.previous_zt_stats = self._calc_previous_zt_stats(prev_df, up_df)

        strong_df = lud.get("strong", pd.DataFrame())
        if isinstance(strong_df, pd.DataFrame) and not strong_df.empty:
            s_cols = [c for c in ["代码", "名称", "涨跌幅", "最新价", "换手率"] if c in strong_df.columns]
            result.strong_top = strong_df[s_cols].head(10).to_dict(orient="records")

        # 一字板 / 开板回封 / 地天近似
        result.yizi_boards, result.reopen_boards = self._detect_board_patterns(up_df)
        result.ditian_boards = self._detect_ditian(
            lud.get("limit_down", pd.DataFrame()),
            lud.get("previous_zt", pd.DataFrame()),
            up_df,
            data,
        )
        # 题材关键词命中（涨停+强势名称）
        result.theme_hits = self._match_themes(up_df, strong_df)

        lhb_df = data.get("lhb", pd.DataFrame())
        result.lhb_highlights = self._extract_lhb_highlights(lhb_df)

        seats_df = data.get("lhb_seats", pd.DataFrame())
        result.seat_top = self._extract_seat_top(seats_df)

        ind = data.get("industry", pd.DataFrame())
        if isinstance(ind, pd.DataFrame) and not ind.empty and "change_pct" in ind.columns:
            ind_sorted = ind.sort_values("change_pct", ascending=False)
            top_n = self.cfg.get("analysis", {}).get("sector_top_n", 10)
            result.industry_top = ind_sorted.head(top_n)[
                [c for c in ["name", "change_pct", "leader", "leader_pct", "up_count", "down_count"] if c in ind.columns]
            ].to_dict(orient="records")
            result.industry_bottom = ind_sorted.tail(top_n)[
                [c for c in ["name", "change_pct", "leader", "leader_pct"] if c in ind.columns]
            ].to_dict(orient="records")

        result.surprise_points = self._build_surprise_points(result, data)
        result.summary_text = self._make_attractive_summary(result)

        logger.info(
            f"复盘完成 @ {trade_date} | 涨停{result.limit_up_count} "
            f"最高连板{result.max_board} 炸板{result.zhaban_count} "
            f"惊喜点{len(result.surprise_points)}条"
        )
        return result

    def _calc_previous_zt_stats(
        self, prev_df: pd.DataFrame, today_up: pd.DataFrame
    ) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "prev_count": 0,
            "still_limit_up": 0,
            "promote_rate": None,
            "avg_pct": None,
            "big_lose_count": 0,
        }
        if not isinstance(prev_df, pd.DataFrame) or prev_df.empty:
            return stats

        stats["prev_count"] = len(prev_df)
        pct_col = "涨跌幅" if "涨跌幅" in prev_df.columns else None
        if pct_col:
            stats["avg_pct"] = round(float(prev_df[pct_col].mean()), 2)
            stats["big_lose_count"] = int((prev_df[pct_col] < -5).sum())

        if isinstance(today_up, pd.DataFrame) and not today_up.empty:
            code_col = "代码" if "代码" in prev_df.columns and "代码" in today_up.columns else None
            if code_col:
                prev_codes = set(prev_df[code_col].astype(str))
                today_codes = set(today_up[code_col].astype(str))
                still = prev_codes & today_codes
                stats["still_limit_up"] = len(still)
                if stats["prev_count"] > 0:
                    stats["promote_rate"] = round(len(still) / stats["prev_count"] * 100, 1)
        return stats

    def _extract_lhb_highlights(self, lhb_df: pd.DataFrame, top_n: int = 8) -> List[Dict[str, Any]]:
        if not isinstance(lhb_df, pd.DataFrame) or lhb_df.empty:
            return []

        df = lhb_df.copy()
        net_col = "龙虎榜净买额" if "龙虎榜净买额" in df.columns else None
        if net_col:
            df["_abs_net"] = df[net_col].abs()
            df = df.sort_values("_abs_net", ascending=False)

        prefer = [
            "代码", "名称", "涨跌幅", "解读", "上榜原因",
            "龙虎榜净买额", "龙虎榜买入额", "龙虎榜卖出额", "换手率", "收盘价",
        ]
        use = [c for c in prefer if c in df.columns]
        rows = df[use].head(top_n).to_dict(orient="records")

        for r in rows:
            for k in ["龙虎榜净买额", "龙虎榜买入额", "龙虎榜卖出额"]:
                if k in r and isinstance(r[k], (int, float)):
                    v = r[k]
                    if abs(v) >= 1e8:
                        r[k] = f"{v/1e8:.2f}亿"
                    elif abs(v) >= 1e4:
                        r[k] = f"{v/1e4:.0f}万"
        return rows

    def _build_surprise_points(self, r: ReviewResult, data: Dict[str, Any]) -> List[str]:
        """提炼奇怪、惊讶、超预期的短句，优先写进小红书开头。"""
        points: List[str] = []

        # 连板高度
        if r.max_board >= 5:
            names = "、".join(str(s.get("名称", "")) for s in r.high_board_stocks[:3])
            points.append(f"🔥 最高连板冲到 {r.max_board} 板！高标：{names or '详见连板梯队'}")
        elif r.max_board >= 3:
            names = "、".join(
                str(s.get("名称", ""))
                for s in r.high_board_stocks
                if s.get("连板数", 0) >= r.max_board
            )
            points.append(f"📈 最高连板 {r.max_board} 板（{names or '多只'}）")

        if r.board_ladder:
            ladder_str = " / ".join(
                f"{k}板{v}家" for k, v in sorted(r.board_ladder.items(), reverse=True) if k >= 2
            )
            if ladder_str:
                points.append(f"连板梯队：{ladder_str}")

        # 地天 / 昨跌停今涨停
        if r.ditian_boards:
            names = "、".join(str(s.get("名称", "")) for s in r.ditian_boards[:4])
            points.append(f"🎢 地天/极端反转：{names}（昨弱今强或大振幅回封）")

        # 一字板
        if r.yizi_boards:
            names = "、".join(str(s.get("名称", "")) for s in r.yizi_boards[:5])
            points.append(f"📌 一字板（早盘秒板且未开板）约 {len(r.yizi_boards)} 只：{names}")

        # 开板回封之王
        if r.reopen_boards:
            top = r.reopen_boards[0]
            points.append(
                f"🔄 开板回封之王：{top.get('名称','')} 炸板 {top.get('炸板次数','?')} 次仍回封"
                + (f"（共{len(r.reopen_boards)}只多次开板回封）" if len(r.reopen_boards) > 1 else "")
            )

        # 题材关键词（电影/节日/梗）
        if r.theme_hits:
            for th in r.theme_hits[:3]:
                points.append(
                    f"🎬 题材情绪·{th.get('theme','')}：关键词「{th.get('keyword','')}」命中 "
                    f"{th.get('count',0)} 只 → {th.get('names','')}"
                )

        # 游资席位
        if r.seat_top:
            for seat in r.seat_top[:3]:
                nick = seat.get("nickname") or ""
                name = seat.get("营业部简称") or seat.get("营业部名称", "")[:18]
                stocks = seat.get("买入股票", "")
                if isinstance(stocks, str) and len(stocks) > 24:
                    stocks = stocks[:24] + "…"
                net = seat.get("净额可读", seat.get("总买卖净额", ""))
                label = f"{nick}·{name}" if nick and nick not in str(name) else name
                points.append(f"🦈 席位·{label} 净买 {net}，买入：{stocks}")

        # 涨停 vs 跌停
        if r.limit_up_count >= 80 and r.limit_down_count <= 15:
            points.append(f"情绪偏强：涨停 {r.limit_up_count} 家，跌停仅 {r.limit_down_count} 家")
        elif r.limit_down_count >= 30:
            points.append(f"⚠️ 跌停高达 {r.limit_down_count} 家，情绪明显转弱")
        elif r.limit_up_count > 0:
            points.append(f"涨停 {r.limit_up_count} 家，跌停 {r.limit_down_count} 家")

        # 炸板率
        if r.zhaban_count > 0 and (r.limit_up_count + r.zhaban_count) > 0:
            rate = r.zhaban_count / (r.limit_up_count + r.zhaban_count) * 100
            if rate >= 40:
                points.append(f"💥 炸板率偏高约 {rate:.0f}%（炸板 {r.zhaban_count} 家），封板质量一般")
            elif rate <= 15 and r.limit_up_count >= 40:
                points.append(f"✅ 炸板率较低约 {rate:.0f}%，封板相对扎实")

        # 晋级率
        ps = r.previous_zt_stats
        if ps.get("prev_count", 0) >= 10 and ps.get("promote_rate") is not None:
            rate = ps["promote_rate"]
            avg = ps.get("avg_pct")
            if rate >= 40:
                points.append(
                    f"昨日涨停晋级率 {rate}%（{ps['still_limit_up']}/{ps['prev_count']}），溢价尚可"
                    + (f"，均值 {avg}%" if avg is not None else "")
                )
            elif rate <= 15:
                points.append(
                    f"昨日涨停晋级率仅 {rate}%，多数兑现/回落"
                    + (f"（均值 {avg}%）" if avg is not None else "")
                )
            if ps.get("big_lose_count", 0) >= 5:
                points.append(f"昨日涨停中有 {ps['big_lose_count']} 只大面（跌超5%）")

        # 龙虎榜故事
        for item in r.lhb_highlights[:4]:
            name = item.get("名称", "")
            jiedu = str(item.get("解读", "") or "")
            reason = str(item.get("上榜原因", "") or "")
            net = item.get("龙虎榜净买额", "")
            pct = item.get("涨跌幅", "")
            if not name:
                continue
            interesting = any(
                k in jiedu for k in ["机构", "游资", "做T", "抢筹", "分歧", "成功率"]
            ) or "涨停" in reason or "偏离" in reason
            if interesting or len(r.lhb_highlights) <= 3:
                snippet = jiedu if jiedu else reason
                if len(snippet) > 28:
                    snippet = snippet[:28] + "…"
                net_s = f"，净买 {net}" if net else ""
                pct_s = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else str(pct)
                points.append(f"🐉 龙虎榜·{name}（{pct_s}）{snippet}{net_s}")

        # 指数与情绪背离
        if r.indices:
            main = next((i for i in r.indices if "上证" in str(i.get("name", ""))), r.indices[0])
            pct = main.get("change_pct", 0) or 0
            if pct > 0.5 and r.limit_down_count >= 20:
                points.append(f"指数涨但跌停不少（上证 {pct:+.2f}% vs 跌停 {r.limit_down_count}），结构分化")
            elif pct < -0.8 and r.limit_up_count >= 50:
                points.append(f"指数偏弱但涨停仍多（上证 {pct:+.2f}% vs 涨停 {r.limit_up_count}），局部仍有火种")

        # 高标行业集中
        if r.high_board_stocks:
            industries = [str(s.get("所属行业", "")) for s in r.high_board_stocks if s.get("所属行业")]
            if industries:
                top_ind = Counter(industries).most_common(2)
                if top_ind and top_ind[0][1] >= 2:
                    points.append(
                        f"高连板偏向：{'、'.join(f'{n}({c}只)' for n, c in top_ind)}"
                    )

        seen = set()
        unique = []
        for p in points:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique[:12]


    def _detect_board_patterns(self, up_df: pd.DataFrame):
        """一字板近似 + 开板回封"""
        yizi, reopen = [], []
        if not isinstance(up_df, pd.DataFrame) or up_df.empty:
            return yizi, reopen
        cfg = self.cfg.get("analysis", {})
        seal_before = str(cfg.get("yizi_seal_before", "093500"))
        zhaban_min = int(cfg.get("reopen_zhaban_min", 5))
        cols = [c for c in ["代码", "名称", "连板数", "炸板次数", "首次封板时间", "最后封板时间", "所属行业"] if c in up_df.columns]
        df = up_df.copy()
        if "首次封板时间" in df.columns and "炸板次数" in df.columns:
            seal = df["首次封板时间"].astype(str).str.replace(":", "").str.zfill(6)
            zb = pd.to_numeric(df["炸板次数"], errors="coerce").fillna(0)
            yizi_df = df[(seal <= seal_before) & (zb == 0)]
            yizi = yizi_df[cols].head(12).to_dict(orient="records")
            reopen_df = df[zb >= zhaban_min].sort_values("炸板次数", ascending=False)
            reopen = reopen_df[cols].head(8).to_dict(orient="records")
        return yizi, reopen

    def _detect_ditian(self, limit_down_df, previous_zt_df, up_df, data) -> list:
        """
        地天/极端反转近似：
        1) 昨日跌停相关难以直接取，用「今日涨停里炸板次数极高」作情绪地天
        2) 若有昨跌停池与今涨停代码交集（未来可扩展）
        当前：从涨停池中找「早盘弱/多次开板但尾盘封住」的叙事票
        """
        out = []
        if not isinstance(up_df, pd.DataFrame) or up_df.empty:
            return out
        if "炸板次数" in up_df.columns:
            zb = pd.to_numeric(up_df["炸板次数"], errors="coerce").fillna(0)
            # 炸板很多次仍封住 = 盘中地天感
            extreme = up_df[zb >= 8].sort_values("炸板次数", ascending=False)
            cols = [c for c in ["代码", "名称", "连板数", "炸板次数", "首次封板时间", "最后封板时间", "所属行业"] if c in up_df.columns]
            out = extreme[cols].head(5).to_dict(orient="records")
        return out

    def _match_themes(self, up_df: pd.DataFrame, strong_df: pd.DataFrame) -> list:
        """股票名称命中配置的题材/节日/事件关键词"""
        keywords = self.cfg.get("analysis", {}).get("theme_keywords") or []
        if not keywords:
            return []
        names = []
        for df in (up_df, strong_df):
            if isinstance(df, pd.DataFrame) and not df.empty and "名称" in df.columns:
                names.extend([(str(r.get("名称","")), str(r.get("代码",""))) for _, r in df.iterrows()])
        hits = []
        for item in keywords:
            kw = str(item.get("keyword", ""))
            if not kw:
                continue
            matched = [(n, c) for n, c in names if kw in n]
            # 去重
            seen = set()
            uniq = []
            for n, c in matched:
                if n not in seen:
                    seen.add(n)
                    uniq.append(n)
            if uniq:
                themes = item.get("themes") or [kw]
                hits.append({
                    "keyword": kw,
                    "theme": themes[0] if themes else kw,
                    "count": len(uniq),
                    "names": "、".join(uniq[:6]),
                    "note": item.get("note", ""),
                })
        hits.sort(key=lambda x: -x["count"])
        return hits[:6]

    def _extract_seat_top(self, seats_df: pd.DataFrame, top_n: int = 6) -> list:
        """游资/营业部席位净买入排行 + 绰号"""
        if not isinstance(seats_df, pd.DataFrame) or seats_df.empty:
            return []
        df = seats_df.copy()
        net_col = "总买卖净额" if "总买卖净额" in df.columns else None
        if net_col:
            df = df.sort_values(net_col, ascending=False)
        famous = self.cfg.get("analysis", {}).get("famous_seats") or []
        rows = []
        for _, row in df.head(top_n * 2).iterrows():
            name = str(row.get("营业部名称", ""))
            if "股通" in name and len(rows) >= 2:
                # 深/沪股通保留1-2个即可
                if sum(1 for r in rows if "股通" in r.get("营业部名称","")) >= 1:
                    continue
            nick = ""
            for f in famous:
                if f.get("match") and f["match"] in name:
                    nick = f.get("nickname", "")
                    break
            net = row.get(net_col, 0) if net_col else 0
            try:
                net_f = float(net)
                if abs(net_f) >= 1e8:
                    net_s = f"{net_f/1e8:.2f}亿"
                else:
                    net_s = f"{net_f/1e4:.0f}万"
            except Exception:
                net_s = str(net)
            short = name
            for prefix in ["证券股份有限公司", "股份有限公司", "有限责任公司"]:
                short = short.replace(prefix, "")
            rows.append({
                "营业部名称": name,
                "营业部简称": short[:20],
                "nickname": nick,
                "买入个股数": row.get("买入个股数"),
                "买入股票": row.get("买入股票"),
                "总买卖净额": net,
                "净额可读": net_s,
            })
            if len(rows) >= top_n:
                break
        return rows


    def _make_attractive_summary(self, r: ReviewResult) -> str:
        lines = [f"【{r.trade_date} A股收盘 · 超预期看点】", ""]

        if r.surprise_points:
            lines.append("⚡ 今日最值得盯的：")
            for i, p in enumerate(r.surprise_points[:8], 1):
                lines.append(f"{i}. {p}")
            lines.append("")

        if r.indices:
            idx_str = "  ".join(
                f"{i.get('name', '')} {i.get('change_pct', 0):+.2f}%" for i in r.indices[:4]
            )
            lines.append(f"指数：{idx_str}")

        lines.append(
            f"涨停 {r.limit_up_count} | 跌停 {r.limit_down_count} | "
            f"炸板 {r.zhaban_count} | 最高连板 {r.max_board}"
        )

        if r.high_board_stocks:
            hb = "、".join(
                f"{s.get('名称', '')}({s.get('连板数', '?')}板)" for s in r.high_board_stocks[:5]
            )
            lines.append(f"高标：{hb}")

        if r.yizi_boards:
            lines.append(f"一字板约 {len(r.yizi_boards)} 只 | 开板回封亮点 {len(r.reopen_boards)} 只")
        if r.ditian_boards:
            lines.append(f"极端回封/地天感 {len(r.ditian_boards)} 只")
        if r.theme_hits:
            ths = "；".join(f"{t.get('theme')}×{t.get('count')}" for t in r.theme_hits[:3])
            lines.append(f"题材关键词命中：{ths}")
        if r.seat_top:
            lines.append(f"游资席位TOP：{len(r.seat_top)} 家营业部")

        if r.lhb_highlights:
            lines.append(f"龙虎榜重点约 {len(r.lhb_highlights)} 条（含解读/净买）")

        lines.append("")
        lines.append("⚠️ 仅供学习研究，不构成任何投资建议。")
        return "\n".join(lines)
