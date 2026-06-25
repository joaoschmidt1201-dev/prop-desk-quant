# region imports
from AlgorithmImports import *
import math
# endregion

class ShortStrangleRUT(QCAlgorithm):
    """
    SHORT STRANGLE RUT (pedido CZ 2026-06-24) — venda de vol naked em RUT, multi-semana.
    Liga: context/PROJECT_short_strangle_rut_backtest.md.

    SPEC (CZ):
      - ATIVO: RUT (índice Russell 2000, europeu, cash-settled, $100/pt).
      - ENTRADA: TODA sexta-feira, um trade novo (vários concorrentes ao mesmo tempo).
      - DTE de entrada: 28 / 35 / 42 (um run por config; pega o expiry com DTE mais próximo do alvo).
      - SHORT PUT ~0.10 delta / SHORT CALL ~0.08 delta (delta da chain -> fallback Black-Scholes).
      - FILL: mid (headline). Loga também conservador (shorts@bid) p/ medir slippage.
      - CLOSE RULES (record-and-derive, TODAS de UMA run; nada é fechado cedo, tudo segura até expiry):
          M0  Hold to expiration
          TP  25% / 50% / 75% do crédito (captura X%)
          DTE Exit @ 14 DTE  /  Exit @ 7 DTE
          combos "TP ou DTE, o que vier primeiro" (TP25|14, TP50|14, TP75|14, TP25|7, TP50|7, TP75|7)
        -> 12 regras por config, derivadas pelo pós-proc dos cruzamentos gravados (first-touch + DATA).

    MARGEM: strangle é NAKED (sem asas). Naked short índice estoura BP no QC e gera artefato
    (ver memória project_qc_optionstrategy_margin_crash). Como o desk lê o P&L do PAYOFF ANALÍTICO
    (não do blotter/equity), setamos BuyingPowerModel.NULL via security-initializer -> as entradas
    preenchem, nada é liquidado à força, e o resultado vem do payoff. Cash-settle europeu no expiry.
    """

    def initialize(self):
        self.entry_hour   = int(self.get_parameter("entry_hour", "10"))
        self.entry_minute = int(self.get_parameter("entry_minute", "0"))
        self.target_dp    = float(self.get_parameter("target_delta_put",  "0.10"))
        self.target_dc    = float(self.get_parameter("target_delta_call", "0.08"))
        self.target_dte   = int(self.get_parameter("target_dte", "42"))      # 28 | 35 | 42 (1 run cada)
        # saídas por tempo (record-and-derive): grava o buyback no 1º dia em que DTE<=cada limiar.
        self.exit_dte_a   = int(self.get_parameter("exit_dte_a", "14"))
        self.exit_dte_b   = int(self.get_parameter("exit_dte_b", "7"))
        self.strike_filter = int(self.get_parameter("strike_filter", "120"))
        self.ticker       = self.get_parameter("ticker", "RUT")
        # alvo de opção: RUT weeklies costumam ser "RUTW". "" -> add_index_option default (monthly).
        self.opt_target   = self.get_parameter("opt_target", "RUTW").strip()
        self.fill_mode    = self.get_parameter("fill_mode", "mid").lower().strip()   # CZ: mid
        self.comm_leg     = float(self.get_parameter("commission_per_contract", "1.5"))
        sd = self.get_parameter("start_date", "2021-06-01").split("-")
        ed = self.get_parameter("end_date",   "2026-06-01").split("-")
        self.run_tag = self.get_parameter("run_tag", "SS_RUT_42")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(1_000_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        # NULL buying power: naked não bloqueia entrada nem dispara liquidação; P&L vem do payoff.
        self.set_security_initializer(lambda s: s.set_buying_power_model(BuyingPowerModel.NULL))
        self.settings.minimum_order_margin_portfolio_percentage = 0

        index = self.add_index(self.ticker, Resolution.MINUTE)
        self.idx = index.symbol
        if self.opt_target:
            option = self.add_index_option(self.idx, self.opt_target, Resolution.MINUTE)
        else:
            option = self.add_index_option(self.idx, Resolution.MINUTE)
        # janela ampla (0..target+7): o contrato vendido fica na cadeia a vida toda (marcação estável).
        option.set_filter(lambda u: u.include_weeklys()
                          .expiration(0, self.target_dte + 7)
                          .strikes(-self.strike_filter, self.strike_filter))
        self.opt = option.symbol

        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        self.mark_every_min = 30
        self.profit_levels = [0.25, 0.50, 0.75]      # TP do CZ
        self.rows = []
        self.skips = []
        self.open_pos = []
        self.entered_today = False
        self.current_day = None
        self.seq = 0
        self._chain_seen = 0     # diagnóstico smoke-test: quantas vezes vimos cadeia não-vazia

        self.schedule.on(self.date_rules.every_day(self.idx),
                         self.time_rules.at(16, 1), self._settle_due)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.current_day != self.time.date():
            self.current_day = self.time.date()
            self.entered_today = False

        # marcação periódica de TODAS as posições abertas (grava TP first-touch + snapshots DTE)
        if self.time.minute % self.mark_every_min == 0:
            chain = slice.option_chains.get(self.opt)
            for pos in self.open_pos:
                self._mark(pos)

        # entrada só na SEXTA, após o horário, uma vez/dia
        if self.entered_today or self.time.weekday() != 4:
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return
        chain = slice.option_chains.get(self.opt)
        if chain is None:
            return
        contracts = [c for c in chain]
        if not contracts:
            self.entered_today = True
            self._skip("cadeia vazia"); return
        self._chain_seen += 1
        self._enter(contracts, self.securities[self.vix].price)
        self.entered_today = True

    # ===================== ENTRADA =====================
    def _enter(self, contracts, vix):
        S = self.securities[self.idx].price
        today = self.time.date()
        # expiry com DTE mais próximo do alvo (>=1 DTE)
        exps = sorted({c.expiry.date() for c in contracts if (c.expiry.date() - today).days >= 1})
        if not exps:
            self._skip("sem expiry futuro"); return
        expiry = min(exps, key=lambda e: abs((e - today).days - self.target_dte))
        dte = (expiry - today).days
        legs = [c for c in contracts if c.expiry.date() == expiry]

        sp = self._pick_by_delta(legs, OptionRight.PUT,  S, expiry, self.target_dp)
        sc = self._pick_by_delta(legs, OptionRight.CALL, S, expiry, self.target_dc)
        if sp is None or sc is None:
            self._skip("sem short put/call no delta"); return

        credit_mid  = self._mid(sp) + self._mid(sc)
        credit_cons = sp.bid_price + sc.bid_price               # vende os dois no bid (conservador)
        credit = credit_mid if self.fill_mode == "mid" else credit_cons
        if credit <= 0:
            self._skip(f"crédito<=0 ({credit:.2f})"); return

        # vende as duas pernas soltas (naked). NULL BP -> preenche sem estourar margem.
        self.market_order(sp.symbol, -1)
        self.market_order(sc.symbol, -1)
        self.seq += 1
        pos = {
            "id": self.seq, "open_time": self.time, "open_date": today, "expiry": expiry,
            "dte_entry": dte, "S_entry": S, "vix": vix,
            "sp": sp.strike, "sc": sc.strike, "sp_sym": sp.symbol, "sc_sym": sc.symbol,
            "sp_delta": self._delta(sp, S, expiry), "sc_delta": self._delta(sc, S, expiry),
            "credit": credit, "credit_mid": credit_mid, "credit_cons": credit_cons,
            "cross_p": {lvl: None for lvl in self.profit_levels},   # lvl -> (date, dit, buyback)
            "ds_a": None, "ds_b": None,                              # snapshot @ exit_dte_a / _b
            "closed": False,
        }
        self.open_pos.append(pos)
        if self.seq <= 3:
            self.debug(f"{self.time} SS#{self.seq} dte={dte} P{sp.strike}/C{sc.strike} "
                       f"cr={credit:.2f} dP={pos['sp_delta']} dC={pos['sc_delta']} vix={vix:.1f}")

    def _pick_by_delta(self, legs, right, S, expiry, target):
        """Short strike: |delta| mais próximo do alvo no lado certo (put<S, call>S)."""
        side = [c for c in legs if c.right == right and
                (c.strike < S if right == OptionRight.PUT else c.strike > S)]
        best, bestgap = None, 1e9
        for c in side:
            d = self._delta(c, S, expiry)
            if d is None:
                continue
            gap = abs(abs(d) - target)
            if gap < bestgap:
                best, bestgap = c, gap
        return best

    # ===================== MARCAÇÃO (grava TP + snapshots DTE) =====================
    def _mark(self, pos):
        if pos.get("closed"):
            return
        # buyback (custo de fechar) no MID, coerente com o fill headline=mid
        sp_b = self.securities[pos["sp_sym"]].bid_price; sp_a = self.securities[pos["sp_sym"]].ask_price
        sc_b = self.securities[pos["sc_sym"]].bid_price; sc_a = self.securities[pos["sc_sym"]].ask_price
        sp_mid = (sp_b + sp_a) / 2.0 if (sp_b > 0 and sp_a > 0) else (sp_a or sp_b)
        sc_mid = (sc_b + sc_a) / 2.0 if (sc_b > 0 and sc_a > 0) else (sc_a or sc_b)
        if sp_mid <= 0 and sc_mid <= 0:
            return
        buyback = sp_mid + sc_mid
        cr = pos["credit"]
        dte_now = (pos["expiry"] - self.time.date()).days
        dit = (self.time.date() - pos["open_date"]).days

        # TP X%: recompra barata (<= (1-X)*crédito) — first-touch (DATA + DIT + buyback)
        for lvl in self.profit_levels:
            if pos["cross_p"][lvl] is None and buyback <= (1.0 - lvl) * cr:
                pos["cross_p"][lvl] = (self.time.strftime("%Y-%m-%d"), dit, round(buyback, 2))

        # snapshots por DTE: 1º dia em que DTE <= limiar (grava DATA + DIT + buyback)
        if pos["ds_a"] is None and dte_now <= self.exit_dte_a:
            pos["ds_a"] = (self.time.strftime("%Y-%m-%d"), dit, round(buyback, 2))
        if pos["ds_b"] is None and dte_now <= self.exit_dte_b:
            pos["ds_b"] = (self.time.strftime("%Y-%m-%d"), dit, round(buyback, 2))

    # ===================== SETTLE (cash-settle europeu) =====================
    def _settle_due(self):
        if not self.open_pos:
            return
        S_T = self.securities[self.idx].price
        still = []
        for pos in self.open_pos:
            if pos["expiry"] != self.time.date():
                still.append(pos); continue
            put_loss  = max(0.0, pos["sp"] - S_T)        # naked: sem cap
            call_loss = max(0.0, S_T - pos["sc"])
            pnl_pts = pos["credit"] - put_loss - call_loss
            # zera holdings residuais no settle (cash-settle limpo)
            for sym in (pos["sp_sym"], pos["sc_sym"]):
                if self.portfolio[sym].invested:
                    self.liquidate(sym)
            self._record(pos, S_T, pnl_pts)
        self.open_pos = still

    def _record(self, pos, S_T, pnl_pts):
        def r(x, n=2):
            return round(x, n) if isinstance(x, (int, float)) else ""
        cp = pos["cross_p"]; da = pos["ds_a"]; db = pos["ds_b"]
        net = round(pnl_pts * 100.0, 2)
        commissions = round(2 * self.comm_leg, 2)        # 2 pernas na entrada (cash-settle = sem saída)
        self.rows.append({
            "id": pos["id"], "open_date": pos["open_date"].strftime("%Y-%m-%d"),
            "expiry_date": pos["expiry"].strftime("%Y-%m-%d"), "dte_entry": pos["dte_entry"],
            "vix": round(pos["vix"], 2), "vix_bucket": self._vix_bucket(pos["vix"]),
            "S_entry": round(pos["S_entry"], 2), "S_settle": round(S_T, 2),
            "short_put": pos["sp"], "short_call": pos["sc"],
            "sp_delta": round(pos["sp_delta"], 4) if pos["sp_delta"] is not None else "",
            "sc_delta": round(pos["sc_delta"], 4) if pos["sc_delta"] is not None else "",
            "credit": round(pos["credit"], 2), "credit_mid": r(pos["credit_mid"]),
            "credit_cons": r(pos["credit_cons"]),
            "gross_credit_mid": r(pos["credit_mid"] * 100.0),
            "gross_credit_cons": r(pos["credit_cons"] * 100.0),
            **{f"tp{int(l*100)}_date": (cp[l][0] if cp[l] else "") for l in self.profit_levels},
            **{f"tp{int(l*100)}_dit":  (cp[l][1] if cp[l] else "") for l in self.profit_levels},
            **{f"tp{int(l*100)}_v":    (cp[l][2] if cp[l] else "") for l in self.profit_levels},
            "dsa_date": da[0] if da else "", "dsa_dit": da[1] if da else "", "dsa_v": da[2] if da else "",
            "dsb_date": db[0] if db else "", "dsb_dit": db[1] if db else "", "dsb_v": db[2] if db else "",
            "exit_dte_a": self.exit_dte_a, "exit_dte_b": self.exit_dte_b,
            "commissions": commissions,
            "settle_pnl_pts": round(pnl_pts, 2), "settle_net": net,
            "settle_result": "W" if pnl_pts > 0 else "L",
        })

    # ===================== GREEKS / HELPERS =====================
    def _delta(self, c, S, expiry):
        # 1) greeks da cadeia (quando o QC popula)
        try:
            g = c.greeks
            if g is not None and g.delta is not None and abs(g.delta) > 1e-6:
                return float(g.delta)
        except Exception:
            pass
        if S <= 0 or c.strike <= 0:
            return None
        exp_dt = datetime(expiry.year, expiry.month, expiry.day, 16, 0)
        T = max((exp_dt - self.time).total_seconds() / (365.0 * 24 * 3600), 1e-6)
        # 2) IV da cadeia -> 3) fallback: inverte IV do MID (BS), gold-standard do SS42.
        #    Sem isso, dias com IV/greeks esparsos só "enxergam" strikes distantes -> delta errado.
        iv = c.implied_volatility or 0.0
        if iv <= 0:
            iv = self._iv_from_mid(c, S, c.strike, T) or 0.0
        if iv <= 0:
            return None
        d1 = (math.log(S / c.strike) + (0.04 + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
        nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
        return nd1 if c.right == OptionRight.CALL else nd1 - 1.0

    @staticmethod
    def _bs_price(right, S, K, T, sigma, r=0.04):
        if sigma <= 0 or T <= 0:
            intr = (S - K) if right == OptionRight.CALL else (K - S)
            return max(0.0, intr)
        srt = sigma * math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / srt
        d2 = d1 - srt
        nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
        nd2 = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
        disc = math.exp(-r * T)
        if right == OptionRight.CALL:
            return S * nd1 - K * disc * nd2
        return K * disc * (1.0 - nd2) - S * (1.0 - nd1)

    def _iv_from_mid(self, c, S, K, T):
        """IV implícita por bisseção a partir do mid (Black-Scholes europeu)."""
        px = self._mid(c)
        if px <= 0:
            return None
        lo, hi = 0.01, 3.0
        plo = self._bs_price(c.right, S, K, T, lo)
        phi = self._bs_price(c.right, S, K, T, hi)
        if not (plo <= px <= phi):       # fora do bracket (deep ITM/arbitragem) -> descarta
            return None
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            pm = self._bs_price(c.right, S, K, T, mid)
            if pm < px:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    @staticmethod
    def _mid(c):
        b, a = c.bid_price, c.ask_price
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return c.last_price or a or b or 0.0

    @staticmethod
    def _vix_bucket(vix):
        if vix < 15:  return "<15"
        if vix < 17:  return "15-17"
        if vix < 22:  return "17-22"
        if vix < 32:  return "22-32"
        return "32+"

    def _skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    # ===================== DERIVAÇÃO DAS 12 REGRAS =====================
    def _rule_pnl(self, r, rule):
        """P&L (em $) de cada close rule, derivado dos cruzamentos gravados. mid headline."""
        cr = r["credit"]; settle = r["settle_net"]
        def tp_hit(lvl):  return r.get(f"tp{lvl}_v") not in ("", None)
        def tp_dit(lvl):  return r.get(f"tp{lvl}_dit")
        def tp_pnl(lvl):  return cr * (lvl / 100.0) * 100.0
        def dte_pnl(key):
            v = r.get(key)
            return (cr - float(v)) * 100.0 if v not in ("", None) else settle
        def dte_dit(key): return r.get(key)

        if rule == "hold":
            return settle
        if rule in ("tp25", "tp50", "tp75"):
            lvl = int(rule[2:]); return tp_pnl(lvl) if tp_hit(lvl) else settle
        if rule == "dte_a":  return dte_pnl("dsa_v")
        if rule == "dte_b":  return dte_pnl("dsb_v")
        # combos: "TP ou DTE, o que vier primeiro" (compara DIT)
        if "_" in rule and rule[:2] == "tp":
            lvl = int(rule[2:4]); dkey = rule[5:]                 # ex.: tp25_a -> lvl25, snapshot a
            vkey = "dsa_v" if dkey == "a" else "dsb_v"; ditkey = "dsa_dit" if dkey == "a" else "dsb_dit"
            tdit = tp_dit(lvl); ddit = r.get(ditkey)
            tp_first = tp_hit(lvl) and (tdit not in ("", None)) and \
                       (ddit in ("", None) or int(tdit) <= int(ddit))
            return tp_pnl(lvl) if tp_first else dte_pnl(vkey)
        return settle

    def _emit_runtime_stats(self):
        rows = self.rows
        if not rows:
            self.set_runtime_statistic("WARN", "0 trades — cadeia/dados RUT?")
            return
        from collections import defaultdict
        rules = ["hold", "tp25", "tp50", "tp75", "dte_a", "dte_b",
                 "tp25_a", "tp50_a", "tp75_a", "tp25_b", "tp50_b", "tp75_b"]
        for rule in rules:
            ps = [self._rule_pnl(r, rule) for r in rows]
            net = sum(ps); wr = 100.0 * sum(1 for x in ps if x > 0) / len(ps)
            self.set_runtime_statistic(f"R {rule}", f"${net:,.0f} / WR {wr:.0f}% (n={len(ps)})")
        # quebra por ano e VIX no baseline hold
        by_yr, cnt = defaultdict(float), defaultdict(int)
        for r in rows:
            by_yr[r["open_date"][:4]] += r["settle_net"]; cnt[r["open_date"][:4]] += 1
        for yr in sorted(by_yr):
            self.set_runtime_statistic(f"hold {yr}", f"${by_yr[yr]:,.0f} (n={cnt[yr]})")
        for b in ["<15", "15-17", "17-22", "22-32", "32+"]:
            rs = [r for r in rows if r["vix_bucket"] == b]
            if rs:
                self.set_runtime_statistic(f"hold VIX {b}",
                                           f"${sum(r['settle_net'] for r in rs):,.0f} (n={len(rs)})")
        import statistics as _st
        self.set_runtime_statistic("credit med (pts)", f"{_st.median(r['credit'] for r in rows):.2f}")
        self.set_runtime_statistic("dte_entry med", f"{_st.median(r['dte_entry'] for r in rows):.0f}")
        self.set_runtime_statistic("exits a/b", f"{self.exit_dte_a}/{self.exit_dte_b} DTE")
        # --- diagnóstico de delta (veridicidade: confirma 0.10/0.08 e quantos desviam) ---
        spd = [abs(float(r["sp_delta"])) for r in rows if r.get("sp_delta") not in ("", None)]
        scd = [abs(float(r["sc_delta"])) for r in rows if r.get("sc_delta") not in ("", None)]
        if spd:
            self.set_runtime_statistic("absDelta put med/min/max",
                f"{_st.median(spd):.3f} / {min(spd):.3f} / {max(spd):.3f}")
            off = sum(1 for d in spd if not (0.5*self.target_dp <= d <= 2.0*self.target_dp))
            self.set_runtime_statistic("delta put off-target", f"{off}/{len(spd)}")
        if scd:
            self.set_runtime_statistic("absDelta call med/min/max",
                f"{_st.median(scd):.3f} / {min(scd):.3f} / {max(scd):.3f}")
            off = sum(1 for d in scd if not (0.5*self.target_dc <= d <= 2.0*self.target_dc))
            self.set_runtime_statistic("delta call off-target", f"{off}/{len(scd)}")
        self.set_runtime_statistic("skips", str(len(self.skips)))

    def on_end_of_algorithm(self):
        cols = (["id", "open_date", "expiry_date", "dte_entry", "vix", "vix_bucket",
                 "S_entry", "S_settle", "short_put", "short_call", "sp_delta", "sc_delta",
                 "credit", "credit_mid", "credit_cons", "gross_credit_mid", "gross_credit_cons"]
                + [f"tp{int(l*100)}_date" for l in self.profit_levels]
                + [f"tp{int(l*100)}_dit" for l in self.profit_levels]
                + [f"tp{int(l*100)}_v" for l in self.profit_levels]
                + ["dsa_date", "dsa_dit", "dsa_v", "dsb_date", "dsb_dit", "dsb_v",
                   "exit_dte_a", "exit_dte_b", "commissions",
                   "settle_pnl_pts", "settle_net", "settle_result"])
        lines = [",".join(cols)] + [",".join(str(r.get(c, "")) for c in cols) for r in self.rows]
        try:
            self.object_store.save(f"ss_strangle_{self.run_tag}.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou: {e}")

        # CANAL ROBUSTO: log compacto CTRADE (ObjectStore download é bloqueado no free tier).
        # Tudo que o pós-proc precisa p/ derivar as 12 regras: credit (mid+cons), settle, TP (DIT,
        # touched), snapshots a/b (DIT + buyback). ~260 trades/run cabe no cap de log.
        plv = [int(l * 100) for l in self.profit_levels]
        chdr = ["id", "date", "exp", "dte", "vix", "sE", "sT", "sp", "sc", "spd", "scd",
                "crM", "crC", "pnl", "tp25dit", "tp50dit", "tp75dit",
                "aDit", "aV", "bDit", "bV"]
        self.log("CTRADEHDR|" + ",".join(chdr) + "|plv=" + "/".join(str(x) for x in plv)
                 + f"|exits={self.exit_dte_a}/{self.exit_dte_b}")
        for r in self.rows:
            row = [r["id"], r["open_date"], r["expiry_date"], r["dte_entry"],
                   r.get("vix", ""), r.get("S_entry", ""), r.get("S_settle", ""),
                   r["short_put"], r["short_call"], r.get("sp_delta", ""), r.get("sc_delta", ""),
                   r.get("credit_mid", ""), r.get("credit_cons", ""), r.get("settle_pnl_pts", ""),
                   r.get("tp25_dit", ""), r.get("tp50_dit", ""), r.get("tp75_dit", ""),
                   r.get("dsa_dit", ""), r.get("dsa_v", ""), r.get("dsb_dit", ""), r.get("dsb_v", "")]
            self.log("CTRADE|" + ",".join(str(x) for x in row))
        self._emit_runtime_stats()
        n = len(self.rows)
        net = sum(r["settle_net"] for r in self.rows)
        w = sum(1 for r in self.rows if r["settle_result"] == "W")
        self.log(f"=== SHORT STRANGLE RUT [{self.run_tag}] === n={n} | "
                 f"W={w} ({(w/n*100 if n else 0):.0f}%) | net hold=${net:,.0f} | "
                 f"chain_seen={self._chain_seen} | skips={len(self.skips)}")
        for d, why in self.skips[:8]:
            self.log(f"SKIP|{d}|{why}")
