"""
nepse_data.py — Shared NEPSE data layer for PowerTrader_AI (NEPSE Edition)

Provides:
  - Company list (cached to nepse_companies.json, refreshed every 24h)
  - Current price (10s cache)
  - Historical OHLC candles
  - Market hours check (Mon–Fri, 11:00–15:00 NST = UTC+5:45)

Usage:
    nepse = NEPSEData()
    print(nepse.get_company_list())
    print(nepse.get_current_price("NABIL"))
    print(nepse.get_historical_ohlc("NABIL", days=20))
    print(NEPSEData.is_market_open())

Run directly to verify:
    python nepse_data.py
"""

import json
import os
import time
import datetime
import requests
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://newweb.nepalstock.com/api"
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_COMPANIES_CACHE_PATH = os.path.join(_SCRIPT_DIR, "nepse_companies.json")
_COMPANIES_TTL_SECONDS = 24 * 60 * 60  # refresh every 24 hours

_DEFAULT_TIMEOUT = 15  # HTTP request timeout in seconds

# Nepal Standard Time is UTC+5:45
_NST_OFFSET = datetime.timezone(datetime.timedelta(hours=5, minutes=45))

_MARKET_OPEN_HOUR = 11   # 11:00 NST
_MARKET_CLOSE_HOUR = 15  # 15:00 NST (3 PM)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nst_now() -> datetime.datetime:
    """Return current datetime in Nepal Standard Time."""
    return datetime.datetime.now(_NST_OFFSET)


