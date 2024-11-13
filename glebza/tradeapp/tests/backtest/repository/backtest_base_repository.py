from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


# Define BacktestLaunch table
class BacktestLaunch(Base):
    __tablename__ = 'backtest_launches'
    id = Column(Integer, primary_key=True, autoincrement=True)
    launch_dtm = Column(DateTime, nullable=False)
    backtest_start = Column(DateTime, nullable=False)
    backtest_end = Column(DateTime, nullable=False)
    backtest_interval = Column(String(20))
    kline_interval = Column(String(10))
    strategy_details_id = Column(Integer, ForeignKey('strategy.id'))
    slippage = Column(Numeric(10, 5))
    commission = Column(Numeric(10, 5))
    risk_factor = Column(Numeric(10, 5))
    start_money = Column(Numeric(20, 2))


# Define BacktestDeal table
class BacktestDeal(Base):
    __tablename__ = 'backtest_deals'
    id = Column(Integer, primary_key=True, autoincrement=True)
    launch_id = Column(Integer, ForeignKey('backtest_launches.id'), nullable=False)
    deal_id = Column(Integer, ForeignKey('deals.id'), nullable=False)


# Define Strategy table
class Strategy(Base):
    __tablename__ = 'strategy'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100), nullable=False)
    description = Column(String(300))


# Define StrategyParameter table
class StrategyParameter(Base):
    __tablename__ = 'strategy_parameters'
    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter_title = Column(String(100), nullable=False)
    parameter_description = Column(String(300))


# Define BacktestStrategyDetail table
class BacktestStrategyDetail(Base):
    __tablename__ = 'backtest_strategy_details'
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey('strategy.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('strategy_parameters.id'), nullable=False)
    parameter_value = Column(Numeric(10, 5))

    # Relationships to other tables
    strategy = relationship("Strategy", back_populates="strategy_details")
    parameter = relationship("StrategyParameter", back_populates="parameter_details")
