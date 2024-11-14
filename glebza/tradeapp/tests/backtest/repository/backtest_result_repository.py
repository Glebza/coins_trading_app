from glebza.tradeapp.tests.backtest.repository.backtest_base_repository import BacktestLaunch, BacktestDeal, \
    BacktestStrategyDetail, BacktestResult
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine,text
import os


class BacktestResultRepository:
    def __init__(self):
        self.engine = create_engine(os.environ['DATABASE_URL'])
        session = sessionmaker(bind=self.engine)
        self.session = session()

    def add_backtest_result(self, launch_id, total_profit_loss=0.0, win_rate=0.0, max_drawdown=0.0,
                            sharpe_ratio=0.0, other_metrics=None):
        new_result = BacktestResult(
            launch_id=launch_id,
            total_profit_loss=total_profit_loss,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            other_metrics=other_metrics if other_metrics else {}
        )
        self.session.add(new_result)
        self.session.commit()
        return new_result

    def evaluate_result(self,launch_id):
        try:
            # Run the SQL query with the specified launch_id
            result = self.session.execute(
                text("""
                            SELECT SUM(b.origqty * (b2.price - b.price)) AS profit
                            FROM deals d
                            JOIN backtest_deals bd ON d.id = bd.deal_id
                            JOIN "order" b ON d.buy_order_id = b.id
                            JOIN "order" b2 ON d.sell_order_id = b2.id
                            WHERE bd.launch_id = :launch_id;
                        """),
                {"launch_id": launch_id}
            ).fetchone()

            # Return the profit value if the query was successful
            return result if result else None

        except Exception as e:
            print(f"Error evaluating result: {e}")
            return None
    def get_backtest_results(self, launch_id):
        return self.session.query(BacktestResult).filter_by(launch_id=launch_id).all()

    def close_session(self):
        self.session.close()


