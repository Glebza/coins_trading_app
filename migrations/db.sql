create sequence coins_id_seq
    as integer;

create sequence deals_id_seq;
create sequence kline_periods_id_seq
    as integer;

create table coins
(
    id     serial not null
        constraint coins_pkey
            primary key,
    ticker varchar
);

\

-- auto-generated definition
create table deals
(
    -- Only integer types can be auto increment
    id            numeric default nextval('deals_id_seq'::regclass) not null
        constraint deals_pk
            primary key,
    buy_order_id  numeric
        constraint deals_buy_fk
            references orders,
    sell_order_id numeric
        constraint deals_orders_fk
            references orders,
    start_date    timestamp,
    end_date      timestamp,
    ticker_id     integer
        constraint deals_ticker_fk
            references coins,
    column_7      integer
);

comment on table deals is 'pair of buy and sell orders';


create unique index deals_id_uindex
    on deals (id);

\


create table kline_1m
(
    id          serial not null
        constraint minute_klines_pkey
            primary key,
    ticker_id   integer
        constraint minute_klines_ticker_id_fkey
            references coins,
    open_price  double precision,
    high_price  double precision,
    low_price   double precision,
    close_price double precision,
    volume      numeric,
    k_interval  timestamp
);

create table kline_15m
(
    id          serial not null
        constraint fifteen_minutes_klines_pkey
            primary key,
    ticker_id   integer
        constraint fifteen_minutes_klines_ticker_id_fkey
            references coins,
    open_price  double precision,
    high_price  double precision,
    low_price   double precision,
    close_price double precision,
    volume      numeric,
    k_interval  timestamp
);

create table orders
(
    id            numeric not null
        constraint orders_pkey
            primary key,
    ticker_id     integer
        constraint orders_ticker_id_fkey
            references coins,
    orderlistid   integer,
    clientorderid varchar,
    transacttime  timestamp,
    price         double precision,
    origqty       double precision,
    executedqty   double precision,
    status        varchar,
    type          varchar,
    side          varchar
);
