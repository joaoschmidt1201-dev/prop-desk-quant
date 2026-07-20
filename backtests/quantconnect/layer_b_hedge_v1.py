# region imports
from AlgorithmImports import *
import math
# endregion

class LayerBHedgeV1(QCAlgorithm):
    """
    LAYER B - 1x2 SQUARE ROOT HEDGE (Fat Tail / Black Swan hedge de PORTFOLIO).
    Liga: hedge/Kurze Anleitung zur Pflege bzw. Adj.txt (fonte primaria, Discord DE).

    SPEC (fonte primaria, traduzida):
      - Compra 2 long puts @ delta 10, financiados por 1 short put @ delta 25.
        "I.d.R. ergibt sich ein Credit" -> normalmente abre a credito.
      - LZ ideal 40-45 DTE (max 60). Alvo 42.
      - Roll TODA SEXTA, ASSIMETRICO:
          ALTA  -> rola +1 semana de vencimento E re-strikeia os deltas de volta p/ 10/25
          BAIXA -> NAO re-strikear; rola SO HORIZONTAL (mesmos strikes, +1 semana)
        Re-strikear na baixa arrastaria a cova junto com o spot e entregaria a protecao
        ja acumulada.
      - Manter 40-45 DTE segura vega alto / gamma baixo e evita expirar sobre a cova.
      - "Dieser Hedge wird ab einem Drawdown von ca. 12% seine volle Wirkung entfalten."

    A fonte afirma "Ihr habt Null Risk, solange Ihr Euren Hedge pflegt". ISSO E FALSO e
    NAO esta implementado como verdade: a cova e risco real (o proprio texto admite P&L
    negativa na queda) e o roll e dependencia OPERACIONAL, nao disciplina. O backtest
    assume que o roll de sexta sempre acontece -- essa e uma premissa, nao um fato.

    AMBIGUIDADE DA FONTE: ela nao define "Aufwaerts/Abwaerts" em relacao a QUE.
    Virou parametro (roll_ref x roll_band), nao chute. Zona neutra -> horizontal
    (escolha conservadora: nao re-strikeia). Nao e record-and-derive: cada variante
    muda os strikes dai pra frente (state-dependent) -> uma run por variante.

    CONTABILIDADE: posicao CONTINUA rolada, nao trades independentes. Tudo e FLUXO DE
    CAIXA (positivo = dinheiro entrando), que e exatamente o que mede a restricao #1
    do Joao ("receber credito semanalmente"):
        cash_open  = P_short - 2*P_long          (credito na entrada)
        cash_close = 2*P_long' - P_short'        (o que sobra ao desmontar)
        net do roll = cash_close(velha) + cash_open(nova)   <- restricao #1
        P&L total   = cash acumulado + mark da posicao aberta
    Confere na entrada: cash=+credito, mark=-credito, P&L=0.

    MARGEM: BuyingPowerModel.NULL (fix validado do crash OptionStrategyPositionGroup-
    BuyingPowerModel em multi-perna; um 1x2 ratio e exatamente o caso). Isso faz o QC
    PARAR de policiar margem -> a restricao #3 do Joao (margem sob portfolio margin)
    fica EXPLICITAMENTE SEM RESPOSTA nesta fase, por decisao.

    FILL: mid e headline (regra do Joao: sempre mid). cons (cruzando o spread) e
    diagnostico -> mede quanto a iliquidez custa em RUT vs SPX. Padrao da casa,
    igual short_strangle_rut.py:130-132.
    """

    def initialize(self):
        self.entry_hour   = int(self.get_parameter("entry_hour", "10"))
        self.entry_minute = int(self.get_parameter("entry_minute", "0"))
        self.d_long       = float(self.get_parameter("delta_long",  "0.10"))   # compra 2x
        self.d_short      = float(self.get_parameter("delta_short", "0.25"))   # vende 1x
        self.target_dte   = int(self.get_parameter("target_dte", "42"))        # 40-45 ideal
        self.dte_lo       = int(self.get_parameter("dte_lo", "40"))            # so p/ diagnostico
        self.dte_hi       = int(self.get_parameter("dte_hi", "45"))
        self.strike_filter = int(self.get_parameter("strike_filter", "120"))
        # --- aceleracao da cadeia (nao muda resultado; ver A/B em reports/layer_b) ---
        # O motor so opera PUTS (as calls sao descartadas no _open) e o roll so toca a janela
        # ~35-45 DTE (o _open escolhe o expiry mais perto de target_dte). Carregar 0-52 DTE e a
        # cadeia de calls inteira e trabalho jogado fora. Defaults = comportamento ANTIGO, pra
        # nenhuma run ja agendada mudar de perfil sem passar pelo A/B.
        # exp_lo=25 da margem de 3 rolls perdidos (42 -> 35 -> 28) antes de a perna sair do filtro.
        # strike_filter NAO se mexe: no roll horizontal o strike fica parado enquanto o spot cai,
        # entao ele deriva p/ ITM num bear -- cortar a janela positiva quebraria justo 2022.
        self.exp_lo    = int(self.get_parameter("exp_lo", "0"))
        self.puts_only = self.get_parameter("puts_only", "0").strip().lower() in ("1", "true", "yes")
        # --- robustez do mid no roll (pedido Joao 2026-07-19): mediana de ~15min p/ nao pegar 1 minuto
        # spiky/stale. robust_mark=1 usa o robusto no headline; mkdev loga o desvio vs instantaneo. ---
        self.robust_mark = self.get_parameter("robust_mark", "1").strip().lower() in ("1", "true", "yes")
        self.robust_min  = int(self.get_parameter("robust_min", "15"))
        self._last_close_mkdev = 0.0
        self.ticker       = self.get_parameter("ticker", "SPX")
        self.opt_target   = self.get_parameter("opt_target", "SPXW").strip()
        self.fill_mode    = self.get_parameter("fill_mode", "mid").lower().strip()
        self.comm_leg     = float(self.get_parameter("commission_per_contract", "1.5"))
        # roll: referencia do movimento + banda neutra (a fonte nao define -> sweep)
        self.roll_ref     = self.get_parameter("roll_ref", "wow").lower().strip()  # wow|entry|strike
        self.roll_band    = float(self.get_parameter("roll_band", "0.0"))          # 0 | 0.005 | 0.01
        sd = self.get_parameter("start_date", "2021-06-01").split("-")
        ed = self.get_parameter("end_date",   "2026-06-01").split("-")
        self.run_tag = self.get_parameter("run_tag", "LB_SPX_wow_0")

        self.set_start_date(int(sd[0]), int(sd[1]), int(sd[2]))
        self.set_end_date(int(ed[0]), int(ed[1]), int(ed[2]))
        # Base da conta (pedido do Joao 2026-07-17: 100k, nao 1M). NAO muda o headline: o P&L
        # do CROLL e analitico em PONTOS no mid, e o BuyingPowerModel.NULL desliga o policiamento
        # de margem -> a ordem preenche igual. Mexe SO na leitura de equity/Return% do blotter.
        # Consequencia a declarar: a 1 unidade o blotter perde ~$63k/ano; sobre 100k isso e
        # -63%/ano e a conta vira negativa. O numero nao fica errado, fica CRU -- o Return% e
        # que deixa de significar coisa (nao ha conta de 100k que carregue 1 unidade disto).
        self.base_cash = float(self.get_parameter("base_cash", "100000"))
        self.set_cash(self.base_cash)
        self.set_time_zone(TimeZones.NEW_YORK)

        self.set_security_initializer(lambda s: s.set_buying_power_model(BuyingPowerModel.NULL))
        self.settings.minimum_order_margin_portfolio_percentage = 0

        index = self.add_index(self.ticker, Resolution.MINUTE)
        self.idx = index.symbol
        if self.opt_target:
            option = self.add_index_option(self.idx, self.opt_target, Resolution.MINUTE)
        else:
            option = self.add_index_option(self.idx, Resolution.MINUTE)
        def _chain_filter(u):
            u = u.include_weeklys()
            if self.puts_only:
                u = u.puts_only()
            return u.expiration(self.exp_lo, self.target_dte + 10) \
                    .strikes(-self.strike_filter, self.strike_filter)

        option.set_filter(_chain_filter)
        self.opt = option.symbol

        self.vix = self.add_index("VIX", Resolution.MINUTE).symbol

        self.mark_every_min = 30
        self.pos = None            # posicao unica, continua
        self.rows = []             # uma linha por roll
        self.skips = []
        self.cum_cash = 0.0        # fluxo de caixa acumulado (pts)
        self.cum_cash_cons = 0.0
        self.cum_comm = 0.0
        self.S_first = None        # spot na 1a entrada (ref "entry")
        self.idx_peak = 0.0        # running max do indice -> drawdown
        self.rolled_today = False
        self.current_day = None
        self.seq = 0
        self._chain_seen = 0

        self.schedule.on(self.date_rules.every_day(self.idx),
                         self.time_rules.at(16, 1), self._settle_guard)

    # ===================== LOOP =====================
    def on_data(self, slice: Slice):
        if self.current_day != self.time.date():
            self.current_day = self.time.date()
            self.rolled_today = False

        S = self.securities[self.idx].price
        if S > 0:
            self.idx_peak = max(self.idx_peak, S)

        # marcacao: rastreia os extremos INTRA-SEMANA sem gastar linha de log.
        # Um crash pode ir e voltar dentro da semana; amostrar so no roll perderia o fundo.
        if self.time.minute % self.mark_every_min == 0 and self.pos is not None:
            self._track_extremes(S)

        if self.rolled_today or self.time.weekday() != 4:      # 4 = sexta
            return
        if (self.time.hour, self.time.minute) < (self.entry_hour, self.entry_minute):
            return
        chain = slice.option_chains.get(self.opt)
        if chain is None:
            return
        contracts = [c for c in chain]
        if not contracts:
            self.rolled_today = True
            self._skip("cadeia vazia"); return
        self._chain_seen += 1
        self._roll_or_enter(contracts)
        self.rolled_today = True

    def _track_extremes(self, S):
        p = self.pos
        if S > 0:
            p["S_min"] = min(p["S_min"], S) if p["S_min"] else S
        mv = self._mark_value(p)
        if mv is not None:
            p["mark_max"] = mv if p["mark_max"] is None else max(p["mark_max"], mv)

    # ===================== ROLL / ENTRADA =====================
    def _roll_or_enter(self, contracts):
        S = self.securities[self.idx].price
        if S <= 0:
            self._skip("spot<=0"); return

        if self.pos is None:
            newp = self._open(contracts, S, keep=None)
            if newp is not None:
                self.S_first = S
                self._record_roll(newp, direction="entry", restruck=1,
                                  cash_close=0.0, cash_close_cons=0.0, old=None)
            return

        old = self.pos
        # --- direcao do movimento (a fonte nao define a referencia -> parametro) ---
        if self.roll_ref == "entry":
            ref = self.S_first
        elif self.roll_ref == "strike":
            ref = old["k_short"]
        else:                                   # "wow" = week-over-week (default)
            ref = old["S_roll"]
        chg = (S - ref) / ref if ref else 0.0
        # ALTA (acima da banda) -> re-strikeia. Baixa OU zona neutra -> horizontal.
        up = chg > self.roll_band
        keep = None if up else (old["k_short"], old["k_long"])

        # abre a nova ANTES de fechar a velha: se nao achar pernas, nao fica descoberto.
        newp = self._open(contracts, S, keep=keep)
        if newp is None:
            self._skip("sem pernas p/ rolar - mantem posicao"); return
        cash_close, cash_close_cons = self._close(old)
        self._record_roll(newp, direction=("up" if up else "down"),
                          restruck=(1 if up else 0),
                          cash_close=cash_close, cash_close_cons=cash_close_cons, old=old)

    def _open(self, contracts, S, keep):
        """keep=None -> escolhe strikes por delta (10/25). keep=(k_short,k_long) -> horizontal."""
        today = self.time.date()
        exps = sorted({c.expiry.date() for c in contracts if (c.expiry.date() - today).days >= 1})
        if not exps:
            self._skip("sem expiry futuro"); return None
        expiry = min(exps, key=lambda e: abs((e - today).days - self.target_dte))
        dte = (expiry - today).days
        legs = [c for c in contracts if c.expiry.date() == expiry and c.right == OptionRight.PUT]
        if not legs:
            self._skip("sem puts no expiry"); return None

        if keep is None:
            sh = self._pick_by_delta(legs, S, expiry, self.d_short)
            lg = self._pick_by_delta(legs, S, expiry, self.d_long)
        else:
            sh = self._pick_by_strike(legs, keep[0])
            lg = self._pick_by_strike(legs, keep[1])
        if sh is None or lg is None:
            self._skip("sem perna short/long"); return None

        # GATE DE TOPOLOGIA: o comprado tem que estar ABAIXO do vendido, senao nao e
        # um 1x2 backspread (a cova some e o perfil vira outra coisa).
        if lg.strike >= sh.strike:
            cand = [c for c in legs if c.strike < sh.strike]
            if not cand:
                self._skip("sem strike abaixo do short"); return None
            lg = max(cand, key=lambda c: c.strike)

        # DERIVA SILENCIOSA DE STRIKE (medida, nao assumida): no roll horizontal a fonte manda
        # MANTER o strike. Se o strike pedido nao existe na cadeia -- p.ex. ele derivou p/ fora
        # da janela `strike_filter` durante um bear, que e exatamente quando a regra importa --
        # o _pick_by_strike devolve "o mais proximo" e re-strikeia SEM AVISAR, justo onde a
        # regra proibe. Medido depois do gate de topologia p/ capturar tb o ajuste dele.
        # k_gap > 0 num roll "down" = aquele roll nao obedeceu a regra e o numero esta sujo.
        k_gap = 0.0
        if keep is not None:
            k_gap = max(abs(sh.strike - keep[0]), abs(lg.strike - keep[1]))

        # MID ROBUSTO (mediana de ~15 min) p/ a valuation nao pegar 1 minuto spiky/stale no roll.
        # Guarda tambem o instantaneo p/ MEDIR o desvio (mkdev) e provar que a robustez importou.
        sh_mid, sh_inst = self._robust_mid_sym(sh.symbol, self.robust_min)
        lg_mid, lg_inst = self._robust_mid_sym(lg.symbol, self.robust_min)
        if not self.robust_mark:
            sh_mid, lg_mid = sh_inst, lg_inst
        if sh_mid <= 0 or lg_mid <= 0:
            self._skip("preco<=0 numa perna"); return None

        cash_open      = sh_mid - 2.0 * lg_mid                    # headline: mid robusto
        cash_open_inst = sh_inst - 2.0 * lg_inst                 # mesma conta no minuto do roll
        cash_open_cons = sh.bid_price - 2.0 * lg.ask_price        # cruzando o spread

        self.market_order(sh.symbol, -1)
        self.market_order(lg.symbol, +2)
        self.cum_cash      += cash_open
        self.cum_cash_cons += cash_open_cons
        self.cum_comm      += 3.0 * self.comm_leg                 # 1 short + 2 long

        self.seq += 1
        p = {
            "id": self.seq, "open_date": today, "expiry": expiry, "dte": dte,
            "S_roll": S, "k_short": sh.strike, "k_long": lg.strike,
            "sh_sym": sh.symbol, "lg_sym": lg.symbol,
            "d_sh": self._delta(sh, S, expiry), "d_lg": self._delta(lg, S, expiry),
            "cash_open": cash_open, "cash_open_cons": cash_open_cons,
            "open_mark": 2.0 * lg_mid - sh_mid,               # mark robusto do que acabou de abrir (= -cash_open)
            "mkdev_open": abs(cash_open - cash_open_inst),    # |robusto - instantaneo| na abertura
            "S_min": S, "mark_max": None, "k_gap": k_gap,
        }
        self.pos = p
        return p

    def _close(self, pos):
        """Desmonta: recompra o short, vende os 2 longs. Retorna (cash_mid, cash_cons).
        cash_close = P&L REALIZADO da semana -> e o mais critico de robustecer contra pico/stale."""
        sh_mid, sh_inst = self._robust_mid_sym(pos["sh_sym"], self.robust_min)
        lg_mid, lg_inst = self._robust_mid_sym(pos["lg_sym"], self.robust_min)
        if not self.robust_mark:
            sh_mid, lg_mid = sh_inst, lg_inst
        cash_mid = 2.0 * lg_mid - sh_mid
        cash_inst = 2.0 * lg_inst - sh_inst
        self._last_close_mkdev = abs(cash_mid - cash_inst)   # |robusto - instantaneo| no desmonte
        sh_a = self.securities[pos["sh_sym"]].ask_price
        lg_b = self.securities[pos["lg_sym"]].bid_price
        cash_cons = 2.0 * lg_b - sh_a
        for sym in (pos["sh_sym"], pos["lg_sym"]):
            if self.portfolio[sym].invested:
                self.liquidate(sym)
        self.cum_cash      += cash_mid
        self.cum_cash_cons += cash_cons
        self.cum_comm      += 3.0 * self.comm_leg
        return cash_mid, cash_cons

    def _mark_value(self, pos):
        """Valor de desmontagem da posicao aberta (pts). P&L total = cum_cash + mark."""
        sh_mid = self._mid_sym(pos["sh_sym"]); lg_mid = self._mid_sym(pos["lg_sym"])
        if sh_mid <= 0 and lg_mid <= 0:
            return None
        return 2.0 * lg_mid - sh_mid

    def _record_roll(self, newp, direction, restruck, cash_close, cash_close_cons, old):
        S = self.securities[self.idx].price
        dd = (S / self.idx_peak - 1.0) if self.idx_peak > 0 else 0.0
        # net do roll = o que sobrou ao desmontar a velha + o credito da nova  <- restricao #1
        net_roll      = cash_close + newp["cash_open"]
        net_roll_cons = cash_close_cons + newp["cash_open_cons"]
        # mark ROBUSTO do que acabou de abrir (mesmos mids do cash_open -> invariante P&L=0 na abertura).
        mark = newp.get("open_mark")
        if mark is None:
            mark = self._mark_value(newp)
        pnl_total = self.cum_cash + (mark if mark is not None else 0.0)
        # desvio robusto-vs-instantaneo deste roll (abre + desmonta) -> quantifica o efeito do pico
        mkdev = round(newp.get("mkdev_open", 0.0) + getattr(self, "_last_close_mkdev", 0.0), 2)
        self._last_close_mkdev = 0.0
        # extremos INTRA-SEMANA da posicao que acabou de ser desmontada
        dd_wk = ""
        mk_wk = ""
        if old is not None:
            if old["S_min"] and self.idx_peak > 0:
                dd_wk = round(old["S_min"] / self.idx_peak - 1.0, 4)
            if old["mark_max"] is not None:
                mk_wk = round(old["mark_max"], 2)
        self.rows.append({
            "id": newp["id"], "date": newp["open_date"].strftime("%Y-%m-%d"),
            "dir": direction, "restruck": restruck,
            "S": round(S, 2), "dd": round(dd, 4), "dd_wk": dd_wk,
            "vix": round(self.securities[self.vix].price, 2),
            "exp": newp["expiry"].strftime("%Y-%m-%d"), "dte": newp["dte"],
            "in_band": 1 if self.dte_lo <= newp["dte"] <= self.dte_hi else 0,
            "k_sh": newp["k_short"], "k_lg": newp["k_long"],
            "d_sh": round(newp["d_sh"], 4) if newp["d_sh"] is not None else "",
            "d_lg": round(newp["d_lg"], 4) if newp["d_lg"] is not None else "",
            "cash_close": round(cash_close, 2), "cash_open": round(newp["cash_open"], 2),
            "net_roll": round(net_roll, 2), "net_roll_cons": round(net_roll_cons, 2),
            "cum_cash": round(self.cum_cash, 2), "cum_cash_cons": round(self.cum_cash_cons, 2),
            "mark": round(mark, 2) if mark is not None else "",
            "mark_max_wk": mk_wk,
            "pnl_total": round(pnl_total, 2),
            "comm": round(self.cum_comm, 2),
            "k_gap": round(newp["k_gap"], 2),   # >0 num roll "down" = re-strike proibido, silencioso
            "mkdev": mkdev,                     # |robusto - instantaneo| do roll (pts): pico/stale detectado
        })
        if newp["id"] <= 3:
            self.debug(f"{self.time} LB#{newp['id']} {direction} dte={newp['dte']} "
                       f"K {newp['k_long']}x2 / {newp['k_short']} "
                       f"open={newp['cash_open']:.2f} net={net_roll:.2f}")

    # ===================== SELECAO DE PERNA =====================
    def _pick_by_delta(self, legs, S, expiry, target):
        best, bestgap = None, 1e9
        for c in legs:
            if c.strike >= S:                 # so puts OTM
                continue
            d = self._delta(c, S, expiry)
            if d is None:
                continue
            gap = abs(abs(d) - target)
            if gap < bestgap:
                best, bestgap = c, gap
        return best

    @staticmethod
    def _pick_by_strike(legs, k):
        """Roll horizontal: mesmo strike no novo expiry. Se nao existir, o mais proximo."""
        if not legs:
            return None
        return min(legs, key=lambda c: abs(c.strike - k))

    # ===================== SETTLE (guarda) =====================
    def _settle_guard(self):
        """A posicao e rolada toda sexta e o expiry fica ~42d fora, entao isto nunca deve
        disparar. Se disparar, o roll falhou por semanas -> settle europeu no intrinseco."""
        if self.pos is None or self.pos["expiry"] != self.time.date():
            return
        S_T = self.securities[self.idx].price
        p = self.pos
        # payoff analitico no vencimento (o desk le P&L do payoff, nao do blotter)
        val = 2.0 * max(0.0, p["k_long"] - S_T) - max(0.0, p["k_short"] - S_T)
        self.cum_cash      += val
        self.cum_cash_cons += val
        for sym in (p["sh_sym"], p["lg_sym"]):
            if self.portfolio[sym].invested:
                self.liquidate(sym)
        self.log(f"SETTLE|{self.time.date()}|roll falhou - expirou|val={val:.2f}")
        self.pos = None

    # ===================== GREEKS / HELPERS =====================
    def _delta(self, c, S, expiry):
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
        px = self._mid(c)
        if px <= 0:
            return None
        lo, hi = 0.01, 3.0
        if not (self._bs_price(c.right, S, K, T, lo) <= px <= self._bs_price(c.right, S, K, T, hi)):
            return None
        for _ in range(40):
            m = 0.5 * (lo + hi)
            if self._bs_price(c.right, S, K, T, m) < px:
                lo = m
            else:
                hi = m
        return 0.5 * (lo + hi)

    @staticmethod
    def _mid(c):
        b, a = c.bid_price, c.ask_price
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return c.last_price or a or b or 0.0

    def _mid_sym(self, sym):
        b = self.securities[sym].bid_price; a = self.securities[sym].ask_price
        if b > 0 and a > 0:
            return (b + a) / 2.0
        return self.securities[sym].price or a or b or 0.0

    @staticmethod
    def _median(vals):
        v = sorted(x for x in vals if x is not None and x > 0)
        n = len(v)
        if n == 0:
            return None
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0

    def _robust_mid_sym(self, sym, minutes=15):
        """Mid ROBUSTO a pico/stale de 1 minuto: mediana do mid dos ultimos `minutes` minutos
        (pedido do Joao 2026-07-19 -- 'veja horarios proximos, troque se nao fizer sentido').
        Fallback: mid instantaneo se a history vier vazia. Devolve (robusto, instantaneo)."""
        inst = self._mid_sym(sym)
        try:
            # forma com indexador generico -> devolve QuoteBar tipado (nao DataFrame do pandas)
            hist = self.history[QuoteBar](sym, timedelta(minutes=minutes), Resolution.MINUTE)
            mids = []
            for bar in hist:
                bid = bar.bid.close if bar.bid is not None else 0.0
                ask = bar.ask.close if bar.ask is not None else 0.0
                if bid > 0 and ask > 0:
                    mids.append((bid + ask) / 2.0)
            med = self._median(mids)
            if med is not None:
                return med, inst
        except Exception:
            self._robust_fail = getattr(self, "_robust_fail", 0) + 1
        return inst, inst

    def _skip(self, reason):
        self.skips.append((self.time.strftime("%Y-%m-%d"), reason))

    # ===================== SAIDA =====================
    def _emit_runtime_stats(self):
        rows = self.rows
        if not rows:
            self.set_runtime_statistic("WARN", "0 rolls - cadeia/dados?")
            return
        import statistics as _st
        rolls = [r for r in rows if r["dir"] != "entry"]
        n = len(rolls)

        # --- RESTRICAO #1 do Joao: "receber credito semanalmente" ---
        if n:
            nets = [r["net_roll"] for r in rolls]
            pos_n = sum(1 for x in nets if x > 0)
            self.set_runtime_statistic("R1 rolls em credito",
                                       f"{pos_n}/{n} = {100.0*pos_n/n:.0f}%")
            self.set_runtime_statistic("R1 net/roll med (pts)", f"{_st.median(nets):.2f}")
            netc = [r["net_roll_cons"] for r in rolls]
            pc = sum(1 for x in netc if x > 0)
            self.set_runtime_statistic("R1 cons rolls em credito",
                                       f"{pc}/{n} = {100.0*pc/n:.0f}%")

        # --- carrego / P&L ---
        last = rows[-1]
        self.set_runtime_statistic("PnL total (pts)", f"{last['pnl_total']:.2f}")
        self.set_runtime_statistic("PnL total ($)", f"${last['pnl_total']*100.0:,.0f}")
        self.set_runtime_statistic("comissoes ($)", f"${last['comm']:,.0f}")
        gap = last["cum_cash"] - last["cum_cash_cons"]
        self.set_runtime_statistic("custo iliquidez mid-cons ($)", f"${gap*100.0:,.0f}")

        # --- RESTRICAO #3 (grind lento) vs #2 (crash): P&L por faixa de drawdown ---
        bands = [(-1.00, -0.12, "DD<=-12% (tail)"), (-0.12, -0.04, "DD -12..-4% (cova)"),
                 (-0.04, -0.005, "DD -4..-0.5%"), (-0.005, 1.0, "DD ~topo")]
        for lo, hi, label in bands:
            rs = [r for r in rolls if lo <= r["dd"] < hi]
            if rs:
                s = sum(r["net_roll"] for r in rs)
                self.set_runtime_statistic(f"#{label}",
                                           f"net {s:+.1f} pts (n={len(rs)})")

        # --- qualidade da escada de vencimentos (confunde a comparacao SPX x RUT) ---
        inb = sum(1 for r in rows if r["in_band"] == 1)
        self.set_runtime_statistic("DTE na janela 40-45",
                                   f"{inb}/{len(rows)} = {100.0*inb/len(rows):.0f}%")
        self.set_runtime_statistic("DTE med", f"{_st.median(r['dte'] for r in rows):.0f}")

        # --- veracidade dos deltas (se desviar, a selecao esta errada) ---
        ds = [abs(float(r["d_sh"])) for r in rows if r["d_sh"] not in ("", None)]
        dl = [abs(float(r["d_lg"])) for r in rows if r["d_lg"] not in ("", None)]
        if ds:
            self.set_runtime_statistic("absDelta short med/min/max",
                                       f"{_st.median(ds):.3f} / {min(ds):.3f} / {max(ds):.3f}")
        if dl:
            self.set_runtime_statistic("absDelta long med/min/max",
                                       f"{_st.median(dl):.3f} / {min(dl):.3f} / {max(dl):.3f}")
        up = sum(1 for r in rolls if r["dir"] == "up")
        self.set_runtime_statistic("rolls up/down", f"{up}/{n-up}")
        self.set_runtime_statistic("skips", str(len(self.skips)))

    def on_end_of_algorithm(self):
        cols = ["id", "date", "dir", "restruck", "S", "dd", "dd_wk", "vix", "exp", "dte",
                "in_band", "k_sh", "k_lg", "d_sh", "d_lg", "cash_close", "cash_open",
                "net_roll", "net_roll_cons", "cum_cash", "cum_cash_cons", "mark",
                "mark_max_wk", "pnl_total", "comm", "k_gap", "mkdev"]
        lines = [",".join(cols)] + [",".join(str(r.get(c, "")) for c in cols) for r in self.rows]
        try:
            self.object_store.save(f"layer_b_{self.run_tag}.csv", "\n".join(lines))
        except Exception as e:
            self.debug(f"ObjectStore save falhou: {e}")

        # CANAL ROBUSTO: ObjectStore e bloqueado no free tier; o log compacto e a fonte real.
        # ~260 rolls/run (52/ano x 5a) cabe no cap (~707 linhas).
        self.log("CROLLHDR|" + ",".join(cols) + f"|ref={self.roll_ref}|band={self.roll_band}")
        for r in self.rows:
            self.log("CROLL|" + ",".join(str(r.get(c, "")) for c in cols))
        self._emit_runtime_stats()
        n = len(self.rows)
        last = self.rows[-1] if self.rows else {}
        self.log(f"=== LAYER B [{self.run_tag}] === rolls={n} | "
                 f"pnl_total={last.get('pnl_total','?')} pts | "
                 f"chain_seen={self._chain_seen} | skips={len(self.skips)}")
        for d, why in self.skips[:8]:
            self.log(f"SKIP|{d}|{why}")
