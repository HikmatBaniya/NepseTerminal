import base64
import datetime
import json
import uuid
import time
import math
import webbrowser
from typing import Any, Dict, List, Optional
import requests
import os
import colorama
from colorama import Fore, Style
import traceback

from nepse_data import NEPSEData as _NEPSEDataClass
_nepse_instance = _NEPSEDataClass()

# -----------------------------
# GUI HUB OUTPUTS
# -----------------------------
HUB_DATA_DIR = os.environ.get("POWERTRADER_HUB_DIR", os.path.join(os.path.dirname(__file__), "hub_data"))
os.makedirs(HUB_DATA_DIR, exist_ok=True)

TRADER_STATUS_PATH = os.path.join(HUB_DATA_DIR, "trader_status.json")
TRADE_HISTORY_PATH = os.path.join(HUB_DATA_DIR, "trade_history.jsonl")
PNL_LEDGER_PATH = os.path.join(HUB_DATA_DIR, "pnl_ledger.json")
ACCOUNT_VALUE_HISTORY_PATH = os.path.join(HUB_DATA_DIR, "account_value_history.jsonl")



# Initialize colorama
colorama.init(autoreset=True)

# -----------------------------
# GUI SETTINGS (coins list + main_neural_dir)
# -----------------------------
_GUI_SETTINGS_PATH = os.environ.get("POWERTRADER_GUI_SETTINGS") or os.path.join(
	os.path.dirname(os.path.abspath(__file__)),
	"gui_settings.json"
)

_gui_settings_cache = {
	"mtime": None,
	"coins": ['NABIL', 'NTC', 'NICA', 'NLIC', 'SBL'],  # fallback NEPSE defaults
	"main_neural_dir": None,
	"trade_start_level": 3,
	"start_allocation_pct": 0.10,
	"capital": 100000.0,
	"dca_multiplier": 2.0,
	"dca_levels": [-2.5, -5.0, -10.0, -20.0],
	"max_dca_buys_per_24h": 1,
	"tms_url": "https://tms58.nepsetms.com.np/",

	# Trailing PM settings (defaults match previous hardcoded behavior)
	"pm_start_pct_no_dca": 5.0,
	"pm_start_pct_with_dca": 2.5,
	"trailing_gap_pct": 0.5,
}







