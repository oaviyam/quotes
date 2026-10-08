import sys
import time
import requests
from requests import Request, Session
import json
import os
import logging
import asyncio
import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# GetQuote class to fetch quotes from NASDAQ API one object per ticker
class GetQuote:
    def __init__(self, ticker):
        self.ticker = ticker
        logger.debug(f"Initializing GetQuote for {ticker}")
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Dnt": "1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "authority": "api.nasdaq.com",
            "path": f"/api/quote/{ticker}/info?assetclass=stocks"
        }
        self.url = f'https://api.nasdaq.com/api/quote/{ticker}/info?assetclass=stocks'

        # Current quote data
        self.isReal = False
        self.price = None
        self.isUp = False
        self.volume = None
        self.percentage = None
        self.time = None
        self.epoch = None
        self.bidPrice = None
        self.askPrice = None
        self.bidSize = None
        self.askSize = None
        self.marketOpen = False
        # History of quotes
        self.quote_history = []

    @classmethod
    def get_quote(self):
        """Fetch current quote from NASDAQ API and update object state"""
        logger.debug(f"Fetching quote for {self.ticker} from {self.url}")
        
        try:
            r = requests.get(self.url, headers=self.headers, timeout=10)
            logger.debug(f"API response status code: {r.status_code}")
            
            if r.status_code != 200:
                logger.error(f"HTTP error {r.status_code} for {self.ticker}: {r.content}")
                return None
                
            data = r.content.decode('utf-8')
            logger.debug(f"Response received for {self.ticker}, length: {len(data)} bytes")
            
            dict_data = json.loads(data)
            logger.debug(f"Parsed JSON data for {self.ticker}")
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching quote for {self.ticker}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception for {self.ticker}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {self.ticker}: {e}")
            return None
            
        try:
            price = dict_data['data']['primaryData']
            logger.debug(f"Primary data extracted for {self.ticker}")
            
            self.lastSalePrice = self.get_float(price['lastSalePrice'])
            self.netChange = self.get_float(price['netChange'])
            self.percentageChange = self.get_float(price['percentageChange'])
            self.deltaIndicator = price['deltaIndicator']
            self.lastTradeTimestamp = price['lastTradeTimestamp']
            self.time = price['lastTradeTimestamp']
            self.isRealTime = price['isRealTime']
            self.bidPrice = self.get_float(price['bidPrice'])
            self.askPrice = self.get_float(price['askPrice'])
            self.bidSize = self.get_float(price['bidSize'])
            self.askSize = self.get_float(price['askSize'])
            self.isUp = True if price['deltaIndicator'] == 'up' else False
            self.volume = self.get_float(price['volume'])
            self.percentage = self.get_float(price['percentageChange'])
            self.marketOpen = True if dict_data['data'].get('marketStatus') == 'Open' else False
            
            logger.info(f"{self.ticker}: ${self.lastSalePrice} ({self.deltaIndicator} {self.percentageChange}%), "
                       f"Volume: {self.volume}, RealTime: {self.isRealTime}, Market: {'Open' if self.marketOpen else 'Closed'}")
            
            try:
                self.epoch = time.mktime(time.strptime(price['lastTradeTimestamp'], "%b %d, %Y %I:%M %p ET"))
                logger.debug(f"Parsed timestamp with time: {self.epoch}")
            except:
                self.epoch = time.mktime(time.strptime(price['lastTradeTimestamp'], "%b %d, %Y"))
                logger.debug(f"Parsed timestamp without time: {self.epoch}")
            
            # Store in history
            self._add_to_history()
            logger.debug(f"Added quote to history for {self.ticker}, history size: {len(self.quote_history)}")
            
        except KeyError as e:
            logger.error(f"Key error parsing data for {self.ticker}: {e}")
            self.price = 0
            try:
                error_code = dict_data['status']['bCodeMessage'][0]['code']
                error_message = dict_data['status']['bCodeMessage'][0]['errorMessage']
                logger.error(f"API error for {self.ticker}: code={error_code}, message={error_message}")
                price = {
                    "code": error_code,
                    "message": error_message
                }
            except:
                logger.error(f"Unable to parse error message for {self.ticker}")
                price = {"code": "UNKNOWN", "message": "Unknown error"}
        except Exception as e:
            logger.error(f"Unexpected error parsing quote for {self.ticker}: {type(e).__name__}: {e}")
            self.price = 0
            price = {"code": "EXCEPTION", "message": str(e)}
            
        return price
    
    def _add_to_history(self):
        """Add current quote data to history"""
        quote_data = {
            'symbol': self.ticker,
            'time': self.time,
            'epoch': self.epoch,
            'price': self.lastSalePrice,
            'isUp': self.isUp,
            'volume': self.volume,
            'isReal': self.isRealTime,
            'bidPrice': self.bidPrice,
            'askPrice': self.askPrice,
            'bidSize': self.bidSize,
            'askSize': self.askSize,
            'percentage': self.percentage
        }
        self.quote_history.append(quote_data)
        logger.debug(f"Quote data added to history for {self.ticker}")
    
    def collect_quotes(self, file_handle, interval=5, duration=30):
        """
        Collect quotes at regular intervals and write to file
        
        Args:
            file_handle: Open file handle to write data to
            interval: Time in seconds between quote fetches (default: 5)
            duration: Total duration in seconds to collect quotes (default: 30)
        """
        logger.info(f"Starting collection for {self.ticker}: interval={interval}s, duration={duration}s")
        elapsed_time = 0
        iteration = 0
        
        while elapsed_time < duration:
            iteration += 1
            logger.debug(f"Collection iteration {iteration} for {self.ticker} (elapsed: {elapsed_time}s/{duration}s)")
            
            price = self.get_quote()
            if hasattr(self, 'price') and self.price == 0:
                logger.error(f"Error fetching quote for {self.ticker}, stopping collection")
                break
            
            # Write to file
            self._write_quote_to_file(file_handle)
            logger.debug(f"Quote written to file for {self.ticker}")
            
            if elapsed_time + interval < duration:
                logger.debug(f"Sleeping for {interval} seconds before next fetch for {self.ticker}")
                time.sleep(interval)
            
            elapsed_time += interval
        
        logger.info(f"Completed collection for {self.ticker}: {iteration} iterations, {len(self.quote_history)} quotes collected")
    
    def _write_quote_to_file(self, file_handle):
        """Write current quote data to file"""
        time_str = self.time.replace(',', '') if self.time else ''
        line = f"{self.ticker},{time_str},{self.epoch},{self.lastSalePrice},{self.isUp},{self.volume},{self.isRealTime},{self.bidPrice},{self.askPrice},{self.bidSize},{self.askSize}\n"
        file_handle.write(line)
        file_handle.flush()
        logger.debug(f"Wrote quote line for {self.ticker}: price={self.lastSalePrice}")
    
    def get_history(self):
        """Return the complete history of quotes collected"""
        return self.quote_history
    
    def clear_history(self):
        """Clear the quote history"""
        self.quote_history = []
    
    # ==================== ASYNC METHODS ====================
    
    async def get_quote_async(self, session):
        """Fetch current quote from NASDAQ API asynchronously and update object state"""
        logger.debug(f"Fetching quote async for {self.ticker} from {self.url}")
        
        try:
            async with session.get(self.url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                logger.debug(f"API response status code: {response.status}")
                
                if response.status != 200:
                    content = await response.text()
                    logger.error(f"HTTP error {response.status} for {self.ticker}: {content}")
                    return None
                    
                data = await response.text()
                logger.debug(f"Response received for {self.ticker}, length: {len(data)} bytes")
                
                dict_data = json.loads(data)
                logger.debug(f"Parsed JSON data for {self.ticker}")
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching quote for {self.ticker}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Request exception for {self.ticker}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {self.ticker}: {e}")
            return None
            
        try:
            price = dict_data['data']['primaryData']
            logger.debug(f"Primary data extracted for {self.ticker}")
            
            self.lastSalePrice = self.get_float(price['lastSalePrice'])
            self.netChange = self.get_float(price['netChange'])
            self.percentageChange = self.get_float(price['percentageChange'])
            self.deltaIndicator = price['deltaIndicator']
            self.lastTradeTimestamp = price['lastTradeTimestamp']
            self.time = price['lastTradeTimestamp']
            self.isRealTime = price['isRealTime']
            self.bidPrice = self.get_float(price['bidPrice'])
            self.askPrice = self.get_float(price['askPrice'])
            self.bidSize = self.get_float(price['bidSize'])
            self.askSize = self.get_float(price['askSize'])
            self.isUp = True if price['deltaIndicator'] == 'up' else False
            self.volume = self.get_float(price['volume'])
            self.percentage = self.get_float(price['percentageChange'])
            self.marketOpen = True if dict_data['data'].get('marketStatus') == 'Open' else False
            
            logger.info(f"{self.ticker}: ${self.lastSalePrice} ({self.deltaIndicator} {self.percentageChange}%), "
                       f"Volume: {self.volume}, RealTime: {self.isRealTime}, Market: {'Open' if self.marketOpen else 'Closed'}")
            
            try:
                self.epoch = time.mktime(time.strptime(price['lastTradeTimestamp'], "%b %d, %Y %I:%M %p ET"))
                logger.debug(f"Parsed timestamp with time: {self.epoch}")
            except:
                self.epoch = time.mktime(time.strptime(price['lastTradeTimestamp'], "%b %d, %Y"))
                logger.debug(f"Parsed timestamp without time: {self.epoch}")
            
            # Store in history
            self._add_to_history()
            logger.debug(f"Added quote to history for {self.ticker}, history size: {len(self.quote_history)}")
            
        except KeyError as e:
            logger.error(f"Key error parsing data for {self.ticker}: {e}")
            self.price = 0
            try:
                error_code = dict_data['status']['bCodeMessage'][0]['code']
                error_message = dict_data['status']['bCodeMessage'][0]['errorMessage']
                logger.error(f"API error for {self.ticker}: code={error_code}, message={error_message}")
                price = {
                    "code": error_code,
                    "message": error_message
                }
            except:
                logger.error(f"Unable to parse error message for {self.ticker}")
                price = {"code": "UNKNOWN", "message": "Unknown error"}
        except Exception as e:
            logger.error(f"Unexpected error parsing quote for {self.ticker}: {type(e).__name__}: {e}")
            self.price = 0
            price = {"code": "EXCEPTION", "message": str(e)}
            
        return price
    
    async def collect_quotes_async(self, file_handle, interval=5, duration=30):
        """
        Collect quotes at regular intervals asynchronously and write to file
        
        Args:
            file_handle: Open file handle to write data to
            interval: Time in seconds between quote fetches (default: 5)
            duration: Total duration in seconds to collect quotes (default: 30)
        """
        logger.info(f"Starting async collection for {self.ticker}: interval={interval}s, duration={duration}s")
        elapsed_time = 0
        iteration = 0
        
        async with aiohttp.ClientSession() as session:
            while elapsed_time < duration:
                iteration += 1
                logger.debug(f"Collection iteration {iteration} for {self.ticker} (elapsed: {elapsed_time}s/{duration}s)")
                
                price = await self.get_quote_async(session)
                if hasattr(self, 'price') and self.price == 0:
                    logger.error(f"Error fetching quote for {self.ticker}, stopping collection")
                    break
                
                # Write to file
                self._write_quote_to_file(file_handle)
                logger.debug(f"Quote written to file for {self.ticker}")
                
                if elapsed_time + interval < duration:
                    logger.debug(f"Sleeping for {interval} seconds before next fetch for {self.ticker}")
                    await asyncio.sleep(interval)
                
                elapsed_time += interval
            
            logger.info(f"Completed async collection for {self.ticker}: {iteration} iterations, {len(self.quote_history)} quotes collected")

    @staticmethod
    def get_price_from_csv(line):
        return line.rstrip().split(',')

    @staticmethod
    def get_file_hanlde(file):
        return open(file)

    def get_quote_mock(self, file):
        f = None
        if not os.path.isfile(file):
            return None
        if not f:
            f = self.get_file_hanlde(file)
        yield self.get_price_from_csv(f.readline())
    @staticmethod
    def get_float(string_number):
        if string_number == "N/A":
            return None
        return float(string_number.replace('$', '').replace('%', '').replace(',', ''))


if __name__ == '__main__':
    aapl = GetQuote('AAPL')
    aapl_price = aapl.get_quote()
    print(aapl.price)
    amzn = GetQuote('AMZN')
    amzn_price = amzn.get_quote()
    print(amzn.price)


'''
error:
{"data":null,"message":null,"status":{"rCode":200,"bCodeMessage":[{"code":3004,"errorMessage":"Error while calling vendor"}],"developerMessage":null}}
off hours:
{"data":{"symbol":"AAPL","companyName":"Apple Inc. Common Stock","stockType":"Common Stock","exchange":"NASDAQ-GS","isNasdaqListed":true,"isNasdaq100":true,"isHeld":false,"primaryData":{"lastSalePrice":"$176.65","netChange":"-0.92","percentageChange":"-0.52%","deltaIndicator":"down","lastTradeTimestamp":"Nov 3, 2023","isRealTime":false,"bidPrice":"N/A","askPrice":"N/A","bidSize":"N/A","askSize":"N/A","volume":"79,829,246"},"secondaryData":null,"marketStatus":"Closed","assetClass":"STOCKS","keyStats":{"fiftyTwoWeekHighLow":{"label":"52 Week Range:","value":"124.17 - 198.23"},"dayrange":{"label":"High/Low:","value":"173.35 - 176.82"}},"notifications":[{"headline":"HIGH TECHNICAL ATTRIBUTE","eventTypes":[{"message":"AAPL has a High Technical Rating by Nasdaq Dorsey Wright. Discover why technical analysis matters","eventName":"High Technical Attribute","url":{"label":"Discover why technical analysis matters","value":"https://www.nasdaq.com/solutions/nasdaq-dorsey-wright/technical-analysis"},"id":"tech_attribute"}]}]},"message":null,"status":{"rCode":200,"bCodeMessage":null,"developerMessage":null}}
{"data":{"symbol":"NVR","companyName":"NVR, Inc. Common Stock","stockType":"Common Stock","exchange":"NYSE","isNasdaqListed":false,"isNasdaq100":false,"isHeld":false,"primaryData":{"lastSalePrice":"$5,890.63","netChange":"+191.72","percentageChange":"+3.36%","deltaIndicator":"up","lastTradeTimestamp":"Nov 3, 2023","isRealTime":false,"bidPrice":"N/A","askPrice":"N/A","bidSize":"N/A","askSize":"N/A","volume":"22,002"},"secondaryData":null,"marketStatus":"Closed","assetClass":"STOCKS","keyStats":{"fiftyTwoWeekHighLow":{"label":"52 Week Range:","value":"4,027.04 - 6,525.00"},"dayrange":{"label":"High/Low:","value":"5,811.71 - 5,961.82"}},"notifications":[]},"message":null,"status":{"rCode":200,"bCodeMessage":null,"developerMessage":null}}
pre-market
{"data":{"symbol":"AAPL","companyName":"Apple Inc. Common Stock","stockType":"Common Stock","exchange":"NASDAQ-GS","isNasdaqListed":true,"isNasdaq100":true,"isHeld":false,"primaryData":{"lastSalePrice":"$176.96","netChange":"+0.31","percentageChange":"+0.18%","deltaIndicator":"up","lastTradeTimestamp":"Nov 6, 2023 5:08 AM ET","isRealTime":true,"bidPrice":"$176.96","askPrice":"$177.02","bidSize":"1","askSize":"100","volume":"51,986"},"secondaryData":{"lastSalePrice":"$176.65","netChange":"-0.92","percentageChange":"-0.52%","deltaIndicator":"down","lastTradeTimestamp":"Closed at Nov 3, 2023 4:00 PM ET","isRealTime":false,"bidPrice":"","askPrice":"","bidSize":"","askSize":"","volume":""},"marketStatus":"Pre-Market","assetClass":"STOCKS","keyStats":{"fiftyTwoWeekHighLow":{"label":"52 Week Range:","value":"124.17 - 198.23"},"dayrange":{"label":"High/Low:","value":"NA"}},"notifications":[{"headline":"HIGH TECHNICAL ATTRIBUTE","eventTypes":[{"message":"AAPL has a High Technical Rating by Nasdaq Dorsey Wright. Discover why technical analysis matters","eventName":"High Technical Attribute","url":{"label":"Discover why technical analysis matters","value":"https://www.nasdaq.com/solutions/nasdaq-dorsey-wright/technical-analysis"},"id":"tech_attribute"}]}]},"message":null,"status":{"rCode":200,"bCodeMessage":null,"developerMessage":null}}
'''