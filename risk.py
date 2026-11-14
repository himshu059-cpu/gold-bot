from dataclasses import dataclass
from datetime import date


@dataclass
class RiskManager:
    equity: float                    # abhi ka account balance (USDT)
    risk_per_trade: float = 0.01     # ek trade me max 1% risk
    stop_loss: float = 0.01          # price 1% ulta jaye to exit
    max_leverage: float = 2.0        # leverage ki upar limit
    max_daily_loss: float = 0.03     # roz ka max 3% loss, phir bot band
    max_trades_per_day: int = 6
    killed: bool = False             # True hote hi bot kuch nahi karega

    def __post_init__(self):
        self.day = date.today()
        self.day_start_equity = self.equity
        self.trades_today = 0

    def _new_day_check(self):
        if date.today() != self.day:
            self.day = date.today()
            self.day_start_equity = self.equity
            self.trades_today = 0

    def update_equity(self, equity):
        self._new_day_check()
        self.equity = equity

    def can_trade(self):
        self._new_day_check()
        if self.killed:
            return False, "kill-switch ON"
        loss = 1 - self.equity / self.day_start_equity
        if loss >= self.max_daily_loss:
            self.killed = True
            return False, f"daily loss limit hit ({loss:.1%})"
        if self.trades_today >= self.max_trades_per_day:
            return False, "max trades per day"
        return True, "ok"

    def position_size(self):
        """Notional size (USDT) jisme stop lagne par sirf risk_per_trade% jaye."""
        notional = self.equity * self.risk_per_trade / self.stop_loss
        return min(notional, self.equity * self.max_leverage)

    def record_trade(self):
        self.trades_today += 1
