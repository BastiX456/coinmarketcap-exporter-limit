from prometheus_client import start_http_server, Metric, REGISTRY
from threading import Lock
from cachetools import cached, TTLCache
from requests import Request, Session
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
import argparse
import json
import logging
import os
import sys
import time

# lock of the collect method
lock = Lock()

# logging setup
log = logging.getLogger('coinmarketcap-exporter')
log.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)

currency = os.environ.get('CURRENCY', 'USD')
cak = os.environ.get('COINMARKETCAP_API_KEY')
# Angeblich bis zu 200(100 davor.. sicher!) Aufrufe Pro Credit (10000 Credits/Monat)
# -> bei 1600 Werten -> max Aufrufe = (10000*100 / 1600) / 30 Tage -> 20.8 am Tag
# -> Annahme Jede Minuten -> Limit_max = (10000 *100 / 46100 (ca. jede Minute im Monat)) -> 21,6 
# caching API for 170min (every 3 hours)
# Note the api limits: https://pro.coinmarketcap.com/features
# cache_ttl = int(os.environ.get('CACHE_TTL', 10200)) # Original
# caching API for every 60 min
#cache_ttl = int(os.environ.get('CACHE_TTL', 3600))
cache_ttl = int(os.environ.get('CACHE_TTL', 7200)) #14.04.2024
#cache_max_size = int(os.environ.get('CACHE_MAX_SIZE', 10000)) # Original
#cache_max_size = int(os.environ.get('CACHE_MAX_SIZE', 2000))
cache_max_size = int(os.environ.get('CACHE_MAX_SIZE', 4000)) #14.04.2024
limit_max = int(os.environ.get('LIMIT_MAX', 1600)) #10.11.2024 Limit der Max. Werte
debug = int(os.environ.get('DEBUG', 0)) #10.11.2024
mode = int(os.environ.get('MODE', 1)) #10.11.2024
symbol = os.environ.get('SYMBOL', 'BTC') #10.11.2024
#symbol2 = os.environ.get('SYMBOL2', 'BTC') #10.11.2024
cache = TTLCache(maxsize=cache_max_size, ttl=cache_ttl)


class CoinClient():
  def __init__(self):

    self.headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': cak}
    
    if mode == 2:
      self.url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
      self.parameters = {'symbol': symbol, 'convert': currency} #10.11.2024
    elif mode == 3:
      self.url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
      self.parameters = {'symbol': symbol, 'convert': currency} #10.11.2024
    else:
      self.url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
      self.parameters = {'start': '1', 'limit': limit_max, 'convert': currency} #10.11.2024
      #self.parameters = {'start': '1', 'limit': '5000', 'convert': currency} # original
      #self.parameters = {'start': '1', 'limit': '1600', 'convert': currency}
      #self.parameters = {'start': '1', 'limit': '1600', 'convert': currency} #14.04.2024

  @cached(cache)
  def tickers(self):
    log.info('Fetching data from the API')
    session = Session()
    session.headers.update(self.headers)
    r = session.get(self.url, params=self.parameters)
    data = json.loads(r.text)
    if 'data' not in data:
      log.error('No data in response. Is your API key set?')
      log.info(data)
    return data

class CoinCollector():
  def __init__(self):
    self.client = CoinClient()

  def collect(self):
    with lock:
      log.info('collecting... in Mode:' + str(mode))
      log.info('DEBUG: ' + str(debug))
      
      if debug == 1:
        log.info('CURRENCY: ' + currency)
        log.info('CACHE_TTL: ' + str(cache_ttl))
        log.info('CACHE_MAX_SIZE: ' + str(cache_max_size))
        log.info('LIMIT_MAX: ' + str(limit_max))
        log.info('MODE: ' + str(mode))
        log.info('SYMBOL: ' + symbol)
        log.info('SYMBOL2: ' + symbol2)
        
      # query the api
      response = self.client.tickers()
      metric = Metric('status', 'coin_market', 'coinmarketcap metric values', 'gauge')
      if 'data' not in response:
        log.error('No data in response. Is your API key set?')
      else:
        if debug == 2:
          log.info('Response: ' + str(response))

        #Neuer Code für individuelle Abfragen
        if mode == 3: 
          for value in response['data'].values():
            log.info('Test1: ' + str(value))
            for that in ['Check']: # z.B. BTC oder ETC
                log.info('Test2: ' + str(that)) ########## = BTC     
                for that in ['cmc_rank', 'total_supply', 'max_supply', 'circulating_supply']:
                  log.info('Test10:' + str(that)) ##########
                  coinmarketmetric = '_'.join(['coin_market', that])
                  if value[that] is not None:
                    log.info('Test11:' + str(that)) ##########
                    metric.add_sample(coinmarketmetric, value=float(value[that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})
                for price in [currency]:
                  for that in ['price', 'volume_24h', 'market_cap', 'percent_change_1h', 'percent_change_24h', 'percent_change_7d']:
                    coinmarketmetric = '_'.join(['coin_market', that, price]).lower()
                    if value['quote'][price] is None:
                      continue
                    if value['quote'][price][that] is not None:
                      metric.add_sample(coinmarketmetric, value=float(value['quote'][price][that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})
        elif mode == 2:
          for value in response['status']:  #Status holen
            for that in ['elapsed']:
            coinmarketmetric = '_'.join(['status', that])      
              if value[that] is not None:
                metric.add_sample(coinmarketmetric, value=float(value[that]), labels={'timestamp': value['timestamp'], 'error_code': value['name'], 'error_message': value['name'], 'elapsed': value['name'], 'credit_count': value['name'], 'notice': value['name']})         
        
        #alter Code für Standard abfragen
        else:
          for value in response['data']:  #jeder Hauptdatensatz. (BTC, ETH, ...)
            for that in ['cmc_rank', 'total_supply', 'max_supply', 'circulating_supply']: # z.B. cmc_rank in BTC = 1
              coinmarketmetric = '_'.join(['coin_market', that])
              if value[that] is not None:
                metric.add_sample(coinmarketmetric, value=float(value[that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})
            for price in [currency]: # z.B. "price" im Ersten BTC Datensatz in z.B. USD[]
              for that in ['price', 'volume_24h', 'market_cap', 'percent_change_1h', 'percent_change_24h', 'percent_change_7d']:
                coinmarketmetric = '_'.join(['coin_market', that, price]).lower()
                if value['quote'][price] is None:
                  continue
                if value['quote'][price][that] is not None:
                  metric.add_sample(coinmarketmetric, value=float(value['quote'][price][that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})  
      
      yield metric

if __name__ == '__main__':
  try:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', nargs='?', const=9101, help='The TCP port to listen on', default=9101)
    parser.add_argument('--addr', nargs='?', const='0.0.0.0', help='The interface to bind to', default='0.0.0.0')
    args = parser.parse_args()
    log.info('listening on http://%s:%d/metrics' % (args.addr, args.port))

    REGISTRY.register(CoinCollector())
    start_http_server(int(args.port), addr=args.addr)

    while True:
      time.sleep(60)
  except KeyboardInterrupt:
    print(" Interrupted")
    exit(0)
