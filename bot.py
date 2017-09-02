import numpy as np
import requests
import time
import hmac
import hashlib

CHUNK = 50
DEPTH_LIMIT = 20
MAX_TRADE_BTC = 0.0005
CHECK_DELAY = 5.0

from config import API_KEY, API_SECRET
from urllib.parse import urlencode


class YobitAPI:
    def __init__(self, key, secret):
        self.api_key = key
        self.api_secret = secret

    def yo_query(self, method, values):
        md_public = ['info', 'ticker', 'depth', 'trades']

        if method in md_public:
            url = 'https://yobit.net/api/3/' + method
            for k in values:
                if (k == 'currency') and (values[k] != ''):
                    url += '/' + ','.join(values[k])
            for k in values:
                if (k != 'currency') and (values[k] != ''):
                    url += '?' + k + '=' + values[k]

            req = requests.get(url)
            return req.json()

        else:
            url = 'https://yobit.net/tapi'
            values['method'] = method
            values['nonce'] = str(int(time.time()))
            body = urlencode(values)
            signature = hmac.new(self.api_secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha512).hexdigest()
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Key': self.api_key,
                'Sign': signature
            }

            req = requests.post(url, data=values, headers=headers)
            return req.json()

    def get_pairs(self):
        return self.yo_query('info', {})['pairs'].keys()

    def get_trades(self, pairs):
        return self.yo_query('trades', {'currency': pairs, 'limit': 10})

    def get_depth(self, pairs):
        return self.yo_query('depth', {'currency': pairs, 'limit': 10})

    def get_trades_stat(self, trades, lookback_seconds=300):
        oldest_trade = trades[-1]['timestamp']
        now = time.time()
        delta = lookback_seconds

        bid_trades = [t for t in trades if t['type'] == 'bid']

        stat = {
            'buy_count': sum([1 for t in trades if t['type'] == 'bid']),
            'buy_volume': sum([t['amount'] for t in bid_trades]),
            'mean_volume': np.mean([t['amount'] for t in bid_trades]) if bid_trades else 0.0,
            'is_buy_recent': oldest_trade > now - delta,
            'sell_count': sum([1 for t in trades if t['type'] == 'ask']),
        }
        return stat

    def open_trade(self, pair, buy_price, sell_price, volume):
        # buy order
        buy_params = {
            'pair': pair,
            'type': 'buy',
            'rate': buy_price,
            'amount': volume
        }
        buy_order = self.yo_query('Trade', buy_params)
        print('BUY: ')
        print(buy_order)

        # sell order
        sell_params = {
            'pair': pair,
            'type': 'sell',
            'rate': sell_price,
            'amount': volume
        }
        sell_order = self.yo_query('Trade', sell_params)
        print('SELL: ')
        print(sell_order)


def check_pairs(yo):
    # get pairs
    pairs = yo.get_pairs()

    # get trades
    for _pairs in [pairs[i:i + CHUNK] for i in range(0, len(pairs), CHUNK)]:
        trades = yo.get_trades(_pairs)
        depth = yo.get_depth(_pairs)
        for pair, _trades in trades.items():
            stat = yo.get_trades_stat(_trades)
            if stat['buy_count'] == DEPTH_LIMIT and stat['is_buy_recent']:

                ask_price = depth[pair]['asks'][0][0]
                ask_volume = depth[pair]['asks'][0][1]

                next_ask_price = depth[pair]['asks'][1][0]
                next_ask_volume = depth[pair]['asks'][1][1]

                if stat['mean_volume'] * 10 >= ask_volume and ask_volume < next_ask_volume:
                    trade_volume = min(ask_volume, 1.0*MAX_TRADE_BTC/ask_price)
                    if trade_volume:
                        if '_btc' in pair:
                            if ask_price*trade_volume <= MAX_TRADE_BTC:
                                print('Open trade: ', pair, trade_volume, ask_price, next_ask_price)
                                print('Pair: ', pair)
                                print('Trade volume: ', trade_volume)
                                print('Buy price: ', ask_price)
                                print('Sell price: ', next_ask_price)
                                print('Profit: ', (next_ask_price - ask_price)*trade_volume)
                                print()
                                yo.open_trade(pair, ask_price, next_ask_price, trade_volume)


if __name__ == "__main__":

    yo = YobitAPI(API_KEY, API_SECRET)

    while True:
        check_pairs(yo)
        time.sleep(CHECK_DELAY)
