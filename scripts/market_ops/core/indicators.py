def flow_label(*, px_chg, oi_chg):
    if not isinstance(px_chg, (int, float)) or not isinstance(oi_chg, (int, float)):
        return "资金方向不明"
    if oi_chg >= 5 and px_chg >= 1:
        return "多头加仓（价↑OI↑）"
    if oi_chg >= 5 and px_chg <= -1:
        return "空头加仓（价↓OI↑）"
    if oi_chg <= -5 and px_chg >= 1:
        return "空头回补（价↑OI↓）"
    if oi_chg <= -5 and px_chg <= -1:
        return "多头止损/出清（价↓OI↓）"
    return "轻微/震荡（价/OI变化不大）"
