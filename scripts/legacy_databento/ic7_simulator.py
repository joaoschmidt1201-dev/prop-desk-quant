"""
===============================================================================
 IC7 SIMULATOR — Iron Condor 7DTE Breakeven Engine
 Prop Desk Quant | Senior Quant Developer
===============================================================================
 Motor quantitativo que calcula o movimento esperado de 1 Desvio Padrão
 para uma janela de 7 dias corridos (7DTE) a partir da Volatilidade
 Histórica (HV) anualizada dos últimos 30 pregões do NDX.
===============================================================================
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# PARÂMETROS DO MOTOR
# ─────────────────────────────────────────────────────────────────────────────
TICKER = "^NDX"
HV_WINDOW = 30          # Janela de pregões para cálculo da HV
TRADING_DAYS_YEAR = 252  # Pregões anuais (padrão mercado US)
DTE_CALENDAR_DAYS = 7    # Horizonte operacional mínimo da mesa
CALENDAR_DAYS_YEAR = 365
SD_MULTIPLIER = 1.0      # 1 Desvio Padrão (ajustável para 1.5, 2.0, etc.)


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES DO MOTOR QUANTITATIVO
# ─────────────────────────────────────────────────────────────────────────────

def fetch_price_data(ticker: str, period: str = "3mo") -> pd.DataFrame:
    """Baixa dados históricos via yfinance."""
    data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if data.empty:
        raise ValueError(f"[ERRO] Nenhum dado retornado para {ticker}.")
    return data


def calc_annualized_hv(closes: pd.Series, window: int, trading_days: int) -> float:
    """
    Calcula a Volatilidade Histórica (HV) anualizada.

    Fórmula:
        log_returns = ln(Close_t / Close_{t-1})
        HV = std(log_returns[-window:]) * sqrt(trading_days)
    """
    log_returns = np.log(closes / closes.shift(1)).dropna()
    if len(log_returns) < window:
        raise ValueError(
            f"[ERRO] Dados insuficientes: {len(log_returns)} retornos "
            f"disponíveis, mínimo necessário = {window}."
        )
    hv = log_returns.tail(window).std() * np.sqrt(trading_days)
    return float(hv)


def calc_expected_move(spot: float, hv_annual: float,
                       dte_days: int, calendar_year: int,
                       sd_mult: float) -> float:
    """
    Calcula o movimento esperado em pontos absolutos para o horizonte DTE.

    Fórmula:
        Expected Move = Spot × HV_anual × sqrt(DTE / 365) × SD_multiplier
    """
    return spot * hv_annual * np.sqrt(dte_days / calendar_year) * sd_mult


def calc_ic_breakevens(spot: float, expected_move: float) -> tuple[float, float]:
    """Define os alvos de Breakeven Superior e Inferior do Iron Condor."""
    upper_be = spot + expected_move
    lower_be = spot - expected_move
    return upper_be, lower_be


# ─────────────────────────────────────────────────────────────────────────────
# RELATÓRIO TERMINAL
# ─────────────────────────────────────────────────────────────────────────────

def print_report(ticker: str, spot: float, hv: float,
                 move_pts: float, upper: float, lower: float,
                 dte: int, window: int) -> None:
    """Imprime o relatório formatado no terminal."""
    width = 62
    border = "═" * width
    divider = "─" * width

    print()
    print(f"╔{border}╗")
    print(f"║{'IC7 SIMULATOR — PROP DESK QUANT':^{width}}║")
    print(f"║{'Iron Condor 7DTE Breakeven Engine':^{width}}║")
    print(f"╠{border}╣")
    print(f"║  Data do Relatório:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<{width - 23}}║")
    print(f"║  Ativo:              {ticker:<{width - 23}}║")
    print(f"║  Janela HV:          {window} pregões{' ' * (width - 34)}║")
    print(f"║  Horizonte DTE:      {dte} dias corridos{' ' * (width - 39)}║")
    print(f"╠{border}╣")
    print(f"║{'DADOS DO MOTOR':^{width}}║")
    print(f"╠{border}╣")
    print(f"║  Último Fechamento:  {spot:>12,.2f} pts{' ' * (width - 38)}║")
    print(f"║  HV Anualizada:      {hv * 100:>12.2f} %{' ' * (width - 37)}║")
    print(f"║  Movimento 1 SD:     {move_pts:>12,.2f} pts{' ' * (width - 38)}║")
    print(f"╠{border}╣")
    print(f"║{'ALVOS BREAKEVEN — IRON CONDOR 7DTE':^{width}}║")
    print(f"╠{border}╣")
    print(f"║  ▲ Breakeven SUP (+1 SD):  {upper:>12,.2f} pts{' ' * (width - 44)}║")
    print(f"║  ● Spot Atual:             {spot:>12,.2f} pts{' ' * (width - 44)}║")
    print(f"║  ▼ Breakeven INF (-1 SD):  {lower:>12,.2f} pts{' ' * (width - 44)}║")
    print(f"╠{border}╣")
    print(f"║  Distância ao BE Sup:  +{move_pts:>10,.2f} pts  "
          f"({move_pts / spot * 100:>5.2f}%){' ' * (width - 53)}║")
    print(f"║  Distância ao BE Inf:  -{move_pts:>10,.2f} pts  "
          f"({move_pts / spot * 100:>5.2f}%){' ' * (width - 53)}║")
    print(f"╚{border}╝")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# EXECUÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # 1. Fetch data
    df = fetch_price_data(TICKER)
    closes = df["Close"].squeeze()
    spot = float(closes.iloc[-1])

    # 2. Volatilidade Histórica anualizada (30 pregões)
    hv = calc_annualized_hv(closes, HV_WINDOW, TRADING_DAYS_YEAR)

    # 3. Movimento esperado de 1 SD para 7DTE
    move_1sd = calc_expected_move(
        spot, hv, DTE_CALENDAR_DAYS, CALENDAR_DAYS_YEAR, SD_MULTIPLIER
    )

    # 4. Breakevens do Iron Condor
    upper_be, lower_be = calc_ic_breakevens(spot, move_1sd)

    # 5. Relatório
    print_report(TICKER, spot, hv, move_1sd, upper_be, lower_be,
                 DTE_CALENDAR_DAYS, HV_WINDOW)


if __name__ == "__main__":
    main()
