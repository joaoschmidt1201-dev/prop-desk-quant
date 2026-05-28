# region imports
from AlgorithmImports import *
import math
# endregion

class IronFly0DTE(QCAlgorithm):
    """
    0DTE IRON FLY (ThetaProfits / "Doc" Severson) = "Open Range Iron Fly" do CZ (estratégia #2).
    Spec/regras: memória project_zerodte_ironfly_playbook. DISTINTA da IC 0DTE (iron_condor_0dte.py).

    SETUP:
      - SPXW 0DTE. Entra 10:00 ET, TODO dia (ESTRATIFICA — entra sempre, grava contexto, NÃO filtra).
      - Shorts put+call no MESMO strike = 1º strike ACIMA do spot às 10:00 (skew: puts caras).
      - Asas (longs) no EXPECTED MOVE do dia (EM = straddle ATM = mid call ATM + mid put ATM),
        arredondado à grade. LP = centro − EM, LC = centro + EM.
      - Combo de risco DEFINIDO = 2 verticais (bull put spread + bear call spread) — evita naked short
        (lição da margem do Batman). Crédito conservador (vende no bid, compra no ask).
      - Contexto gravado p/ estratificar: opening range (9:30–10:00) high/low/width + flag in-range,
        VIX, flag SPX>SMA200 diária (gate macro do desk), expected move, crédito.
      - CLOSE: hold (base, grava cruzamentos) OU executa TP a X% do net credit + stop ao tocar centro±EM.
      - Settle: cash-settle no preço oficial (payoff LIMPO num único S — imune ao artefato do QC).

    PARÂMETROS:
      tp_close_frac: none | 0.10 | 0.20 | 0.30   (executa TP a X% do crédito)
      stop_close:    none | on                   (executa stop ao tocar centro±EM = as asas)
    """

    def initialize(self):
        self.entry_hour   = int(self.get_parameter("entry_hour", "10"))
        self.entry_minute = int(self.get_parameter("entry_minute", "0"))
        self.or_start_h, self.or_start_m = 9, 30           # opening range: 9:30–10:00
        _tp = self.get_parameter("tp_close_frac", "none")
        self.tp_close_frac = None if _tp in ("none", "None", "") else float(_tp)
        self.stop_close   = self.get_parameter("stop_close", "none") not in ("none", "None", "")
        sd = self.get_parameter("start_date", "2022-06-20").split("-")
        ed = self.get_parameter("end_date",   "2026-05-13").split("-")
        self.run_tag = self.get_parameter("run_tag", "IF0DTE")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        index = self.add_index("SPX", Resolution.MINUTE)
        self.spx = index.symbol
        option = self.add_index_option(self.spx, "SPXW", Resolution.MINUTE)
        option.set_filter(lambda u: u.include_weeklys().expiration(0, 1).strikes(-80, 80))
        self.spxw = option.symbol
        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        # gate macro: SPX acima da SMA200 diária. Warm-up p/ ficar ready desde o início.
        self.sma200 = self.sma(self.spx, 200, Resolution.DAILY)
        self.set_warm_up(200, Resolution.DAILY)

        self.mark_every_min = 5
        self.profit_levels = [0.05, 0.10, 0.20, 0.30, 0.50]   # TP como % do net credit (grava cruzamentos)

        self.rows = []
        self.skips = []
        self.open_flies = []
        self.entered_today = False
        self.current_day = None
        self.or_high = None
        self.or_low = None
        self.fly_seq = 0

        self.schedule.on(self.date_rules.every_day(self.spx),
                         self.time_rules.at(16, 1), self._settle_due)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.is_warming_up:
            return
        if self.current_day != self.time.date():
            self.current_day = self.time.date()
            self.entered_today = False
            self.or_high = None
            self.or_low = None

        # acumula o opening range (9:30–10:00)
        S = self.securities[self.spx].price
        if S > 0 and (self.or_start_h, self.or_start_m) <= (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            self.or_high = S if self.or_high is None else max(self.or_high, S)
            self.or_low = S if self.or_low is None else min(self.or_low, S)

        # marcação intraday das flies de hoje
        if self.time.minute % self.mark_every_min == 0:
            for fly in self.open_flies:
                if fly["expiry"] == self.time.date():
                    self._mark_fly(fly)

        if self.entered_today:
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return

        chain = slice.option_chains.get(self.spxw)
        if chain is None:
            return
        contracts = [c for c in chain if c.expiry.date() == self.time.date()]   # 0DTE
        if not contracts:
            self.entered_today = True
            self._skip("sem 0DTE"); return

        self._enter_fly(contracts, self.securities[self.vix].price)
        self.entered_today = True

    # ===================== ENTRADA =====================
    def _enter_fly(self, contracts, vix):
        S = self.securities[self.spx].price
        expiry = self.time.date()
        strikes = sorted({c.strike for c in contracts})
        if not strikes:
            self._skip("sem strikes"); return
        # short = 1º strike ACIMA do spot
        above = [k for k in strikes if k > S]
        if not above:
            self._skip("sem strike acima"); return
        center = above[0]
        by = {(c.right, c.strike): c for c in contracts}
        cp = by.get((OptionRight.PUT, center)); cc = by.get((OptionRight.CALL, center))
        if cp is None or cc is None:
            self._skip("sem ATM put/call"); return

        # expected move = straddle ATM (mid call + mid put no centro)
        def mid(c):
            b, a = c.bid_price, c.ask_price
            return (b + a) / 2 if (b > 0 and a > 0) else (c.last_price or 0)
        em = mid(cp) + mid(cc)
        if em <= 0:
            self._skip("EM<=0"); return
        # asa = EM arredondado à grade de strikes (passo mais comum)
        step = min((strikes[i + 1] - strikes[i] for i in range(len(strikes) - 1)), default=5) or 5
        wing = max(step, round(em / step) * step)
        lp = by.get((OptionRight.PUT, center - wing))
        lc = by.get((OptionRight.CALL, center + wing))
        if lp is None or lc is None:
            self._skip(f"sem asa (wing={wing})"); return

        # crédito conservador: vende shorts no bid, compra longs no ask
        credit = (cp.bid_price + cc.bid_price) - (lp.ask_price + lc.ask_price)
        if credit <= 0:
            self._skip(f"crédito<=0 ({credit:.2f})"); return

        # 2 verticais reconhecidos (risco definido)
        self.buy(OptionStrategies.bull_put_spread(self.spxw, center, center - wing, cp.expiry), 1)
        self.buy(OptionStrategies.bear_call_spread(self.spxw, center, center + wing, cc.expiry), 1)

        in_range = (self.or_low is not None and self.or_high is not None
                    and self.or_low <= S <= self.or_high)
        pos = ((S - self.or_low) / (self.or_high - self.or_low)
               if (self.or_high and self.or_low and self.or_high > self.or_low) else None)
        above_sma = (S > self.sma200.current.value) if self.sma200.is_ready else None

        self.fly_seq += 1
        fly = {
            "id": self.fly_seq, "open_time": self.time, "expiry": expiry, "exp_dt": cp.expiry,
            "S_entry": S, "vix": vix, "center": center, "wing": wing, "lp": center - wing, "lc": center + wing,
            "cp_sym": cp.symbol, "cc_sym": cc.symbol, "lp_sym": lp.symbol, "lc_sym": lc.symbol,
            "credit": credit, "em": em,
            "or_high": self.or_high, "or_low": self.or_low, "in_range": in_range, "or_pos": pos,
            "above_sma200": above_sma,
            "max_value": credit, "cross_stop": None,
            "cross_p": {lvl: None for lvl in self.profit_levels}, "closed": False,
        }
        self.open_flies.append(fly)
        if self.fly_seq <= 3:
            self.debug(f"{self.time} IF#{self.fly_seq} c={center} wing={wing} EM={em:.1f} cr={credit:.2f} "
                       f"OR[{self.or_low}/{self.or_high}] inR={in_range} >sma200={above_sma}")

    # ===================== MARCAÇÃO =====================
    def _mark_fly(self, fly):
        if fly.get("closed"):
            return
        S = self.securities[self.spx].price
        cp_a = self.securities[fly["cp_sym"]].ask_price
        cc_a = self.securities[fly["cc_sym"]].ask_price
        lp_b = self.securities[fly["lp_sym"]].bid_price
        lc_b = self.securities[fly["lc_sym"]].bid_price
        if min(cp_a, cc_a) <= 0:
            return
        buyback = (cp_a + cc_a) - (lp_b + lc_b)         # custo p/ fechar
        if buyback > fly["max_value"]:
            fly["max_value"] = buyback
        cr = fly["credit"]
        # PROFIT X% do crédito: recompra barata (<= (1-X)*crédito)
        for lvl in self.profit_levels:
            if fly["cross_p"][lvl] is None and buyback <= (1.0 - lvl) * cr:
                fly["cross_p"][lvl] = (self.time.strftime("%H:%M"), round(buyback, 2))
        # STOP: spot tocou centro±EM (= as asas lp/lc)
        touched = (S <= fly["lp"]) or (S >= fly["lc"])
        if fly["cross_stop"] is None and touched:
            fly["cross_stop"] = (self.time.strftime("%H:%M"), round(buyback, 2))

        # EXECUÇÃO (runs Doc): TP a X% OU stop ao tocar centro±EM — o que vier 1º
        if self.tp_close_frac is not None and buyback <= (1.0 - self.tp_close_frac) * cr:
            self._close(fly, S, buyback); return
        if self.stop_close and touched:
            self._close(fly, S, buyback); return

    def _close(self, fly, S, buyback):
        self.sell(OptionStrategies.bull_put_spread(self.spxw, fly["center"], fly["lp"], fly["exp_dt"]), 1)
        self.sell(OptionStrategies.bear_call_spread(self.spxw, fly["center"], fly["lc"], fly["exp_dt"]), 1)
        fly["closed"] = True
        self._record(fly, S, fly["credit"] - buyback)   # realiza: crédito − custo de recompra

    # ===================== SETTLE =====================
    def _settle_due(self):
        if not self.open_flies:
            return
        S_T = self.securities[self.spx].price
        still = []
        for fly in self.open_flies:
            if fly["expiry"] != self.time.date():
                still.append(fly); continue
            if fly.get("closed"):
                continue
            put_loss  = min(fly["wing"], max(0.0, fly["center"] - S_T))
            call_loss = min(fly["wing"], max(0.0, S_T - fly["center"]))
            self._record(fly, S_T, fly["credit"] - put_loss - call_loss)
        self.open_flies = still

    def _record(self, fly, S_T, pnl_pts):
        cs = fly["cross_stop"]
        self.rows.append({
            "fly_id": fly["id"], "open_date": fly["open_time"].strftime("%Y-%m-%d"),
            "open_time": fly["open_time"].strftime("%H:%M"), "expiry_date": fly["expiry"].strftime("%Y-%m-%d"),
            "vix": round(fly["vix"], 2), "vix_bucket": self._vix_bucket(fly["vix"]),
            "S_entry": round(fly["S_entry"], 2), "S_settle": round(S_T, 2),
            "center": fly["center"], "wing": fly["wing"], "long_put": fly["lp"], "long_call": fly["lc"],
            "em": round(fly["em"], 2), "credit": round(fly["credit"], 2),
            "or_high": fly["or_high"], "or_low": fly["or_low"],
            "in_range": fly["in_range"], "or_pos": round(fly["or_pos"], 3) if fly["or_pos"] is not None else "",
            "above_sma200": fly["above_sma200"], "max_value": round(fly["max_value"], 2),
            "cross_stop_t": cs[0] if cs else "", "cross_stop_v": cs[1] if cs else "",
            **{f"cross_p{int(l*100)}_t": (fly["cross_p"][l][0] if fly["cross_p"][l] else "") for l in self.profit_levels},
            **{f"cross_p{int(l*100)}_v": (fly["cross_p"][l][1] if fly["cross_p"][l] else "") for l in self.profit_levels},
            "settle_pnl_pts": round(pnl_pts, 2), "settle_net": round(pnl_pts * 100.0, 2),
            "settle_result": "W" if pnl_pts > 0 else "L",
        })

    # ===================== GREEKS / HELPERS =====================
    @staticmethod
    def _vix_bucket(vix):
        if vix < 15:  return "<15"
        if vix < 17:  return "15-17"
        if vix < 22:  return "17-22"
        if vix < 32:  return "22-32"
        return "32+"

    def _skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    # ===================== EXPORT / RUNTIME STATS =====================
    def _emit_runtime_stats(self):
        rows = self.rows
        if not rows:
            return
        from collections import defaultdict

        def pnl(r, mode):
            if mode == "hold":
                return r["settle_net"]
            # TP a X%: se cruzou, realiza crédito − recompra; senão settle
            v = r.get(f"cross_p{int(mode*100)}_v", "") if isinstance(mode, float) else ""
            if v not in ("", None):
                return (r["credit"] - float(v)) * 100.0
            return r["settle_net"]

        for b in ["<15", "15-17", "17-22", "22-32", "32+"]:
            rs = [r for r in rows if r["vix_bucket"] == b]
            if rs:
                self.set_runtime_statistic(f"M0 VIX {b}", f"${sum(pnl(r,'hold') for r in rs):,.0f} (n={len(rs)})")
        by_yr, cnt = defaultdict(float), defaultdict(int)
        for r in rows:
            by_yr[r["open_date"][:4]] += pnl(r, "hold"); cnt[r["open_date"][:4]] += 1
        for yr in sorted(by_yr):
            self.set_runtime_statistic(f"M0 {yr}", f"${by_yr[yr]:,.0f} (n={cnt[yr]})")
        # estratificação dos filtros do Doc
        for lbl, sub in [("in-range", [r for r in rows if r["in_range"]]),
                         ("out-range", [r for r in rows if not r["in_range"]]),
                         (">SMA200", [r for r in rows if r["above_sma200"] is True]),
                         ("<SMA200", [r for r in rows if r["above_sma200"] is False])]:
            if sub:
                net = sum(pnl(r, "hold") for r in sub)
                wr = 100.0 * sum(1 for r in sub if pnl(r, "hold") > 0) / len(sub)
                self.set_runtime_statistic(f"HOLD {lbl}", f"${net:,.0f} / WR {wr:.0f}% (n={len(sub)})")
        # hold vs TP %-crédito (net + WR) no universo inteiro
        for lvl in self.profit_levels:
            net = sum(pnl(r, lvl) for r in rows)
            wr = 100.0 * sum(1 for r in rows if pnl(r, lvl) > 0) / len(rows)
            self.set_runtime_statistic(f"NET TP{int(lvl*100)}%", f"${net:,.0f} / WR {wr:.0f}%")
        self.set_runtime_statistic("NET hold", f"${sum(pnl(r,'hold') for r in rows):,.0f}")
        import statistics as _st
        self.set_runtime_statistic("credit med", f"{_st.median(r['credit'] for r in rows):.2f}")
        self.set_runtime_statistic("wing med", f"{_st.median(r['wing'] for r in rows):.0f}")
        n_stopped = sum(1 for r in rows if r.get("cross_stop_v") not in ("", None))
        self.set_runtime_statistic("touched EM %", f"{100.0*n_stopped/len(rows):.0f}%")

    def on_end_of_algorithm(self):
        cols = (["fly_id", "open_date", "open_time", "expiry_date", "vix", "vix_bucket",
                 "S_entry", "S_settle", "center", "wing", "long_put", "long_call", "em", "credit",
                 "or_high", "or_low", "in_range", "or_pos", "above_sma200", "max_value",
                 "cross_stop_t", "cross_stop_v"]
                + [f"cross_p{int(l*100)}_t" for l in self.profit_levels]
                + [f"cross_p{int(l*100)}_v" for l in self.profit_levels]
                + ["settle_pnl_pts", "settle_net", "settle_result"])
        lines = [",".join(cols)] + [",".join(str(r.get(c, "")) for c in cols) for r in self.rows]
        try:
            self.object_store.save(f"ironfly_{self.run_tag}.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou: {e}")
        self._emit_runtime_stats()
        n = len(self.rows)
        net = sum(r["settle_net"] for r in self.rows)
        w = sum(1 for r in self.rows if r["settle_result"] == "W")
        self.log(f"=== IRON FLY 0DTE [{self.run_tag}] === n={n} | W={w} ({(w/n*100 if n else 0):.0f}%) "
                 f"| net hold=${net:,.0f} | skips={len(self.skips)}")
