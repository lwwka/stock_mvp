from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class WatchItem:
    """Manual watchlist metadata for the beginner stock MVP."""

    symbol: str
    name: str
    theme: str
    dividend_hint: str
    growth_proxy: str
    valuation_proxy: str
    profitability_hint: str
    balance_sheet_hint: str
    moat_hint: str
    main_risk: str
    notes: str


@dataclass(frozen=True, slots=True)
class KlineStats:
    """Simple K-line statistics used as price-based proxies."""

    rows: int
    return_20d_pct: float | None
    return_60d_pct: float | None
    distance_from_60d_low_pct: float | None
    distance_from_60d_high_pct: float | None
    avg_volume_20d: float | None


@dataclass(frozen=True, slots=True)
class StockMvpRow:
    """Final row used by Markdown and CSV reports."""

    symbol: str
    name: str
    theme: str
    update_time: str
    last_price: float
    change_pct: float
    volume: float
    volume_ratio: float
    spread_bps: float | None
    return_20d_pct: float | None
    return_60d_pct: float | None
    distance_from_60d_low_pct: float | None
    dividend_hint: str
    dividend_read: str
    growth_proxy: str
    growth_read: str
    valuation_proxy: str
    valuation_read: str
    profitability_hint: str
    balance_sheet_hint: str
    moat_hint: str
    quality_read: str
    value_trap_read: str
    main_risk: str
    beginner_read: str
    notes: str


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the read-only stock MVP."""
    parser = argparse.ArgumentParser(description="Beginner stock MVP using read-only Futu quote data.")
    parser.add_argument("--watchlist", default="config/watchlist.csv", help="CSV with stock MVP watchlist fields.")
    parser.add_argument("--out", default="reports", help="Output directory.")
    parser.add_argument("--host", default="127.0.0.1", help="Futu OpenD host.")
    parser.add_argument("--port", type=int, default=11111, help="Futu OpenD port.")
    parser.add_argument("--history-days", type=int, default=120, help="Calendar days for daily K-line context.")
    return parser.parse_args()


def load_watchlist(path: str | Path) -> list[WatchItem]:
    """Load manual stock model metadata from CSV."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"watchlist file not found: {target}")

    required = {
        "symbol",
        "name",
        "theme",
        "dividend_hint",
        "growth_proxy",
        "valuation_proxy",
        "profitability_hint",
        "balance_sheet_hint",
        "moat_hint",
        "main_risk",
        "notes",
    }
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            missing = sorted(required.difference(set(reader.fieldnames or [])))
            raise ValueError(f"watchlist missing columns: {missing}")
        rows = [
            WatchItem(
                symbol=str(row["symbol"]).strip().upper(),
                name=str(row["name"]).strip(),
                theme=str(row["theme"]).strip(),
                dividend_hint=str(row["dividend_hint"]).strip().lower(),
                growth_proxy=str(row["growth_proxy"]).strip().lower(),
                valuation_proxy=str(row["valuation_proxy"]).strip().lower(),
                profitability_hint=str(row["profitability_hint"]).strip().lower(),
                balance_sheet_hint=str(row["balance_sheet_hint"]).strip().lower(),
                moat_hint=str(row["moat_hint"]).strip().lower(),
                main_risk=str(row["main_risk"]).strip(),
                notes=str(row["notes"]).strip(),
            )
            for row in reader
            if str(row.get("symbol", "")).strip()
        ]
    if not rows:
        raise ValueError("watchlist is empty")
    return rows


def fetch_rows(
    watchlist: list[WatchItem],
    host: str,
    port: int,
    history_days: int,
) -> list[StockMvpRow]:
    """Fetch read-only Futu data and build beginner stock MVP rows."""
    try:
        from futu import AuType, KLType, OpenQuoteContext, RET_OK
    except ImportError as exc:
        raise RuntimeError("futu-api is not installed. Run: python -m pip install -r requirements.txt") from exc

    quote_ctx = OpenQuoteContext(host=host, port=port)
    try:
        codes = [item.symbol for item in watchlist]
        ret, snapshot_data = quote_ctx.get_market_snapshot(codes)
        if ret != RET_OK:
            raise RuntimeError(f"Futu get_market_snapshot failed: {_safe_error(snapshot_data)}")

        snapshots = {str(row.get("code", "")).upper(): row for row in snapshot_data.to_dict("records")}
        rows: list[StockMvpRow] = []
        end = date.today()
        start = end - timedelta(days=history_days)

        for item in watchlist:
            snapshot = snapshots.get(item.symbol)
            if snapshot is None:
                continue

            ret, kline_data, _ = quote_ctx.request_history_kline(
                item.symbol,
                start=start.isoformat(),
                end=end.isoformat(),
                ktype=KLType.K_DAY,
                autype=AuType.QFQ,
                max_count=1000,
            )
            stats = KlineStats(0, None, None, None, None, None)
            if ret == RET_OK:
                stats = build_kline_stats(kline_data.to_dict("records"))
            rows.append(build_stock_row(item, snapshot, stats))
        return rows
    finally:
        quote_ctx.close()