def _load_gui_settings() -> dict:
	"""
	Reads gui_settings.json and returns a dict with:
	- coins: uppercased list
	- main_neural_dir: string (may be None)
	Caches by mtime so it is cheap to call frequently.
	"""
	try:
		if not os.path.isfile(_GUI_SETTINGS_PATH):
			return dict(_gui_settings_cache)

		mtime = os.path.getmtime(_GUI_SETTINGS_PATH)
		if _gui_settings_cache["mtime"] == mtime:
			return dict(_gui_settings_cache)

		with open(_GUI_SETTINGS_PATH, "r", encoding="utf-8") as f:
			data = json.load(f) or {}

		# Accept "stocks" (NEPSE) or "coins" (legacy) key
		coins = data.get("stocks", data.get("coins", None))
		if not isinstance(coins, list) or not coins:
			coins = list(_gui_settings_cache["coins"])
		coins = [str(c).strip().upper() for c in coins if str(c).strip()]
		if not coins:
			coins = list(_gui_settings_cache["coins"])

		main_neural_dir = data.get("main_neural_dir", None)
		if isinstance(main_neural_dir, str):
			main_neural_dir = main_neural_dir.strip() or None
		else:
			main_neural_dir = None

		trade_start_level = data.get("trade_start_level", _gui_settings_cache.get("trade_start_level", 3))
		try:
			trade_start_level = int(float(trade_start_level))
		except Exception:
			trade_start_level = int(_gui_settings_cache.get("trade_start_level", 3))
		trade_start_level = max(1, min(trade_start_level, 7))

		start_allocation_pct = data.get("start_allocation_pct", _gui_settings_cache.get("start_allocation_pct", 0.005))
		try:
			start_allocation_pct = float(str(start_allocation_pct).replace("%", "").strip())
		except Exception:
			start_allocation_pct = float(_gui_settings_cache.get("start_allocation_pct", 0.005))
		if start_allocation_pct < 0.0:
			start_allocation_pct = 0.0

		dca_multiplier = data.get("dca_multiplier", _gui_settings_cache.get("dca_multiplier", 2.0))
		try:
			dca_multiplier = float(str(dca_multiplier).strip())
		except Exception:
			dca_multiplier = float(_gui_settings_cache.get("dca_multiplier", 2.0))
		if dca_multiplier < 0.0:
			dca_multiplier = 0.0

		dca_levels = data.get("dca_levels", _gui_settings_cache.get("dca_levels", [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0]))
		if not isinstance(dca_levels, list) or not dca_levels:
			dca_levels = list(_gui_settings_cache.get("dca_levels", [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0]))
		parsed = []
		for v in dca_levels:
			try:
				parsed.append(float(v))
			except Exception:
				pass
		if parsed:
			dca_levels = parsed
		else:
			dca_levels = list(_gui_settings_cache.get("dca_levels", [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0]))

		max_dca_buys_per_24h = data.get("max_dca_buys_per_24h", _gui_settings_cache.get("max_dca_buys_per_24h", 2))
		try:
			max_dca_buys_per_24h = int(float(max_dca_buys_per_24h))
		except Exception:
			max_dca_buys_per_24h = int(_gui_settings_cache.get("max_dca_buys_per_24h", 2))
		if max_dca_buys_per_24h < 0:
			max_dca_buys_per_24h = 0


		# --- Trailing PM settings ---
		pm_start_pct_no_dca = data.get("pm_start_pct_no_dca", _gui_settings_cache.get("pm_start_pct_no_dca", 5.0))
		try:
			pm_start_pct_no_dca = float(str(pm_start_pct_no_dca).replace("%", "").strip())
		except Exception:
			pm_start_pct_no_dca = float(_gui_settings_cache.get("pm_start_pct_no_dca", 5.0))
		if pm_start_pct_no_dca < 0.0:
			pm_start_pct_no_dca = 0.0

		pm_start_pct_with_dca = data.get("pm_start_pct_with_dca", _gui_settings_cache.get("pm_start_pct_with_dca", 2.5))
		try:
			pm_start_pct_with_dca = float(str(pm_start_pct_with_dca).replace("%", "").strip())
		except Exception:
			pm_start_pct_with_dca = float(_gui_settings_cache.get("pm_start_pct_with_dca", 2.5))
		if pm_start_pct_with_dca < 0.0:
			pm_start_pct_with_dca = 0.0

		trailing_gap_pct = data.get("trailing_gap_pct", _gui_settings_cache.get("trailing_gap_pct", 0.5))
		try:
			trailing_gap_pct = float(str(trailing_gap_pct).replace("%", "").strip())
		except Exception:
			trailing_gap_pct = float(_gui_settings_cache.get("trailing_gap_pct", 0.5))
		if trailing_gap_pct < 0.0:
			trailing_gap_pct = 0.0


		capital = data.get("capital", _gui_settings_cache.get("capital", 100000.0))
		try:
			capital = float(capital)
		except Exception:
			capital = 100000.0
		if capital < 0.0:
			capital = 0.0

		tms_url = data.get("tms_url", _gui_settings_cache.get("tms_url", "https://tms58.nepsetms.com.np/"))

		_gui_settings_cache["mtime"] = mtime
		_gui_settings_cache["coins"] = coins
		_gui_settings_cache["main_neural_dir"] = main_neural_dir
		_gui_settings_cache["trade_start_level"] = trade_start_level
		_gui_settings_cache["start_allocation_pct"] = start_allocation_pct
		_gui_settings_cache["capital"] = capital
		_gui_settings_cache["tms_url"] = tms_url
		_gui_settings_cache["dca_multiplier"] = dca_multiplier
		_gui_settings_cache["dca_levels"] = dca_levels
		_gui_settings_cache["max_dca_buys_per_24h"] = max_dca_buys_per_24h

		_gui_settings_cache["pm_start_pct_no_dca"] = pm_start_pct_no_dca
		_gui_settings_cache["pm_start_pct_with_dca"] = pm_start_pct_with_dca
		_gui_settings_cache["trailing_gap_pct"] = trailing_gap_pct


		return {
			"mtime": mtime,
			"coins": list(coins),
			"main_neural_dir": main_neural_dir,
			"trade_start_level": trade_start_level,
			"start_allocation_pct": start_allocation_pct,
			"capital": capital,
			"tms_url": tms_url,
			"dca_multiplier": dca_multiplier,
			"dca_levels": list(dca_levels),
			"max_dca_buys_per_24h": max_dca_buys_per_24h,

			"pm_start_pct_no_dca": pm_start_pct_no_dca,
			"pm_start_pct_with_dca": pm_start_pct_with_dca,
			"trailing_gap_pct": trailing_gap_pct,
		}




	except Exception:
		return dict(_gui_settings_cache)


