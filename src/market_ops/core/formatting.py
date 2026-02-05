def fmt_pct(x):
    if x is None:
        return "?"
    return f"{float(x):+.1f}%"


def fmt_usd(x):
    if x is None:
        return "?"
    v = float(x)
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"