def build_stock_row(item: WatchItem, snapshot: dict[str, Any], stats: KlineStats) -> StockMvpRow:
    """Build one beginner stock MVP output row."""
    last_price = _number(snapshot, "last_price", "cur_price")
    previous_close = _number(snapshot, "prev_close_price", "last_close_price", default=0.0)
    volume = _number(snapshot, "volume", default=0.0)
    volume_ratio = _number(snapshot, "volume_ratio", default=0.0)
    bid_price = _number(snapshot, "bid_price", default=0.0)
    ask_price = _number(snapshot, "ask_price", default=0.0)
    change_pct = 0.0 if previous_close == 0 else ((last_price - previous_close) / previous_close) * 100
    spread_bps = _spread_bps(bid_price, ask_price)

    dividend_read = read_dividend(item.dividend_hint)
    growth_read = read_growth(item.growth_proxy, stats.return_20d_pct, stats.return_60d_pct, volume_ratio)
    valuation_read = read_valuation(
        item.valuation_proxy,
        stats.distance_from_60d_low_pct,
        stats.distance_from_60d_high_pct,
    )
    quality_score = quality_score_from_hints(
        item.profitability_hint,
        item.balance_sheet_hint,
        item.moat_hint,
    )
    quality_read = read_quality(
        item.profitability_hint,
        item.balance_sheet_hint,
        item.moat_hint,
        quality_score,
    )
    value_trap_read = read_value_trap(item.valuation_proxy, quality_score, stats.return_60d_pct)
    beginner_read = build_beginner_read(
        change_pct,
        volume_ratio,
        spread_bps,
        growth_read,
        valuation_read,
        value_trap_read,
    )

    return StockMvpRow(
        symbol=item.symbol,
        name=item.name,
        theme=item.theme,
        update_time=str(snapshot.get("update_time", "")),
        last_price=round(last_price, 4),
        change_pct=round(change_pct, 3),
        volume=round(volume, 2),
        volume_ratio=round(volume_ratio, 3),
        spread_bps=round(spread_bps, 2) if spread_bps is not None else None,
        return_20d_pct=stats.return_20d_pct,
        return_60d_pct=stats.return_60d_pct,
        distance_from_60d_low_pct=stats.distance_from_60d_low_pct,
        dividend_hint=item.dividend_hint,
        dividend_read=dividend_read,
        growth_proxy=item.growth_proxy,
        growth_read=growth_read,
        valuation_proxy=item.valuation_proxy,
        valuation_read=valuation_read,
        profitability_hint=item.profitability_hint,
        balance_sheet_hint=item.balance_sheet_hint,
        moat_hint=item.moat_hint,
        quality_read=quality_read,
        value_trap_read=value_trap_read,
        main_risk=item.main_risk,
        beginner_read=beginner_read,
        notes=item.notes,
    )


def build_kline_stats(records: list[dict[str, Any]]) -> KlineStats:
    """Compute simple price-trend proxies from daily K-lines."""
    closes = [_number(row, "close", default=0.0) for row in records if _number(row, "close", default=0.0) > 0]
    volumes = [_number(row, "volume", default=0.0) for row in records if _number(row, "volume", default=0.0) >= 0]
    low_60d = min(closes[-60:]) if closes else None
    high_60d = max(closes[-60:]) if closes else None
    last = closes[-1] if closes else None
    distance_low = ((last / low_60d) - 1) * 100 if last and low_60d else None
    distance_high = ((last / high_60d) - 1) * 100 if last and high_60d else None
    avg_volume = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else None
    return KlineStats(
        rows=len(records),
        return_20d_pct=_round_optional(_period_return(closes, 20)),
        return_60d_pct=_round_optional(_period_return(closes, 60)),
        distance_from_60d_low_pct=_round_optional(distance_low),
        distance_from_60d_high_pct=_round_optional(distance_high),
        avg_volume_20d=round(avg_volume, 2) if avg_volume is not None else None,
    )


def read_dividend(dividend_hint: str) -> str:
    """Explain the dividend part of the beginner model."""
    mapping = {
        "none": "股息不是主要賺錢來源；先不要把它當收息股。",
        "low": "股息提示偏低；主要仍看價差、成長或估值變化。",
        "medium": "有一定股息/回購想像，可作為長期回報的一小部分。",
        "high": "偏收息型；要額外檢查派息是否穩定與是否可持續。",
    }
    return mapping.get(dividend_hint, "未知股息分類；請在 watchlist 修正。")


