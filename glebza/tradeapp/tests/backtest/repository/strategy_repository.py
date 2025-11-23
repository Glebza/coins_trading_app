from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
import os

from glebza.tradeapp.tests.backtest.repository.backtest_base_repository import Strategy, StrategyParameter


class StrategyRepository:
    def __init__(self):
        self.engine = create_engine(os.environ['DATABASE_URL'])
        session = sessionmaker(bind=self.engine)
        self.session = session()

    # Add a new strategy
    def add_strategy(self, title, description):
        new_strategy = Strategy(title=title, description=description)
        self.session.add(new_strategy)
        self.session.commit()
        return new_strategy

    # Add a new strategy parameter
    def add_strategy_parameter(self, parameter_title, parameter_description):
        new_param = StrategyParameter(parameter_title=parameter_title, parameter_description=parameter_description)
        self.session.add(new_param)
        self.session.commit()
        return new_param

    # Retrieve all strategies
    def get_strategies(self):
        return self.session.query(Strategy).all()

    def get_strategy_by_title(self, title):
        return self.session.query(Strategy).filter_by(title=title).one_or_none()

    # Retrieve all strategy parameters
    def get_strategy_parameters(self):
        return self.session.query(StrategyParameter).all()

    def close_session(self):
        self.session.close()