def _http_get(path: str, params: Optional[Dict] = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
    """GET BASE_URL + path, return parsed JSON.  Raises on HTTP error."""
    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")
    headers = {
        "Accept": "application/json",
        "User-Agent": "PowerTrader-AI-NEPSE/1.0",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# NEPSEData
# ---------------------------------------------------------------------------

class NEPSEData:
    """
    Thin wrapper around Nepal Stock Exchange public API.

    All methods are safe to call repeatedly — they use in-process caches.
    The company list is also persisted to disk (nepse_companies.json).
    """

    # ---- class-level price cache (10 second TTL) ----
    _price_cache: Dict[str, Dict] = {}   # sym → {"price": float, "ts": float}
    _PRICE_TTL = 10  # seconds

    # ---- company list cache ----
    _companies: Optional[List[Dict]] = None
    _companies_loaded_at: float = 0.0

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get_company_list(self) -> List[Dict]:
        """
        Return list of all NEPSE-listed companies.

        Each entry: {"symbol": str, "companyName": str, "sector": str, ...}

        Cached to disk (nepse_companies.json) and refreshed every 24 hours.
        Falls back to disk cache if API is unavailable.
        """
        now = time.time()
        if (
            NEPSEData._companies is not None
            and (now - NEPSEData._companies_loaded_at) < _COMPANIES_TTL_SECONDS
        ):
            return NEPSEData._companies

        # Try to load from disk first (if fresh enough)
        disk_data = self._load_companies_from_disk()
        if disk_data is not None:
            NEPSEData._companies = disk_data
            NEPSEData._companies_loaded_at = now
            return NEPSEData._companies

        # Fetch from network
        try:
            NEPSEData._companies = self._fetch_company_list()
            NEPSEData._companies_loaded_at = now
            self._save_companies_to_disk(NEPSEData._companies)
            return NEPSEData._companies
        except Exception as exc:
            print(f"[NEPSEData] Warning: could not fetch company list: {exc}")
            # Return whatever we have, even if stale
            if NEPSEData._companies:
                return NEPSEData._companies
            # Last resort: return empty list rather than crashing
            return []

    def get_current_price(self, symbol: str) -> float:
        """
        Return last-traded price for *symbol* (e.g. "NABIL").

        Caches result for 10 seconds.  Raises RuntimeError if unavailable.
        """
        sym = self.format_symbol(symbol)
        now = time.time()
        entry = NEPSEData._price_cache.get(sym)
        if entry and (now - entry["ts"]) < self._PRICE_TTL:
            return entry["price"]

        try:
            price = self._fetch_current_price(sym)
        except Exception as exc:
            # Graceful fallback: return last known price if we have one
            if entry:
                print(f"[NEPSEData] Warning: price fetch failed for {sym}, using cached: {exc}")
                return entry["price"]
            raise RuntimeError(f"NEPSEData: cannot get price for {sym}: {exc}") from exc

        NEPSEData._price_cache[sym] = {"price": price, "ts": now}
        return price

    def get_historical_ohlc(self, symbol: str, days: int = 250) -> List[Dict]:
        """
        Return list of OHLC dicts for the last *days* trading days.

        Each entry:
            {
                "date":   "YYYY-MM-DD",
                "open":   float,
                "high":   float,
                "low":    float,
                "close":  float,
                "volume": float,
            }

        Sorted oldest → newest.
        """
        sym = self.format_symbol(symbol)
        try:
            return self._fetch_historical_ohlc(sym, days)
        except Exception as exc:
            raise RuntimeError(f"NEPSEData: cannot get OHLC for {sym}: {exc}") from exc

    @staticmethod
    def is_market_open() -> bool:
        """
        Return True if NEPSE is currently open (Mon–Fri, 11:00–15:00 NST).

        Also tries the live market-status endpoint; falls back to time check.
        """
        try:
            data = _http_get("/market-open", timeout=5)
            # API may return {"isOpen": true/false} or {"data": {"isOpen": ...}}
            if isinstance(data, dict):
                flag = data.get("isOpen") or data.get("data", {}).get("isOpen")
                if flag is not None:
                    return bool(flag)
        except Exception:
            pass  # fall through to time-based check

        nst = _nst_now()
        weekday = nst.weekday()  # Mon=0 … Sun=6
        if weekday >= 5:  # Saturday or Sunday — NEPSE closed (Sun–Thu trading week)
            # Nepal's trading week is Sun–Thu (0=Mon,6=Sun → Sun=6, Thu=3)
            pass
        # Nepal working week: Sunday (6) through Thursday (3)
        nepse_open_days = {6, 0, 1, 2, 3}  # Sun, Mon, Tue, Wed, Thu
        if weekday not in nepse_open_days:
            return False
        t = nst.time()
        return datetime.time(_MARKET_OPEN_HOUR, 0) <= t < datetime.time(_MARKET_CLOSE_HOUR, 0)

    @staticmethod
    def format_symbol(raw: str) -> str:
        """Normalise symbol: 'nabil' → 'NABIL'."""
        return (raw or "").strip().upper()

    # -----------------------------------------------------------------------
    # Private helpers — data fetching
    # -----------------------------------------------------------------------

    def _fetch_company_list(self) -> List[Dict]:
        """Fetch full security list from NEPSE API."""
        data = _http_get("/SecurityList")
        # The response might be wrapped: {"data": [...]} or a bare list
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            raw_list = (
                data.get("data")
                or data.get("securities")
                or data.get("results")
                or []
            )
        else:
            raw_list = []

        companies = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            symbol = (
                item.get("symbol")
                or item.get("Symbol")
                or item.get("ticker")
                or ""
            ).strip().upper()
            if not symbol:
                continue
            companies.append(
                {
                    "symbol": symbol,
                    "companyName": (
                        item.get("companyName")
                        or item.get("name")
                        or item.get("company_name")
                        or symbol
                    ),
                    "sector": (
                        item.get("sector")
                        or item.get("sectorName")
                        or item.get("instrumentType")
                        or ""
                    ),
                    "securityId": item.get("id") or item.get("securityId") or "",
                    "raw": item,  # keep original for debugging
                }
            )
        return companies

    def _fetch_current_price(self, symbol: str) -> float:
        """Fetch last-traded price for a symbol."""
        # Try Company detail endpoint
        try:
            data = _http_get(f"/Company/detail/{symbol}", timeout=8)
            price = self._extract_price_from_detail(data)
            if price is not None:
                return price
        except Exception:
            pass

        # Fallback: market summary / ticker endpoint
        try:
            data = _http_get(f"/marketSummary/detail/{symbol}", timeout=8)
            price = self._extract_price_from_detail(data)
            if price is not None:
                return price
        except Exception:
            pass

        # Fallback: security details
        data = _http_get(f"/security/{symbol}", timeout=8)
        price = self._extract_price_from_detail(data)
        if price is not None:
            return price

        raise RuntimeError(f"Price not found in API response for {symbol}")

    def _extract_price_from_detail(self, data: Any) -> Optional[float]:
        """Try to pull a numeric price out of various response shapes."""
        if not isinstance(data, dict):
            return None

        # Unwrap common envelope shapes
        inner = data.get("data") or data.get("result") or data

        candidates = [
            "lastTradedPrice", "last_traded_price", "ltp",
            "closingPrice", "close", "price",
            "lastPrice", "last_price",
        ]
        if isinstance(inner, dict):
            for key in candidates:
                val = inner.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        pass
        return None

    def _fetch_historical_ohlc(self, symbol: str, days: int) -> List[Dict]:
        """Fetch OHLC history from NEPSE API."""
        # Primary: priceHistory endpoint
        try:
            data = _http_get(f"/Company/priceHistory/{symbol}", timeout=15)
            candles = self._parse_ohlc_response(data)
            if candles:
                # Sort oldest → newest and slice to requested window
                candles.sort(key=lambda x: x["date"])
                return candles[-days:]
        except Exception:
            pass

        # Fallback: floorsheet / chart endpoint
        data = _http_get(f"/security/history/{symbol}", timeout=15)
        candles = self._parse_ohlc_response(data)
        candles.sort(key=lambda x: x["date"])
        return candles[-days:]

    def _parse_ohlc_response(self, data: Any) -> List[Dict]:
        """Parse various OHLC response shapes into a normalised list."""
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            raw_list = (
                data.get("data")
                or data.get("history")
                or data.get("priceHistory")
                or data.get("results")
                or []
            )
        else:
            return []

        candles = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            try:
                date_val = (
                    item.get("date")
                    or item.get("businessDate")
                    or item.get("tradeDate")
                    or item.get("d")
                    or ""
                )
                open_p = float(
                    item.get("openPrice") or item.get("open") or item.get("o") or 0
                )
                high_p = float(
                    item.get("highPrice") or item.get("high") or item.get("h") or 0
                )
                low_p = float(
                    item.get("lowPrice") or item.get("low") or item.get("l") or 0
                )
                close_p = float(
                    item.get("closePrice")
                    or item.get("closingPrice")
                    or item.get("close")
                    or item.get("c")
                    or 0
                )
                volume = float(
                    item.get("totalTradeQuantity")
                    or item.get("volume")
                    or item.get("v")
                    or 0
                )
                if close_p == 0:
                    continue
                candles.append(
                    {
                        "date": str(date_val),
                        "open": open_p,
                        "high": high_p,
                        "low": low_p,
                        "close": close_p,
                        "volume": volume,
                    }
                )
            except (TypeError, ValueError):
                continue
        return candles

    # -----------------------------------------------------------------------
    # Disk cache helpers for company list
    # -----------------------------------------------------------------------

    def _load_companies_from_disk(self) -> Optional[List[Dict]]:
        """Load company list from disk if it exists and is fresh."""
        try:
            if not os.path.isfile(_COMPANIES_CACHE_PATH):
                return None
            mtime = os.path.getmtime(_COMPANIES_CACHE_PATH)
            if (time.time() - mtime) > _COMPANIES_TTL_SECONDS:
                return None
            with open(_COMPANIES_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
        return None

    def _save_companies_to_disk(self, companies: List[Dict]) -> None:
        """Persist company list to disk (atomic write)."""
        try:
            tmp = _COMPANIES_CACHE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(companies, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _COMPANIES_CACHE_PATH)
        except Exception as exc:
            print(f"[NEPSEData] Warning: could not save companies cache: {exc}")


# ---------------------------------------------------------------------------
# Convenience module-level singleton
# ---------------------------------------------------------------------------

_default_instance: Optional[NEPSEData] = None


def get_nepse_data() -> NEPSEData:
    """Return the module-level singleton NEPSEData instance."""
    global _default_instance
    if _default_instance is None:
        _default_instance = NEPSEData()
    return _default_instance


# ---------------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("NEPSEData self-test")
    print("=" * 60)

    nd = NEPSEData()

    # 1. Company list
    print("\n[1] Fetching company list …")
    companies = nd.get_company_list()
    print(f"    Total companies: {len(companies)}")
    if companies:
        print(f"    Sample entry:    {companies[0]}")

    # 2. Market hours
    print("\n[2] Market open check …")
    nst = _nst_now()
    print(f"    Current NST:     {nst.strftime('%A %Y-%m-%d %H:%M:%S %Z')}")
    print(f"    Market is open:  {NEPSEData.is_market_open()}")

    # 3. Sample price + OHLC (use first symbol from company list or fallback)
    test_sym = companies[0]["symbol"] if companies else "NABIL"
    print(f"\n[3] Current price for {test_sym} …")
    try:
        price = nd.get_current_price(test_sym)
        print(f"    Price: {price}")
    except Exception as e:
        print(f"    Error: {e}")

    print(f"\n[4] Historical OHLC for {test_sym} (last 5 days) …")
    try:
        ohlc = nd.get_historical_ohlc(test_sym, days=5)
        for row in ohlc:
            print(f"    {row}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\nSelf-test complete.")
