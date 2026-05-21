"""
Pos-fix: confere que o P&L REALIZADO por perna agora e' limitado (regra dos 10% intacta) e que
os numeros assustadores (-23k etc.) que aparecem na aba Trades sao a coluna MAE (max adverse
excursion = pior oscilacao INTRADAY em papel), NAO o P&L realizado.
Colunas QC: 0=EntryTime 1=Symbol 2=ExitTime 3=Dir 4=EntryPx 5=ExitPx 6=Qty 7=P&L 8=Fees 9=MAE 10=MFE 11=Drawdown 12=IsWin 13=OrderIds
"""
import csv

ANALYTIC = {
 "2024-12-18":-300,"2024-08-07":-295,"2024-07-30":1661,"2024-07-24":2548,"2024-09-11":-290,
 "2024-09-10":-285,"2024-07-15":-270,"2024-10-09":1444,"2024-07-10":2402,"2024-12-23":-295,
}  # subset p/ os trades de maior MAE (os "assustadores")

RAW = r'''
"2024-07-10T14:00:00Z,""SPXW  240710C05600000"",2024-07-11T05:00:00Z,Buy,3.2,0,1,-320,0,-320,3170,3490,1,""    193,196"" "
"2024-07-10T14:00:00Z,""SPXW  240710C05630000"",2024-07-11T05:00:00Z,Sell,0.1,0,2,20,0,-980,20,990,0,""    194,197"" "
"2024-07-10T14:00:00Z,""SPXW  240710C05660000"",2024-07-11T05:00:00Z,Buy,0.05,0,1,-5,0,-5,5,10,0,""    195,198"" "
"2024-07-24T14:00:00Z,""SPXW  240724P05400000"",2024-07-25T05:00:00Z,Buy,0.4,0,1,-40,0,-40,37.5,77.5,0,""    217,220"" "
"2024-07-24T14:00:00Z,""SPXW  240724P05430000"",2024-07-25T05:00:00Z,Sell,1.05,0,2,210,0,-1710,210,1820,0,""    218,221"" "
"2024-07-24T14:00:00Z,""SPXW  240724P05460000"",2024-07-25T05:00:00Z,Buy,4.6,0,1,-460,0,-460,3460,3920,1,""    219,222"" "
"2024-07-30T14:00:00Z,""SPXW  240730P05395000"",2024-07-31T05:00:00Z,Buy,0.3,0,1,-30,0,-30,870,900,0,""    229,232"" "
"2024-07-30T14:00:00Z,""SPXW  240730P05425000"",2024-07-31T05:00:00Z,Sell,1.15,0,2,230,0,-5010,230,5030,1,""    230,233"" "
"2024-07-30T14:00:00Z,""SPXW  240730P05455000"",2024-07-31T05:00:00Z,Buy,5,0,1,-500,0,-500,4760,5260,1,""    231,234"" "
"2024-08-07T14:00:00Z,""SPXW  240807P05235000"",2024-08-08T05:00:00Z,Buy,2.15,0,1,-215,0,-215,3529,3744,1,""    241,244"" "
"2024-08-07T14:00:00Z,""SPXW  240807P05265000"",2024-08-08T05:00:00Z,Sell,4.4,0,2,880,0,-12870,880,13130,0,""    242,245"" "
"2024-08-07T14:00:00Z,""SPXW  240807P05295000"",2024-08-08T05:00:00Z,Buy,9.6,0,1,-960,0,-960,8780,9740,1,""    243,246"" "
"2024-12-18T15:00:00Z,""SPXW  241218P05960000"",2024-12-19T06:00:00Z,Buy,0.3,0,1,-30,0,-30,8730,8760,1,""    415,418"" "
"2024-12-18T15:00:00Z,""SPXW  241218P05990000"",2024-12-19T06:00:00Z,Sell,1.05,0,2,210,0,-23010,210,23160,0,""    416,419"" "
"2024-12-18T15:00:00Z,""SPXW  241218P06020000"",2024-12-19T06:00:00Z,Buy,4.8,0,1,-480,0,-480,14210,14690,1,""    417,420"" "
'''

trades = {}
for line in RAW.strip().splitlines():
    line = line.strip()
    if not line:
        continue
    if line.startswith('"') and line.endswith('"'):
        line = line[1:-1]
    line = line.replace('""', '"').rstrip().rstrip('"').rstrip()
    f = next(csv.reader([line]))
    d = f[0][:10]
    pnl, mae = float(f[7]), float(f[9])
    t = trades.setdefault(d, {"pnl": 0.0, "worst_mae": 0.0, "max_leg_loss": 0.0})
    t["pnl"] += pnl
    t["worst_mae"] = min(t["worst_mae"], mae)
    t["max_leg_loss"] = min(t["max_leg_loss"], pnl)

print(f"{'data':<12}{'P&L real (col7)':>16}{'pior MAE (col9)':>18}{'analitico':>12}")
print("-"*58)
for d in sorted(trades, key=lambda x: trades[x]["worst_mae"]):
    t = trades[d]
    print(f"{d:<12}{t['pnl']:>16,.0f}{t['worst_mae']:>18,.0f}{ANALYTIC.get(d,'?'):>12}")
print("-"*58)
all_leg_losses = min(t["max_leg_loss"] for t in trades.values())
print(f"Pior P&L REALIZADO de UMA perna (col 7), nesses trades: ${all_leg_losses:,.0f}")
print("=> os -$23k/-$12k/-$5k que aparecem na aba Trades sao a coluna MAE (oscilacao intraday),")
print("   NAO o P&L realizado. O net real de cada trade = ~debit (loser) ou o winner — limitado.")