def read_growth(
    growth_proxy: str,
    return_20d_pct: float | None,
    return_60d_pct: float | None,
    volume_ratio: float,
) -> str:
    """Explain the growth proxy using manual classification and price confirmation."""
    trend = "趨勢資料不足"
    if return_20d_pct is not None and return_60d_pct is not None:
        if return_20d_pct > 5 and return_60d_pct > 8:
            trend = "價格趨勢正在確認成長敘事"
        elif return_20d_pct < -5 and return_60d_pct < -8:
            trend = "市場暫時不買成長故事"
        else:
            trend = "價格趨勢未給出明確成長確認"
    volume = "成交量有確認" if volume_ratio >= 1.5 else "成交量確認不足"
    return f"手動成長分類={growth_proxy}；{trend}；{volume}。"


def read_valuation(
    valuation_proxy: str,
    distance_from_60d_low_pct: float | None,
    distance_from_60d_high_pct: float | None,
) -> str:
    """Explain valuation repair proxy with simple price location."""
    if distance_from_60d_low_pct is None or distance_from_60d_high_pct is None:
        return f"估值分類={valuation_proxy}；K 線資料不足，暫時不能判斷估值修復。"
    if valuation_proxy in {"cheap", "cyclical"} and 5 <= distance_from_60d_low_pct <= 25:
        return f"估值分類={valuation_proxy}；價格已離 60 日低位 {distance_from_60d_low_pct:.2f}%，可能在早期修復區。"
    if valuation_proxy == "expensive" and distance_from_60d_high_pct > -5:
        return f"估值分類=expensive；價格接近 60 日高位，追價風險較高。"
    return (
        f"估值分類={valuation_proxy}；距 60 日低位 {distance_from_60d_low_pct:.2f}%，"
        f"距 60 日高位 {distance_from_60d_high_pct:.2f}%。"
    )


def quality_score_from_hints(profitability_hint: str, balance_sheet_hint: str, moat_hint: str) -> int:
    """Score manual quality hints to separate undervalued candidates from value traps."""
    score_map = {"weak": 0, "medium": 1, "strong": 2}
    return (
        score_map.get(profitability_hint, 0)
        + score_map.get(balance_sheet_hint, 0)
        + score_map.get(moat_hint, 0)
    )


def read_quality(
    profitability_hint: str,
    balance_sheet_hint: str,
    moat_hint: str,
    quality_score: int,
) -> str:
    """Explain whether the company still looks strong enough for undervaluation study."""
    if quality_score >= 5:
        level = "公司實力初步看起來較強"
    elif quality_score >= 3:
        level = "公司實力中等，需要更多財報確認"
    else:
        level = "公司實力偏弱，容易是 value trap"
    return (
        f"{level}；profitability={profitability_hint}，"
        f"balance_sheet={balance_sheet_hint}，moat={moat_hint}。"
    )


def read_value_trap(valuation_proxy: str, quality_score: int, return_60d_pct: float | None) -> str:
    """Flag beginner value-trap risk using manual quality hints and price trend."""
    weak_trend = return_60d_pct is not None and return_60d_pct < -10
    if valuation_proxy in {"cheap", "cyclical"} and quality_score >= 5 and not weak_trend:
        return "低估候選：看起來不是單純便宜，仍有公司實力支撐。"
    if valuation_proxy in {"cheap", "cyclical"} and quality_score < 3:
        return "Value trap 警告：看似便宜，但公司實力提示偏弱。"
    if valuation_proxy in {"cheap", "cyclical"} and weak_trend:
        return "Value trap 觀察：價格趨勢仍弱，市場可能仍在下修預期。"
    if valuation_proxy == "expensive":
        return "不是低估候選：估值提示偏貴，先學會等更好的價格或更強成長確認。"
    return "中性：估值未明顯偏低，先作觀察。"


def build_beginner_read(
    change_pct: float,
    volume_ratio: float,
    spread_bps: float | None,
    growth_read: str,
    valuation_read: str,
    value_trap_read: str,
) -> str:
    """Create a plain-language beginner read, not a recommendation."""
    spread_ok = spread_bps is not None and spread_bps <= 20
    if change_pct > 1 and volume_ratio >= 1.5 and spread_ok:
        return "價差機會有成交量支持，但仍要看明天是否延續。"
    if change_pct < -1 and volume_ratio >= 1.5:
        return "下跌有成交量支持，先學會等待，不要急著接刀。"
    if spread_bps is None or spread_bps > 20:
        return "買賣成本偏不清楚或偏高，新手先觀察。"
    if "早期修復區" in valuation_read:
        if "Value trap" in value_trap_read:
            return "價位像修復，但有 value trap 風險；先不要急，等更多確認。"
        return "可列入估值修復觀察名單，但需要後續價格與成交量確認。"
    if "確認成長敘事" in growth_read:
        return "成長 proxy 有市場確認，可加入明日觀察。"
    return "目前只是觀察名單，未形成清楚 paper thesis。"


