# region imports
from AlgorithmImports import *
import math
# endregion

class IronCondor0DTE(QCAlgorithm):
    """
    IRON CONDOR SPX 0DTE (CZ spec 2026-05-27) — estratégia #4 da mesa ("0DTE IC c/ stop").
    Liga: context/0DTE strategies/PROJECT_qc_backtest_scope.md, memória project_desk_strategy_framework.

    SPEC (CZ):
      - ABERTURA: 12:30 ET, TODO dia útil, expiry do MESMO dia (0DTE) em SPXW.
      - SHORT STRIKES: o strike com delta mais próximo de 0.16 em cada lado (put e call).
      - LONG STRIKES: 5 pontos FORA de cada short (asa de 5). Ex.: LP 7485 / SP 7490 / SC 7540 / LC 7545.
      - CREDIT: vende a IC (recebe crédito).
      - CLOSE RULES (derivadas de UMA run, ver abaixo):
          (a) Hold to expiration  -> cash-settle no preço oficial (lição da Fase 1: NÃO manda market
              order no expiry; SPXW liquida em CAIXA).
          (b) Stop "2x New credit" -> fecha quando o custo de recompra atinge 2x o crédito (perda ~1x
              crédito). Como é DETERMINÍSTICO, não precisa de run separada: gravo o 1º cruzamento de
              2x e o export deriva o P&L do stop. De brinde gravo profit 25/50/75% do crédito.

    LIÇÕES (não repetir): combo RECONHECIDO (iron_condor) p/ margem de risco definido — nada de pernas
    soltas (naked short estoura margem). Ler a EQUITY/payoff limpo, não o blotter. O P&L por-trade vem
    do payoff num ÚNICO preço de settle (imune ao artefato de split-settle do QC; ver project_batman_resume).
    """

    def initialize(self):
        self.entry_hour   = int(self.get_parameter("entry_hour", "12"))
        self.entry_minute = int(self.get_parameter("entry_minute", "30"))
        self.target_delta = float(self.get_parameter("target_delta", "0.16"))
        self.wing_width   = float(self.get_parameter("wing_width", "5"))      # asa: 5 pts fora do short
        self.stop_mult    = float(self.get_parameter("stop_mult", "2.0"))     # stop = 2x crédito
        # stop_close: "none" = só GRAVA o cruzamento (run hold); senão EXECUTA o stop (run stop-2x,
        # p/ o recon pegar o fill exato do fechamento — cross_* do motor não exporta).
        self.stop_close   = self.get_parameter("stop_close", "none") not in ("none", "None", "")
        self.ticker       = self.get_parameter("ticker", "SPX")
        sd = self.get_parameter("start_date", "2022-06-20").split("-")
        ed = self.get_parameter("end_date",   "2026-05-13").split("-")
        self.run_tag = self.get_parameter("run_tag", "IC0DTE")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        index = self.add_index("SPX", Resolution.MINUTE)
        self.spx = index.symbol
        option = self.add_index_option(self.spx, "SPXW", Resolution.MINUTE)
        option.set_filter(lambda u: u.include_weeklys().expiration(0, 1).strikes(-60, 60))
        self.spxw = option.symbol
        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        # níveis a GRAVAR (fração do crédito): stop=2x recompra; profits = recompra barata
        self.mark_every_min = 5
        self.profit_levels = [0.25, 0.50, 0.75]   # fechar capturando X% do crédito

        self.rows = []
        self.skips = []
        self.open_ics = []
        self.entered_today = False
        self.current_day = None
        self.ic_seq = 0

        self.schedule.on(self.date_rules.every_day(self.spx),
                         self.time_rules.at(16, 1), self._settle_due)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.current_day != self.time.date():
            self.current_day = self.time.date()
            self.entered_today = False

        if self.time.minute % self.mark_every_min == 0:
            for ic in self.open_ics:
                if ic["expiry"] == self.time.date():
                    self._mark_ic(ic)

        if self.entered_today:
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return

        chain = slice.option_chains.get(self.spxw)
        if chain is None:
            return
        contracts = [c for c in chain]
        if not contracts:
            self.entered_today = True
            self._skip("cadeia vazia"); return

        self._enter_ic(contracts, self.securities[self.vix].price)
        self.entered_today = True

    # ===================== ENTRADA =====================
    def _enter_ic(self, contracts, vix):
        S = self.securities[self.spx].price
        today = self.time.date()
        legs0 = [c for c in contracts if c.expiry.date() == today]   # 0DTE: expiry HOJE
        if not legs0:
            self._skip("sem expiry 0DTE"); return
        expiry = today

        sp = self._pick_by_delta(legs0, OptionRight.PUT, S, expiry)
        sc = self._pick_by_delta(legs0, OptionRight.CALL, S, expiry)
        if sp is None or sc is None:
            self._skip("sem short @16D"); return

        by = {(c.right, c.strike): c for c in legs0}
        lp = by.get((OptionRight.PUT,  sp.strike - self.wing_width))
        lc = by.get((OptionRight.CALL, sc.strike + self.wing_width))
        if lp is None or lc is None:
            self._skip("sem long (asa 5)"); return

        # crédito CONSERVADOR: vende shorts no bid, compra longs no ask
        credit = (sp.bid_price + sc.bid_price) - (lp.ask_price + lc.ask_price)
        if credit <= 0:
            self._skip(f"crédito<=0 ({credit:.2f})"); return

        # combo RECONHECIDO (risco definido = wing - credit). lp<sp<sc<lc.
        self.buy(OptionStrategies.iron_condor(self.spxw, lp.strike, sp.strike,
                                              sc.strike, lc.strike, sp.expiry), 1)
        self.ic_seq += 1
        ic = {
            "id": self.ic_seq, "open_time": self.time, "expiry": expiry, "exp_dt": sp.expiry,
            "S_entry": S, "vix": vix,
            "lp": lp.strike, "sp": sp.strike, "sc": sc.strike, "lc": lc.strike,
            "sp_sym": sp.symbol, "sc_sym": sc.symbol, "lp_sym": lp.symbol, "lc_sym": lc.symbol,
            "credit": credit, "sp_delta": self._delta(sp, S, expiry), "sc_delta": self._delta(sc, S, expiry),
            "max_value": credit, "cross_stop": None,
            "cross_p": {lvl: None for lvl in self.profit_levels}, "closed": False,
        }
        self.open_ics.append(ic)
        if self.ic_seq <= 3:
            self.debug(f"{self.time} IC#{self.ic_seq} {lp.strike}/{sp.strike}/{sc.strike}/{lc.strike} "
                       f"cr={credit:.2f} vix={vix:.1f}")

    def _pick_by_delta(self, legs, right, S, expiry):
        """Short strike: delta (abs) mais próximo de target_delta no lado certo (put<S, call>S)."""
        side = [c for c in legs if c.right == right and (c.strike < S if right == OptionRight.PUT else c.strike > S)]
        best, bestgap = None, 1e9
        for c in side:
            d = self._delta(c, S, expiry)
            if d is None:
                continue
            gap = abs(abs(d) - self.target_delta)
            if gap < bestgap:
                best, bestgap = c, gap
        return best

    # ===================== MARCAÇÃO (grava stop 2x + profits) =====================
    def _mark_ic(self, ic):
        if ic.get("closed"):
            return
        # custo de RECOMPRA (fechar): compra shorts no ask, vende longs no bid
        sp_a = self.securities[ic["sp_sym"]].ask_price
        sc_a = self.securities[ic["sc_sym"]].ask_price
        lp_b = self.securities[ic["lp_sym"]].bid_price
        lc_b = self.securities[ic["lc_sym"]].bid_price
        if min(sp_a, sc_a) <= 0:
            return
        buyback = (sp_a + sc_a) - (lp_b + lc_b)
        if buyback > ic["max_value"]:
            ic["max_value"] = buyback
        cr = ic["credit"]
        # STOP 2x: custo de recompra >= stop_mult*crédito
        if ic["cross_stop"] is None and buyback >= self.stop_mult * cr:
            ic["cross_stop"] = (self.time.strftime("%H:%M"), round(buyback, 2))
            if self.stop_close:                      # run stop-2x: FECHA a IC (compra de volta)
                self.sell(OptionStrategies.iron_condor(self.spxw, ic["lp"], ic["sp"],
                                                       ic["sc"], ic["lc"], ic["exp_dt"]), 1)
                ic["closed"] = True
                self._record(ic, self.securities[self.spx].price, cr - buyback)   # realiza no stop
                return
        # PROFIT X%: recompra barata (<= (1-X)*crédito)
        for lvl in self.profit_levels:
            if ic["cross_p"][lvl] is None and buyback <= (1.0 - lvl) * cr:
                ic["cross_p"][lvl] = (self.time.strftime("%H:%M"), round(buyback, 2))

    # ===================== SETTLE =====================
    def _settle_due(self):
        if not self.open_ics:
            return
        S_T = self.securities[self.spx].price
        still = []
        for ic in self.open_ics:
            if ic["expiry"] != self.time.date():
                still.append(ic); continue
            if ic.get("closed"):
                continue                              # já realizada pelo stop-2x — não settla de novo
            # payoff LIMPO num único preço: perda dos spreads, capada na asa
            put_loss  = min(self.wing_width, max(0.0, ic["sp"] - S_T))
            call_loss = min(self.wing_width, max(0.0, S_T - ic["sc"]))
            pnl_pts = ic["credit"] - put_loss - call_loss     # pontos
            self._record(ic, S_T, pnl_pts)
        self.open_ics = still

    def _record(self, ic, S_T, pnl_pts):
        cs = ic["cross_stop"]
        self.rows.append({
            "ic_id": ic["id"], "open_date": ic["open_time"].strftime("%Y-%m-%d"),
            "open_time": ic["open_time"].strftime("%H:%M"), "expiry_date": ic["expiry"].strftime("%Y-%m-%d"),
            "vix": round(ic["vix"], 2), "vix_bucket": self._vix_bucket(ic["vix"]),
            "S_entry": round(ic["S_entry"], 2), "S_settle": round(S_T, 2),
            "long_put": ic["lp"], "short_put": ic["sp"], "short_call": ic["sc"], "long_call": ic["lc"],
            "sp_delta": round(ic["sp_delta"], 4) if ic["sp_delta"] is not None else "",
            "sc_delta": round(ic["sc_delta"], 4) if ic["sc_delta"] is not None else "",
            "credit": round(ic["credit"], 2), "max_value": round(ic["max_value"], 2),
            "cross_stop_t": cs[0] if cs else "", "cross_stop_v": cs[1] if cs else "",
            **{f"cross_p{int(l*100)}_t": (ic["cross_p"][l][0] if ic["cross_p"][l] else "") for l in self.profit_levels},
            **{f"cross_p{int(l*100)}_v": (ic["cross_p"][l][1] if ic["cross_p"][l] else "") for l in self.profit_levels},
            "settle_pnl_pts": round(pnl_pts, 2), "settle_net": round(pnl_pts * 100.0, 2),
            "settle_result": "W" if pnl_pts > 0 else "L",
        })

    # ===================== GREEKS / HELPERS =====================
    def _delta(self, c, S, expiry):
        try:
            g = c.greeks
            if g is not None and g.delta is not None and abs(g.delta) > 1e-6:
                return float(g.delta)
        except Exception:
            pass
        iv = c.implied_volatility or 0.0
        if iv <= 0 or S <= 0 or c.strike <= 0:
            return None
        exp_dt = datetime(expiry.year, expiry.month, expiry.day, 16, 0)
        T = max((exp_dt - self.time).total_seconds() / (365.0 * 24 * 3600), 1e-6)
        d1 = (math.log(S / c.strike) + (0.04 + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
        nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
        return nd1 if c.right == OptionRight.CALL else nd1 - 1.0

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
            if mode == "stop":                       # 2x credit -> sai com a recompra gravada
                v = r.get("cross_stop_v", "")
                if v not in ("", None):
                    return (r["credit"] - float(v)) * 100.0
            return r["settle_net"]                    # hold (ou stop nunca cruzado) -> settle

        for b in ["<15", "15-17", "17-22", "22-32", "32+"]:
            rs = [r for r in rows if r["vix_bucket"] == b]
            if rs:
                self.set_runtime_statistic(f"M0 VIX {b}", f"${sum(pnl(r,'hold') for r in rs):,.0f} (n={len(rs)})")
        by_yr, cnt = defaultdict(float), defaultdict(int)
        for r in rows:
            by_yr[r["open_date"][:4]] += pnl(r, "hold"); cnt[r["open_date"][:4]] += 1
        for yr in sorted(by_yr):
            self.set_runtime_statistic(f"M0 {yr}", f"${by_yr[yr]:,.0f} (n={cnt[yr]})")
        for mode, lbl in [("hold", "NET hold"), ("stop", "NET stop-2x")]:
            net = sum(pnl(r, mode) for r in rows)
            wr = 100.0 * sum(1 for r in rows if pnl(r, mode) > 0) / len(rows)
            self.set_runtime_statistic(lbl, f"${net:,.0f} / WR {wr:.0f}%")
        import statistics as _st
        self.set_runtime_statistic("credit med", f"{_st.median(r['credit'] for r in rows):.2f}")
        n_stopped = sum(1 for r in rows if r.get("cross_stop_v") not in ("", None))
        self.set_runtime_statistic("stopped %", f"{100.0*n_stopped/len(rows):.0f}%")

    def on_end_of_algorithm(self):
        cols = (["ic_id", "open_date", "open_time", "expiry_date", "vix", "vix_bucket",
                 "S_entry", "S_settle", "long_put", "short_put", "short_call", "long_call",
                 "sp_delta", "sc_delta", "credit", "max_value", "cross_stop_t", "cross_stop_v"]
                + [f"cross_p{int(l*100)}_t" for l in self.profit_levels]
                + [f"cross_p{int(l*100)}_v" for l in self.profit_levels]
                + ["settle_pnl_pts", "settle_net", "settle_result"])
        lines = [",".join(cols)] + [",".join(str(r.get(c, "")) for c in cols) for r in self.rows]
        try:
            self.object_store.save(f"ic0dte_{self.run_tag}.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou: {e}")
        self._emit_runtime_stats()
        n = len(self.rows)
        net = sum(r["settle_net"] for r in self.rows)
        w = sum(1 for r in self.rows if r["settle_result"] == "W")
        self.log(f"=== IC 0DTE [{self.run_tag}] === n={n} | W={w} ({(w/n*100 if n else 0):.0f}%) "
                 f"| net hold=${net:,.0f} | skips={len(self.skips)}")
