"""
mt5_trader.py - MT5 实盘交易执行模块

基于 MetaTrader 5 API 实现实盘交易功能，
包括市价单买卖、挂单管理、止盈止损设置以及账户信息查询。

⚠️ 注意：MetaTrader5 仅支持 Windows 平台。
"""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class MT5Trader:
    """MT5 实盘交易执行器

    通过 MetaTrader 5 API 执行现货黄金（XAUUSD）的实盘交易操作，
    支持市价开仓、设置止盈止损、查询持仓和账户余额等功能。

    Attributes:
        login (int): MT5 账户登录号
        password (str): MT5 账户密码
        server (str): MT5 服务器地址
        symbol (str): 交易品种，默认 'XAUUSD'
        magic (int): EA 魔术号，用于标识本系统发出的订单
    """

    def __init__(self, symbol: str = "XAUUSD"):
        """初始化 MT5 交易执行器

        从 .env 文件加载账户配置，并设置交易品种。

        Args:
            symbol: 交易品种代码，默认 'XAUUSD'
        """
        self.login = int(os.getenv("MT5_LOGIN", "0"))
        self.password = os.getenv("MT5_PASSWORD", "")
        self.server = os.getenv("MT5_SERVER", "")
        self.symbol = symbol
        self.magic = int(os.getenv("MAGIC_NUMBER", "123456"))
        self._mt5 = None  # 延迟导入

    def _import_mt5(self):
        """延迟导入 MetaTrader5，避免在 Linux 上直接报错"""
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5
                self._mt5 = mt5
            except ImportError:
                raise ImportError(
                    "MetaTrader5 模块仅支持 Windows 平台。"
                    "请在 Windows 环境下运行实盘交易模块。"
                )
        return self._mt5

    def connect(self) -> bool:
        """连接 MT5 交易终端

        初始化 MT5 并使用配置的账户信息登录。

        Returns:
            bool: 连接成功返回 True，失败返回 False
        """
        mt5 = self._import_mt5()

        if not mt5.initialize():
            print(f"[MT5Trader] ❌ MT5 初始化失败: {mt5.last_error()}")
            return False

        if self.login:
            authorized = mt5.login(
                login=self.login,
                password=self.password,
                server=self.server,
            )
            if not authorized:
                print(f"[MT5Trader] ❌ MT5 登录失败: {mt5.last_error()}")
                mt5.shutdown()
                return False

        account = mt5.account_info()
        print(f"[MT5Trader] ✅ 已连接 | 账户: {account.login} | "
              f"余额: {account.balance:.2f} | 服务器: {account.server}")
        return True

    def disconnect(self) -> None:
        """断开 MT5 交易终端连接"""
        mt5 = self._import_mt5()
        mt5.shutdown()
        print("[MT5Trader] 🔌 MT5 连接已断开")

    def get_account_info(self) -> Optional[dict]:
        """查询账户信息

        获取当前交易账户的详细信息。

        Returns:
            dict: 包含以下键值的账户信息字典：
                - balance (float): 账户余额
                - equity (float): 净值
                - margin (float): 已用保证金
                - free_margin (float): 可用保证金
                - profit (float): 浮动盈亏
            若查询失败返回 None。
        """
        mt5 = self._import_mt5()
        account = mt5.account_info()
        if account is None:
            print(f"[MT5Trader] ❌ 获取账户信息失败: {mt5.last_error()}")
            return None

        info = {
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "free_margin": account.margin_free,
            "profit": account.profit,
        }
        print(f"[MT5Trader] 💰 账户信息 | 余额: {info['balance']:.2f} | "
              f"净值: {info['equity']:.2f} | 浮动盈亏: {info['profit']:.2f}")
        return info

    def _get_symbol_info(self):
        """获取品种信息并确保品种可见"""
        mt5 = self._import_mt5()
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            print(f"[MT5Trader] ❌ 品种 {self.symbol} 不存在")
            return None

        if not symbol_info.visible:
            if not mt5.symbol_select(self.symbol, True):
                print(f"[MT5Trader] ❌ 无法选中品种 {self.symbol}")
                return None

        return symbol_info

    def buy(
        self,
        lot: float = 0.01,
        sl_points: Optional[int] = None,
        tp_points: Optional[int] = None,
        comment: str = "Gold_Quant_Buy",
    ) -> Optional[dict]:
        """市价买入开仓

        以当前市场价发送买入订单。

        Args:
            lot: 交易手数，默认 0.01 手（最小手数）
            sl_points: 止损点数（距入场价的点数），None 表示不设止损
            tp_points: 止盈点数（距入场价的点数），None 表示不设止盈
            comment: 订单备注信息

        Returns:
            dict: 订单执行结果字典，包含：
                - order_id (int): 订单号
                - price (float): 成交价格
                - volume (float): 成交手数
            若下单失败返回 None。
        """
        mt5 = self._import_mt5()

        symbol_info = self._get_symbol_info()
        if symbol_info is None:
            return None

        price = mt5.symbol_info_tick(self.symbol).ask
        point = symbol_info.point

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "magic": self.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # 设置止损
        if sl_points is not None:
            request["sl"] = price - sl_points * point

        # 设置止盈
        if tp_points is not None:
            request["tp"] = price + tp_points * point

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[MT5Trader] ❌ 买入失败 | 错误码: {result.retcode} | {result.comment}")
            return None

        order_result = {
            "order_id": result.order,
            "price": result.price,
            "volume": result.volume,
        }
        print(f"[MT5Trader] ✅ 买入成功 | 订单号: {result.order} | "
              f"价格: {result.price:.2f} | 手数: {result.volume}")
        return order_result

    def sell(
        self,
        lot: float = 0.01,
        sl_points: Optional[int] = None,
        tp_points: Optional[int] = None,
        comment: str = "Gold_Quant_Sell",
    ) -> Optional[dict]:
        """市价卖出开仓

        以当前市场价发送卖出订单。

        Args:
            lot: 交易手数，默认 0.01 手
            sl_points: 止损点数（距入场价的点数），None 表示不设止损
            tp_points: 止盈点数（距入场价的点数），None 表示不设止盈
            comment: 订单备注信息

        Returns:
            dict: 订单执行结果字典（同 buy 方法）
            若下单失败返回 None。
        """
        mt5 = self._import_mt5()

        symbol_info = self._get_symbol_info()
        if symbol_info is None:
            return None

        price = mt5.symbol_info_tick(self.symbol).bid
        point = symbol_info.point

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
            "magic": self.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # 设置止损（卖出方向止损在上方）
        if sl_points is not None:
            request["sl"] = price + sl_points * point

        # 设置止盈（卖出方向止盈在下方）
        if tp_points is not None:
            request["tp"] = price - tp_points * point

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[MT5Trader] ❌ 卖出失败 | 错误码: {result.retcode} | {result.comment}")
            return None

        order_result = {
            "order_id": result.order,
            "price": result.price,
            "volume": result.volume,
        }
        print(f"[MT5Trader] ✅ 卖出成功 | 订单号: {result.order} | "
              f"价格: {result.price:.2f} | 手数: {result.volume}")
        return order_result

    def close_position(self, position_id: int) -> bool:
        """平仓指定持仓

        根据持仓 ID 平掉对应的持仓。

        Args:
            position_id: 持仓 ID（ticket）

        Returns:
            bool: 平仓成功返回 True，失败返回 False
        """
        mt5 = self._import_mt5()

        # 获取持仓信息
        positions = mt5.positions_get(ticket=position_id)
        if not positions:
            print(f"[MT5Trader] ⚠️ 未找到持仓 ID: {position_id}")
            return False

        pos = positions[0]

        # 反向下单平仓
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = (mt5.symbol_info_tick(self.symbol).bid
                 if pos.type == mt5.ORDER_TYPE_BUY
                 else mt5.symbol_info_tick(self.symbol).ask)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": position_id,
            "price": price,
            "magic": self.magic,
            "comment": "Gold_Quant_Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[MT5Trader] ❌ 平仓失败 | ID: {position_id} | "
                  f"错误码: {result.retcode} | {result.comment}")
            return False

        print(f"[MT5Trader] ✅ 平仓成功 | ID: {position_id} | 价格: {result.price:.2f}")
        return True

    def close_all_positions(self) -> int:
        """平掉当前品种的所有持仓

        遍历并平掉当前交易品种下的所有持仓。

        Returns:
            int: 成功平仓的数量
        """
        mt5 = self._import_mt5()

        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            print(f"[MT5Trader] 当前 {self.symbol} 无持仓")
            return 0

        closed = 0
        for pos in positions:
            if self.close_position(pos.ticket):
                closed += 1

        print(f"[MT5Trader] 批量平仓完成 | 成功: {closed}/{len(positions)}")
        return closed

    def get_positions(self) -> list:
        """查询当前品种的所有持仓

        获取当前交易品种下的所有活跃持仓信息。

        Returns:
            list[dict]: 持仓列表，每个元素包含：
                - ticket (int): 持仓 ID
                - type (str): 持仓方向（'buy' 或 'sell'）
                - volume (float): 持仓手数
                - price_open (float): 开仓价格
                - sl (float): 止损价格
                - tp (float): 止盈价格
                - profit (float): 当前盈亏
        """
        mt5 = self._import_mt5()

        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            print(f"[MT5Trader] 当前 {self.symbol} 无持仓")
            return []

        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "type": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell",
                "volume": pos.volume,
                "price_open": pos.price_open,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
            })

        print(f"[MT5Trader] 📋 当前持仓 {len(result)} 笔:")
        for p in result:
            print(f"  #{p['ticket']} | {p['type'].upper()} | "
                  f"{p['volume']}手 @ {p['price_open']:.2f} | 盈亏: {p['profit']:.2f}")

        return result
