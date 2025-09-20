# src/engine.py
import os, json, time, math, tempfile
from collections import deque, defaultdict
from datetime import datetime

class GridEngine:
    """
    OKX Grid Engine (一次性掛滿 + 可選初始倉位 + 首次成交忽略補單)
    - 初始化：現價以下掛買單、現價以上掛賣單（一次性掛滿）
    - 可選：啟動時市價買入一筆，數量=所有賣單數量之和（對沖上方賣單）
    - 首次成交忽略補單（僅在啟用初始倉位時）
    - 後續成交規則：
        * 買單成交 -> 在該買單上方一格掛賣單
        * 賣單成交 -> 在該賣單下方一格掛買單
    - 保留：價格帶保護、部分成交入賬、原子寫狀態、命令通道
    """

    def __init__(
        self,
        okx,                  # ccxt okx 實例
        symbol: str,
        mkt: dict,           # okx.market(symbol)
        entry_price: float,
        contract_size: float,
        levels: list[float],              # 網格價位列表（已對齊精度）
        grid_qty_by_level: dict[float,float],  # 每價位合約數量
        place_limit,         # 函數: place_limit(side, price, qty) -> order dict
        snap_price,          # 函數: snap_price(price) -> price with precision
        state_path: str = "grid_state.json",
        commands_path: str = "grid_commands.jsonl",
        fee_rate: float = 0.0005,
        sleep_sec: float = 0.5,
        loop_sleep: float = 2.0,
        band_ttl: float = 8.0,
        init_position: bool = False,      # <--- 新增：是否啟用初始倉位
    ):
        self.okx = okx
        self.symbol = symbol
        self.mkt = mkt
        self.entry_price = float(entry_price)
        self.contract_size = float(contract_size)
        self.levels = sorted(set(float(self.p_prec(p)) for p in levels))
        self.GRID_QTY_BY_LEVEL = {float(self.p_prec(k)): float(v) for k, v in grid_qty_by_level.items()}
        self.place_limit = place_limit
        self.snap_price = snap_price

        self.STATE_PATH = state_path
        self.COMMANDS_PATH = commands_path
        self.fee_rate = float(fee_rate)
        self.SLEEP_SEC = float(sleep_sec)
        self.LOOP_SLEEP = float(loop_sleep)

        # 參數：價格帶快取
        self._band_cache = None   # (max_buy, min_sell)
        self._band_ts = 0.0
        self._band_ttl = float(band_ttl)

        # 運行態
        self.open_orders: dict[float, str] = {}   # price -> order_id
        self.order_meta: dict[str, dict] = {}     # oid -> {price, side, last_filled}
        self.trades_log = deque(maxlen=5000)
        self.inventory = deque()  # FIFO lots: {'contracts', 'price'}
        self.realized_pnl = 0.0
        self.fills_at = defaultdict(lambda: {'buy': 0, 'sell': 0})
        self.equity_series = deque(maxlen=5000)

        # 一次性掛滿 初始化控制
        self._initialized_full = False
        self._init_position_enabled = bool(init_position)
        # 啟用初始倉位時，首次成交要忽略補單；未啟用則不忽略
        self._first_fill_ignore = bool(init_position)

    # ---------- 精度助手 ----------
    def p_prec(self, price: float) -> float:
        return float(self.okx.price_to_precision(self.symbol, price))

    def q_prec(self, qty: float) -> float:
        return float(self.okx.amount_to_precision(self.symbol, qty))

    # ---------- 鄰格 ----------
    def neighbor_above(self, p: float):
        hs = [x for x in self.levels if x > p]
        return hs[0] if hs else None

    def neighbor_below(self, p: float):
        ls = [x for x in self.levels if x < p]
        return ls[-1] if ls else None

    # ---------- 原子寫 JSON ----------
    def _atomic_write_json(self, path: str, data: dict):
        dir_ = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=dir_)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            try:
                if os.path.exists(tmp): os.remove(tmp)
            except Exception:
                pass

    # ---------- 當前價格 ----------
    def current_mark_or_mid(self) -> float:
        try:
            tk = self.okx.fetch_ticker(self.symbol)
            try:
                mark = float(tk['info'].get('markPx'))
                if mark:
                    return self.p_prec(mark)
            except Exception:
                pass
            ob = self.okx.fetch_order_book(self.symbol, limit=1)
            if ob.get('bids') and ob.get('asks'):
                mid = (ob['bids'][0][0] + ob['asks'][0][0]) / 2.0
                return self.p_prec(mid)
            return self.p_prec(float(tk.get('last') or self.entry_price))
        except Exception:
            return self.entry_price

    # ---------- 價格帶（帶快取） ----------
    def fetch_price_band_cached(self, fallback_price: float):
        now = time.time()
        if self._band_cache and (now - self._band_ts) < self._band_ttl:
            return self._band_cache
        try:
            inst_id = self.mkt['id']
            res = self.okx.publicGetPublicPriceLimit({'instId': inst_id})
            data = res.get('data', [])
            if not data:
                raise RuntimeError("empty price limit data")
            row = data[0]
            max_buy = self.p_prec(float(row['buyLmt']))
            min_sell = self.p_prec(float(row['sellLmt']))
            self._band_cache = (max_buy, min_sell)
        except Exception:
            px = self.p_prec(fallback_price)
            self._band_cache = (self.p_prec(px * 1.02), self.p_prec(px * 0.98))
        finally:
            self._band_ts = now
        return self._band_cache

    # ---------- 下單 / 取消 ----------
    def safe_place(self, side: str, price: float, qty: float):
        price = self.p_prec(price)
        qty = self.q_prec(qty)
        if price in self.open_orders:
            return None
        max_buy_band, min_sell_band = self.fetch_price_band_cached(self.current_mark_or_mid())
        if side == 'buy' and price > max_buy_band:
            print(f"! skip BUY {price}: > maxBuy {max_buy_band}"); return None
        if side == 'sell' and price < min_sell_band:
            print(f"! skip SELL {price}: < minSell {min_sell_band}"); return None
        try:
            o = self.place_limit(side, price, qty)
            self.open_orders[price] = o['id']
            self.order_meta[o['id']] = {'price': price, 'side': side, 'last_filled': 0.0}
            print(f"+ {side}@{price} id={o['id']}")
            time.sleep(self.SLEEP_SEC)
            return o
        except Exception as e:
            print(f"! place {side}@{price} err: {e}")
            time.sleep(self.SLEEP_SEC)
            return None

    def safe_cancel_by_price(self, price: float):
        p = self.p_prec(float(price))
        oid = self.open_orders.pop(p, None)
        if not oid:
            return False
        try:
            self.okx.cancel_order(oid, self.symbol)
        except Exception as e:
            print(f"cancel_order({oid}) err:", e)
        self.order_meta.pop(oid, None)
        print(f"- canceled order at {p}")
        return True

    def cancel_all_open_orders(self):
        for p, oid in list(self.open_orders.items()):
            try:
                self.okx.cancel_order(oid, self.symbol)
            except Exception as e:
                print(f"cancel_order({oid}) err:", e)
            self.order_meta.pop(oid, None)
            self.open_orders.pop(p, None)
        print("- canceled ALL open orders")

    # ---------- 市價開倉（初始倉位） ----------
    def _place_market(self, side: str, qty_contracts: float):
        """簡單市價單，用於初始倉位；需要時可擴展參數（如 reduceOnly、postOnly 不適用市價）。"""
        try:
            params = {'tdMode': 'cross'}
            o = self.okx.create_order(self.symbol, 'market', side, self.q_prec(qty_contracts), None, params)
            print(f"+ market {side} {qty_contracts}c id={o.get('id')}")
            return o
        except Exception as e:
            print(f"! market {side} err: {e}")
            return None

    # ---------- 成交記帳 ----------
    def on_fill(self, side: str, price: float, contracts: float):
        ts = datetime.utcnow().isoformat() + "Z"
        self.trades_log.append({'ts': ts, 'side': side, 'price': price, 'contracts': contracts})
        self.fills_at[price][side] += 1

        if side == 'buy':
            self.inventory.append({'contracts': contracts, 'price': price})
        else:  # sell
            to_sell = contracts
            while to_sell > 1e-12 and self.inventory:
                lot = self.inventory[0]
                use = min(to_sell, lot['contracts'])
                pnl = (price - lot['price']) * (use * self.contract_size)
                fees = self.fee_rate * price * (use * self.contract_size) \
                     + self.fee_rate * lot['price'] * (use * self.contract_size)
                self.realized_pnl += (pnl - fees)
                lot['contracts'] -= use
                to_sell -= use
                if lot['contracts'] <= 1e-12:
                    self.inventory.popleft()

    # ---------- 成交後補單（符合你描述的規則） ----------
    def handle_post_close(self, side: str, price: float, filled_contracts: float):
        print(f"* closed {side}@{price} ({filled_contracts}c)")
        # 啟用初始倉位時，第一次成交忽略補單
        if self._first_fill_ignore:
            self._first_fill_ignore = False
            print("* first fill ignored (init_position enabled)")
            return

        qty = self.GRID_QTY_BY_LEVEL.get(price, 0.0)
        if qty <= 0:
            return

        if side == 'buy':
            # 買單成交 -> 在上方鄰居掛賣單
            up = self.neighbor_above(price)
            if up is not None:
                up_qty = self.GRID_QTY_BY_LEVEL.get(up, 0.0)
                if up_qty > 0 and up not in self.open_orders:
                    self.safe_place('sell', up, up_qty)
        else:  # side == 'sell'
            # 賣單成交 -> 在下方鄰居掛買單
            dn = self.neighbor_below(price)
            if dn is not None:
                dn_qty = self.GRID_QTY_BY_LEVEL.get(dn, 0.0)
                if dn_qty > 0 and dn not in self.open_orders:
                    self.safe_place('buy', dn, dn_qty)

    # ---------- 命令處理（保留） ----------
    def process_commands(self):
        try:
            if not os.path.exists(self.COMMANDS_PATH):
                return
            with open(self.COMMANDS_PATH, "r") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            open(self.COMMANDS_PATH, "w").close()
            for ln in lines:
                try:
                    cmd = json.loads(ln)
                except Exception:
                    continue
                op = cmd.get("op")
                if op == "cancel_all":
                    self.cancel_all_open_orders()

                elif op == "cancel_by_price":
                    p = self.p_prec(float(cmd["price"])); self.safe_cancel_by_price(p)

                elif op == "place_limit":
                    side = cmd["side"]; price = self.p_prec(float(cmd["price"]))
                    cts = float(cmd["contracts"]); ro = bool(cmd.get("reduceOnly", (side == "sell")))
                    params = {'tdMode': 'cross'}
                    if side == 'sell' and ro:
                        params['reduceOnly'] = True
                    try:
                        if price in self.open_orders:
                            print(f"! skip place_limit: already have order at {price}"); continue
                        o = self.okx.create_order(self.symbol, 'limit', side, cts, price, params)
                        self.open_orders[price] = o['id']; self.order_meta[o['id']] = {'price': price, 'side': side, 'last_filled': 0.0}
                        print(f"[cmd] + {side}@{price} id={o['id']}")
                    except Exception as e:
                        print(f"[cmd] place_limit error: {e}")

                elif op in ("hold_level", "cancel_and_hold"):
                    # 傳統掛滿版可選保留此操作：單層暫停不交易
                    p = self.p_prec(float(cmd["price"]))
                    self.safe_cancel_by_price(p)
                    print(f"[cmd] {op} {p} (traditional mode: level is canceled/held externally)")

                elif op == "restore_level":
                    p = self.p_prec(float(cmd["price"]))
                    if p not in self.open_orders:
                        qty = self.GRID_QTY_BY_LEVEL.get(p, 0.0)
                        if qty > 0:
                            side = 'buy' if p < self.current_mark_or_mid() else 'sell'
                            o = self.safe_place(side, p, qty)
                            if o is None:
                                print(f"[cmd] restore_level {p} failed (band/dup)")
                        else:
                            print(f"[cmd] restore_level {p} skipped (qty=0)")
                    else:
                        print(f"[cmd] restore_level {p} skipped (already has order)")
        except Exception as e:
            print("process_commands error:", e)

    # ---------- 快照/估值 ----------
    def snapshot_and_dump(self):
        px = self.current_mark_or_mid()
        unreal = 0.0; total_contracts = 0.0; cost_notional = 0.0
        for lot in self.inventory:
            c = lot['contracts']
            total_contracts += c
            cost_notional += lot['price'] * (c * self.contract_size)
            unreal += (px - lot['price']) * (c * self.contract_size)
        avg_cost = (cost_notional / (total_contracts * self.contract_size)) if total_contracts > 1e-12 else 0.0
        equity = self.realized_pnl + unreal

        self.equity_series.append({
            'ts': datetime.utcnow().isoformat() + 'Z',
            'equity': equity,
            'realized': self.realized_pnl,
            'unrealized': unreal,
        })

        open_list = []
        for p, oid in self.open_orders.items():
            meta = self.order_meta.get(oid, {})
            open_list.append({'price': p, 'id': oid, 'side': meta.get('side', '?')})
        open_list.sort(key=lambda x: x['price'])

        max_buy_band, min_sell_band = self.fetch_price_band_cached(px)

        state = {
            'ts': datetime.utcnow().isoformat() + 'Z',
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'current_price': px,
            'contract_size': self.contract_size,
            'levels': self.levels,
            'grid_qty_by_level': self.GRID_QTY_BY_LEVEL,
            'open_orders': open_list,
            'hold_levels': [],  # 在傳統掛滿模式中不再使用
            'inventory_contracts': total_contracts,
            'inventory_btc': total_contracts * self.contract_size,
            'inventory_avg_cost': avg_cost,
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': unreal,
            'equity': equity,
            'fee_rate': self.fee_rate,
            'price_band': {'max_buy': max_buy_band, 'min_sell': min_sell_band},
            'trades': list(self.trades_log)[-300:],
            'equity_series': list(self.equity_series)[-2000:],
        }
        self._atomic_write_json(self.STATE_PATH, state)

    # ---------- 輪詢成交（支持部分成交） ----------
    def poll_and_handle_fills(self):
        for oid, meta in list(self.order_meta.items()):
            p = meta['price']; side = meta['side']
            try:
                od = self.okx.fetch_order(oid, self.symbol)
            except Exception:
                continue

            filled = float(od.get('filled', 0) or 0.0)
            prev = float(meta.get('last_filled', 0.0))
            inc = max(0.0, filled - prev)

            # 1) 增量部分先入帳
            if inc > 0:
                self.on_fill(side, p, inc)
                self.order_meta[oid]['last_filled'] = filled

            st = (od.get('status') or '').lower()
            # 2) 完結後執行補單邏輯
            if st == 'closed':
                self.open_orders.pop(p, None)
                self.order_meta.pop(oid, None)
                self.handle_post_close(side, p, filled)

    # ---------- 一次性掛滿 + 可選初始倉位 ----------
    def _initialize_full_grid_once(self):
        if self._initialized_full:
            return
        px = self.current_mark_or_mid()

        # 1) 一次性掛滿：px 以下掛買，px 以上掛賣；等於 px 的層跳過
        sell_total_contracts = 0.0
        for p in self.levels:
            qty = self.GRID_QTY_BY_LEVEL.get(p, 0.0)
            if qty <= 0:
                continue
            if p > px:
                # 上方 -> 賣單
                if self.safe_place('sell', p, qty):
                    sell_total_contracts += qty
            elif p < px:
                # 下方 -> 買單
                self.safe_place('buy', p, qty)
            else:
                # p == px：跳過不掛，以避免尷尬位置
                pass

        # 2) 初始倉位：市價買入 = 所有已掛賣單數量之和（可選）
        if self._init_position_enabled and sell_total_contracts > 0:
            self._place_market('buy', sell_total_contracts)

        self._initialized_full = True
        print(f"Initialized full grid. init_position={self._init_position_enabled}, "
              f"entry={px}, sell_total={sell_total_contracts:.6f}c")

    # ---------- 主循環 ----------
    def run_forever(self, heartbeat_every: int = 20):
        loop_i = 0
        print("Grid engine (traditional full placement) started. Ctrl+C to stop.")
        try:
            while True:
                loop_i += 1

                # 初始化一次性掛滿 + 可選初始倉位
                if not self._initialized_full:
                    self._initialize_full_grid_once()

                self.process_commands()
                self.poll_and_handle_fills()
                self.snapshot_and_dump()

                if heartbeat_every and (loop_i % heartbeat_every == 0):
                    buys = sum(1 for pr, oid in self.open_orders.items() if self.order_meta.get(oid,{}).get('side')=='buy')
                    sells = sum(1 for pr, oid in self.open_orders.items() if self.order_meta.get(oid,{}).get('side')=='sell')
                    inv_c = sum(l['contracts'] for l in self.inventory)
                    print(f"[{loop_i}] open: buy={buys}, sell={sells}, inv={inv_c:.4f}c, "
                          f"PnL(real={self.realized_pnl:.2f})")
                time.sleep(self.LOOP_SLEEP)
        except KeyboardInterrupt:
            print("Engine stopped.")
