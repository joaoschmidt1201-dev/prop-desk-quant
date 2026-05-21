# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class Fase1ClassicOtmFly(QCAlgorithm):
    """
    PROJETO Ernie Butterfly Backtest — FASE 1 (baseline)
    Charter: context/0DTE strategies/PROJECT_qc_backtest_scope.md

    Classic OTM 0DTE butterfly em SPXW.
      - Dias:    seg/ter/qua (cadência do Ernie)
      - Entrada: horário fixo (10:00 ET)
      - Lado:    tendência via EMA9 diária (Call fly acima em uptrend / Put fly abaixo em downtrend); chop -> pula
      - Center:  ~sigma_mult * expected move de 1 dia OTM (sigma vindo da IV ATM da cadeia)
      - Asa:     fixa em pts; debit limitado a debit_cap_frac da asa (pula o dia se exceder)
      - Gestão:  hold-to-expiry (SPXW PM cash-settle). Hook de profit target p/ Fase 2.

    Emite log por-trade no ObjectStore (`fase1_trades.csv`) para ingestão no app do desk
    (CZ Dashboard / Trade Auditor) — colunas alinhadas ao log do Ernie + extras.

    >>> Validação curta (nov/2024) JÁ PASSOU. Agora rodamos o estudo por BLOCOS DE ANO:
        2024 -> 2022(jun→dez) -> 2023 -> 2025 -> 2026 (o Claude costura os CSVs). <<<
    """

    # ===================== CONFIG (parâmetros varríveis) =====================
    def initialize(self):
        # ---- Estudo de ANO INTEIRO — bloco 2024 (fix de settlement VALIDADO na janela curta:
        # nov/2024 deu End Equity +$175 ≈ analítico +$185, winner 06/nov pagou +$985 cheio,
        # zero perna fantasma). Depois de 2024: 2022(jun→dez)/2023/2025/2026. ----
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        # ---- Parâmetros ----
        self.entry_hour, self.entry_minute = 10, 0     # ET
        self.trade_weekdays = {0, 1, 2}                # Mon=0, Tue=1, Wed=2
        self.use_hull = False                          # False = EMA9 (default desk) | True = Hull MA (default Ernie)
        self.ma_period = 9
        self.placement_mode = "debit"                  # "debit" = 0DTE (regra real do Ernie) | "sigma" = DTE alto (Convexity/Sigma Drift)
        self.target_debit_frac = 0.10                  # modo "debit": center OTM onde debit ~ 10% da asa (R:R ~1:9)
        self.sigma_mult = 2.0                          # modo "sigma": center a N*sigma OTM (varrer 1.75-2.5) — só p/ DTE alto
        self.wing = 30                                 # asa em pts SPX (varrer 20 / 25 / 30 / 35)
        self.debit_cap_frac = 0.10                     # debit máximo = 10% da asa (regra do Ernie)
        self.enforce_debit_cap = True                  # True = pula o dia se debit > cap
        self.profit_target_frac = None                 # None = hold-to-expiry | ex.: 0.5 = sai a 50% do lucro máx (Fase 2)

        # ---- Universo ----
        index = self.add_index("SPX", Resolution.MINUTE)
        self.spx = index.symbol
        # SPXW = contratos weekly/daily (têm 0DTE todo dia). AJUSTAR se o QC reclamar da assinatura.
        option = self.add_index_option(self.spx, "SPXW", Resolution.MINUTE)
        # strikes(min,max) = Nº DE STRIKES em torno do ATM (não pontos). ±60 cobre folgado a fly 0DTE
        # (center ~10-120 pts OTM + asa) e mantém o backtest leve — essencial p/ o run 2022→presente no tier free.
        option.set_filter(lambda u: u.include_weeklys().expiration(0, 0).strikes(-60, 60))
        self.spxw = option.symbol

        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        # ---- MA de tendência no diário ----
        self.ma = self.hma(self.spx, self.ma_period, Resolution.DAILY) if self.use_hull \
            else self.ema(self.spx, self.ma_period, Resolution.DAILY)
        self.ma_hist = RollingWindow[float](3)         # série diária da MA p/ medir slope

        self.set_warm_up(timedelta(days=40))

        # ---- Estado ----
        self.trades = []
        self.skips = []
        self.open_trade = None
        self.entered_today = False
        self.current_day = None

        # Liquidação/registro do trade na expiração (16:01 ET, após o close)
        self.schedule.on(self.date_rules.every_day(self.spx),
                         self.time_rules.at(16, 1),
                         self._settle_open_trade)

    # ===================== TENDÊNCIA =====================
    def _trend_bias(self):
        """+1 bullish (call fly), -1 bearish (put fly), 0 chop (pula)."""
        if not self.ma.is_ready or self.ma_hist.count < 2:
            return 0
        price = self.securities[self.spx].price
        ma_now, ma_prev = self.ma_hist[0], self.ma_hist[1]
        slope_up = ma_now > ma_prev
        if price > ma_now and slope_up:
            return 1
        if price < ma_now and not slope_up:
            return -1
        return 0

    # ===================== LOOP PRINCIPAL =====================
    def on_data(self, slice: Slice):
        # novo dia -> reset + amostra a MA diária (reflete o último close diário)
        if self.current_day != self.time.date():
            self.current_day = self.time.date()
            self.entered_today = False
            if self.ma.is_ready:
                self.ma_hist.add(self.ma.current.value)

        if self.is_warming_up:
            return

        # gestão do trade aberto (só age se houver profit target — Fase 2)
        if self.open_trade is not None and self.profit_target_frac is not None:
            self._check_profit_target(slice)

        # ---- entrada ----
        if self.entered_today or self.open_trade is not None:
            return
        if self.time.weekday() not in self.trade_weekdays:
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return

        bias = self._trend_bias()
        if bias == 0:
            self.entered_today = True
            self._log_skip("chop/flat")
            return

        chain = slice.option_chains.get(self.spxw)
        if chain is None:
            return  # cadeia ainda não chegou neste minuto; tenta no próximo
        contracts = [c for c in chain]
        if not contracts:
            self.entered_today = True
            self._log_skip("cadeia vazia")
            return

        self._enter_fly(contracts, bias)
        self.entered_today = True

    # ===================== ENTRADA =====================
    def _enter_fly(self, contracts, bias):
        right = OptionRight.CALL if bias == 1 else OptionRight.PUT
        legs = [c for c in contracts if c.right == right]
        if not legs:
            self._log_skip("sem contratos do lado")
            return

        S = self.securities[self.spx].price
        strikes = sorted({c.strike for c in legs})
        by_strike = {c.strike: c for c in legs}

        # IV ATM (p/ logging do sigma; placement em 0DTE usa a regra dos 10%, NÃO sigma)
        atm = min(legs, key=lambda c: abs(c.strike - S))
        iv = atm.implied_volatility or 0.0
        sigma_1d = S * iv / np.sqrt(252.0) if iv > 0 else 0.0

        def build(center):
            """Monta a fly simétrica nesse center; retorna (lo, center, up, c_low, c_mid, c_up, debit)."""
            lo = min(strikes, key=lambda k: abs(k - (center - self.wing)))
            up = min(strikes, key=lambda k: abs(k - (center + self.wing)))
            if len({lo, center, up}) < 3:
                return None
            cl, cm, cu = by_strike.get(lo), by_strike.get(center), by_strike.get(up)
            if not (cl and cm and cu):
                return None
            d = (cl.ask_price + cu.ask_price) - 2 * cm.bid_price   # compra asas no ask, vende corpo no bid
            return (lo, center, up, cl, cm, cu, d)

        # ---- escolha do center ----
        if self.placement_mode == "sigma":
            # DTE alto (Convexity Stack / Sigma Drift): center a N*sigma OTM
            if sigma_1d <= 0:
                self._log_skip("sem IV (modo sigma)"); return
            tgt = S + self.sigma_mult * sigma_1d if bias == 1 else S - self.sigma_mult * sigma_1d
            cands = [k for k in strikes if (k > S) == (bias == 1)]
            center = min(cands, key=lambda k: abs(k - tgt), default=None)
            built = build(center) if center is not None else None
        else:
            # 0DTE (regra real do Ernie): center OTM onde debit ~ target_debit_frac * asa.
            # O debit cai à medida que o center vai OTM -> varre near-money -> OTM e pega o mais perto do alvo.
            otm = sorted([k for k in strikes if (k > S if bias == 1 else k < S)], key=lambda k: abs(k - S))
            target = self.target_debit_frac * self.wing
            built, best_gap = None, None
            for center in otm:
                fb = build(center)
                if fb is None or fb[6] <= 0:
                    continue
                gap = abs(fb[6] - target)
                if best_gap is None or gap < best_gap:
                    best_gap, built = gap, fb
                if fb[6] < target:        # já passamos do alvo indo OTM -> para
                    break

        if built is None:
            self._log_skip("não montou fly (cadeia rala / sem alvo)"); return
        lower, center, upper, c_low, c_mid, c_up, debit = built

        if debit <= 0:
            self._log_skip(f"debit<=0 ({debit:.2f}) — cotação ruim"); return
        if self.enforce_debit_cap and debit > self.debit_cap_frac * self.wing:
            self._log_skip(f"debit {debit:.2f} > cap {self.debit_cap_frac*self.wing:.2f}"); return

        # pernas: +1 lower, -2 center, +1 upper
        self.market_order(c_low.symbol, 1)
        self.market_order(c_mid.symbol, -2)
        self.market_order(c_up.symbol, 1)

        self.open_trade = {
            "open_time": self.time, "side": "Call" if right == OptionRight.CALL else "Put",
            "S_entry": S, "iv": iv, "sigma": sigma_1d,
            "lower": lower, "center": center, "upper": upper, "wing": self.wing,
            "entry_debit": debit, "vix": self.securities[self.vix].price,
        }
        self.debug(f"{self.time} ENTRY {self.open_trade['side']} fly "
                   f"{lower}/{center}/{upper} debit={debit:.2f} S={S:.0f} iv={iv:.3f}")

    # ===================== SAÍDA / SETTLE =====================
    def _check_profit_target(self, slice):
        """Hook Fase 2: sai se valor atual >= entry_debit + profit_target_frac * (asa - debit)."""
        pass  # implementar na Fase 2

    def _settle_open_trade(self):
        """Hold-to-expiry: paga o intrínseco da fly no settlement (close 0DTE)."""
        if self.open_trade is None:
            return
        t = self.open_trade
        S_T = self.securities[self.spx].price
        lo, mid, up = t["lower"], t["center"], t["upper"]
        if t["side"] == "Call":
            payoff = max(0, S_T - lo) - 2 * max(0, S_T - mid) + max(0, S_T - up)
        else:
            payoff = max(0, lo - S_T) - 2 * max(0, mid - S_T) + max(0, up - S_T)

        debit = t["entry_debit"]
        net = (payoff - debit) * 100.0                # multiplicador SPX = $100
        ret = (payoff - debit) / debit if debit > 0 else 0.0
        rec = {
            "open_date": t["open_time"].strftime("%Y-%m-%d"),
            "close_date": self.time.strftime("%Y-%m-%d"),
            "open_time": t["open_time"].strftime("%H:%M"),
            "side": t["side"], "S_entry": round(t["S_entry"], 2), "S_settle": round(S_T, 2),
            "lower": lo, "center": mid, "upper": up, "wing": t["wing"],
            "entry_debit": round(debit, 2), "payoff": round(payoff, 2),
            "return": round(ret, 4), "net_pl": round(net, 2),
            "r2r": round((t["wing"] - debit) / debit, 2) if debit > 0 else 0.0,
            "vix": round(t["vix"], 2), "sigma": round(t["sigma"], 1),
            "zone": self._zone(ret), "result": "W" if net > 0 else "L",
        }
        self.trades.append(rec)
        # ⚠️ NÃO liquidar via market order. SPXW é europeu, PM cash-settled: a posição liquida
        # em CAIXA no preço oficial de settlement (= intrínseco, SEM spread). Mandar market order
        # no minuto do expiry cruzava o spread enorme das pernas deep-ITM e gerava perdas/cortes
        # FANTASMAS que violam a convexidade do fly (ex.: 18/dez/2024 perna -$26k; winners cortados
        # pela metade). Deixar o LEAN cash-settle as SPXW no expiry -> equity oficial = intrínseco.
        # (Recordamos o intrínseco analítico acima; a equity do QC deve bater após o fix.)
        self.open_trade = None
        self.debug(f"{self.time} SETTLE {rec['side']} S_T={S_T:.0f} payoff={payoff:.2f} net={net:.0f} zone={rec['zone']}")

    @staticmethod
    def _zone(ret):
        """4 zonas do Ernie por retorno líquido."""
        if ret <= -0.5:  return 0   # full/near-full loss
        if ret <= 1.0:   return 1   # modest winner
        if ret <= 4.0:   return 2   # big winner
        return 3                    # fat tail

    def _log_skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    # ===================== EXPORT =====================
    def on_end_of_algorithm(self):
        cols = ["open_date", "close_date", "open_time", "side", "S_entry", "S_settle",
                "lower", "center", "upper", "wing", "entry_debit", "payoff",
                "return", "net_pl", "r2r", "vix", "sigma", "zone", "result"]
        lines = [",".join(cols)]
        for r in self.trades:
            lines.append(",".join(str(r[c]) for c in cols))

        # ObjectStore: o download é gated no tier free, mas mantemos como secundário (e lê de graça no Research)
        try:
            self.object_store.save("fase1_trades.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou (ok no tier free): {e}")

        # PRIMÁRIO no tier free: despeja o CSV no LOG (downloadável via 'Download Logs' OU copiável)
        self.log(">>>CSV_START fase1_trades")
        for ln in lines:
            self.log(ln)
        self.log(">>>CSV_END")

        n = len(self.trades)
        wins = sum(1 for r in self.trades if r["result"] == "W")
        pnl = sum(r["net_pl"] for r in self.trades)
        self.log(f"=== FASE 1 RESUMO === trades={n} | wins={wins} ({(wins/n*100 if n else 0):.0f}%) "
                 f"| net P/L=${pnl:,.0f} | skips={len(self.skips)}")
        from collections import Counter
        reasons = Counter(r for _, r in self.skips)
        if reasons:
            self.log("SKIPS por motivo: " + ", ".join(f"{k}={v}" for k, v in reasons.items()))
        self.log("CSV: copie as linhas entre >>>CSV_START e >>>CSV_END acima, ou use 'Download Logs'.")