def render_markdown(rows: list[StockMvpRow]) -> str:
    """Render a Traditional Chinese beginner stock MVP report."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"# 低估候選 MVP 報告 - {generated_at}",
        "",
        "邊界：只讀 FUTU 牛牛行情資料，只做 paper / research，不交易、不送單、不用槓桿。",
        "",
        "## 1. 價差",
        "| Symbol | Last | Chg % | Volume Ratio | Spread bps | 新手解讀 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.symbol} | {_fmt(row.last_price)} | {_fmt(row.change_pct)} | "
            f"{_fmt(row.volume_ratio)} | {_fmt_optional(row.spread_bps)} | {row.beginner_read} |"
        )

    lines.extend(["", "## 2. 股息提示", "| Symbol | Dividend Hint | 解讀 |", "|---|---|---|"])
    for row in rows:
        lines.append(f"| {row.symbol} | {row.dividend_hint} | {row.dividend_read} |")

    lines.extend(
        [
            "",
            "## 3. 公司成長 Proxy",
            "| Symbol | Growth Proxy | 20D Return % | 60D Return % | 解讀 |",
            "|---|---|---:|---:|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.symbol} | {row.growth_proxy} | {_fmt_optional(row.return_20d_pct)} | "
            f"{_fmt_optional(row.return_60d_pct)} | {row.growth_read} |"
        )

    lines.extend(
        [
            "",
            "## 4. 估值修復 Proxy",
            "| Symbol | Valuation Proxy | From 60D Low % | 解讀 | Value Trap |",
            "|---|---|---:|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.symbol} | {row.valuation_proxy} | "
            f"{_fmt_optional(row.distance_from_60d_low_pct)} | {row.valuation_read} | {row.value_trap_read} |"
        )

    lines.extend(
        [
            "",
            "## 5. 公司實力檢查",
            "| Symbol | Profitability | Balance Sheet | Moat | Main Risk | 解讀 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.symbol} | {row.profitability_hint} | {row.balance_sheet_hint} | "
            f"{row.moat_hint} | {row.main_risk} | {row.quality_read} |"
        )

    lines.extend(
        [
            "",
            "## 低估候選檢查",
            "1. 它是否真的便宜，還是只是股價跌了？",
            "2. 公司實力是否仍在：盈利、資產負債表、護城河？",
            "3. 價格是否已離低位回升，而且有成交量支持？",
            "4. 最大風險是短期壞消息，還是公司基本面永久變差？",
            "5. 如果明天價格反轉或成交量消失，這個低估 thesis 是否仍成立？",
            "",
            "## 免責聲明",
            "這份報告是學習工具，不是投資建議。手動 proxy 不是財報估值；它只幫你練習區分低估候選與 value trap。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_csv(path: str | Path, rows: list[StockMvpRow]) -> None:
    """Write the MVP rows to CSV for inspection."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = list(StockMvpRow.__dataclass_fields__.keys())
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: getattr(row, column) for column in columns})


def main() -> None:
    """Run the read-only stock MVP."""
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    watchlist = load_watchlist(args.watchlist)
    rows = fetch_rows(watchlist, args.host, args.port, args.history_days)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"stock_mvp_{suffix}.md"
    csv_path = out_dir / f"stock_mvp_{suffix}.csv"
    md_path.write_text(render_markdown(rows), encoding="utf-8")
    write_csv(csv_path, rows)
    print(f"wrote {md_path}")
    print(f"wrote {csv_path}")


def _number(row: dict[str, Any], *keys: str, default: float | None = None) -> float:
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(number) or math.isinf(number):
            continue
        return number
    if default is not None:
        return default
    raise ValueError(f"missing numeric field from candidates: {keys}")


def _spread_bps(bid: float, ask: float) -> float | None:
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2
    return None if mid <= 0 else ((ask - bid) / mid) * 10000


def _period_return(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or closes[-days - 1] == 0:
        return None
    return ((closes[-1] / closes[-days - 1]) - 1) * 100


def _round_optional(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _fmt_optional(value: float | None) -> str:
    return "N/A" if value is None else _fmt(float(value))


def _safe_error(value: Any) -> str:
    return str(value).replace("\n", " ").replace("\r", " ")[:240]


if __name__ == "__main__":
    main()
