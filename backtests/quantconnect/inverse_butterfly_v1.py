# region imports
from AlgorithmImports import *
import numpy as np
import math
from collections import deque, defaultdict, Counter
# endregion


class _OptBpInit(BrokerageModelSecurityInitializer):
    def initialize(self, security):
        super().initialize(security)
        if security.type == SecurityType.INDEX_OPTION:
            security.set_buying_power_model(BuyingPowerModel.NULL)


class InverseButterflyV1(QCAlgorithm):
    """
    INVERSE (SHORT) BUTTERFLY 1-2-1 em SPX — estratégia do vídeo alemão (Castle Trader).
    Charter: context/PROJECT_burrito_invertido_backtest.md (família) | brief do João.

    ESTRUTURA (1-2-1, net CRÉDITO, long vega/gamma — "tenda pra baixo"):
        +2 CALL ATM (C)   -1 CALL (C-W)   -1 CALL (C+W)
      (compra 2 ATM, vende 1 acima e 1 abaixo a W pontos). Vale (perda máx) no centro;
      lucro plano (= crédito) nas asas. GANHA se o preço SE MEXE (p/ qualquer lado), PERDE parado.
      W = round5(width_sigma · σ). σ do straddle ATM / IV. (Calls; switch p/ puts é ~idêntico.)

    TRACKING SINTÉTICO (sem ordens): subscreve as pernas, P&L 100% analítico do bid/ask (mid+cons).
    Evita o crash OptionStrategyPositionGroupBuyingPowerModel. Equity do QC fica flat; fonte = dataset.

    RECORD-AND-DERIVE (não executa): grava por trade, em mid E cons:
      - 1º cruzamento de cada TP (% do crédito);
      - MTM com D DTE RESTANTES (grade) -> saída antecipada p/ DTEs longos;
      - snapshot no DIA DO EXPIRY na ABERTURA e em 11/12/13/14/15h ET
        (1DTE -> sair 12:00; Seg-Sex -> sair sexta na abertura);
      - MFE/MAE.
    Hold-to-expiry = baseline (cash-settle analítico). Pós-proc deriva toda política × 3 slippages.
    """

    def initialize(self):
        self.target_dte    = int(self.get_parameter("dte", "30"))
        self.width_sigma   = float(self.get_parameter("width_sigma", "0.15"))   # 0.15σ ≈ ±30pt do vídeo
        self.fixed_width   = self.get_parameter("fixed_width", "")              # se setado, W fixo em pts (override σ)
        self.right_str     = self.get_parameter("right", "call").lower()
        self.entry_weekday = self.get_parameter("entry_weekday", "4")           # 4=sexta; "all"=diário
        self.entry_offset  = self.get_parameter("entry_time", "open")           # open|+30|+60
        # resolução dos dados (default hour = baseline; "minute" p/ spot-check de spread confiável)
        _res = self.get_parameter("data_res", "hour").lower()
        self.data_res = Resolution.MINUTE if _res in ("minute", "min", "1") else Resolution.HOUR
        self.strike_half = int(self.get_parameter("strike_half", "160"))         # ±strikes; estreitar p/ minute

        sd = self.get_parameter("start_date", "2021-01-01").split("-")
        ed = self.get_parameter("end_date",   "2026-06-08").split("-")
        self.run_tag = self.get_parameter("run_tag", f"ibfly_d{self.target_dte}_w{self.width_sigma:g}")
        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        base = 9 * 60 + 31
        off = {"open": 0, "+30": 29, "+60": 59}.get(self.entry_offset, 0)
        self.entry_hour, self.entry_minute = (base + off) // 60, (base + off) % 60

        self.tp_levels   = [0.25, 0.50, 0.75]            # % do crédito
        self.dte_exit_grid = [d for d in (30, 21, 14, 10, 7, 5, 3) if d < self.target_dte]
        self.expiry_snaps = ["open", 11, 12, 13, 14, 15]  # snapshots no DIA do expiry
        self.mark_every_min = 30
        self.right = OptionRight.CALL if self.right_str == "call" else OptionRight.PUT

        self.set_security_initializer(_OptBpInit(self.brokerage_model, SecuritySeeder.NULL))
        index = self.add_index("SPX", self.data_res)
        self.spx = index.symbol
        option = self.add_index_option(self.spx, "SPXW", self.data_res)
        lo = max(0, self.target_dte - 3); hi = self.target_dte + 4
        option.set_filter(lambda u: u.include_weeklys().expiration(lo, hi).strikes(-self.strike_half, self.strike_half))
        self.spxw = option.symbol
        self.vix = self.add_index("VIX", self.data_res).symbol

        self.rows = []; self.skips = []; self.open_trades = []
        self.entered_today = False; self.current_day = None; self.seq = 0
        self.schedule.on(self.date_rules.every_day(self.spx), self.time_rules.at(16, 1), self._settle_due)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.current_day != self.time.date():
            self.current_day = self.time.date(); self.entered_today = False
        # horário = barras esparsas -> marca em TODA barra (não depende do alinhamento :00/:30).
        for tr in self.open_trades:
            if tr["expiry"] >= self.time.date():
                self._mark(tr)
        if self.entered_today:
            return
        if self.entry_weekday != "all" and self.time.weekday() != int(self.entry_weekday):
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return
        chain = slice.option_chains.get(self.spxw)
        if chain is None:
            return
        legs = [c for c in chain]
        if not legs:
            self.entered_today = True; self._skip("cadeia vazia"); return
        self._enter(legs); self.entered_today = True

    def _pick_expiry(self, legs, today):
        exps = sorted({c.expiry.date() for c in legs if c.expiry.date() >= today})
        if self.target_dte == 0:
            same = [e for e in exps if e == today]; return same[0] if same else None
        fut = [e for e in exps if e > today]
        return min(fut, key=lambda e: abs((e - today).days - self.target_dte)) if fut else None

    def _enter(self, legs_all):
        S = self.securities[self.spx].price
        vix = self.securities[self.vix].price
        today = self.time.date()
        expiry = self._pick_expiry(legs_all, today)
        if expiry is None:
            self._skip(f"sem expiry dte{self.target_dte}"); return
        dte_real = max((expiry - today).days, 0)
        legs0 = [c for c in legs_all if c.expiry.date() == expiry and c.right == self.right]
        if not legs0:
            self._skip("sem legs (right) no expiry"); return

        # ATM + sigma (straddle p/ EM; VIX fallback)
        atm = min((c.strike for c in legs0), key=lambda k: abs(k - S))
        catm = next((c for c in legs0 if c.strike == atm), None)
        atm_iv = (catm.implied_volatility if catm and catm.implied_volatility else 0.0) or (vix / 100.0 if vix > 0 else 0.0)
        dte_cal = max(dte_real, 1)
        sigma = S * atm_iv * math.sqrt(dte_cal / 365.0)
        if sigma <= 0:
            self._skip("sigma<=0"); return
        W = float(self.fixed_width) if self.fixed_width not in ("", None) else round(self.width_sigma * sigma / 5.0) * 5.0
        W = max(5.0, W)

        by = {c.strike: c for c in legs0}
        c0, clo, cup = by.get(atm), by.get(atm - W), by.get(atm + W)
        if c0 is None or clo is None or cup is None:
            self._skip(f"falta perna (W={W:g})"); return
        cs = [(c0, 2), (clo, -1), (cup, -1)]   # (contrato, qty)

        def _mid(c):
            b, a = c.bid_price, c.ask_price
            return (b + a) / 2.0 if (b > 0 and a > 0) else (a or b or 0.0)
        # entry cost: cons = long@ask / short@bid (pior). mid = mids.
        cost_cons = 2 * c0.ask_price - clo.bid_price - cup.bid_price
        cost_mid  = 2 * _mid(c0) - _mid(clo) - _mid(cup)
        credit_mid, credit_cons = -cost_mid * 100.0, -cost_cons * 100.0
        if credit_mid <= 0:
            self._skip(f"credito_mid<=0 ({credit_mid:.0f})"); return

        for c, _ in cs:
            try: self.add_index_option_contract(c.symbol, self.data_res)
            except Exception: pass

        self.seq += 1
        tr = {
            "id": self.seq, "open_time": self.time, "expiry": expiry, "dte_real": dte_real,
            "S_entry": S, "vix": vix, "atm_iv": atm_iv, "sigma": sigma, "W": W, "C": atm,
            "Clo": atm - W, "Cup": atm + W, "legs": cs,
            "cost_mid": cost_mid, "cost_cons": cost_cons, "credit_mid": credit_mid, "credit_cons": credit_cons,
            "mfe": 0.0, "mae": 0.0, "closed": False,
            "tp": {l: None for l in self.tp_levels},
            "dte_val": {d: None for d in self.dte_exit_grid},
            "snap": {s: None for s in self.expiry_snaps},
        }
        self.open_trades.append(tr)
        if self.seq <= 3:
            self.debug(f"{self.time} ENTRY#{self.seq} exp={expiry} dte={dte_real} S={S:.0f} C={atm:g} "
                       f"W={W:g}({self.width_sigma:g}σ) credit_mid=${credit_mid:.0f}")

    # ===================== MARCAÇÃO =====================
    def _close_vals(self, tr):
        """(pnl_mid, pnl_cons, spot). cons: vende longs@bid, recompra shorts@ask. None se sem quote."""
        tot_mid = tot_cons = 0.0
        for c, q in tr["legs"]:
            sec = self.securities[c.symbol]; b, a = sec.bid_price, sec.ask_price
            if b <= 0 or a <= 0:
                return None
            tot_mid += q * (b + a) / 2.0
            tot_cons += q * (b if q > 0 else a)   # long fecha no bid, short recompra no ask
        pnl_mid = (tot_mid - tr["cost_mid"]) * 100.0
        pnl_cons = (tot_cons - tr["cost_cons"]) * 100.0
        return pnl_mid, pnl_cons, self.securities[self.spx].price

    def _mark(self, tr):
        if tr.get("closed"):
            return
        v = self._close_vals(tr)
        if v is None:
            return
        pnl_mid, pnl_cons, S = v
        if pnl_mid > tr["mfe"]: tr["mfe"] = pnl_mid
        if pnl_cons < tr["mae"]: tr["mae"] = pnl_cons
        dte_rem = (tr["expiry"] - self.time.date()).days
        cr = tr["credit_mid"]
        for l in self.tp_levels:
            if tr["tp"][l] is None and pnl_mid >= l * cr:
                tr["tp"][l] = (round(pnl_mid, 2), round(pnl_cons, 2), round(S, 2))
        for d in self.dte_exit_grid:
            if tr["dte_val"][d] is None and dte_rem <= d:
                tr["dte_val"][d] = (round(pnl_mid, 2), round(pnl_cons, 2), round(S, 2))
        # snapshots no DIA do expiry — robusto ao alinhamento horário (captura pela HORA, qualquer minuto)
        if self.time.date() == tr["expiry"]:
            snap = (round(pnl_mid, 2), round(pnl_cons, 2), round(S, 2))
            # 'open' = 1ª barra do dia (abertura) -> hora <= 10 (pega 9:30/10:00/10:30)
            if tr["snap"]["open"] is None and self.time.hour <= 10:
                tr["snap"]["open"] = snap
            for hh in (11, 12, 13, 14, 15):
                if tr["snap"][hh] is None and self.time.hour == hh:
                    tr["snap"][hh] = snap

    # ===================== SETTLE =====================
    def _settle_due(self):
        if not self.open_trades:
            return
        S_T = self.securities[self.spx].price
        still = []
        for tr in self.open_trades:
            if tr["expiry"] != self.time.date():
                still.append(tr); continue
            if tr.get("closed"):
                continue
            terminal = sum(q * self._intr(self.right, S_T, k) for (q, k) in
                           [(2, tr["C"]), (-1, tr["Clo"]), (-1, tr["Cup"])])
            self._record(tr, S_T, terminal)
        self.open_trades = still

    @staticmethod
    def _intr(right, S, K):
        return max(0.0, S - K) if right == OptionRight.CALL else max(0.0, K - S)

    def _record(self, tr, S_T, terminal):
        net_mid = (terminal - tr["cost_mid"]) * 100.0
        net_cons = (terminal - tr["cost_cons"]) * 100.0
        row = {
            "id": tr["id"], "open_date": tr["open_time"].strftime("%Y-%m-%d"),
            "open_time": tr["open_time"].strftime("%H:%M"), "expiry_date": tr["expiry"].strftime("%Y-%m-%d"),
            "dte_real": tr["dte_real"], "dow": tr["open_time"].weekday(),
            "vix": round(tr["vix"], 2), "vix_bucket": self._vix_bucket(tr["vix"]),
            "atm_iv": round(tr["atm_iv"], 4), "sigma": round(tr["sigma"], 1), "W": tr["W"],
            "S_entry": round(tr["S_entry"], 2), "S_settle": round(S_T, 2),
            "C": tr["C"], "Clo": tr["Clo"], "Cup": tr["Cup"],
            "credit_mid": round(tr["credit_mid"], 2), "credit_cons": round(tr["credit_cons"], 2),
            "mfe": round(tr["mfe"], 2), "mae": round(tr["mae"], 2), "terminal": round(terminal, 4),
            "hold_net_mid": round(net_mid, 2), "hold_net_cons": round(net_cons, 2),
            "realized_move": round(abs(S_T - tr["S_entry"]), 2),
            "result": "W" if net_cons > 0 else "L",
        }
        for l in self.tp_levels:
            cx = tr["tp"][l]; t = f"tp{int(l*100)}"
            row[f"{t}_m"], row[f"{t}_c"], row[f"{t}_s"] = (cx if cx else ("", "", ""))
        for d in self.dte_exit_grid:
            cx = tr["dte_val"][d]
            row[f"x{d}_m"], row[f"x{d}_c"], row[f"x{d}_s"] = (cx if cx else ("", "", ""))
        for s in self.expiry_snaps:
            cx = tr["snap"][s]; tag = f"e{s}"
            row[f"{tag}_m"], row[f"{tag}_c"], row[f"{tag}_s"] = (cx if cx else ("", "", ""))
        self.rows.append(row)

    # ===================== HELPERS / EXPORT =====================
    @staticmethod
    def _vix_bucket(v):
        if v < 15: return "<15"
        if v < 20: return "15-20"
        if v < 30: return "20-30"
        return "30+"

    def _skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    def _emit_runtime(self):
        rows = self.rows
        if not rows:
            return
        import statistics as _st
        def agg(pls):
            net = sum(pls); wr = 100.0 * sum(1 for x in pls if x > 0) / len(pls); return net, wr
        # hold mid/cons
        for mode in ("mid", "cons"):
            net, wr = agg([r[f"hold_net_{mode}"] for r in rows])
            self.set_runtime_statistic(f"HOLD {mode}", f"${net:,.0f}/{wr:.0f}%")
        # saída por DTE-restante (mid/cons): fallback hold se não atingiu
        for d in self.dte_exit_grid:
            pm = [(float(r[f"x{d}_m"]) if r[f"x{d}_m"] not in ("", None) else r["hold_net_mid"]) for r in rows]
            pc = [(float(r[f"x{d}_c"]) if r[f"x{d}_c"] not in ("", None) else r["hold_net_cons"]) for r in rows]
            nm, wm = agg(pm); nc, wc = agg(pc)
            self.set_runtime_statistic(f"EXIT {d}DTE", f"mid ${nm:,.0f}/{wm:.0f}% | cons ${nc:,.0f}/{wc:.0f}%")
        # saída no dia do expiry (open / 12h) — p/ 1DTE e Seg-Sex
        for s in ("open", 12):
            pm = [(float(r[f"e{s}_m"]) if r[f"e{s}_m"] not in ("", None) else r["hold_net_mid"]) for r in rows]
            nm, wm = agg(pm)
            self.set_runtime_statistic(f"EXIT expiry {s}", f"mid ${nm:,.0f}/{wm:.0f}%")
        # TP (mid)
        for l in self.tp_levels:
            t = f"tp{int(l*100)}"
            pm = [(float(r[f"{t}_m"]) if r[f"{t}_m"] not in ("", None) else r["hold_net_mid"]) for r in rows]
            nm, wm = agg(pm)
            self.set_runtime_statistic(f"TP {int(l*100)}%", f"mid ${nm:,.0f}/{wm:.0f}%")
        rm = _st.mean(r["realized_move"] for r in rows); im = _st.mean(r["sigma"] for r in rows)
        self.set_runtime_statistic("real vs impl", f"real {rm:.0f}p / σ {im:.0f}p / {rm/im:.2f}")
        self.set_runtime_statistic("n / dte / W", f"n={len(rows)} dte={_st.median(r['dte_real'] for r in rows):.0f} W={_st.median(r['W'] for r in rows):.0f}")
        self.set_runtime_statistic("credit med", f"mid ${_st.median(r['credit_mid'] for r in rows):.0f}")

    def on_end_of_algorithm(self):
        cols = (["id", "open_date", "open_time", "expiry_date", "dte_real", "dow", "vix", "vix_bucket",
                 "atm_iv", "sigma", "W", "S_entry", "S_settle", "C", "Clo", "Cup",
                 "credit_mid", "credit_cons", "mfe", "mae", "terminal", "hold_net_mid", "hold_net_cons",
                 "realized_move", "result"]
                + [f"tp{int(l*100)}_{x}" for l in self.tp_levels for x in ("m", "c", "s")]
                + [f"x{d}_{x}" for d in self.dte_exit_grid for x in ("m", "c", "s")]
                + [f"e{s}_{x}" for s in self.expiry_snaps for x in ("m", "c", "s")])
        lines = [",".join(cols)]
        for r in self.rows:
            lines.append(",".join(str(r.get(c, "")) for c in cols))
        try:
            self.object_store.save(f"{self.run_tag}.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou: {e}")
        if len(self.rows) <= 70:
            self.log(f">>>CSV_START {self.run_tag}")
            for ln in lines: self.log(ln)
            self.log(">>>CSV_END")
        self._log_ctrade(cols)
        self._emit_runtime()
        n = len(self.rows); w = sum(1 for r in self.rows if r["result"] == "W")
        net = sum(r["hold_net_cons"] for r in self.rows)
        self.log(f"=== INVERSE BFLY [{self.run_tag}] === n={n} | W={w} ({(w/n*100 if n else 0):.0f}%) "
                 f"| hold cons net=${net:,.0f} | skips={len(self.skips)}")
        reasons = Counter(r for _, r in self.skips)
        if reasons:
            self.log("SKIPS: " + ", ".join(f"{k}={v}" for k, v in list(reasons.items())[:10]))

    def _log_ctrade(self, cols):
        self.log("CTRADEHDR|" + ",".join(cols))
        for r in self.rows:
            self.log("CTRADE|" + ",".join(str(r.get(c, "")) for c in cols))
