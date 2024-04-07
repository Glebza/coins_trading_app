import requests,os
import logging
import psycopg2


api_base_url = "https://fapi.binance.com/{}"
api_url_24h_price_changed = "fapi/v1/ticker/24hr"


def load_tickers():
    response = requests.get(api_base_url.format(api_url_24h_price_changed))
    tickers = [item['symbol'] for item in response.json() if "USDC" not in item['symbol'] and "BTCUSDT" not in item['symbol']]
    save_tickers_to_db(tickers)



def save_tickers_to_db(tickers):
    conn = None
    try:
        database_url = os.environ['DATABASE_URL']
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        sql_insert = '''
         insert into coins (ticker )
         values (%s);
         '''
        print(sql_insert)
        dbrows = []
        # date in mm-dd-yyyy format
        symbol_idx = 0
        for ticker in tickers:
            if ticker is not None:
                dbrows.append((ticker,))
        cur.executemany(sql_insert, dbrows)
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        logging.error(error)
    finally:
        if conn is not None:
            conn.close()



load_tickers()