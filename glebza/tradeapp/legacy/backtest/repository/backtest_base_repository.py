from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey, BigInteger, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


# Define BacktestLaunch table
class BacktestLaunch(Base):
    __tablename__ = 'backtest_launches'
    __table_args__ = {"schema": "backtests"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    launch_dtm = Column(DateTime, nullable=False)
    backtest_start = Column(DateTime, nullable=False)
    backtest_end = Column(DateTime, nullable=False)
    backtest_interval = Column(String(20))
    kline_interval = Column(String(10))
    strategy_details_id = Column(Integer, ForeignKey('backtests.backtest_strategy_details.id'))
    slippage = Column(Numeric(10, 5))
    commission = Column(Numeric(10, 5))
    risk_factor = Column(Numeric(10, 5))
    start_money = Column(Numeric(20, 2))
    # Relationship to backtest_result
    results = relationship("BacktestResult", back_populates="launch")

class Deal(Base):
    __tablename__ = 'deals'
    __table_args__ = {"schema": "backtests"}
    id = Column(Integer, primary_key=True, autoincrement=True)

    backtest_deals = relationship("BacktestDeal", back_populates="deal")

# Define BacktestDeal table
class BacktestDeal(Base):
    __tablename__ = 'backtest_deals'
    __table_args__ = {"schema": "backtests"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    launch_id = Column(Integer, ForeignKey('backtests.backtest_launches.id'), nullable=False)
    deal_id = Column(Integer, ForeignKey('backtests.deals.id'), nullable=False)

    deal = relationship("Deal", back_populates="backtest_deals")


# Define Strategy table
class Strategy(Base):
    __tablename__ = 'strategy'
    __table_args__ = {"schema": "backtests"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100), nullable=False)
    description = Column(String(300))

    strategy_details = relationship("BacktestStrategyDetail", back_populates="strategy")


# Define StrategyParameter table
class StrategyParameter(Base):
    __tablename__ = 'strategy_parameters'
    __table_args__ = {"schema": "backtests"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter_title = Column(String(100), nullable=False)
    parameter_description = Column(String(300))

    parameter_details = relationship("BacktestStrategyDetail", back_populates="parameter")


# Define BacktestStrategyDetail table
class BacktestStrategyDetail(Base):
    __tablename__ = 'backtest_strategy_details'
    __table_args__ = {"schema": "backtests"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey('backtests.strategy.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('backtests.strategy_parameters.id'), nullable=False)
    parameter_value = Column(Numeric(10, 5))

    # Relationships to other tables
    strategy = relationship("Strategy", back_populates="strategy_details")
    parameter = relationship("StrategyParameter", back_populates="parameter_details")


class BacktestResult(Base):
    __tablename__ = 'backtest_result'
    __table_args__ = {"schema": "backtests"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    launch_id = Column(BigInteger, ForeignKey('backtests.backtest_launches.id'), nullable=False)
    total_profit_loss = Column(Numeric(20, 2), default=0.0)
    win_rate = Column(Numeric(5, 2), default=0.0)
    max_drawdown = Column(Numeric(10, 5), default=0.0)
    sharpe_ratio = Column(Numeric(10, 5), default=0.0)
    other_metrics = Column(JSON)

    # Relationship to backtest_launches
    launch = relationship("BacktestLaunch", back_populates="results")
