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
mode_auto = int(os.environ.get('MODE_AUTO', 0)) #10.11.2024
symbol = os.environ.get('SYMBOL', 'BTC') #10.11.2024
#symbol2 = os.environ.get('SYMBOL2', 'BTC') #10.11.2024
if mode_auto == 1:
  cache_ttl = cache_ttl/2
  
cache = TTLCache(maxsize=cache_max_size, ttl=cache_ttl)
modeswitch = 0
CollectDataNumber = 0
MetricTrue = 0
response0 = 0
response1 = 0


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
    global modeswitch  # Declare modeswitch as a global variable inside the class
    global CollectDataNumber
    
    #log.info('Fetching data from the API #Modeswitch: ' + str(modeswitch))
    if mode_auto == 1: #Wechseln der Abfragen
      log.info('Fetching data from the API #Modeswitch: ' + str(modeswitch))
      if modeswitch == 0:  #normale Abfrage
        modeswitch = 1
        self.url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
        self.parameters = {'start': '1', 'limit': limit_max, 'convert': currency} #10.11.2024
      else: 
        modeswitch = 0 
        self.url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
        self.parameters = {'symbol': symbol, 'convert': currency} #10.11.2024

      CollectDataNumber = CollectDataNumber + 1
    else:
      log.info('Fetching data from the API #Modeswitch: OFF')
      
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
    global mode        # Declare modes as a global variable inside the class
    global response    # Declare modes as a global variable inside the class
    global response0   # Declare modes as a global variable inside the class
    global response1   # Declare modes as a global variable inside the class   
    global CollectDataNumber
    global MetricTrue
    
    with lock:
            
      if debug == 1:
        log.info('CURRENCY: ' + currency)
        log.info('CACHE_TTL: ' + str(cache_ttl))
        log.info('CACHE_MAX_SIZE: ' + str(cache_max_size))
        log.info('LIMIT_MAX: ' + str(limit_max))
        log.info('MODE: ' + str(mode))
        log.info('SYMBOL: ' + symbol)
        log.info('MODE_AUTO: ' + str(mode_auto))
        log.info('modeswitch: ' + str(modeswitch))
        log.info('CollectDataNumber: ' + str(CollectDataNumber))
      
      log.info('Check Data...') if debug == 3 else None
      
      #Modus prüfen
      if mode_auto != 1: #Wechseln der Abfragen
        CollectDataNumber = 2 

      if CollectDataNumber == 0:
        CollectDataNumber = 1
      # query the api
      if CollectDataNumber == 1:
        response0 = self.client.tickers()
      elif CollectDataNumber == 2: 
        #response1 = self.client.tickers()
        response1 = self.client.tickers()
        
      metric = Metric('coin_market', 'coinmarketcap metric values', 'gauge')

      if CollectDataNumber == 3:
        log.info('CollectDataNumber: 2 Check')
        if isinstance(response0, int) or 'data' not in response0:
          log.error('No data in response0. Is your API key set?')
          CollectDataNumber = 0
        elif isinstance(response1, int) or 'data' not in response1:
          log.error('No data in response1. Is your API key set?')
          CollectDataNumber = 0
        else:
          CollectDataNumber = 2
          MetricTrue = 1
          while CollectDataNumber > 0:

            if mode_auto == 1: #Wechseln der Abfragen
              if CollectDataNumber == 2:
                mode = 1
                response = response0
              elif CollectDataNumber == 1: 
                mode = 3
                response = response1
            else:
              response = response1   

            if debug == 2:
              if CollectDataNumber == 2:
                log.info('Response0: ' + str(response0))
                log.info('Response1: ' + str(response1))
                
            CollectDataNumber = CollectDataNumber - 1
            if mode_auto == 0:
              CollectDataNumber = 0
              
            log.info('collecting... in Mode:' + str(mode))  if debug == 1 else None
            #log.info('modeF: ' + str(mode))
            #Neuer Code für individuelle Abfragen + Status
            if mode == 3: 
              for key, value in response['status'].items(): #Alle Status Infos loggen!
                log.info('Mode3#1: ' + str(value)) if debug == 1 else None
                log.info('Mode3#2: ' + str(key)) if debug == 1 else None
                coinmarketmetric = '_'.join(['coin_market', key])
                
                if key not in response['status']:
                    continue
                metric.add_sample(coinmarketmetric, value=float(0), labels={str(key): str(value)})

              try:
                for value in response['data'].values():
                  log.info('Mode3#3: ' + str(value)) if debug == 1 else None
                  for that in ['Check']: # z.B. BTC oder ETC
                      log.info('Mode3#4: ' + str(that)) if debug == 1 else None 
                      for that in ['cmc_rank', 'total_supply', 'max_supply', 'circulating_supply']:
                        log.info('Mode3#5:' + str(that)) if debug == 1 else None
                        coinmarketmetric = '_'.join(['coin_market', that])
                        if value[that] is not None:
                          log.info('Mode3#6:' + str(that)) if debug == 1 else None
                          metric.add_sample(coinmarketmetric, value=float(value[that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})
                      for price in [currency]:
                        for that in ['price', 'volume_24h', 'volume_change_24h', 'market_cap', 'percent_change_1h', 'percent_change_24h', 'percent_change_7d', 'percent_change_30d', 'percent_change_60d', 'percent_change_90d', 'market_cap_dominance', 'fully_diluted_market_cap']:
                          coinmarketmetric = '_'.join(['coin_market', that, price]).lower()
                          if value['quote'][price] is None:
                            continue
                          if value['quote'][price][that] is not None:
                            metric.add_sample(coinmarketmetric, value=float(value['quote'][price][that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})
              except AttributeError as e:
                log.error('ErrorsProcessResponse1: ' + str(e))
            # Nur Test der Status Abfrage
            elif mode == 2:
    
              for key, value in response['status'].items():
                log.info('Mode2#1: ' + str(value)) if debug == 1 else None
                log.info('Mode2#2: ' + str(key)) if debug == 1 else None
                coinmarketmetric = '_'.join(['coin_market', key])
                
                if key not in response['status']:
                    continue
                metric.add_sample(coinmarketmetric, value=float(0), labels={str(key): str(value)})
    
        
            #alter Code für Standard abfragen
            else:
              for key, value in response['status'].items(): #Alle Status Infos loggen!
                log.info('Mode1#1: ' + str(value)) if debug == 1 else None
                log.info('Mode1#2: ' + str(key)) if debug == 1 else None
                coinmarketmetric = '_'.join(['coin_market', key])
              
                if key not in response['status']:
                    continue
                metric.add_sample(coinmarketmetric, value=float(0), labels={str(key): str(value)})
              
              for value in response['data']:  #jeder Hauptdatensatz. (BTC, ETH, ...)
                log.info('Mode1#3: ' + str(value)) if debug == 1 else None
                for that in ['cmc_rank', 'total_supply', 'max_supply', 'circulating_supply']: # z.B. cmc_rank in BTC = 1
                  coinmarketmetric = '_'.join(['coin_market', that])
                  if value[that] is not None:
                    metric.add_sample(coinmarketmetric, value=float(value[that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})
                for price in [currency]: # z.B. "price" im Ersten BTC Datensatz in z.B. USD[]
                  for that in ['price', 'volume_24h', 'volume_change_24h', 'market_cap', 'percent_change_1h', 'percent_change_24h', 'percent_change_7d', 'percent_change_30d', 'percent_change_60d', 'percent_change_90d', 'market_cap_dominance', 'fully_diluted_market_cap']:
                    coinmarketmetric = '_'.join(['coin_market', that, price]).lower()
                    if value['quote'][price] is None:
                      continue
                    if value['quote'][price][that] is not None:
                      metric.add_sample(coinmarketmetric, value=float(value['quote'][price][that]), labels={'id': value['slug'], 'name': value['name'], 'symbol': value['symbol']})  
          
          #yield metric
      if MetricTrue == 1:
        yield metric

if __name__ == '__main__':
  try:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', nargs='?', const=9101, help='The TCP port to listen on', default=9101)
    parser.add_argument('--addr', nargs='?', const='0.0.0.0', help='The interface to bind to', default='0.0.0.0')
    args = parser.parse_args()
    log.info('listening on http://%s:%d/metrics' % (args.addr, args.port))
    log.info('DEBUG: ' + str(debug))
    
    REGISTRY.register(CoinCollector())
    start_http_server(int(args.port), addr=args.addr)

    while True:
      time.sleep(10)
  except KeyboardInterrupt:
    print(" Interrupted")
    exit(0)
