import ccxt
import pandas as pd
import requests
import os
import time

# --- CONFIGURATION ---
# We fetch the Webhook URL from GitHub Secrets
WEBHOOK_URL = os.environ.get('WEBHOOK_URL') 

TIMEFRAMES = ['30m', '1h', '4h']
TOLERANCE_PCT = 0.2  # 0.2% Tolerance
LIMIT_PAIRS = 100    # <--- UPDATED: Scans Top 100 Pairs

# --- PATTERN LOGIC ---
def check_pattern(df, tolerance=0.002):
    if len(df) < 3: return None

    # Candles: c1 (Left), c2 (Middle), c3 (Right)
    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    # 1. Determine Colors
    c1_green = c1['close'] > c1['open']
    c2_green = c2['close'] > c2['open']
    c3_green = c3['close'] > c3['open']

    # 2. Check Sequence
    # RGR: Red, Green, Red
    is_rgr = (not c1_green) and c2_green and (not c3_green)
    # GRG: Green, Red, Green
    is_grg = c1_green and (not c2_green) and c3_green

    if not (is_rgr or is_grg):
        return None

    # 3. Check Equal Highs AND Lows (Strict Mode)
    # We compare Middle Candle (c2) to Left Candle (c1)
    high_diff = abs(c2['high'] - c1['high'])
    low_diff  = abs(c2['low'] - c1['low'])

    avg_price = c1['close']
    allowed_diff = avg_price * tolerance

    is_equal_high = high_diff <= allowed_diff
    is_equal_low  = low_diff <= allowed_diff

    # Both High and Low must be within tolerance
    if is_equal_high and is_equal_low:
        if is_rgr:
            return "BULLISH RGR (Red-Green-Red)"
        if is_grg:
            return "BEARISH GRG (Green-Red-Green)"

    return None

# --- MAIN SCANNER ---
def run_scan():
    print(f"🚀 Starting RGR/GRG Scan...")
    
    # Connect to MEXC
    exchange = ccxt.mexc({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

    try:
        # 1. Get Top Pairs
        tickers = exchange.fetch_tickers()
        valid_pairs = []
        for symbol, data in tickers.items():
            vol = data.get('quoteVolume')
            if vol and '/USDT' in symbol and '3L' not in symbol and '3S' not in symbol:
                valid_pairs.append({'symbol': symbol, 'volume': vol})
        
        # Sort and Slice
        sorted_pairs = sorted(valid_pairs, key=lambda x: x['volume'], reverse=True)
        top_list = [x['symbol'] for x in sorted_pairs[:LIMIT_PAIRS]]
        
        print(f"📋 Scanning Top {len(top_list)} pairs...")
        
        alerts = []

        # 2. Loop
        for symbol in top_list:
            # Short pause to avoid rate limits (safe for 100 pairs)
            time.sleep(0.05) 
            
            for tf in TIMEFRAMES:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=5)
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    pattern = check_pattern(df, tolerance=TOLERANCE_PCT/100)
                    
                    if pattern:
                        price = df.iloc[-1]['close']
                        emoji = "🟢" if "BULLISH" in pattern else "🔴"
                        alerts.append(f"{emoji} **{symbol}** [{tf}]\n`{pattern}`\nPrice: `{price}`")
                        print(f"Found: {symbol} {tf} {pattern}")
                except Exception:
                    continue

        # 3. Send to Discord
        if alerts and WEBHOOK_URL:
            header = "🎯 **DUAL PATTERN DETECTED** 🎯\n*(Equal Highs/Lows + Color Flip)*\n\n"
            msg_content = header + "\n----------------\n".join(alerts)
            
            # Split if message is too long (Discord limit 2000 chars)
            if len(msg_content) > 1900:
                msg_content = msg_content[:1900] + "\n...(truncated)"

            requests.post(WEBHOOK_URL, json={'content': msg_content})
            print("✅ Sent to Discord.")
        else:
            print("✅ Scan complete. No patterns found.")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_scan()