def _build_base_paths(main_dir_in: str, coins_in: list) -> dict:
	"""
	Safety rule:
	- BTC uses main_dir directly
	- other coins use <main_dir>/<SYM> ONLY if that folder exists
	  (no fallback to BTC folder — avoids corrupting BTC data)
	"""
	out = {"BTC": main_dir_in}
	try:
		for sym in coins_in:
			sym = str(sym).strip().upper()
			if not sym:
				continue
			if sym == "BTC":
				out["BTC"] = main_dir_in
				continue
			sub = os.path.join(main_dir_in, sym)
			if os.path.isdir(sub):
				out[sym] = sub
	except Exception:
		pass
	return out


# Live globals (will be refreshed inside manage_trades())
crypto_symbols = ['NABIL', 'NTC', 'NICA', 'NLIC', 'SBL']

# Default main_dir behavior if settings are missing
main_dir = os.getcwd()
base_paths = {}
TRADE_START_LEVEL = 3
START_ALLOC_PCT = 0.10
CAPITAL_NPR = 100000.0
TMS_URL = "https://tms58.nepsetms.com.np/"
DCA_MULTIPLIER = 2.0
DCA_LEVELS = [-2.5, -5.0, -10.0, -20.0]
MAX_DCA_BUYS_PER_24H = 1

# Trailing PM hot-reload globals (defaults match previous hardcoded behavior)
TRAILING_GAP_PCT = 0.5
PM_START_PCT_NO_DCA = 5.0
PM_START_PCT_WITH_DCA = 2.5



_last_settings_mtime = None




def _refresh_paths_and_symbols():
	"""
	Hot-reload GUI settings while trader is running.
	Updates globals: crypto_symbols, main_dir, base_paths,
	                TRADE_START_LEVEL, START_ALLOC_PCT, CAPITAL_NPR, TMS_URL,
	                DCA_MULTIPLIER, DCA_LEVELS, MAX_DCA_BUYS_PER_24H,
	                TRAILING_GAP_PCT, PM_START_PCT_NO_DCA, PM_START_PCT_WITH_DCA
	"""
	global crypto_symbols, main_dir, base_paths
	global TRADE_START_LEVEL, START_ALLOC_PCT, CAPITAL_NPR, TMS_URL
	global DCA_MULTIPLIER, DCA_LEVELS, MAX_DCA_BUYS_PER_24H
	global TRAILING_GAP_PCT, PM_START_PCT_NO_DCA, PM_START_PCT_WITH_DCA
	global _last_settings_mtime


	s = _load_gui_settings()
	mtime = s.get("mtime", None)

	# If settings file doesn't exist, keep current defaults
	if mtime is None:
		return

	if _last_settings_mtime == mtime:
		return

	_last_settings_mtime = mtime

	coins = s.get("stocks") or s.get("coins") or list(crypto_symbols)
	mndir = s.get("main_neural_dir") or main_dir
	CAPITAL_NPR = float(s.get("capital", CAPITAL_NPR) or CAPITAL_NPR)
	TMS_URL = s.get("tms_url", TMS_URL) or TMS_URL
	TRADE_START_LEVEL = max(1, min(int(s.get("trade_start_level", TRADE_START_LEVEL) or TRADE_START_LEVEL), 7))
	START_ALLOC_PCT = float(s.get("start_allocation_pct", START_ALLOC_PCT) or START_ALLOC_PCT)
	if START_ALLOC_PCT < 0.0:
		START_ALLOC_PCT = 0.0

	DCA_MULTIPLIER = float(s.get("dca_multiplier", DCA_MULTIPLIER) or DCA_MULTIPLIER)
	if DCA_MULTIPLIER < 0.0:
		DCA_MULTIPLIER = 0.0

	DCA_LEVELS = list(s.get("dca_levels", DCA_LEVELS) or DCA_LEVELS)

	try:
		MAX_DCA_BUYS_PER_24H = int(float(s.get("max_dca_buys_per_24h", MAX_DCA_BUYS_PER_24H) or MAX_DCA_BUYS_PER_24H))
	except Exception:
		MAX_DCA_BUYS_PER_24H = int(MAX_DCA_BUYS_PER_24H)
	if MAX_DCA_BUYS_PER_24H < 0:
		MAX_DCA_BUYS_PER_24H = 0


	# Trailing PM hot-reload values
	TRAILING_GAP_PCT = float(s.get("trailing_gap_pct", TRAILING_GAP_PCT) or TRAILING_GAP_PCT)
	if TRAILING_GAP_PCT < 0.0:
		TRAILING_GAP_PCT = 0.0

	PM_START_PCT_NO_DCA = float(s.get("pm_start_pct_no_dca", PM_START_PCT_NO_DCA) or PM_START_PCT_NO_DCA)
	if PM_START_PCT_NO_DCA < 0.0:
		PM_START_PCT_NO_DCA = 0.0

	PM_START_PCT_WITH_DCA = float(s.get("pm_start_pct_with_dca", PM_START_PCT_WITH_DCA) or PM_START_PCT_WITH_DCA)
	if PM_START_PCT_WITH_DCA < 0.0:
		PM_START_PCT_WITH_DCA = 0.0


	# Keep it safe if folder isn't real on this machine
	if not os.path.isdir(mndir):
		mndir = os.getcwd()

	crypto_symbols = list(coins)
	main_dir = mndir
	base_paths = _build_base_paths(main_dir, crypto_symbols)






