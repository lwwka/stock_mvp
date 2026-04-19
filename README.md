# Stock MVP - 低估候選最小模型

這是一個只讀 FUTU / 牛牛 API 的股票學習 MVP。它不交易、不送單、不讀帳戶資料，只把「便宜 + 有實力」這個低估候選框架變成每日數字報告。

## 最小模型 1-4

1. **價差**：價格升跌、成交量、spread，判斷短期買賣成本與市場是否有確認。
2. **股息提示**：用 watchlist 手動欄位提醒這家公司是否偏股息型。
3. **公司成長 proxy**：用 watchlist 手動欄位 + 20 日/60 日價格趨勢做初步觀察。
4. **估值修復 proxy**：用 watchlist 手動欄位 + 價格是否從低位回升做初步觀察。
5. **公司實力檢查**：用手動欄位檢查盈利能力、資產負債表、護城河，避免把 value trap 當低估。

市場情緒工具可以放在後面接入；這個 MVP 先幫你把「股票本身的基本數字」看清楚。

## Setup

先開啟 Futu OpenD 並登入，預設：

```text
127.0.0.1:11111
```

Clone repo：

```powershell
git clone https://github.com/lwwka/stock_mvp.git
cd stock_mvp
```

建立獨立 venv：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

執行：

```powershell
python .\src\stock_mvp.py
```

## Output

輸出到：

```text
reports\
```

包含：

- `stock_mvp_*.md`：繁體中文報告
- `stock_mvp_*.csv`：數字表

## Watchlist

修改：

```text
config\watchlist.csv
```

手動欄位說明：

- `dividend_hint`: `none`, `low`, `medium`, `high`
- `growth_proxy`: `low`, `medium`, `high`
- `valuation_proxy`: `cheap`, `fair`, `expensive`, `cyclical`
- `profitability_hint`: `weak`, `medium`, `strong`
- `balance_sheet_hint`: `weak`, `medium`, `strong`
- `moat_hint`: `weak`, `medium`, `strong`
- `main_risk`: 你認為這家公司最大的風險

這些不是精準估值，只是初學階段的分類提示。真正估值要之後再接財報、現金流與估值倍數。

## 低估候選 vs Value Trap

最重要的判斷：

```text
便宜 + 公司實力仍在 + 價格開始修復 = 低估候選
便宜 + 公司實力變差 = value trap
```

這個 MVP 不會告訴你買不買，只會提醒你應該問哪幾個問題。

## 邊界

- 不使用 FUTU Trade API。
- 不做真錢交易。
- 不提供投資建議。
- 只做 paper / research。
