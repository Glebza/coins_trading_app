from glebza.tradeapp.tests.backtest.repository.backtest_base_repository import BacktestLaunch, BacktestDeal, \
    BacktestStrategyDetail
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine


class BacktestLaunchRepository:
    def __init__(self, database_url):
        self.engine = create_engine(database_url)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    # Method to add a new backtest launch
    def add_backtest_launch(self, launch_dtm, backtest_start, backtest_end, backtest_interval, kline_interval,
                            strategy_details_id, slippage, commission, risk_factor, start_money):
        new_launch = BacktestLaunch(
            launch_dtm=launch_dtm,
            backtest_start=backtest_start,
            backtest_end=backtest_end,
            backtest_interval=backtest_interval,
            kline_interval=kline_interval,
            strategy_details_id=strategy_details_id,
            slippage=slippage,
            commission=commission,
            risk_factor=risk_factor,
            start_money=start_money
        )
        self.session.add(new_launch)
        self.session.commit()
        return new_launch

    # Method to add a backtest deal
    def add_backtest_deal(self, launch_id, deal_id):
        new_deal = BacktestDeal(launch_id=launch_id, deal_id=deal_id)
        self.session.add(new_deal)
        self.session.commit()
        return new_deal

    # Method to add a backtest strategy detail
    def add_backtest_strategy_detail(self, strategy_id, parameter_id, parameter_value):
        new_strategy_detail = BacktestStrategyDetail(
            strategy_id=strategy_id,
            parameter_id=parameter_id,
            parameter_value=parameter_value
        )
        self.session.add(new_strategy_detail)
        self.session.commit()
        return new_strategy_detail

    # Retrieve all backtest strategy details
    def get_backtest_strategy_details(self, strategy_id=None):
        query = self.session.query(BacktestStrategyDetail)
        if strategy_id:
            query = query.filter_by(strategy_id=strategy_id)
        return query.all()

    def close_session(self):
        self.session.close()