# =============================================================================
# SignalTracker — NEPSE Edition (replaces Robinhood CryptoAPITrading)
# =============================================================================
# Reads signals from pt_thinker.py, tracks portfolio via manual trade log,
# and writes status JSON for pt_hub.py.  No orders are placed automatically.
# =============================================================================

class SignalTracker:
    """
    Signal-only trading tracker for NEPSE.

    - Reads long_dca_signal.txt / short_dca_signal.txt from thinker
    - Suggests buy quantities in whole lots (NEPSE minimum 1 share)
    - Records manual trades via record_manual_trade()
    - Writes trader_status.json so pt_hub.py can display positions + signals
    """

    def __init__(self):
        self.path_map = dict(base_paths)

        # Per-symbol signal + position state
        self.signal_state: Dict[str, Dict] = {}
        self.dca_levels_triggered: Dict[str, list] = {}
        self.dca_levels = list(DCA_LEVELS)
        self.max_dca_buys_per_24h = int(MAX_DCA_BUYS_PER_24H)
        self.dca_window_seconds = 24 * 60 * 60
        self._dca_buy_ts: Dict[str, list] = {}

        self.trailing_gap_pct = float(TRAILING_GAP_PCT)
        self.pm_start_pct_no_dca = float(PM_START_PCT_NO_DCA)
        self.pm_start_pct_with_dca = float(PM_START_PCT_WITH_DCA)

        # Persistent portfolio ledger
        self._pnl_ledger = self._load_pnl_ledger()

        # Cache last good account snapshot
        self._last_good_snapshot: Dict = {}

    # ------------------------------------------------------------------
    # File I/O helpers
    # ------------------------------------------------------------------

    def _atomic_write_json(self, path: str, data: dict) -> None:
        try:
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            pass

    def _append_jsonl(self, path: str, obj: dict) -> None:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj) + "\n")
        except Exception:
            pass

    def _write_trader_status(self, status: dict) -> None:
        self._atomic_write_json(TRADER_STATUS_PATH, status)

    def _load_pnl_ledger(self) -> dict:
        try:
            if os.path.isfile(PNL_LEDGER_PATH):
                with open(PNL_LEDGER_PATH, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            pass
        return {}

    def _save_pnl_ledger(self) -> None:
        self._atomic_write_json(PNL_LEDGER_PATH, self._pnl_ledger)

    # ------------------------------------------------------------------
    # Signal reading
    # ------------------------------------------------------------------

    def read_signal(self, symbol: str) -> dict:
        """
        Read the current thinker signals for *symbol*.

        Returns:
            {
                "symbol": str,
                "long_signal": int (0-7),
                "short_signal": int (0-7),
                "pm": float,
                "side": "BUY" | "SELL" | "HOLD",
            }
        """
        sym = symbol.strip().upper()
        folder = self._symbol_folder(sym)
        result = {"symbol": sym, "long_signal": 0, "short_signal": 0, "pm": 0.0, "side": "HOLD"}

        try:
            long_path = os.path.join(folder, "long_dca_signal.txt")
            if os.path.isfile(long_path):
                with open(long_path, "r", encoding="utf-8") as f:
                    result["long_signal"] = int(float(f.read().strip() or "0"))
        except Exception:
            pass

        try:
            short_path = os.path.join(folder, "short_dca_signal.txt")
            if os.path.isfile(short_path):
                with open(short_path, "r", encoding="utf-8") as f:
                    result["short_signal"] = int(float(f.read().strip() or "0"))
        except Exception:
            pass

        try:
            pm_path = os.path.join(folder, "futures_long_profit_margin.txt")
            if os.path.isfile(pm_path):
                with open(pm_path, "r", encoding="utf-8") as f:
                    result["pm"] = float(f.read().strip() or "0")
        except Exception:
            pass

        # Determine side
        if result["long_signal"] >= TRADE_START_LEVEL:
            result["side"] = "BUY"
        elif result["short_signal"] >= TRADE_START_LEVEL:
            result["side"] = "SELL"
        else:
            result["side"] = "HOLD"

        return result

    # ------------------------------------------------------------------
    # Quantity calculation (NEPSE whole-lot sizing)
    # ------------------------------------------------------------------

    def get_suggested_qty(self, symbol: str, signal_level: int, capital: float, price: float) -> int:
        """
        Return suggested buy quantity in whole shares for NEPSE.

        Uses capital * start_allocation_pct * (2 ^ DCA_step) / price,
        rounded down to nearest integer (minimum 1 if positive capital).
        """
        if price <= 0 or capital <= 0:
            return 0
        try:
            alloc = capital * START_ALLOC_PCT
            qty = int(alloc / price)
            return max(0, qty)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Manual trade recording
    # ------------------------------------------------------------------

    def record_manual_trade(
        self,
        symbol: str,
        side: str,       # "BUY" or "SELL"
        qty: int,
        price: float,
        note: str = "",
    ) -> dict:
        """
        Record a trade that the user placed manually on TMS.

        Updates pnl_ledger.json and appends to trade_history.jsonl.
        Returns the trade record dict.
        """
        sym = symbol.strip().upper()
        now_ts = time.time()
        now_str = datetime.datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d %H:%M:%S")
        trade_id = str(uuid.uuid4())

        record = {
            "id": trade_id,
            "timestamp": now_ts,
            "datetime": now_str,
            "symbol": sym,
            "side": side.upper(),
            "qty": int(qty),
            "price": float(price),
            "total_npr": float(qty) * float(price),
            "note": note,
        }

        # Append to trade history
        self._append_jsonl(TRADE_HISTORY_PATH, record)

        # Update ledger
        if sym not in self._pnl_ledger:
            self._pnl_ledger[sym] = {
                "symbol": sym,
                "qty": 0,
                "avg_price": 0.0,
                "total_invested": 0.0,
                "realized_pnl": 0.0,
            }

        ledger_entry = self._pnl_ledger[sym]

        if side.upper() == "BUY":
            old_qty = ledger_entry["qty"]
            old_total = ledger_entry["avg_price"] * old_qty
            new_qty = old_qty + int(qty)
            new_total = old_total + float(qty) * float(price)
            ledger_entry["qty"] = new_qty
            ledger_entry["avg_price"] = (new_total / new_qty) if new_qty > 0 else 0.0
            ledger_entry["total_invested"] += float(qty) * float(price)

        elif side.upper() == "SELL":
            sell_qty = min(int(qty), ledger_entry["qty"])
            realized = sell_qty * (float(price) - ledger_entry["avg_price"])
            ledger_entry["realized_pnl"] += realized
            ledger_entry["qty"] -= sell_qty
            if ledger_entry["qty"] <= 0:
                ledger_entry["qty"] = 0
                ledger_entry["avg_price"] = 0.0

        self._save_pnl_ledger()
        return record

    # ------------------------------------------------------------------
    # TMS browser opener
    # ------------------------------------------------------------------

    @staticmethod
    def open_tms() -> None:
        """Open the NASA Securities TMS URL in the default browser."""
        try:
            url = TMS_URL
            webbrowser.open(url)
            print(f"[SignalTracker] Opened TMS: {url}")
        except Exception as e:
            print(f"[SignalTracker] Failed to open TMS: {e}")

    # ------------------------------------------------------------------
    # Portfolio helpers
    # ------------------------------------------------------------------

    def _symbol_folder(self, sym: str) -> str:
        """Return the folder path for this symbol's signal files."""
        sym = sym.upper()
        m = self.path_map.get(sym)
        if m and os.path.isdir(m):
            return m
        # Fallback: subdir of main_dir
        sub = os.path.join(main_dir, sym)
        if os.path.isdir(sub):
            return sub
        return main_dir

    def _get_portfolio_summary(self) -> dict:
        """Compute portfolio summary from pnl_ledger + live prices."""
        positions = {}
        total_invested = 0.0
        total_current = 0.0
        total_realized = 0.0

        for sym, entry in self._pnl_ledger.items():
            qty = entry.get("qty", 0)
            avg_price = entry.get("avg_price", 0.0)
            realized = entry.get("realized_pnl", 0.0)
            total_realized += realized

            if qty <= 0:
                continue

            try:
                current_price = _nepse_instance.get_current_price(sym)
            except Exception:
                current_price = avg_price

            market_value = qty * current_price
            cost_value = qty * avg_price
            unrealized = market_value - cost_value

            total_invested += cost_value
            total_current += market_value

            positions[sym] = {
                "symbol": sym,
                "qty": qty,
                "avg_price": avg_price,
                "current_price": current_price,
                "market_value_npr": market_value,
                "unrealized_pnl_npr": unrealized,
                "unrealized_pnl_pct": ((unrealized / cost_value) * 100) if cost_value > 0 else 0.0,
                "realized_pnl_npr": realized,
            }

        return {
            "positions": positions,
            "total_invested_npr": total_invested,
            "total_current_value_npr": total_current,
            "total_unrealized_pnl_npr": total_current - total_invested,
            "total_realized_pnl_npr": total_realized,
            "capital_npr": CAPITAL_NPR,
        }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def manage_trades(self):
        """
        One iteration of the signal tracker loop.

        - Hot-reloads settings
        - Reads current signals for all watched stocks
        - Writes trader_status.json for the hub
        - Prints summary to console
        """
        _refresh_paths_and_symbols()
        self.path_map = dict(base_paths)

        # Reload DCA / PM settings
        self.dca_levels = list(DCA_LEVELS)
        self.max_dca_buys_per_24h = int(MAX_DCA_BUYS_PER_24H)
        self.trailing_gap_pct = float(TRAILING_GAP_PCT)
        self.pm_start_pct_no_dca = float(PM_START_PCT_NO_DCA)
        self.pm_start_pct_with_dca = float(PM_START_PCT_WITH_DCA)
        self._pnl_ledger = self._load_pnl_ledger()

        signals = {}
        for sym in crypto_symbols:
            try:
                sig = self.read_signal(sym)
                # Enrich with current price + suggested qty
                try:
                    price = _nepse_instance.get_current_price(sym)
                except Exception:
                    price = 0.0
                sig["current_price"] = price
                sig["suggested_qty"] = self.get_suggested_qty(
                    sym, sig["long_signal"], CAPITAL_NPR, price
                )
                signals[sym] = sig
            except Exception:
                pass

        portfolio = self._get_portfolio_summary()

        os.system("cls" if os.name == "nt" else "clear")
        print("\n=== PowerTrader NEPSE — Signal Tracker ===")
        print(f"Market open: {_NEPSEDataClass.is_market_open()}")
        print(f"Capital: NPR {CAPITAL_NPR:,.2f}")
        print(f"\n{'Symbol':<8} {'Price':>8} {'Long':>5} {'Short':>6} {'Action':<6} {'Qty':>5}")
        print("-" * 50)
        for sym, s in signals.items():
            print(
                f"{sym:<8} {s['current_price']:>8.2f} {s['long_signal']:>5} "
                f"{s['short_signal']:>6} {s['side']:<6} {s['suggested_qty']:>5}"
            )

        # Write hub status
        try:
            status = {
                "timestamp": time.time(),
                "market_open": _NEPSEDataClass.is_market_open(),
                "capital_npr": CAPITAL_NPR,
                "tms_url": TMS_URL,
                "signals": signals,
                "portfolio": portfolio,
                "account": {
                    "total_account_value": portfolio["total_current_value_npr"],
                    "capital_npr": CAPITAL_NPR,
                    "invested_npr": portfolio["total_invested_npr"],
                    "unrealized_pnl_npr": portfolio["total_unrealized_pnl_npr"],
                    "realized_pnl_npr": portfolio["total_realized_pnl_npr"],
                },
                "positions": portfolio["positions"],
            }
            self._append_jsonl(
                ACCOUNT_VALUE_HISTORY_PATH,
                {
                    "ts": status["timestamp"],
                    "total_account_value": portfolio["total_current_value_npr"],
                },
            )
            self._write_trader_status(status)
        except Exception:
            pass

    def run(self):
        while True:
            try:
                self.manage_trades()
                time.sleep(30.0)  # NEPSE: 30s refresh (not 0.5s crypto)
            except Exception as e:
                print(traceback.format_exc())


if __name__ == "__main__":
    tracker = SignalTracker()
    tracker.run()
