# region imports
from AlgorithmImports import *
import numpy as np
import math
# endregion


class _OptBpInit(BrokerageModelSecurityInitializer):
    """Preserva os modelos default (fill/fee/dados) e ANULA o buying-power das opções de índice.
    Contorna o crash 'Sequence contains no matching element' do
    OptionStrategyPositionGroupBuyingPowerModel quando BWBs sobrepostos compartilham strikes
    entre trades concorrentes (o d30/d45 estouravam; o d21 escapava com menos sobreposição)."""
    def initialize(self, security):
        super().initialize(security)
        if security.type == SecurityType.INDEX_OPTION:
            security.set_buying_power_model(BuyingPowerModel.NULL)


class Pl5BwbV1(QCAlgorithm):
    """
    PROJETO "PL5" — Backtest BWB 1-2-2 de PUTS (vídeo, 2026-06-15)
    Charter: context/PROJECT_pl5_bwb_backtest.md
    Plano:   ~/.claude/plans/claude-tem-uma-nova-cozy-tome.md

    Modified broken-wing butterfly de PUTS em SPXW, ancorado em DELTA, swing 21/30/45 DTE.
    Entrada toda SEXTA-FEIRA 10:00 ET; expiry numa sexta minimizando |dte_real - target_dte|.

      - Estrutura (1 "pacote" = unidade de sizing), tudo em puts, ratio 1/2/2:
            +1 put @ -30Δ  (K1, maior strike)   -> long de cima
            -2 puts @ -18Δ (K2)                 -> corpo short
            +2 puts @ -3Δ  (K3, menor strike)   -> cauda long de baixo
        Net long 1 put. Payoff: 0 acima de K1; pico (tent) em K2; vale de perda máx ~K3;
        VOLTA a ganhar abaixo de K3 (a cauda = convexidade de crash — a tese do vídeo).

      - Montagem MECÂNICA via combos RECONHECIDOS (margem = perda máx definida):
            +1K1/-2K2/+2K3 = bear_put_spread(K1,K2) + bull_put_spread(K2,K3) + 1 long put K3.
        (Pernas soltas fariam o QC cobrar margem de NAKED short nos -2K2 -> corrompe o span,
         igual aconteceu no Batman. Combos netam a margem.)

      - Stop:  NENHUM no motor. Max loss = vale (definido). "gerenciar risco, não profit".
      - Gestão: NÃO executa TP/SL. GRAVA, por trade, o instante (hora+DIT) e o valor do
                primeiro cruzamento de cada nível de TP (frac de ref_profit) e SL (frac de
                ref_loss), + MFE/MAE, + MTM em 7/14/21 DIT. As variantes de close + cortes por
                VIX são derivados DEPOIS no app — SEM re-rodar o QC. Tudo segura até cash-settle
                => equity oficial do QC = baseline M0 (hold-to-expiry).

    LIÇÕES DA FASE 1/BATMAN (não repetir): cash-settled NÃO fecha por market order no expiry
    (deixar o LEAN cash-settle nativo); ler a EQUITY, não o blotter (MAE != P&L); QC cloud !=
    arquivo local (colar no editor antes de rodar); free tier = ~10kb log/backtest (CSV grande
    só no ObjectStore -> Research notebook; usar CTRADE| compacto no log).
    """

    # ===================== CONFIG =====================
    def initialize(self):
        # ===== Eixos ESTRUTURAIS (get_parameter; default = comportamento v1) =====
        # Só o que MUDA a posição vira parâmetro. VIX / close-rule NÃO entram aqui: saem de
        # FATIAR o dataset no app. Stratify, don't filter.
        self.target_dte   = int(self.get_parameter("target_dte", "30"))       # 21 | 30 | 45
        self.ticker       = self.get_parameter("ticker", "SPX")               # SPX (multi-ticker = futuro)
        self.entry_weekday = int(self.get_parameter("entry_weekday", "4"))    # 4 = sexta
        self.entry_cadence = self.get_parameter("entry_cadence", "weekly")    # weekly | daily
        # deltas-alvo das 3 pernas (valor ABSOLUTO; são puts)
        self.dlt_k1 = float(self.get_parameter("delta_k1", "0.30"))           # long de cima
        self.dlt_k2 = float(self.get_parameter("delta_k2", "0.18"))           # short (corpo)
        self.dlt_k3 = float(self.get_parameter("delta_k3", "0.03"))           # long cauda

        sd = self.get_parameter("start_date", "2021-06-01").split("-")
        ed = self.get_parameter("end_date",   "2026-06-01").split("-")
        self.run_tag = self.get_parameter("run_tag", f"pl5_bwb_d{self.target_dte}")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        self.entry_hour, self.entry_minute = 10, 0

        # ---- Níveis a GRAVAR (record-and-derive; NÃO executa) ----
        # TP: fração de ref_profit (pico do tent). SL: fração de ref_loss (vale = perda máx definida).
        self.tp_levels = [0.25, 0.50, 0.75, 1.00]
        self.sl_levels = [0.50, 1.00, 1.50, 2.00]
        self.dit_marks = [7, 14, 21, 28, 35]    # MTM nesses dias-no-trade
        # SAÍDA ANTECIPADA (tese CZ 2026-06-16): a estrutura fica positiva no meio e DEVOLVE no expiry
        # quando a tenda reforma. Gravar MTM (mid+cons) com D DTE RESTANTES -> derivar "sair com D DTE".
        self.dte_exit_grid = [30, 21, 14, 10, 7, 5, 3]
        self.mark_every_min = 30                # cadência intraday (swing; menos compute que 0DTE)
        _tpc = self.get_parameter("tp_close_frac", "none")    # só p/ sanidade (default hold)
        self.tp_close_frac = None if _tpc in ("none", "None", "") else float(_tpc)
        _slc = self.get_parameter("sl_close_frac", "none")
        self.sl_close_frac = None if _slc in ("none", "None", "") else float(_slc)

        # ---- Universo (SPX/SPXW; VIX p/ bucket) ----
        # inicializador ANTES dos add_*: anula BP das opções (evita o crash do position-group model)
        self.set_security_initializer(_OptBpInit(self.brokerage_model, SecuritySeeder.NULL))
        index = self.add_index("SPX", Resolution.HOUR)
        self.spx = index.symbol
        option = self.add_index_option(self.spx, "SPXW", Resolution.HOUR)
        lo = max(1, self.target_dte - 7)
        hi = self.target_dte + 10
        # PL5 só usa PUTS abaixo do spot -> corta strikes acima. -300 cobre K3 (-3Δ) em 60 DTE alta-vol
        # (~1100pts OTM em 2022); +5 folga. Tracking sintético (sem ordens) deixa o compute baixo.
        option.set_filter(lambda u: u.include_weeklys().expiration(lo, hi).strikes(-300, 5))
        self.spxw = option.symbol

        self.vix = self.add_index("VIX", Resolution.HOUR).symbol

        # ---- Estado ----
        self.rows = []            # uma linha por TRADE (pacote)
        self.skips = []
        self.open_trades = []     # cada item: dict do pacote aberto
        self.entered_today = False
        self.current_day = None
        self.trade_seq = 0

        # Settle no expiry (16:01 ET, após o close)
        self.schedule.on(self.date_rules.every_day(self.spx),
                         self.time_rules.at(16, 1),
                         self._settle_due)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.current_day != self.time.date():
            self.current_day = self.time.date()
            self.entered_today = False

        # --- marcação intraday em TODOS os dias de vida do trade (swing multi-dia) ---
        if self.time.minute % self.mark_every_min == 0:
            for tr in self.open_trades:
                if tr["expiry"] >= self.time.date():
                    self._mark_trade(tr)

        # --- entrada (uma vez/dia, a partir de 10:00, na SEXTA) ---
        if self.entered_today:
            return
        if self.entry_cadence == "weekly" and self.time.weekday() != self.entry_weekday:
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return

        chain = slice.option_chains.get(self.spxw)
        if chain is None:
            return  # cadeia ainda não chegou neste minuto; tenta no próximo
        contracts = [c for c in chain]
        if not contracts:
            self.entered_today = True
            self._skip("cadeia vazia")
            return

        vix = self.securities[self.vix].price
        self._enter_trade(contracts, vix)
        self.entered_today = True

    # ===================== ENTRADA =====================
    def _pick_expiry(self, contracts, today):
        """Dentre as SEXTAS futuras, a que minimiza |dte_real - target_dte|. Devolve date ou None."""
        fri = sorted({c.expiry.date() for c in contracts
                      if c.expiry.date() > today and c.expiry.date().weekday() == 4})
        if not fri:
            # fallback: qualquer expiry futuro (caso raro sem sexta na janela)
            fri = sorted({c.expiry.date() for c in contracts if c.expiry.date() > today})
        if not fri:
            return None
        return min(fri, key=lambda e: abs((e - today).days - self.target_dte))

    def _enter_trade(self, contracts, vix):
        S = self.securities[self.spx].price
        today = self.time.date()

        expiry = self._pick_expiry(contracts, today)
        if expiry is None:
            self._skip("sem expiry sexta"); return
        dte_real = (expiry - today).days
        puts = [c for c in contracts if c.expiry.date() == expiry and c.right == OptionRight.PUT
                and c.strike < S]
        if len(puts) < 3:
            self._skip("poucos puts OTM"); return

        c_k1 = self._pick_strike_by_delta(puts, self.dlt_k1, S, expiry)   # long de cima
        c_k2 = self._pick_strike_by_delta(puts, self.dlt_k2, S, expiry)   # short corpo
        c_k3 = self._pick_strike_by_delta(puts, self.dlt_k3, S, expiry)   # long cauda
        if c_k1 is None or c_k2 is None or c_k3 is None:
            self._skip("delta pick None (sem greeks/IV)"); return
        K1, K2, K3 = c_k1.strike, c_k2.strike, c_k3.strike
        if not (K1 > K2 > K3):
            self._skip("delta picks colidiram (K1>K2>K3 falhou)"); return

        # custo de entrada. cons = longs@ask, shorts@bid (pior). mid = (bid+ask)/2.
        def _mid(c):
            b, a = c.bid_price, c.ask_price
            return (b + a) / 2.0 if (b > 0 and a > 0) else (a or b or 0.0)
        entry_cost     = (c_k1.ask_price + c_k3.ask_price * 2) - c_k2.bid_price * 2
        entry_cost_mid = (_mid(c_k1) + _mid(c_k3) * 2) - _mid(c_k2) * 2
        # referências de gestão (em pontos):
        ref_profit = (K1 - K2) - entry_cost            # pico do tent (em S_T == K2)
        ref_loss   = (2 * K2 - K1 - K3) + entry_cost   # módulo do vale (perda máx definida, em S_T==K3)
        if ref_profit <= 0 or ref_loss <= 0:
            self._skip(f"refs inválidas (rp={ref_profit:.2f} rl={ref_loss:.2f})"); return

        # TRACKING SINTÉTICO (sem ordens): subscreve as pernas p/ ficarem precificadas; P&L 100% analítico
        # do bid/ask. Evita o crash OptionStrategyPositionGroupBuyingPowerModel que travava d30/d45 em
        # escala (combo/strategy/ordem individual TODOS formam grupo). Ver memória do crash.
        for c in (c_k1, c_k2, c_k3):
            try:
                self.add_index_option_contract(c.symbol, Resolution.HOUR)
            except Exception:
                pass

        self.trade_seq += 1
        tr = {
            "id": self.trade_seq, "open_time": self.time, "expiry": expiry, "dte_real": dte_real,
            "S_entry": S, "vix": vix,
            "K1": K1, "K2": K2, "K3": K3,
            "d_k1": self._delta(c_k1, S, expiry), "d_k2": self._delta(c_k2, S, expiry),
            "d_k3": self._delta(c_k3, S, expiry),
            "c_k1": c_k1, "c_k2": c_k2, "c_k3": c_k3,
            "entry_cost": entry_cost, "entry_cost_mid": entry_cost_mid,
            "ref_profit": ref_profit, "ref_loss": ref_loss,
            # gravação de gestão (preenchida na marcação intraday):
            "mfe": 0.0, "mae": 0.0,
            "tp_cross": {lvl: None for lvl in self.tp_levels},
            "sl_cross": {lvl: None for lvl in self.sl_levels},
            "dit_val": {d: None for d in self.dit_marks},
            "dte_val": {d: None for d in self.dte_exit_grid},   # (pnl_mid, pnl_cons) com D DTE restantes
            "closed": False,
        }
        self.open_trades.append(tr)
        if self.trade_seq <= 3:   # só os 1ºs (free tier = cota de log)
            self.debug(f"{self.time} ENTRY#{self.trade_seq} exp={expiry} dte={dte_real} S={S:.0f} "
                       f"vix={vix:.1f} | K {K1}/{K2}/{K3} cost={entry_cost:.2f} "
                       f"rp={ref_profit:.1f} rl={ref_loss:.1f}")

    def _pick_strike_by_delta(self, puts, target_abs_delta, S, expiry):
        """Put cujo |delta| está mais perto do alvo (padrão iron_condor_0dte._pick_by_delta)."""
        best, bestgap = None, 1e9
        for c in puts:
            d = self._delta(c, S, expiry)
            if d is None:
                continue
            gap = abs(abs(d) - target_abs_delta)
            if gap < bestgap:
                best, bestgap = c, gap
        return best

    # ===================== MARCAÇÃO (grava cruzamentos; NÃO executa) =====================
    def _mark_trade(self, tr):
        if tr.get("closed"):
            return
        c_k1, c_k2, c_k3 = tr["c_k1"], tr["c_k2"], tr["c_k3"]
        s1, s2, s3 = self.securities[c_k1.symbol], self.securities[c_k2.symbol], self.securities[c_k3.symbol]
        k1_b, k1_a = s1.bid_price, s1.ask_price
        k2_b, k2_a = s2.bid_price, s2.ask_price
        k3_b, k3_a = s3.bid_price, s3.ask_price
        if k1_b <= 0 or k3_b <= 0 or k2_a <= 0 or k1_a <= 0 or k3_a <= 0 or k2_b <= 0:
            return
        # valor p/ FECHAR: cons = longs@bid / shorts@ask (pior). mid = (bid+ask)/2.
        close_cons = (k1_b + k3_b * 2) - k2_a * 2
        m1, m2, m3 = (k1_b + k1_a) / 2, (k2_b + k2_a) / 2, (k3_b + k3_a) / 2
        close_mid = (m1 + m3 * 2) - m2 * 2
        pnl      = (close_cons - tr["entry_cost"]) * 100.0       # $/pacote (conservador)
        pnl_mid  = (close_mid - tr["entry_cost_mid"]) * 100.0    # $/pacote (mid)
        S = self.securities[self.spx].price
        # PADRÃO = MID (mid é o padrão de backtest). cons fica só como referência secundária.
        if pnl_mid > tr["mfe"]:
            tr["mfe"] = pnl_mid
        if pnl_mid < tr["mae"]:
            tr["mae"] = pnl_mid

        dit = (self.time.date() - tr["open_time"].date()).days
        dte_rem = (tr["expiry"] - self.time.date()).days
        ts = self.time.strftime("%Y-%m-%d %H:%M")

        # TP: pnl_mid >= L * ref_profit*100
        for lvl in self.tp_levels:
            if tr["tp_cross"][lvl] is None and pnl_mid >= lvl * tr["ref_profit"] * 100.0:
                tr["tp_cross"][lvl] = (ts, dit, round(pnl_mid, 2))
        # SL: pnl_mid <= -L * ref_loss*100
        for lvl in self.sl_levels:
            if tr["sl_cross"][lvl] is None and pnl_mid <= -lvl * tr["ref_loss"] * 100.0:
                tr["sl_cross"][lvl] = (ts, dit, round(pnl_mid, 2))
        # DIT milestones: 1º mark com dit >= alvo (mid)
        for d in self.dit_marks:
            if tr["dit_val"][d] is None and dit >= d:
                tr["dit_val"][d] = round(pnl_mid, 2)
        # SAÍDA ANTECIPADA: 1º mark com D DTE restantes -> grava (pnl_mid, pnl_cons, spot) p/ o caminho
        for d in self.dte_exit_grid:
            if tr["dte_val"][d] is None and dte_rem <= d:
                tr["dte_val"][d] = (round(pnl_mid, 2), round(pnl, 2), round(S, 2))
        # NÃO executa close-rule (tracking sintético + record-and-derive: tudo é derivado no pós-proc
        # a partir de dte_val / tp_cross / sl_cross / settle). tp_close_frac/sl_close_frac aposentados.

    # ===================== SETTLE =====================
    def _settle_due(self):
        """No expiry: registra o intrínseco (cash-settle) de cada pacote. NÃO manda market order
        — SPXW liquida em CAIXA no preço oficial (lição Fase 1)."""
        if not self.open_trades:
            return
        S_T = self.securities[self.spx].price
        still_open = []
        for tr in self.open_trades:
            if tr["expiry"] != self.time.date():
                still_open.append(tr); continue
            if tr.get("closed"):
                continue
            K1, K2, K3 = tr["K1"], tr["K2"], tr["K3"]
            payoff = (1 * max(0.0, K1 - S_T) - 2 * max(0.0, K2 - S_T) + 2 * max(0.0, K3 - S_T))
            self._record(tr, S_T, payoff, settled=True)
        self.open_trades = still_open

    def _record(self, tr, S_T, value, settled):
        cost = tr["entry_cost"]; cost_mid = tr["entry_cost_mid"]
        net      = (value - cost_mid) * 100.0   # MID = PADRÃO (settle = cash, sem spread de saída; só entrada)
        net_cons = (value - cost) * 100.0        # referência conservadora (entrada spread cheio)
        ret_p = net / (tr["ref_loss"] * 100.0) if tr["ref_loss"] > 0 else 0.0  # múltiplos da perda máx
        row = {
            "id": tr["id"],
            "open_date": tr["open_time"].strftime("%Y-%m-%d"),
            "open_time": tr["open_time"].strftime("%H:%M"),
            "expiry_date": tr["expiry"].strftime("%Y-%m-%d"),
            "dte_real": tr["dte_real"],
            "vix": round(tr["vix"], 2), "vix_bucket": self._vix_bucket(tr["vix"]),
            "S_entry": round(tr["S_entry"], 2), "S_settle": round(S_T, 2),
            "K1": tr["K1"], "K2": tr["K2"], "K3": tr["K3"],
            "d_k1": round(tr["d_k1"], 4) if tr["d_k1"] is not None else "",
            "d_k2": round(tr["d_k2"], 4) if tr["d_k2"] is not None else "",
            "d_k3": round(tr["d_k3"], 4) if tr["d_k3"] is not None else "",
            "entry_cost": round(cost, 2), "entry_cost_mid": round(cost_mid, 2),
            "ref_profit": round(tr["ref_profit"], 2), "ref_loss": round(tr["ref_loss"], 2),
            "mfe": round(tr["mfe"], 2), "mae": round(tr["mae"], 2),
            "settle_value": round(value, 2),
            "settle_net": round(net, 2),                 # MID (padrão)
            "settle_net_cons": round(net_cons, 2),       # cons (referência)
            "ret_mult": round(ret_p, 4),
            "exit": "settle" if settled else "closerule",
            "result": "W" if net > 0 else "L",
        }
        # cruzamentos TP/SL (ts | dit | valor) e DIT milestones
        for lvl in self.tp_levels:
            cx = tr["tp_cross"][lvl]
            row[f"tp{int(lvl*100)}_t"]   = cx[0] if cx else ""
            row[f"tp{int(lvl*100)}_dit"] = cx[1] if cx else ""
            row[f"tp{int(lvl*100)}_v"]   = cx[2] if cx else ""
        for lvl in self.sl_levels:
            cx = tr["sl_cross"][lvl]
            row[f"sl{int(lvl*100)}_t"]   = cx[0] if cx else ""
            row[f"sl{int(lvl*100)}_dit"] = cx[1] if cx else ""
            row[f"sl{int(lvl*100)}_v"]   = cx[2] if cx else ""
        for d in self.dit_marks:
            row[f"dit{d}_v"] = tr["dit_val"][d] if tr["dit_val"][d] is not None else ""
        # SAÍDA ANTECIPADA: pnl mid+cons com D DTE restantes (vazio = trade nasceu com < D DTE)
        for d in self.dte_exit_grid:
            dv = tr["dte_val"][d]
            row[f"dte{d}_mid"]  = dv[0] if dv else ""
            row[f"dte{d}_cons"] = dv[1] if dv else ""
        self.rows.append(row)

    # ===================== GREEKS / HELPERS =====================
    def _delta(self, c, S, expiry):
        """delta do contrato: greeks da cadeia se houver; senão Black-Scholes a partir da IV."""
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
        r = 0.04
        d1 = (math.log(S / c.strike) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
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

    # ===================== DERIVAÇÃO (prévia do que o app faz) =====================
    def _pnl_variant(self, r, kind, L):
        """P&L da variante de gestão a partir das colunas gravadas.
        kind=None -> hold (settle); 'tp'/'sl' -> sai no 1º cruzamento de nível L, senão hold."""
        if kind is None:
            return r["settle_net"]
        v = r.get(f"{kind}{int(L*100)}_v", "")
        if v not in ("", None):
            return float(v)
        return r["settle_net"]

    def _log_variant_summary(self):
        """Resumo compacto: net$ e WR% por gestão (hold / +TP / -SL) × bucket de VIX."""
        variants = ([("M0_hold", None, None)]
                    + [(f"TP{int(L*100)}", "tp", L) for L in self.tp_levels]
                    + [(f"SL{int(L*100)}", "sl", L) for L in self.sl_levels])
        buckets = ["<15", "15-17", "17-22", "22-32", "32+", "ALL"]
        self.log("=== VARIANT SUMMARY === net$ / WR% por gestão × VIX bucket (por-trade)")
        for name, kind, L in variants:
            parts = []
            for b in buckets:
                rs = self.rows if b == "ALL" else [r for r in self.rows if r["vix_bucket"] == b]
                if not rs:
                    parts.append(f"{b}:—"); continue
                pls = [self._pnl_variant(r, kind, L) for r in rs]
                net = sum(pls)
                wr = 100.0 * sum(1 for x in pls if x > 0) / len(pls)
                parts.append(f"{b} ${net:,.0f}/{wr:.0f}%")
            self.log(f"{name:8s} | " + " | ".join(parts))

    def _emit_runtime_stats(self):
        """Agregados-chave como RUNTIME STATISTICS — único canal export-safe no tier free."""
        rows = self.rows
        if not rows:
            return
        # M0 (hold) por bucket de VIX
        for b in ["<15", "15-17", "17-22", "22-32", "32+"]:
            rs = [r for r in rows if r["vix_bucket"] == b]
            if rs:
                net = sum(r["settle_net"] for r in rs)
                self.set_runtime_statistic(f"M0 VIX {b}", f"${net:,.0f} (n={len(rs)})")
        # M0 por ano
        from collections import defaultdict
        by_yr, cnt = defaultdict(float), defaultdict(int)
        for r in rows:
            yr = r["open_date"][:4]
            by_yr[yr] += r["settle_net"]; cnt[yr] += 1
        for yr in sorted(by_yr):
            self.set_runtime_statistic(f"M0 {yr}", f"${by_yr[yr]:,.0f} (n={cnt[yr]})")
        # hold vs TP/SL (net + WR) no span inteiro — TODOS os níveis do grid
        for name, kind, L in ([("M0 hold", None, None)]
                              + [(f"TP{int(L*100)}", "tp", L) for L in self.tp_levels]
                              + [(f"SL{int(L*100)}", "sl", L) for L in self.sl_levels]):
            pls = [self._pnl_variant(r, kind, L) for r in rows]
            net = sum(pls)
            wr = 100.0 * sum(1 for x in pls if x > 0) / len(pls)
            self.set_runtime_statistic(f"NET {name}", f"${net:,.0f} / WR {wr:.0f}%")

        # ★ SAÍDA ANTECIPADA (tese CZ): sair com D DTE restantes. net/WR no mid E no cons. Trades que
        # nasceram com < D DTE caem no settle (hold) p/ esse D. Este é o baseline que o CZ defende.
        for d in self.dte_exit_grid:
            pls_mid, pls_cons = [], []
            for r in rows:
                vm = r.get(f"dte{d}_mid", ""); vc = r.get(f"dte{d}_cons", "")
                pls_mid.append(float(vm) if vm not in ("", None) else r["settle_net"])
                pls_cons.append(float(vc) if vc not in ("", None) else r["settle_net"])
            nm = sum(pls_mid); wm = 100.0 * sum(1 for x in pls_mid if x > 0) / len(pls_mid)
            nc = sum(pls_cons); wc = 100.0 * sum(1 for x in pls_cons if x > 0) / len(pls_cons)
            self.set_runtime_statistic(f"EXIT {d}DTE", f"mid ${nm:,.0f}/{wm:.0f}% | cons ${nc:,.0f}/{wc:.0f}%")
        # sanidade
        import statistics as _st
        self.set_runtime_statistic("entry_cost med", f"{_st.median(r['entry_cost'] for r in rows):.2f}")
        self.set_runtime_statistic("dte_real med", f"{_st.median(r['dte_real'] for r in rows):.0f}")

        # ---- VALIDAÇÃO: prova que a marcação e os deltas funcionam ----
        # 1) deltas realizados (mediana) — devem bater com os alvos -0.30/-0.18/-0.03
        for k in ("d_k1", "d_k2", "d_k3"):
            vals = [r[k] for r in rows if r[k] not in ("", None)]
            if vals:
                self.set_runtime_statistic(f"delta {k}", f"{_st.median(vals):.3f} (n={len(vals)})")
        # 2) marcação viva? quantos trades têm MFE>0 ou MAE<0; medianas
        n_marked = sum(1 for r in rows if r["mfe"] > 0 or r["mae"] < 0)
        self.set_runtime_statistic("mark alive n", f"{n_marked}/{len(rows)}")
        self.set_runtime_statistic("mfe med", f"${_st.median(r['mfe'] for r in rows):,.0f}")
        self.set_runtime_statistic("mae med", f"${_st.median(r['mae'] for r in rows):,.0f}")
        # 3) cruzamentos: quantos trades cruzaram ALGUM tp / algum sl
        def _hit(r, kind, lvls):
            return any(r.get(f"{kind}{int(l*100)}_v", "") not in ("", None) for l in lvls)
        self.set_runtime_statistic("hit any TP", f"{sum(1 for r in rows if _hit(r,'tp',self.tp_levels))}")
        self.set_runtime_statistic("hit any SL", f"{sum(1 for r in rows if _hit(r,'sl',self.sl_levels))}")
        # 4) 1º trade detalhado p/ conferir a olho (strikes/deltas/cost/settle)
        r0 = min(rows, key=lambda r: r["id"])
        self.set_runtime_statistic("T1 strikes", f"{r0['K1']}/{r0['K2']}/{r0['K3']} S={r0['S_entry']}")
        self.set_runtime_statistic("T1 deltas", f"{r0['d_k1']}/{r0['d_k2']}/{r0['d_k3']}")
        self.set_runtime_statistic("T1 cost/settle", f"cost={r0['entry_cost']} net={r0['settle_net']} mfe={r0['mfe']} mae={r0['mae']}")

    # ===================== EXPORT =====================
    def on_end_of_algorithm(self):
        cols = (["id", "open_date", "open_time", "expiry_date", "dte_real",
                 "vix", "vix_bucket", "S_entry", "S_settle", "K1", "K2", "K3",
                 "d_k1", "d_k2", "d_k3", "entry_cost", "ref_profit", "ref_loss", "mfe", "mae"]
                + [f"tp{int(l*100)}_t" for l in self.tp_levels]
                + [f"tp{int(l*100)}_dit" for l in self.tp_levels]
                + [f"tp{int(l*100)}_v" for l in self.tp_levels]
                + [f"sl{int(l*100)}_t" for l in self.sl_levels]
                + [f"sl{int(l*100)}_dit" for l in self.sl_levels]
                + [f"sl{int(l*100)}_v" for l in self.sl_levels]
                + [f"dit{d}_v" for d in self.dit_marks]
                + [f"dte{d}_mid" for d in self.dte_exit_grid]
                + [f"dte{d}_cons" for d in self.dte_exit_grid]
                + ["settle_value", "settle_net", "ret_mult", "exit", "result"])
        lines = [",".join(cols)]
        for r in self.rows:
            lines.append(",".join(str(r.get(c, "")) for c in cols))

        try:
            self.object_store.save(f"{self.run_tag}.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou (ok no tier free): {e}")

        # CSV completo só cabe no log em janela curta; em run grande fica no ObjectStore.
        if len(self.rows) <= 80:
            self.log(f">>>CSV_START {self.run_tag}")
            for ln in lines:
                self.log(ln)
            self.log(">>>CSV_END")
        else:
            self._log_ctrade_compact()

        self._log_variant_summary()
        self._emit_runtime_stats()

        # resumo (M0 = hold-to-expiry = o que a equity do QC reflete)
        n = len(self.rows)
        w = sum(1 for r in self.rows if r["result"] == "W")
        net = sum(r["settle_net"] for r in self.rows)
        self.log(f"=== PL5 BWB v1 [{self.run_tag}] === trades={n} | W={w} "
                 f"({(w/n*100 if n else 0):.0f}%) | net M0(hold)=${net:,.0f} | skips={len(self.skips)}")
        from collections import Counter
        reasons = Counter(r for _, r in self.skips)
        if reasons:
            self.log("SKIPS: " + ", ".join(f"{k}={v}" for k, v in reasons.items()))
        self.log("CSV completo no ObjectStore (Research notebook). Variantes de close + cortes "
                 "por VIX saem do dataset NO APP.")

    def _log_ctrade_compact(self):
        """Log compacto p/ caber no cap do free tier (~707 linhas). 1 linha/trade.
        Tempos como OFFSET-em-dias (DIT) já gravados; valores crus p/ derivar P&L no app."""
        tplv = [int(l * 100) for l in self.tp_levels]
        sllv = [int(l * 100) for l in self.sl_levels]
        hdr = (["id", "od", "dte", "vix", "Se", "Ss", "K1", "K2", "K3",
                "cost", "rp", "rl", "mfe", "mae"]
               + [f"tp{l}" for l in tplv] + [f"tpd{l}" for l in tplv]
               + [f"sl{l}" for l in sllv] + [f"sld{l}" for l in sllv]
               + [f"d{d}" for d in self.dit_marks]
               + [f"x{d}m" for d in self.dte_exit_grid] + [f"x{d}c" for d in self.dte_exit_grid]
               + ["snet", "res"])
        self.log("CTRADEHDR|" + ",".join(hdr))
        for r in self.rows:
            row = [r["id"], r["open_date"], r["dte_real"], r["vix"], r["S_entry"], r["S_settle"],
                   r["K1"], r["K2"], r["K3"], r["entry_cost"], r["ref_profit"], r["ref_loss"],
                   r["mfe"], r["mae"]]
            row += [r.get(f"tp{l}_v", "") for l in tplv]
            row += [r.get(f"tp{l}_dit", "") for l in tplv]
            row += [r.get(f"sl{l}_v", "") for l in sllv]
            row += [r.get(f"sl{l}_dit", "") for l in sllv]
            row += [r.get(f"dit{d}_v", "") for d in self.dit_marks]
            row += [r.get(f"dte{d}_mid", "") for d in self.dte_exit_grid]
            row += [r.get(f"dte{d}_cons", "") for d in self.dte_exit_grid]
            row += [r["settle_net"], r["result"]]
            self.log("CTRADE|" + ",".join(str(x) for x in row))
