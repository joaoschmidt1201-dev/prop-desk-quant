# region imports
from AlgorithmImports import *
import numpy as np
import math
# endregion

class Batman1DteV1(QCAlgorithm):
    """
    PROJETO Ernie Butterfly Backtest — v1 "BATMAN 1DTE" (CZ redirect 2026-05-22)
    Charter: context/0DTE strategies/PROJECT_qc_backtest_scope.md
    Plano:   ~/.claude/plans/claude-ontem-n-s-estav-mos-distributed-fiddle.md

    BATMAN (call fly + put fly) em SPXW, entrada 15:45 ET p/ expiry do DIA SEGUINTE (1DTE),
    TODO dia útil. Colocação MECÂNICA (não TA — a TA fica p/ o forward-test).

      - Estrutura: dois OTM symmetric flies (call acima, put abaixo). Pernas por fly: +1/-2/+1.
      - Width:     SEARCH guiado pelo débito — o MAIS LARGO que mantém a fly inteira OTM e
                   débito/lado <= debit_cap_frac (regra dos 5% do CZ). Valida vs banda do Ernie
                   (VIX 22-32 -> 35-45 / VIX 32+ -> 45-60+).
      - Center:    P1 "debit"  -> OTM onde débito ~ target_debit_frac do width (regra do CZ);
                   P2 "delta"   -> short no target_delta nos dois lados (ideia do CZ p/ o skew).
      - Stop:      NENHUM. Max loss = débito (losers correm até expirar). "gerenciar risco, não profit".
      - Gestão:    NÃO executa TP no motor. Em vez disso GRAVA, por fly, o instante+valor do
                   primeiro cruzamento de cada nível de lucro (TP_LEVELS). As variantes de close
                   (150%/200%/hold/etc.) e os cortes por regime de VIX são derivados DEPOIS, no app
                   do desk, a partir do dataset — SEM re-rodar o QC. Tudo segura até o settle
                   (cash-settle nativo) => a equity oficial do QC = baseline M0 (hold-to-expiry).

    >>> POR QUE GRAVAR E NÃO EXECUTAR O TP:
        (1) o objetivo é alimentar o app com UM dataset rico e o CZ escolher a versão lá;
        (2) evita modelar fills intraday no expiry (foi o que gerou o bug de settlement na Fase 1);
        (3) 1 run por placement (debit/delta) gera todas as variantes. <<<

    Emite CSV por-FLY no log (entre >>>CSV_START/>>>CSV_END) e no ObjectStore.
    LIÇÕES DA FASE 1 (não repetir): cash-settled NÃO fecha por market order no expiry; ler a
    EQUITY, não o blotter (MAE != P&L); QC cloud != arquivo local (colar no editor antes de rodar).
    """

    # ===================== CONFIG =====================
    def initialize(self):
        # Mesmo span da Fase 1 (comparabilidade; SPXW tem expiry diário desde ~2022).
        # Se o compute do tier free apertar: partir em blocos anuais e costurar os CSVs.
        # ===== Eixos ESTRUTURAIS (get_parameter; default = comportamento v1) =====
        # Só o que MUDA a posição vira parâmetro. VIX / close-rule / dia-de-abertura NÃO entram aqui:
        # saem de FATIAR o dataset no app (_filter_by_vix / _scan_close_rule). Stratify, don't filter.
        self.structure         = self.get_parameter("structure", "1DTE")           # 0DTE|1DTE|weekly_mon_fri|weekly_fri_fri
        self.placement_mode    = self.get_parameter("placement_mode", "debit")     # debit (P1) | delta (P2)
        self.symmetry          = self.get_parameter("symmetry", "sym")             # sym | asym
        self.ticker            = self.get_parameter("ticker", "SPX")               # SPX (multi-ticker = futuro)
        self.target_delta      = float(self.get_parameter("target_delta", "0.16"))  # 0.16 (CZ); delta-0.15 aposentado
        self.target_debit_frac = float(self.get_parameter("target_debit_frac", "0.05"))
        self.width_mode        = self.get_parameter("width_mode", "vix_table")     # vix_table (CZ/Ernie) | fixed | debit_search
        self.fixed_width       = float(self.get_parameter("fixed_width", "30"))    # usado só c/ width_mode=fixed (25/30/40/50)
        sd = self.get_parameter("start_date", "2022-06-20").split("-")
        ed = self.get_parameter("end_date",   "2026-05-13").split("-")
        # tag única por cenário: key do ObjectStore + nome no relatório. O sweep passa o run_tag.
        self.run_tag = self.get_parameter("run_tag", f"{self.structure}_{self.placement_mode}_{self.symmetry}")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.NEW_YORK)

        # ---- estrutura -> entrada / weekday / janela de expiry do filtro ----
        if self.structure == "0DTE":
            self.entry_hour, self.entry_minute = 10, 0
            self.trade_weekdays = {0, 1, 2, 3, 4};  self._exp_lo, self._exp_hi = 0, 1
        elif self.structure == "weekly_mon_fri":
            self.entry_hour, self.entry_minute = 15, 45
            self.trade_weekdays = {0};              self._exp_lo, self._exp_hi = 1, 7    # seg -> sex (~4DTE)
        elif self.structure == "weekly_fri_fri":
            self.entry_hour, self.entry_minute = 15, 45
            self.trade_weekdays = {4};              self._exp_lo, self._exp_hi = 5, 9    # sex -> sex (~7DTE)
        elif self.structure == "weekly_fri_fri_21d":
            self.entry_hour, self.entry_minute = 15, 45
            self.trade_weekdays = {4};              self._exp_lo, self._exp_hi = 18, 24   # sex -> sex +3sem (~21DTE)
        else:  # "1DTE" (default)
            self.structure = "1DTE"
            self.entry_hour, self.entry_minute = 15, 45
            self.trade_weekdays = {0, 1, 2, 3, 4};  self._exp_lo, self._exp_hi = 0, 4

        self.vix_entry_floor = None        # entra SEMPRE; VIX vira TAG (stratify, não filter)

        # ---- Regra de débito / width (CZ: 5%/lado) — guardrails fixos ----
        self.debit_cap_frac    = 0.06      # teto/lado ~ 1:16 do Ernie (5,9%); pula se exceder nos dois
        self.width_candidates  = [60, 55, 50, 45, 40, 35, 30, 25, 20]   # do mais largo p/ o menor
        self.require_fully_otm = True      # exige a fly INTEIRA OTM (near wing além do spot)
        self.min_debit_frac    = 0.03      # PISO: rejeita fly barata/longe demais
        # symmetry: "sym" = call e put compartilham o MESMO width (put herda o do call);
        # "asym" = cada lado busca seu width livre (expressa skew). Flies SEMPRE internamente
        # equidistantes (exigência do combo ButterflyCall — strikes simétricos em torno do centro).

        # ---- Níveis de lucro a GRAVAR (frações sobre o débito). value de close = (1+L)*débito.
        # Inclui 0.10 e 0.20 p/ casar 1:1 com os profit-targets do app (_scan_close_rule). ----
        self.tp_levels = [0.10, 0.20, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00]
        self.mark_every_min = 5            # cadência de marcação intraday no dia do expiry (compute)
        _tpc = self.get_parameter("tp_close_frac", "none")   # none=hold; ex. 0.5 = fecha a fly a +50% do débito
        self.tp_close_frac = None if _tpc in ("none", "None", "") else float(_tpc)

        # ---- Universo (SPX/SPXW; multi-ticker = futuro) ----
        index = self.add_index("SPX", Resolution.MINUTE)
        self.spx = index.symbol
        option = self.add_index_option(self.spx, "SPXW", Resolution.MINUTE)
        # janela de expiry conforme a estrutura; ±80 strikes p/ caber Batman largo + far-OTM em alta vol.
        option.set_filter(lambda u: u.include_weeklys().expiration(self._exp_lo, self._exp_hi).strikes(-80, 80))
        self.spxw = option.symbol

        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        # ---- Estado ----
        self.rows = []            # uma linha por FLY (call e put separados)
        self.skips = []
        self.open_batmans = []    # cada item: dict com 2 sub-flies + expiry_date
        self.entered_today = False
        self.current_day = None
        self.batman_seq = 0

        # Settle/registro no expiry (16:01 ET, após o close 0DTE)
        self.schedule.on(self.date_rules.every_day(self.spx),
                         self.time_rules.at(16, 1),
                         self._settle_due)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.current_day != self.time.date():
            self.current_day = self.time.date()
            self.entered_today = False

        # --- marcação intraday p/ gravar cruzamentos de TP. Nos SEMANAIS marca em TODOS os
        #     dias da vida do trade (não só no expiry), p/ as colunas de TP valerem no 4/7/21DTE. ---
        if self.time.minute % self.mark_every_min == 0:
            _weekly = self.structure in ("weekly_mon_fri", "weekly_fri_fri", "weekly_fri_fri_21d")
            for bm in self.open_batmans:
                if bm["expiry"] == self.time.date() or (_weekly and bm["expiry"] >= self.time.date()):
                    self._mark_batman(bm)

        # --- entrada (uma vez/dia, a partir de 15:45) ---
        if self.entered_today:
            return
        if self.time.weekday() not in self.trade_weekdays:
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return

        vix = self.securities[self.vix].price
        if self.vix_entry_floor is not None and (vix <= 0 or vix < self.vix_entry_floor):
            self.entered_today = True
            self._skip(f"vix gate ({vix:.1f}<{self.vix_entry_floor})")
            return

        chain = slice.option_chains.get(self.spxw)
        if chain is None:
            return  # cadeia ainda não chegou neste minuto; tenta no próximo (até 15:59)
        contracts = [c for c in chain]
        if not contracts:
            self.entered_today = True
            self._skip("cadeia vazia")
            return

        self._enter_batman(contracts, vix)
        self.entered_today = True

    # ===================== ENTRADA =====================
    def _pick_expiry(self, contracts, today):
        """Escolhe o expiry-alvo conforme a estrutura. Devolve date ou None."""
        exps = sorted({c.expiry.date() for c in contracts})
        if self.structure == "0DTE":
            same = [e for e in exps if e == today]
            return same[0] if same else None
        fut = [e for e in exps if e > today]
        if not fut:
            return None
        if self.structure == "weekly_mon_fri":               # entra seg -> sexta DESTA semana
            fr = [e for e in fut if e.weekday() == 4 and (e - today).days <= 6]
            return fr[0] if fr else None
        if self.structure == "weekly_fri_fri":               # entra sex -> PRÓXIMA sexta (~7d)
            fr = [e for e in fut if e.weekday() == 4 and (e - today).days >= 5]
            return fr[0] if fr else None
        if self.structure == "weekly_fri_fri_21d":           # entra sex -> sexta +3 semanas (~21d)
            fr = [e for e in fut if e.weekday() == 4 and 19 <= (e - today).days <= 24]
            return fr[0] if fr else None
        return fut[0]                                         # 1DTE: próximo expiry > hoje

    def _enter_batman(self, contracts, vix):
        S = self.securities[self.spx].price
        today = self.time.date()

        # expiry conforme a estrutura (0DTE = hoje; 1DTE = próximo; weekly = sexta-alvo)
        expiry = self._pick_expiry(contracts, today)
        if expiry is None:
            self._skip(f"sem expiry p/ {self.structure}"); return
        legs_all = [c for c in contracts if c.expiry.date() == expiry]

        band = self._vix_width_band(vix) if self.width_mode == "vix_table" else None
        call_fly = self._build_side(legs_all, S, expiry, OptionRight.CALL, width_band=band)
        if call_fly is None:
            self._skip("não montou call fly"); return
        # symmetry='sym' -> put herda o MESMO width do call (Batman simétrico); 'asym' -> livre.
        force = call_fly["width"] if self.symmetry == "sym" else None
        put_fly = self._build_side(legs_all, S, expiry, OptionRight.PUT, force_wing=force, width_band=band)
        if put_fly is None:
            self._skip("não montou put fly"); return

        # Cada lado entra como COMBO de butterfly RECONHECIDO -> margem = perda máx = débito.
        # ANTES: 6 market orders soltas faziam o QC cobrar margem de NAKED short nos centros (-2);
        # com SPX subindo isso estourava a margem livre e REJEITAVA as pernas baratas a partir de
        # 2024-05 (posições tortas -> span >2024 corrompido). +1/-2/+1 é idêntico, só que netado.
        self.batman_seq += 1
        for fly in (call_fly, put_fly):
            exp = fly["c_mid"].expiry   # datetime exato do expiry escolhido
            if fly["side"] == "Call":
                strat = OptionStrategies.butterfly_call(
                    self.spxw, fly["upper"], fly["center"], fly["lower"], exp)
            else:
                strat = OptionStrategies.butterfly_put(
                    self.spxw, fly["upper"], fly["center"], fly["lower"], exp)
            self.buy(strat, 1)

        bm = {
            "id": self.batman_seq, "open_time": self.time, "expiry": expiry,
            "S_entry": S, "vix": vix, "flies": [call_fly, put_fly],
        }
        self.open_batmans.append(bm)
        if self.batman_seq <= 3:   # só os 1ºs (free tier = 10kb de log/backtest; ENTRYs estouram a cota)
            self.debug(f"{self.time} ENTRY Batman#{self.batman_seq} exp={expiry} S={S:.0f} vix={vix:.1f} "
                       f"| C w={call_fly['width']} {call_fly['lower']}/{call_fly['center']}/{call_fly['upper']} d={call_fly['entry_debit']:.2f} "
                       f"| P w={put_fly['width']} {put_fly['lower']}/{put_fly['center']}/{put_fly['upper']} d={put_fly['entry_debit']:.2f}")

    def _build_side(self, legs_all, S, expiry, right, force_wing=None, width_band=None):
        """Escolhe width (search) + center (debit/delta) p/ um lado; devolve dict do fly ou None.
        Fly SEMPRE internamente EQUIDISTANTE (exigência do combo ButterflyCall) e inteira OTM.
        force_wing != None -> usa esse width fixo (symmetry='sym': put herda o width do call)."""
        legs = [c for c in legs_all if c.right == right]
        if not legs:
            return None
        strikes = sorted({c.strike for c in legs})
        strike_set = set(strikes)
        by_strike = {c.strike: c for c in legs}
        is_call = (right == OptionRight.CALL)

        def make(center, wing):
            """Fly simétrica com strikes equidistantes REAIS (center±wing têm que existir na cadeia
            — ButterflyCall rejeita não-equidistante). Devolve (center, lo, up, cl, cm, cu, debit, wing)."""
            lo, up = center - wing, center + wing
            if lo not in strike_set or up not in strike_set:             # sem equidistante real -> rejeita
                return None
            cl, cm, cu = by_strike.get(lo), by_strike.get(center), by_strike.get(up)
            if not (cl and cm and cu):
                return None
            if self.require_fully_otm:                                    # near wing REAL além do spot
                if is_call and lo <= S: return None
                if (not is_call) and up >= S: return None
            d = (cl.ask_price + cu.ask_price) - 2 * cm.bid_price          # asas no ask, corpo no bid
            if d <= 0:
                return None
            return (center, lo, up, cl, cm, cu, d, float(wing))           # largura real = wing (simétrica)

        # candidatos de center OTM (do mais perto do ATM p/ o mais longe)
        otm = sorted([k for k in strikes if (k > S if is_call else k < S)], key=lambda k: abs(k - S))
        if not otm:
            return None

        # ---- WIDTH SEARCH: a mais LARGA cuja fly limpa fica com débito ~5% (dentro da banda real).
        # force_wing -> usa só esse width e aceita a melhor center mesmo fora da banda (o width é
        # ditado pelo outro lado no Batman simétrico). ----
        if force_wing is not None:
            wings = [force_wing]                                   # put herda o width do call (sym)
        elif self.width_mode == "fixed":
            wings = [self.fixed_width]                             # width TRAVADA (25/30/40/50); o débito move o short
        elif width_band is not None:
            wings = [w for w in self.width_candidates if width_band[0] <= w <= width_band[1]]
        else:
            wings = self.width_candidates
        relax = (force_wing is not None) or (self.width_mode == "fixed") or (width_band is not None)   # width ditado por fora -> relaxa banda de débito
        chosen, chosen_wing = None, None
        for wing in wings:                           # mais largo primeiro
            best = None                              # (gap, tupla_make)
            for center in otm:
                m = make(center, wing)
                if m is None:
                    continue
                d, aw = m[6], m[7]
                gap = abs(d - self.target_debit_frac * aw)
                if best is None or gap < best[0]:
                    best = (gap, m)
                if d < self.min_debit_frac * aw:     # já barato demais indo OTM -> para de varrer
                    break
            if best is not None:
                d, aw = best[1][6], best[1][7]
                if relax or (self.min_debit_frac <= (d / aw) <= self.debit_cap_frac):
                    chosen, chosen_wing = best[1], wing
                    break
        if chosen is None:
            return None

        # ---- P2 "delta": re-escolhe o center pelo delta-alvo, MESMA intenção de width ----
        if self.placement_mode == "delta":
            cand = None                              # (gapd, tupla_make)
            for center in otm:
                m = make(center, chosen_wing)
                if m is None:
                    continue
                dlt = self._delta(m[4], S, expiry)   # m[4] = cm (short)
                if dlt is None:
                    continue
                gapd = abs(abs(dlt) - self.target_delta)
                if cand is None or gapd < cand[0]:
                    cand = (gapd, m)
            if cand is None:
                return None                          # sem greeks/IV utilizável neste lado
            chosen = cand[1]

        center, lo, up, cl, cm, cu, debit, actual_w = chosen
        short_delta = self._delta(cm, S, expiry)
        return {
            "side": "Call" if is_call else "Put", "width": round(actual_w, 1),
            "lower": lo, "center": center, "upper": up,
            "c_low": cl, "c_mid": cm, "c_up": cu,
            "entry_debit": debit, "debit_frac": (debit / actual_w) if actual_w else 0.0,
            "short_delta": short_delta,
            # gravação de gestão (preenchidos na marcação intraday):
            "max_value": debit, "cross": {lvl: None for lvl in self.tp_levels}, "closed": False,
        }

    # ===================== MARCAÇÃO (grava cruzamentos de TP) =====================
    def _mark_batman(self, bm):
        for fly in bm["flies"]:
            if fly.get("closed"):
                continue
            lo, mid, up = fly["c_low"].symbol, fly["c_mid"].symbol, fly["c_up"].symbol
            # valor p/ FECHAR a fly (conservador): vende as longs no bid, recompra as shorts no ask
            lo_b = self.securities[lo].bid_price
            up_b = self.securities[up].bid_price
            mid_a = self.securities[mid].ask_price
            if lo_b <= 0 or up_b <= 0 or mid_a <= 0:
                continue
            value = (lo_b + up_b) - 2 * mid_a
            if value > fly["max_value"]:
                fly["max_value"] = value
            d = fly["entry_debit"]
            for lvl in self.tp_levels:
                if fly["cross"][lvl] is None and value >= (1.0 + lvl) * d:
                    fly["cross"][lvl] = (self.time.strftime("%H:%M"), round(value, 2))
            # CLOSE-RULE %-over-debit EXECUTADA: fecha a fly ao cruzar (1+tp_close_frac)*débito
            if self.tp_close_frac is not None and value >= (1.0 + self.tp_close_frac) * d:
                exp = fly["c_mid"].expiry
                if fly["side"] == "Call":
                    self.sell(OptionStrategies.butterfly_call(self.spxw, fly["upper"], fly["center"], fly["lower"], exp), 1)
                else:
                    self.sell(OptionStrategies.butterfly_put(self.spxw, fly["upper"], fly["center"], fly["lower"], exp), 1)
                fly["closed"] = True
                self._record(bm, fly, self.securities[self.spx].price, value)   # realiza no valor do TP

    # ===================== SETTLE =====================
    def _settle_due(self):
        """No expiry: registra o intrínseco (cash-settle) de cada fly e fecha o batman.
        NÃO manda market order — SPXW liquida em CAIXA no preço oficial (lição da Fase 1)."""
        if not self.open_batmans:
            return
        S_T = self.securities[self.spx].price
        still_open = []
        for bm in self.open_batmans:
            if bm["expiry"] != self.time.date():
                still_open.append(bm); continue
            for fly in bm["flies"]:
                if fly.get("closed"):
                    continue                      # já fechado pela close-rule (TP) — não settla de novo
                lo, mid, up = fly["lower"], fly["center"], fly["upper"]
                if fly["side"] == "Call":
                    payoff = max(0, S_T - lo) - 2 * max(0, S_T - mid) + max(0, S_T - up)
                else:
                    payoff = max(0, lo - S_T) - 2 * max(0, mid - S_T) + max(0, up - S_T)
                self._record(bm, fly, S_T, payoff)
        self.open_batmans = still_open

    def _record(self, bm, fly, S_T, payoff):
        d = fly["entry_debit"]
        net = (payoff - d) * 100.0
        ret = (payoff - d) / d if d > 0 else 0.0
        c50  = fly["cross"].get(0.50);  c100 = fly["cross"].get(1.00)
        self.rows.append({
            "batman_id": bm["id"],
            "open_date": bm["open_time"].strftime("%Y-%m-%d"),
            "open_time": bm["open_time"].strftime("%H:%M"),
            "expiry_date": bm["expiry"].strftime("%Y-%m-%d"),
            "side": fly["side"], "placement": self.placement_mode, "width": fly["width"],
            "structure": self.structure, "symmetry": self.symmetry,
            "vix": round(bm["vix"], 2), "vix_bucket": self._vix_bucket(bm["vix"]),
            "S_entry": round(bm["S_entry"], 2), "S_settle": round(S_T, 2),
            "lower": fly["lower"], "center": fly["center"], "upper": fly["upper"],
            "short_delta": round(fly["short_delta"], 4) if fly["short_delta"] is not None else "",
            "entry_debit": round(d, 2), "debit_frac": round(fly["debit_frac"], 4),
            "max_value": round(fly["max_value"], 2),
            # cruzamentos: hora e valor de cada nível (vazio = nunca cruzou)
            **{f"cross_{int(lvl*100)}_t": (fly["cross"][lvl][0] if fly["cross"][lvl] else "") for lvl in self.tp_levels},
            **{f"cross_{int(lvl*100)}_v": (fly["cross"][lvl][1] if fly["cross"][lvl] else "") for lvl in self.tp_levels},
            "settle_payoff": round(payoff, 2), "settle_net": round(net, 2), "settle_return": round(ret, 4),
            "zone": self._zone(ret), "settle_result": "W" if net > 0 else "L",
        })

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
        # T em anos (datetime do expiry às 16:00 ET)
        exp_dt = datetime(expiry.year, expiry.month, expiry.day, 16, 0)
        T = max((exp_dt - self.time).total_seconds() / (365.0 * 24 * 3600), 1e-6)
        r = 0.04
        d1 = (math.log(S / c.strike) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
        nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
        return nd1 if c.right == OptionRight.CALL else nd1 - 1.0

    @staticmethod
    def _vix_width_band(vix):
        """Tabela VIX->width do Ernie (CZ, 2026-05-26): banda de largura por regime de VIX."""
        if vix < 17:  return (20, 30)
        if vix < 25:  return (30, 40)
        if vix < 32:  return (40, 50)
        return (50, 60)

    @staticmethod
    def _vix_bucket(vix):
        if vix < 15:  return "<15"
        if vix < 17:  return "15-17"
        if vix < 22:  return "17-22"
        if vix < 32:  return "22-32"
        return "32+"

    @staticmethod
    def _zone(ret):
        if ret <= -0.5:  return 0   # full/near-full loss
        if ret <= 1.0:   return 1   # modest winner
        if ret <= 4.0:   return 2   # big winner
        return 3                    # fat tail

    def _skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    def _log_variant_summary(self):
        """Resumo compacto (cabe no log): net$ e WR% por gestão (M0/+TP) × bucket de VIX, por-fly.
        Prévia do que o app vai gerar — mostra NA HORA se o take-profit do CZ vira o resultado.
        TP[L]: se a fly cruzou (1+L)*débito intraday -> sai nesse valor; senão -> hold (settle)."""
        def pnl(r, L):
            if L is None:
                return r["settle_net"]
            v = r.get(f"cross_{int(L*100)}_v", "")
            if v != "" and v is not None:
                return (float(v) - r["entry_debit"]) * 100.0
            return r["settle_net"]
        variants = [("M0_hold", None)] + [(f"+{int(L*100)}%", L) for L in self.tp_levels]
        buckets = ["<15", "15-17", "17-22", "22-32", "32+", "ALL"]
        self.log("=== VARIANT SUMMARY === net$ / WR% por gestão × VIX bucket (por-fly)")
        for name, L in variants:
            parts = []
            for b in buckets:
                rs = self.rows if b == "ALL" else [r for r in self.rows if r["vix_bucket"] == b]
                if not rs:
                    parts.append(f"{b}:—"); continue
                pls = [pnl(r, L) for r in rs]
                net = sum(pls)
                wr = 100.0 * sum(1 for x in pls if x > 0) / len(pls)
                parts.append(f"{b} ${net:,.0f}/{wr:.0f}%")
            self.log(f"{name:8s} | " + " | ".join(parts))

    def _emit_runtime_stats(self):
        """Cuspe os agregados-chave como RUNTIME STATISTICS — único canal export-safe no tier não
        institucional (ObjectStore export é bloqueado; logs não vêm na API). Lidos depois via
        /backtests/read -> runtimeStatistics. Net por-FLY."""
        rows = self.rows
        if not rows:
            return

        def pnl(r, L):
            if L is None:
                return r["settle_net"]
            v = r.get(f"cross_{int(L*100)}_v", "")
            if v not in ("", None):
                return (float(v) - r["entry_debit"]) * 100.0
            return r["settle_net"]

        # M0 (hold) por bucket de VIX
        for b in ["<15", "15-17", "17-22", "22-32", "32+"]:
            rs = [r for r in rows if r["vix_bucket"] == b]
            if rs:
                net = sum(pnl(r, None) for r in rs)
                self.set_runtime_statistic(f"M0 VIX {b}", f"${net:,.0f} (n={len(rs)})")

        # M0 por ano-calendário
        from collections import defaultdict
        by_yr, cnt = defaultdict(float), defaultdict(int)
        for r in rows:
            yr = r["open_date"][:4]
            by_yr[yr] += pnl(r, None); cnt[yr] += 1
        for yr in sorted(by_yr):
            self.set_runtime_statistic(f"M0 {yr}", f"${by_yr[yr]:,.0f} (n={cnt[yr]})")

        # hold vs TP (net + WR) — testa a tese de TP do CZ no span inteiro
        for L, lbl in [(None, "M0 hold"), (0.5, "+50%"), (1.0, "+100%"), (2.0, "+200%")]:
            net = sum(pnl(r, L) for r in rows)
            wr = 100.0 * sum(1 for r in rows if pnl(r, L) > 0) / len(rows)
            self.set_runtime_statistic(f"NET {lbl}", f"${net:,.0f} / WR {wr:.0f}%")

        # sanidade do width-fallback: débito/lado médio e width médio realizados
        import statistics as _st
        self.set_runtime_statistic("debit_frac med", f"{_st.median(r['debit_frac'] for r in rows):.3f}")
        self.set_runtime_statistic("width med", f"{_st.median(r['width'] for r in rows):.0f}")

    # ===================== EXPORT =====================
    def on_end_of_algorithm(self):
        cols = (["batman_id", "open_date", "open_time", "expiry_date", "side", "placement",
                 "structure", "symmetry", "width",
                 "vix", "vix_bucket", "S_entry", "S_settle", "lower", "center", "upper", "short_delta",
                 "entry_debit", "debit_frac", "max_value"]
                + [f"cross_{int(l*100)}_t" for l in self.tp_levels]
                + [f"cross_{int(l*100)}_v" for l in self.tp_levels]
                + ["settle_payoff", "settle_net", "settle_return", "zone", "settle_result"])
        lines = [",".join(cols)]
        for r in self.rows:
            lines.append(",".join(str(r.get(c, "")) for c in cols))

        try:
            self.object_store.save(f"batman_{self.run_tag}.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou (ok no tier free): {e}")

        # CSV completo só cabe no log em janela curta (free tier = 10kb/backtest). Em run grande
        # fica no ObjectStore -> ler no Research notebook (qb.object_store.read(...)).
        if len(self.rows) <= 80:
            self.log(f">>>CSV_START batman_{self.run_tag}")
            for ln in lines:
                self.log(ln)
            self.log(">>>CSV_END")
        else:
            self.log(f"[CSV completo no ObjectStore: 'batman_{self.run_tag}.csv' "
                     f"({len(self.rows)} flies) — ler no Research notebook / lean cloud object-store get]")

        self._log_variant_summary()
        self._emit_runtime_stats()

        # resumo (M0 = hold-to-expiry, que é o que a equity do QC reflete)
        n = len(self.rows)
        flies_w = sum(1 for r in self.rows if r["settle_result"] == "W")
        net = sum(r["settle_net"] for r in self.rows)
        n_bm = len({r["batman_id"] for r in self.rows})
        self.log(f"=== BATMAN v1 [{self.run_tag}] === batmans={n_bm} | flies={n} "
                 f"| flies W={flies_w} ({(flies_w/n*100 if n else 0):.0f}%) | net M0(hold)=${net:,.0f} | skips={len(self.skips)}")
        from collections import Counter
        reasons = Counter(r for _, r in self.skips)
        if reasons:
            self.log("SKIPS: " + ", ".join(f"{k}={v}" for k, v in reasons.items()))
        self.log("CSV por-FLY entre >>>CSV_START/>>>CSV_END (ou 'Download Logs'). "
                 "As variantes de close (150%/200%/hold) e cortes por VIX saem do dataset NO APP.")
