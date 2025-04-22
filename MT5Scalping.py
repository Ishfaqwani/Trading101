install MetaTrader5 pandas numpy ta time datetime
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import ta
import time
from datetime import datetime

class MT5ScalpingStrategy:
    def __init__(
        self,
        login: 91521102,
        password: "Ishfaq@32030",
        server: "MetaQuotes-Demo",
        symbol: "XAUUSD",
        timeframe=mt5.TIMEFRAME_M5,
        atr_multiplier=1.5,
        rr_ratio=2,
        risk_per_trade=0.01,
    ):
        self.login = login
        self.password = password
        self.server = server
        self.symbol = symbol
        self.timeframe = timeframe
        self.atr_multiplier = atr_multiplier
        self.rr_ratio = rr_ratio
        self.risk_per_trade = risk_per_trade

        # Initialize MT5 connection
        self.initialize_mt5()

    def initialize_mt5(self):
        """Connect to MT5 account and initialize terminal."""
        if not mt5.initialize():
            raise Exception(f"MT5 initialization failed. Error: {mt5.last_error()}")

        # Authenticate with MT5 account
        authorized = mt5.login(
            login=self.login,
            password=self.password,
            server=self.server,
        )
        if not authorized:
            raise Exception(f"MT5 login failed. Error: {mt5.last_error()}")
        
        print(f"✅ Connected to MT5 (Account #{self.login})")
        
        # Enable symbol in Market Watch
        if not mt5.symbol_select(self.symbol, True):
            raise Exception(f"Failed to select {self.symbol}")

    def get_live_data(self, n_bars=100):
        """Fetch live candlestick data."""
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, n_bars)
        if rates is None:
            raise Exception(f"Failed to fetch data for {self.symbol}. Error: {mt5.last_error()}")
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        return df

    def calculate_indicators(self, df):
        """Calculate all technical indicators."""
        # EMAs
        df['ema_8'] = ta.trend.ema_indicator(df['close'], window=8)
        df['ema_21'] = ta.trend.ema_indicator(df['close'], window=21)
        
        # RSI
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        
        # MACD
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # ATR for stop loss
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        
        return df

    def check_buy_signal(self, latest):
        """Check conditions for BUY signal."""
        conditions = [
            latest['ema_8'] > latest['ema_21'],  # Uptrend
            latest['macd'] > latest['macd_signal'],  # MACD bullish
            latest['rsi'] < 35,  # Oversold
            latest['close'] < latest['bb_lower'],  # Price near lower BB
        ]
        return all(conditions)

    def check_sell_signal(self, latest):
        """Check conditions for SELL signal."""
        conditions = [
            latest['ema_8'] < latest['ema_21'],  # Downtrend
            latest['macd'] < latest['macd_signal'],  # MACD bearish
            latest['rsi'] > 65,  # Overbought
            latest['close'] > latest['bb_upper'],  # Price near upper BB
        ]
        return all(conditions)

    def calculate_position_size(self, atr_value):
        """Calculate lot size based on account balance and risk."""
        account_info = mt5.account_info()
        if account_info is None:
            print("⚠️ Failed to get account info. Using default lot size.")
            return 0.1  # Default lot size
        
        balance = account_info.balance
        risk_amount = balance * self.risk_per_trade
        point_value = mt5.symbol_info(self.symbol).point
        risk_points = (atr_value * self.atr_multiplier) / point_value
        
        # Calculate lot size (1 lot = 100,000 units)
        lot_size = round((risk_amount / (risk_points * point_value)) / 100000, 2)
        return max(lot_size, 0.01)  # Minimum lot size = 0.01

    def execute_trade(self, trade_type, atr_value):
        """Execute BUY or SELL order with proper risk management."""
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            print(f"❌ Failed to get symbol info for {self.symbol}")
            return False
        
        point = symbol_info.point
        price = mt5.symbol_info_tick(self.symbol).ask if trade_type == 'BUY' else mt5.symbol_info_tick(self.symbol).bid
        atr_stop = atr_value * self.atr_multiplier
        
        if trade_type == 'BUY':
            sl = price - atr_stop
            tp = price + (atr_stop * self.rr_ratio)
            order_type = mt5.ORDER_TYPE_BUY
        else:
            sl = price + atr_stop
            tp = price - (atr_stop * self.rr_ratio)
            order_type = mt5.ORDER_TYPE_SELL
        
        # Calculate dynamic lot size
        lot_size = self.calculate_position_size(atr_value)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": 123456,  # Unique strategy ID
            "comment": f"Scalping {trade_type}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ Trade failed: {trade_type} {self.symbol}. Error: {result.comment}")
            return False
        else:
            print(f"✅ Trade executed: {trade_type} {self.symbol} {lot_size} lots at {price}")
            return True

    def check_open_positions(self):
        """Check if there are existing positions."""
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return False
        return len(positions) > 0

    def run_strategy(self):
        """Main strategy execution loop."""
        print(f"🚀 Starting live scalping strategy for {self.symbol}")
        
        try:
            while True:
                # Check if market is open (optional)
                now = datetime.now()
                if not (0 <= now.weekday() <= 4):  # Trade only Mon-Fri
                    time.sleep(60)
                    continue
                
                try:
                    # Get fresh data
                    df = self.get_live_data(200)
                    df = self.calculate_indicators(df)
                    latest = df.iloc[-1]
                    
                    # Check for existing positions
                    if not self.check_open_positions():
                        # Check for BUY signal
                        if self.check_buy_signal(latest):
                            print(f"{datetime.now()} - 🔥 BUY signal detected")
                            self.execute_trade('BUY', latest['atr'])
                        
                        # Check for SELL signal
                        elif self.check_sell_signal(latest):
                            print(f"{datetime.now()} - 🔥 SELL signal detected")
                            self.execute_trade('SELL', latest['atr'])
                    
                    # Wait for next tick
                    time.sleep(5)  # Adjust based on timeframe
                    
                except Exception as e:
                    print(f"⚠️ Error in main loop: {e}")
                    time.sleep(10)
                    continue
                    
        except KeyboardInterrupt:
            print("\n🛑 Strategy stopped by user")
        finally:
            mt5.shutdown()

if __name__ == "__main__":
    # ========== MT5 ACCOUNT SETTINGS ==========
    LOGIN = 91521102  # Replace with your MT5 login
    PASSWORD = "Ishfaq@32030"  # Replace with your MT5 password
    SERVER = "MetaQuotes-Demo"  # e.g., "ICMarkets-Demo"
    
    # ========== TRADING SETTINGS ==========
    SYMBOL = "XAUUSD"
    TIMEFRAME = mt5.TIMEFRAME_M5
    
    # ========== RISK MANAGEMENT ==========
    ATR_MULTIPLIER = 1.5  # Stop loss = 1.5x ATR
    RISK_REWARD_RATIO = 2  # TP = 2x SL
    RISK_PER_TRADE = 0.01  # Risk 1% per trade
    
    # ========== RUN STRATEGY ==========
    strategy = MT5ScalpingStrategy(
        login=LOGIN,
        password=PASSWORD,
        server=SERVER,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        atr_multiplier=ATR_MULTIPLIER,
        rr_ratio=RISK_REWARD_RATIO,
        risk_per_trade=RISK_PER_TRADE,
    )
    
    strategy.run_strategy()