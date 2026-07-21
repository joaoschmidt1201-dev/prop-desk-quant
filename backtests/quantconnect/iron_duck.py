# region imports
from AlgorithmImports import *
import math
# endregion

class IronDuck(QCAlgorithm):
    """
    IRON DUCK 45 DTE Income Trade (Reiner / EdgeSeeker / OptionsMastery) — SPX, RUT.
    Fonte: Iron Duck Income Trade.pdf + config tasty exata (João 2026-07-20).

    ESTRUTURA (iron condor 45 DTE, lado CALL dentro do dinheiro = o "duck"):
      - SELL PUT  @ ~15 delta                          (short put OTM)
      - BUY  PUT  @ (strike_short_put  − put_offset)    (long put, offset FIXO em pontos = o risco largo)
      - SELL CALL @ ~65 delta (ITM!)                    (short call dentro do dinheiro)
      - BUY  CALL @ (strike_short_call + call_offset)   (long call, offset FIXO estreito)
    Ordem dos strikes: lp < sp < sc < lc  (combo OptionStrategies.iron_condor -> margem DEFINIDA).
    "use exact strike offsets": longs por PONTOS, não por delta.

    OFFSETS calibrados p/ reproduzir o max loss publicado (VALIDAÇÃO institucional):
      SPX put 480 / call 20  -> max loss = 480*100 − credit ≈ $43.885 (PDF)
      RUT put  70 / call 15  -> max loss =  70*100 − credit ≈ $5.270  (PDF)

    ENTRADA: semanal, Segunda (weekday 0), horário fixo (SPX 09:45). Pula se VIX > vix_max (40).
    GESTÃO (record-and-derive, 1 run MTM deriva todas): TP %crédito {25/40/50/75}, stop {2x/3x crédito},
      saída por TEMPO {7/5/2 DTE}, "exit when tested" (spot fura short strike). Hold = settle no expiry.
      O export deriva cada regra e os COMBOS (TP-ou-DTE-ou-tested o que vier 1º) pelo first-touch.

    P&L LIMPO: payoff analítico num único preço de settle (imune ao split-settle do QC). Combo = risco
      definido (não naked). Marcação de HORA EM HORA (trade de 45 DTE, não intraday).
    """

    def initialize(self):
        self.ticker       = self.get_parameter("ticker", "SPX").strip()
        self.opt_target   = self.get_parameter("opt_target", "SPXW").strip()
        self.entry_dow    = int(self.get_parameter("entry_dow", "0"))          # 0 = Segunda
        self.entry_hour   = int(self.get_parameter("entry_hour", "9"))
        self.entry_minute = int(self.get_parameter("entry_minute", "45"))
        self.target_dte   = int(self.get_parameter("target_dte", "45"))
        self.dte_lo       = int(self.get_parameter("dte_lo", "40"))
        self.dte_hi       = int(self.get_parameter("dte_hi", "52"))
        self.d_put_short  = float(self.get_parameter("delta_put_short",  "0.15"))
        self.d_call_short = float(self.get_parameter("delta_call_short", "0.65"))  # ITM
        # LONGS: "offset" = ponto fixo (SPX/SPY, config Reiner) | "delta" = por delta (RUT: LP10/LC65).
        self.long_mode    = self.get_parameter("long_mode", "offset").lower().strip()
        self.d_put_long   = float(self.get_parameter("delta_put_long",  "0.10"))
        self.d_call_long  = float(self.get_parameter("delta_call_long", "0.65"))
        self.put_offset   = float(self.get_parameter("put_offset",  "480"))    # SPX 480 / SPY 30
        self.call_offset  = float(self.get_parameter("call_offset", "20"))     # SPX 20  / SPY 3
        self.vix_max      = float(self.get_parameter("vix_max", "40"))
        # strike_dn tem que alcancar o LONG PUT = (spot − dist_short_put) − put_offset.
        # Ex SPX: 15d put ~230pt abaixo + offset 480 = ~710pt = ~142 strikes de 5pt -> 175 c/ margem.
        self.strike_dn    = int(self.get_parameter("strike_dn", "175"))        # strikes ABAIXO do ATM
        self.strike_up    = int(self.get_parameter("strike_up", "15"))         # strikes ACIMA
        self.fill_mode    = self.get_parameter("fill_mode", "mid").lower().strip()
        self.comm_leg     = float(self.get_parameter("commission_per_contract", "1.5"))
        self.mult         = float(self.get_parameter("multiplier", "100"))     # opção de índice
        sd = self.get_parameter("start_date", "2021-06-01").split("-")
        ed = self.get_parameter("end_date",   "2026-06-01").split("-")
        self.run_tag = self.get_parameter("run_tag", "ID_SPX")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(1_000_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        index = self.add_index(self.ticker, Resolution.MINUTE)
        self.idx = index.symbol
        option = self.add_index_option(self.idx, self.opt_target, Resolution.MINUTE)
        option.set_filter(lambda u: u.include_weeklys()
                          .expiration(self.dte_lo, self.dte_hi)
                          .strikes(-self.strike_dn, self.strike_up))
        self.opt = option.symbol
        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        # niveis a GRAVAR (record-and-derive)
        self.profit_levels = [0.25, 0.40, 0.50, 0.75]         # TP: recompra <= (1-lvl)*credito
        self.stop_mults    = [1.5, 2.0, 2.5, 3.0]             # stop: buyback >= m*credito (cap da perda)
        self.loss_stops    = [300, 750, 1500, 3000]           # stop por PERDA ABSOLUTA ($) — Reiner SPX=$300
        self.dte_exits     = [7, 5, 2]                        # saida por tempo

        self.rows = []
        self.skips = []
        self.open_ds = []          # posicoes abertas (concorrentes)
        self.entered_key = None    # (ano, semana) da ultima entrada -> 1 por semana
        self.d_seq = 0

        # settle guard: todo dia 16:01 confere expiracoes
        self.schedule.on(self.date_rules.every_day(self.idx),
                         self.time_rules.at(16, 1), self._settle_due)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        # marcacao HORARIA de todas as posicoes abertas (grava TP/stop/DTE/tested)
        if self.time.minute == 0:
            for d in list(self.open_ds):
                self._mark(d)

        # entrada semanal
        if self.time.weekday() != self.entry_dow:
            return
        wk = self.time.isocalendar()[:2]     # (ano, semana ISO)
        if self.entered_key == wk:
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return
        self.entered_key = wk
        vix = self.securities[self.vix].price
        if vix and vix > self.vix_max:
            self._skip(f"VIX>{self.vix_max:g} ({vix:.1f})"); return
        chain = slice.option_chains.get(self.opt)
        if chain is None:
            self._skip("sem chain"); return
        contracts = [c for c in chain]
        if not contracts:
            self._skip("chain vazia"); return
        self._enter(contracts, vix)

    # ===================== ENTRADA =====================
    def _enter(self, contracts, vix):
        S = self.securities[self.idx].price
        today = self.time.date()
        # expiry mais proximo de target_dte (dentro da janela)
        exps = sorted({c.expiry.date() for c in contracts if (c.expiry.date() - today).days >= 1})
        if not exps:
            self._skip("sem expiry"); return
        expiry = min(exps, key=lambda e: abs((e - today).days - self.target_dte))
        dte = (expiry - today).days
        legs = [c for c in contracts if c.expiry.date() == expiry]

        sp = self._pick_by_delta(legs, OptionRight.PUT,  S, expiry, self.d_put_short)
        sc = self._pick_by_delta(legs, OptionRight.CALL, S, expiry, self.d_call_short)
        if sp is None or sc is None:
            self._skip("sem short put/call"); return

        # longs: por DELTA (RUT: LP10/LC65) ou por OFFSET fixo em pontos (SPX/SPY, config Reiner)
        if self.long_mode == "delta":
            lp = self._pick_by_delta(legs, OptionRight.PUT,  S, expiry, self.d_put_long)
            lc = self._pick_by_delta(legs, OptionRight.CALL, S, expiry, self.d_call_long)
        else:
            lp = self._pick_by_strike(legs, OptionRight.PUT,  sp.strike - self.put_offset)
            lc = self._pick_by_strike(legs, OptionRight.CALL, sc.strike + self.call_offset)
        if lp is None or lc is None:
            self._skip("sem long put/call"); return

        # GATE topologia: lp < sp < sc < lc (senao nao e um iron condor de risco definido)
        if not (lp.strike < sp.strike < sc.strike < lc.strike):
            self._skip(f"topologia {lp.strike}/{sp.strike}/{sc.strike}/{lc.strike}"); return

        put_w  = sp.strike - lp.strike
        call_w = lc.strike - sc.strike
        credit_mid  = (self._mid(sp) + self._mid(sc)) - (self._mid(lp) + self._mid(lc))
        credit_cons = (sp.bid_price + sc.bid_price) - (lp.ask_price + lc.ask_price)
        credit = credit_mid if self.fill_mode == "mid" else credit_cons
        if credit <= 0:
            self._skip(f"credito<=0 ({credit:.2f})"); return
        max_loss_pts = max(put_w, call_w) - credit    # risco definido (lado mais largo)

        self.buy(OptionStrategies.iron_condor(self.opt, lp.strike, sp.strike,
                                              sc.strike, lc.strike, sp.expiry), 1)
        self.d_seq += 1
        d = {
            "id": self.d_seq, "open_time": self.time, "open_date": today,
            "expiry": expiry, "exp_dt": sp.expiry, "dte": dte, "S_entry": S, "vix": vix,
            "lp": lp.strike, "sp": sp.strike, "sc": sc.strike, "lc": lc.strike,
            "sp_sym": sp.symbol, "sc_sym": sc.symbol, "lp_sym": lp.symbol, "lc_sym": lc.symbol,
            "put_w": put_w, "call_w": call_w,
            "credit": credit, "credit_mid": credit_mid, "credit_cons": credit_cons,
            "max_loss_pts": max_loss_pts,
            "sp_delta": self._delta(sp, S, expiry), "sc_delta": self._delta(sc, S, expiry),
            "max_value": credit, "closed": False,
            "cross_p": {lvl: None for lvl in self.profit_levels},
            "cross_sm": {m: None for m in self.stop_mults},
            "cross_ls": {L: None for L in self.loss_stops}, # stop por perda absoluta ($)
            "dte_bb": {n: None for n in self.dte_exits},     # buyback no 1o toque de dte<=n
            "cross_tested": None,                            # 1o toque spot fura short strike
        }
        self.open_ds.append(d)
        if self.d_seq <= 3:
            self.debug(f"{self.time} DUCK#{self.d_seq} dte={dte} "
                       f"{lp.strike}/{sp.strike}/{sc.strike}/{lc.strike} "
                       f"cr={credit:.2f} maxloss={max_loss_pts*self.mult:.0f} vix={vix:.1f}")

    def _pick_by_delta(self, legs, right, S, expiry, target):
        """Strike com |delta| mais proximo de target no lado certo. NAO filtra por moneyness
        (o short call e ITM ~65delta -> strike < S; o short put e OTM ~15delta -> strike < S)."""
        best, bestgap = None, 1e9
        for c in legs:
            if c.right != right:
                continue
            d = self._delta(c, S, expiry)
            if d is None:
                continue
            gap = abs(abs(d) - target)
            if gap < bestgap:
                best, bestgap = c, gap
        return best

    @staticmethod
    def _pick_by_strike(legs, right, target):
        side = [c for c in legs if c.right == right]
        return min(side, key=lambda c: abs(c.strike - target)) if side else None

    def _mid_sym(self, sym):
        b = self.securities[sym].bid_price; a = self.securities[sym].ask_price
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return self.securities[sym].price or a or b or 0.0

    # ===================== MARCACAO =====================
    def _mark(self, d):
        if d.get("closed"):
            return
        # REGRA DA MESA: tudo no MID (entradas, saidas, hold). O buyback (custo de fechar) usa o mid de
        # cada perna, NAO o cruzamento bid-ask -> as regras de saida ficam comparaveis ao hold.
        sp_m = self._mid_sym(d["sp_sym"]); sc_m = self._mid_sym(d["sc_sym"])
        lp_m = self._mid_sym(d["lp_sym"]); lc_m = self._mid_sym(d["lc_sym"])
        if sp_m <= 0 or sc_m <= 0:
            return
        buyback = (sp_m + sc_m) - (lp_m + lc_m)          # custo de recompra (fechar) no MID
        if buyback > d["max_value"]:
            d["max_value"] = buyback
        cr = d["credit"]
        S = self.securities[self.idx].price
        # offset COMPACTO em horas desde a abertura (p/ o combo ordenar first-touch sem gastar bytes)
        hoff = int((self.time - d["open_time"]).total_seconds() // 3600)
        bb = round(buyback, 1)
        # spot no toque, como OFFSET inteiro vs entrada (compacto; export reconstroi S_entry+dS).
        # Necessario p/ o Trade Auditor marcar ONDE (eixo X) cada regra fechou o trade.
        dS = int(round(S - d["S_entry"]))

        # TP: recompra barata
        for lvl in self.profit_levels:
            if d["cross_p"][lvl] is None and buyback <= (1.0 - lvl) * cr:
                d["cross_p"][lvl] = (hoff, bb, dS)
        # STOP por MULTIPLO do credito
        for m in self.stop_mults:
            if d["cross_sm"][m] is None and buyback >= m * cr:
                d["cross_sm"][m] = (hoff, bb, dS)
        # STOP por PERDA ABSOLUTA ($): perda = (buyback − credito)*mult. Reiner SPX = $300.
        loss_usd = (buyback - cr) * self.mult
        for L in self.loss_stops:
            if d["cross_ls"][L] is None and loss_usd >= L:
                d["cross_ls"][L] = (hoff, bb, dS)
        # SAIDA POR TEMPO: buyback no 1o toque de dte<=n
        dte_now = (d["expiry"] - self.time.date()).days
        for n in self.dte_exits:
            if d["dte_bb"][n] is None and dte_now <= n:
                d["dte_bb"][n] = (hoff, bb, dS)
        # EXIT WHEN TESTED: SÓ o lado PUT (o short call e ITM POR DESIGN -> "S>=sc" seria verdade
        # desde a entrada; o teste que importa e o downside furar o short put).
        if d["cross_tested"] is None and S <= d["sp"]:
            d["cross_tested"] = (hoff, bb, dS)

    # ===================== SETTLE =====================
    def _settle_due(self):
        if not self.open_ds:
            return
        S_T = self.securities[self.idx].price
        still = []
        for d in self.open_ds:
            if d["expiry"] != self.time.date():
                still.append(d); continue
            if d.get("closed"):
                continue
            put_loss  = min(d["put_w"],  max(0.0, d["sp"] - S_T))
            call_loss = min(d["call_w"], max(0.0, S_T - d["sc"]))
            pnl_pts = d["credit"] - put_loss - call_loss
            d["put_side_pnl"]  = round((d["credit"] / 2.0 - put_loss) * self.mult, 2)
            d["call_side_pnl"] = round((d["credit"] / 2.0 - call_loss) * self.mult, 2)
            self._record(d, S_T, pnl_pts, "expiry")
        self.open_ds = still

    def _record(self, d, S_T, pnl_pts, reason):
        commissions = round(4 * self.comm_leg, 2)        # entrada 4 pernas; cash-settle = sem saida
        net = round(pnl_pts * self.mult, 2)

        def pack(x):   # (hoff, buyback, dS) -> "hoff:buyback:dS" ou ""
            return f"{x[0]}:{x[1]}:{x[2]}" if x else ""

        row = {
            "id": d["id"], "open_date": d["open_date"].strftime("%Y-%m-%d"),
            "open_time": d["open_time"].strftime("%H:%M"),
            "expiry_date": d["expiry"].strftime("%Y-%m-%d"), "dte_entry": d["dte"],
            "dow": d["open_time"].strftime("%A"),
            "vix": round(d["vix"], 2), "underlying": self.ticker,
            "S_entry": round(d["S_entry"], 2), "S_settle": round(S_T, 2),
            "long_put": d["lp"], "short_put": d["sp"], "short_call": d["sc"], "long_call": d["lc"],
            "put_width": d["put_w"], "call_width": d["call_w"],
            "sp_delta": round(d["sp_delta"], 4) if d["sp_delta"] is not None else "",
            "sc_delta": round(d["sc_delta"], 4) if d["sc_delta"] is not None else "",
            "credit": round(d["credit"], 2),
            "credit_mid": round(d["credit_mid"], 2), "credit_cons": round(d["credit_cons"], 2),
            "max_loss_usd": round(d["max_loss_pts"] * self.mult, 2),
            "be_low": round(d["sp"] - d["credit"], 2), "be_high": round(d["sc"] + d["credit"], 2),
            "max_value": round(d["max_value"], 2),
            "cross_tested": pack(d.get("cross_tested")),
            "put_side_pnl": d.get("put_side_pnl", ""), "call_side_pnl": d.get("call_side_pnl", ""),
            "exit_reason": reason,
            "commissions": commissions,
            "settle_pnl_pts": round(pnl_pts, 2), "settle_net": net,
            "settle_result": "W" if pnl_pts > 0 else "L",
        }
        for lvl in self.profit_levels:
            row[f"tp{int(lvl*100)}"] = pack(d["cross_p"][lvl])
        for m in self.stop_mults:
            row[f"sm{int(m*10)}"] = pack(d["cross_sm"][m])
        for L in self.loss_stops:
            row[f"ls{L}"] = pack(d["cross_ls"][L])
        for n in self.dte_exits:
            row[f"dte{n}"] = pack(d["dte_bb"][n])
        self.rows.append(row)

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
    def _mid(c):
        b, a = c.bid_price, c.ask_price
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return c.last_price or a or b or 0.0

    def _skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    # ===================== EXPORT / RUNTIME STATS =====================
    def _derive(self, r, rule):
        """P&L de uma regra a partir dos first-touch gravados. buyback -> P&L = (credit - buyback)*mult."""
        cr = r["credit"]; settle = r["settle_net"]

        def bb_of(field):
            v = r.get(field, "")
            if v in ("", None):
                return None
            try:
                return float(str(v).split(":")[1])
            except Exception:
                return None

        if rule == "hold":
            return settle
        if rule.startswith("tp"):
            bb = bb_of(rule)
            return (cr - bb) * self.mult if bb is not None else settle
        if rule.startswith("sm") or rule.startswith("ls"):
            bb = bb_of(rule)
            return (cr - bb) * self.mult if bb is not None else settle
        if rule.startswith("dte"):
            bb = bb_of(rule)
            return (cr - bb) * self.mult if bb is not None else settle
        if rule == "tested":
            bb = bb_of("cross_tested")
            return (cr - bb) * self.mult if bb is not None else settle
        return settle

    def _emit_runtime_stats(self):
        rows = self.rows
        if not rows:
            self.set_runtime_statistic("WARN", "0 trades")
            return
        from collections import defaultdict
        import statistics as _st

        # headline hold
        net = sum(r["settle_net"] for r in rows)
        wr = 100.0 * sum(1 for r in rows if r["settle_net"] > 0) / len(rows)
        self.set_runtime_statistic("NET hold", f"${net:,.0f} / WR {wr:.0f}%")
        self.set_runtime_statistic("trades", str(len(rows)))
        self.set_runtime_statistic("credit med", f"{_st.median(r['credit'] for r in rows):.2f}")
        self.set_runtime_statistic("maxloss med usd", f"{_st.median(r['max_loss_usd'] for r in rows):.0f}")
        self.set_runtime_statistic("sp_delta med", f"{_st.median(abs(float(r['sp_delta'])) for r in rows if r['sp_delta'] not in ('', None)):.3f}")
        self.set_runtime_statistic("sc_delta med", f"{_st.median(abs(float(r['sc_delta'])) for r in rows if r['sc_delta'] not in ('', None)):.3f}")
        self.set_runtime_statistic("skips", str(len(self.skips)))

        # por ano
        by_yr, cnt = defaultdict(float), defaultdict(int)
        for r in rows:
            by_yr[r["open_date"][:4]] += r["settle_net"]; cnt[r["open_date"][:4]] += 1
        for yr in sorted(by_yr):
            self.set_runtime_statistic(f"Y {yr}", f"${by_yr[yr]:,.0f} (n={cnt[yr]})")

        # cada regra isolada
        rules = ["hold"] + [f"tp{int(l*100)}" for l in self.profit_levels] \
                + [f"sm{int(m*10)}" for m in self.stop_mults] \
                + [f"ls{L}" for L in self.loss_stops] \
                + [f"dte{n}" for n in self.dte_exits] + ["tested"]
        for rule in rules:
            ps = [self._derive(r, rule) for r in rows]
            n = sum(ps); w = 100.0 * sum(1 for x in ps if x > 0) / len(ps)
            worst = min(ps)                              # pior trade unico = o quanto a regra CAPA a perda
            self.set_runtime_statistic(f"R {rule}", f"${n:,.0f} / WR {w:.0f}% / pior ${worst:,.0f}")

        # COMBOS EXATOS do Reiner (SEM "tested"): SPX=TP40+5DTE+stop · RUT=TP50+5DTE · SPY=TP50+2DTE.
        # first-touch por horas desde a abertura. Cada campo passado e um gatilho ativo.
        def combo_pnl(r, fields):
            cr = r["credit"]
            cands = []
            for f in fields:
                v = r.get(f, "")
                if v not in ("", None):
                    parts = str(v).split(":")
                    cands.append((int(parts[0]), float(parts[1])))
            if not cands:
                return r["settle_net"]
            cands.sort(key=lambda x: x[0])
            return (cr - cands[0][1]) * self.mult
        combos = {
            "C SPX-reiner tp40+dte5+ls300": ["tp40", "dte5", "ls300"],   # $300 stop (config exata)
            "C SPX tp40+dte5+ls750":        ["tp40", "dte5", "ls750"],
            "C SPX tp40+dte5+ls1500":       ["tp40", "dte5", "ls1500"],
            "C RUT-reiner tp50+dte5":       ["tp50", "dte5"],
            "C SPY-reiner tp50+dte2":       ["tp50", "dte2"],
            "C tp40+dte5 (no stop)":        ["tp40", "dte5"],
        }
        for lbl, fields in combos.items():
            ps = [combo_pnl(r, fields) for r in rows]
            n = sum(ps); w = 100.0 * sum(1 for x in ps if x > 0) / len(ps)
            worst = min(ps)
            self.set_runtime_statistic(lbl, f"${n:,.0f} / WR {w:.0f}% / pior ${worst:,.0f}")

    def on_end_of_algorithm(self):
        self._emit_runtime_stats()
        cols = ["id", "open_date", "open_time", "dow", "expiry_date", "dte_entry", "underlying",
                "vix", "S_entry", "S_settle", "long_put", "short_put", "short_call", "long_call",
                "put_width", "call_width", "sp_delta", "sc_delta", "credit", "credit_mid",
                "credit_cons", "max_loss_usd", "be_low", "be_high", "max_value",
                "cross_tested", "put_side_pnl", "call_side_pnl", "exit_reason", "commissions",
                "settle_pnl_pts", "settle_net", "settle_result"]
        cols += [f"tp{int(l*100)}" for l in self.profit_levels]
        cols += [f"sm{int(m*10)}" for m in self.stop_mults]
        cols += [f"ls{L}" for L in self.loss_stops]
        cols += [f"dte{n}" for n in self.dte_exits]
        self.log("DUCKHDR|" + ",".join(cols) + f"|tag={self.run_tag}")
        for r in self.rows:
            self.log("DUCK|" + ",".join(str(r.get(c, "")) for c in cols))
        # skips resumidos
        from collections import Counter
        sk = Counter(reason for _, reason in self.skips)
        for reason, n in sk.most_common(10):
            self.log(f"SKIP|{n}|{reason}")
