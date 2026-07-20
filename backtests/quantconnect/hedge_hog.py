# region imports
from AlgorithmImports import *
import math
# endregion

class HedgeHog(QCAlgorithm):
    """
    HEDGE HOG — High Probability Income Trade (Reiner / EdgeSeeker) — SPX.
    Fonte: Hege Hog High Prob Income Trade.pdf (texto alemao).

    ESTRUTURA (3 pernas, 2 expiracoes):
      "Der Hedge" — Long Put Vertical (DEBITO), ~30 DTE:
        BUY  put @ ~0.30 delta
        SELL put @ ~0.20 delta            (R:R ~3:1)
      "Das Schwein" — short put LONGO (CREDITO), 75-115 DTE (~90):
        SELL put @ ~0.05-0.10 delta
      Restricao: premio do short longo > debito do LPV  ->  net CREDITO.

    GESTAO (4 triggers do PDF; acao universal = fechar+reabrir a peca):
      T1  Short longo > 50% do lucro max      -> rola o short longo (reabre 90 DTE)
      T2  LPV > 80% do lucro max              -> rola o LPV (reabre 30 DTE)
      T3  LPV < 7 DTE                          -> rola o LPV (gamma acelera)
      T4  Spot fura o short strike do LPV      -> fecha+reabre TUDO (o hedge nao ajuda mais)
          em < 10 dias da entrada do LPV
      + hold: cada perna rola no proprio vencimento.

    Contabilidade = FLUXO DE CAIXA (posicao continua rolada, como o Layer B): cada roll = fecha a
    perna velha (cash) + abre a nova (cash). P&L = cum_cash + mark. Naked short longo -> BuyingPowerModel.
    NULL (nao estoura margem); risco lido do payoff. Marcacao HORARIA (trade de semanas). Canal HHOG.
    """

    def initialize(self):
        self.ticker       = self.get_parameter("ticker", "SPX").strip()
        self.opt_target   = self.get_parameter("opt_target", "SPXW").strip()
        self.d_lpv_long   = float(self.get_parameter("delta_lpv_long",  "0.30"))
        self.d_lpv_short  = float(self.get_parameter("delta_lpv_short", "0.20"))
        self.d_far        = float(self.get_parameter("delta_far",       "0.07"))   # 5-10 delta
        self.lpv_dte      = int(self.get_parameter("lpv_dte", "30"))
        self.far_dte      = int(self.get_parameter("far_dte", "90"))               # 75-115
        self.far_dte_lo   = int(self.get_parameter("far_dte_lo", "75"))
        self.far_dte_hi   = int(self.get_parameter("far_dte_hi", "115"))
        self.tp_far       = float(self.get_parameter("tp_far", "0.50"))            # T1
        self.tp_lpv       = float(self.get_parameter("tp_lpv", "0.80"))            # T2
        self.lpv_roll_dte = int(self.get_parameter("lpv_roll_dte", "7"))           # T3
        self.break_days   = int(self.get_parameter("break_days", "10"))           # T4 janela
        self.strike_dn    = int(self.get_parameter("strike_dn", "120"))
        self.strike_up    = int(self.get_parameter("strike_up", "10"))
        self.fill_mode    = self.get_parameter("fill_mode", "mid").lower().strip()
        self.comm_leg     = float(self.get_parameter("commission_per_contract", "1.5"))
        self.mult         = float(self.get_parameter("multiplier", "100"))
        sd = self.get_parameter("start_date", "2021-06-01").split("-")
        ed = self.get_parameter("end_date",   "2026-06-01").split("-")
        self.run_tag = self.get_parameter("run_tag", "HH_SPX")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(1_000_000)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_security_initializer(lambda s: s.set_buying_power_model(BuyingPowerModel.NULL))
        self.settings.minimum_order_margin_portfolio_percentage = 0

        index = self.add_index(self.ticker, Resolution.MINUTE)
        self.idx = index.symbol
        # HH e SO PUTS -> puts_only() (metade dos contratos). expiration comeca antes do LPV (nao do
        # 0) p/ pular a escada DIARIA curta (glut = OOM do Layer B), e vai ate o far.
        option = self.add_index_option(self.idx, self.opt_target, Resolution.MINUTE)
        option.set_filter(lambda u: u.include_weeklys().puts_only()
                          .expiration(max(0, self.lpv_dte - 10), self.far_dte_hi + 5)
                          .strikes(-self.strike_dn, self.strike_up))
        self.opt = option.symbol
        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        self.pos = None          # posicao continua unica (LPV + far)
        self.rows = []           # 1 linha por EVENTO (entrada/roll/settle) — canal HHOG
        self.skips = []
        self.cum_cash = 0.0
        self.seq = 0
        self.n_t = {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "lpv_exp": 0, "far_exp": 0}

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.time.minute != 0:            # marcacao/gestao HORARIA
            return
        chain = slice.option_chains.get(self.opt)
        if chain is None:
            return
        contracts = [c for c in chain]
        if not contracts:
            return
        S = self.securities[self.idx].price
        if S <= 0:
            return

        if self.pos is None:
            self._enter(contracts, S)
            return
        self._manage(contracts, S)

    # ===================== ENTRADA / ROLL =====================
    def _open_lpv(self, contracts, S):
        """LPV ~30 DTE: buy 0.30d put / sell 0.20d put. Retorna dict ou None."""
        expiry = self._pick_expiry(contracts, self.lpv_dte)
        if expiry is None:
            return None
        puts = [c for c in contracts if c.expiry.date() == expiry and c.right == OptionRight.PUT]
        lg = self._pick_delta(puts, S, expiry, self.d_lpv_long)     # long 30d
        sh = self._pick_delta(puts, S, expiry, self.d_lpv_short)    # short 20d
        if lg is None or sh is None or lg.strike <= sh.strike:
            return None                                             # long strike > short strike (put debit vertical)
        debit = self._mid(lg) - self._mid(sh)                       # paga (debito)
        if debit <= 0:
            return None
        self.buy(lg.symbol, 1); self.sell(sh.symbol, 1)
        self.cum_cash -= debit                                      # pagou o debito
        return {"lg_sym": lg.symbol, "sh_sym": sh.symbol, "lg_k": lg.strike, "sh_k": sh.strike,
                "expiry": expiry, "open_dt": self.time, "debit": debit,
                "width": lg.strike - sh.strike, "max_profit": (lg.strike - sh.strike) - debit,
                "d_lg": self._delta(lg, S, expiry), "d_sh": self._delta(sh, S, expiry)}

    def _open_far(self, contracts, S):
        """Short put longo ~90 DTE @ ~0.07 delta (credito)."""
        expiry = self._pick_expiry(contracts, self.far_dte, self.far_dte_lo, self.far_dte_hi)
        if expiry is None:
            return None
        puts = [c for c in contracts if c.expiry.date() == expiry and c.right == OptionRight.PUT]
        f = self._pick_delta(puts, S, expiry, self.d_far)
        if f is None:
            return None
        credit = self._mid(f)
        if credit <= 0:
            return None
        self.sell(f.symbol, 1)
        self.cum_cash += credit
        return {"f_sym": f.symbol, "f_k": f.strike, "expiry": expiry, "open_dt": self.time,
                "credit": credit, "max_profit": credit, "d_f": self._delta(f, S, expiry)}

    def _enter(self, contracts, S):
        lpv = self._open_lpv(contracts, S)
        if lpv is None:
            self._skip("sem LPV"); return
        far = self._open_far(contracts, S)
        if far is None:
            # desfaz o LPV p/ nao ficar so com o debito
            self._close_lpv(lpv); self._skip("sem far"); return
        # restricao da fonte: credito do far > debito do LPV
        net_credit = far["credit"] - lpv["debit"]
        self.seq += 1
        self.pos = {"id": self.seq, "lpv": lpv, "far": far, "open_dt": self.time, "S_open": S,
                    "vix": self.securities[self.vix].price, "net_credit_open": net_credit}
        self._record("entry", S)
        if self.seq <= 3:
            self.debug(f"{self.time} HH#{self.seq} LPV {lpv['lg_k']}/{lpv['sh_k']} deb={lpv['debit']:.2f} "
                       f"far {far['f_k']} cr={far['credit']:.2f} net={net_credit:.2f}")

    def _close_lpv(self, lpv):
        lg_b = self.securities[lpv["lg_sym"]].bid_price     # vende o long (bid)
        sh_a = self.securities[lpv["sh_sym"]].ask_price     # recompra o short (ask)
        val = lg_b - sh_a                                   # valor de desmontagem do LPV
        for sym in (lpv["lg_sym"], lpv["sh_sym"]):
            if self.portfolio[sym].invested:
                self.liquidate(sym)
        self.cum_cash += val
        return val

    def _close_far(self, far):
        a = self.securities[far["f_sym"]].ask_price         # recompra o short (ask)
        if self.portfolio[far["f_sym"]].invested:
            self.liquidate(far["f_sym"])
        self.cum_cash -= a
        return -a

    # ===================== GESTAO =====================
    def _manage(self, contracts, S):
        p = self.pos; lpv = p["lpv"]; far = p["far"]
        lpv_dte_now = (lpv["expiry"] - self.time.date()).days
        far_dte_now = (far["expiry"] - self.time.date()).days

        # valores atuais (recompra)
        lpv_val = self._lpv_value(lpv)     # quanto vale desmontar o LPV agora (>0 = a favor)
        far_buyback = self.securities[far["f_sym"]].ask_price

        # T4: spot furou o short strike do LPV em < break_days da entrada do LPV -> fecha+reabre TUDO
        days_since_lpv = (self.time - lpv["open_dt"]).days
        if S <= lpv["sh_k"] and days_since_lpv < self.break_days:
            self.n_t["T4"] += 1
            self._close_lpv(lpv); self._close_far(far)
            self._record("T4_reopen", S); self.pos = None; return

        # T3: LPV < 7 DTE -> rola o LPV
        if lpv_dte_now <= self.lpv_roll_dte:
            self.n_t["T3"] += 1
            self._roll_lpv(contracts, S, "T3_lpv_roll"); return

        # T2: LPV > 80% do lucro max -> rola o LPV
        if lpv["max_profit"] > 0 and lpv_val >= self.tp_lpv * lpv["max_profit"]:
            self.n_t["T2"] += 1
            self._roll_lpv(contracts, S, "T2_lpv_tp"); return

        # far vencendo -> rola o far
        if far_dte_now <= self.lpv_roll_dte:
            self.n_t["far_exp"] += 1
            self._roll_far(contracts, S, "far_exp"); return

        # T1: short longo > 50% do lucro max (buyback <= 50% do credito) -> rola o far
        if far["credit"] > 0 and far_buyback <= (1.0 - self.tp_far) * far["credit"]:
            self.n_t["T1"] += 1
            self._roll_far(contracts, S, "T1_far_tp"); return

    def _roll_lpv(self, contracts, S, reason):
        self._close_lpv(self.pos["lpv"])
        new = self._open_lpv(contracts, S)
        if new is None:
            # nao conseguiu reabrir: fecha o far tb e zera (nao fica descoberto no far sem hedge)
            self._close_far(self.pos["far"]); self._record(reason + "_flat", S); self.pos = None
            self._skip("roll LPV sem reabrir"); return
        self.pos["lpv"] = new
        self._record(reason, S)

    def _roll_far(self, contracts, S, reason):
        self._close_far(self.pos["far"])
        new = self._open_far(contracts, S)
        if new is None:
            self._close_lpv(self.pos["lpv"]); self._record(reason + "_flat", S); self.pos = None
            self._skip("roll far sem reabrir"); return
        self.pos["far"] = new
        self._record(reason, S)

    def _lpv_value(self, lpv):
        lg_b = self.securities[lpv["lg_sym"]].bid_price
        sh_a = self.securities[lpv["sh_sym"]].ask_price
        return lg_b - sh_a

    # ===================== SETTLE (guarda de vencimento) =====================
    # A marcacao horaria + rolls por DTE (<=7) tratam quase tudo; um vencimento nao rolado seria
    # capturado aqui, mas com lpv_roll_dte=7 e far tb rolado, nao deve sobrar posicao no expiry.

    # ===================== HELPERS =====================
    def _pick_expiry(self, contracts, target, lo=None, hi=None):
        today = self.time.date()
        exps = sorted({c.expiry.date() for c in contracts if (c.expiry.date() - today).days >= 1})
        if lo is not None:
            exps = [e for e in exps if lo <= (e - today).days <= hi]
        if not exps:
            return None
        return min(exps, key=lambda e: abs((e - today).days - target))

    def _pick_delta(self, puts, S, expiry, target):
        best, bestgap = None, 1e9
        for c in puts:
            d = self._delta(c, S, expiry)
            if d is None:
                continue
            gap = abs(abs(d) - target)
            if gap < bestgap:
                best, bestgap = c, gap
        return best

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
        return nd1 - 1.0     # put

    @staticmethod
    def _mid(c):
        b, a = c.bid_price, c.ask_price
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return c.last_price or a or b or 0.0

    def _mark_total(self):
        """Valor de desmontagem da posicao inteira (pts): LPV + (-far buyback)."""
        p = self.pos
        if p is None:
            return 0.0
        lpv_val = self._lpv_value(p["lpv"])
        far_bb  = self.securities[p["far"]["f_sym"]].ask_price
        return lpv_val - far_bb

    def _record(self, event, S):
        p = self.pos
        mark = self._mark_total() if p is not None else 0.0
        pnl_total = self.cum_cash + mark
        dd = 0.0
        lpv = p["lpv"] if p else None
        far = p["far"] if p else None
        self.rows.append({
            "id": (p["id"] if p else self.seq), "date": self.time.strftime("%Y-%m-%d"),
            "time": self.time.strftime("%H:%M"), "event": event,
            "S": round(S, 2), "vix": round(self.securities[self.vix].price, 2),
            "lpv_long": lpv["lg_k"] if lpv else "", "lpv_short": lpv["sh_k"] if lpv else "",
            "lpv_exp": lpv["expiry"].strftime("%Y-%m-%d") if lpv else "",
            "lpv_debit": round(lpv["debit"], 2) if lpv else "",
            "d_lpv_lg": round(lpv["d_lg"], 3) if (lpv and lpv["d_lg"] is not None) else "",
            "d_lpv_sh": round(lpv["d_sh"], 3) if (lpv and lpv["d_sh"] is not None) else "",
            "far_short": far["f_k"] if far else "", "far_exp": far["expiry"].strftime("%Y-%m-%d") if far else "",
            "far_credit": round(far["credit"], 2) if far else "",
            "d_far": round(far["d_f"], 3) if (far and far["d_f"] is not None) else "",
            "net_credit": round(p["net_credit_open"], 2) if p else "",
            "cum_cash": round(self.cum_cash, 2), "mark": round(mark, 2),
            "pnl_total": round(pnl_total, 2), "pnl_usd": round(pnl_total * self.mult, 2),
        })

    def _skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    # ===================== EXPORT =====================
    def on_end_of_algorithm(self):
        rows = self.rows
        if rows:
            final = rows[-1]["pnl_usd"]
            self.set_runtime_statistic("PnL total usd", f"${final:,.0f}")
            self.set_runtime_statistic("events", str(len(rows)))
            self.set_runtime_statistic("cycles", str(self.seq))
            for k, v in self.n_t.items():
                self.set_runtime_statistic(f"n {k}", str(v))
            from collections import defaultdict
            by_yr = defaultdict(float)
            prev = 0.0
            for r in rows:
                by_yr[r["date"][:4]] = r["pnl_usd"]
            self.set_runtime_statistic("skips", str(len(self.skips)))
        cols = ["id", "date", "time", "event", "S", "vix", "lpv_long", "lpv_short", "lpv_exp",
                "lpv_debit", "d_lpv_lg", "d_lpv_sh", "far_short", "far_exp", "far_credit", "d_far",
                "net_credit", "cum_cash", "mark", "pnl_total", "pnl_usd"]
        self.log("HHOGHDR|" + ",".join(cols) + f"|tag={self.run_tag}")
        for r in rows:
            self.log("HHOG|" + ",".join(str(r.get(c, "")) for c in cols))
        from collections import Counter
        for reason, n in Counter(reason for _, reason in self.skips).most_common(10):
            self.log(f"SKIP|{n}|{reason}")
