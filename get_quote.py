import sys
import time
import requests
from requests import Request, Session
import json
import os

class GetQuote:
    def __init__(self, symbol):
        self.symbol = symbol
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Dnt": "1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "authority": "api.nasdaq.com",
            "path": f"/api/quote/{symbol}/info?assetclass=stocks"
        }
        self.url = f'https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=stocks'

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

    def get_quote(self):
        r = requests.get(self.url, headers=self.headers)
        if r.status_code != 200:
            # error getting the page
            print(r.content)
            return None
        data = r.content.decode('utf-8')

        dict_data = json.loads(data)
        try:
            price = dict_data['data']['primaryData']
            self.isReal = price['isRealTime']
            self.price = self.get_float(price['lastSalePrice'])
            self.isUp = True if price['deltaIndicator'] == 'up' else False
            self.volume = self.get_float(price['volume'])
            self.percentage = self.get_float(price['percentageChange'])
            self.time = price['lastTradeTimestamp']
            self.bidPrice = self.get_float(price['bidPrice'])
            self.askPrice = self.get_float(price['askPrice'])
            self.bidSize = self.get_float(price['bidSize'])
            self.askSize = self.get_float(price['askSize'])
            try:
                self.epoch = time.mktime(time.strptime(price['lastTradeTimestamp'], "%b %d, %Y %I:%M %p ET"))
            except:
                self.epoch = time.mktime(time.strptime(price['lastTradeTimestamp'], "%b %d, %Y"))
        except Exception as e:
            self.price = 0
            price = {
                "code": dict_data['status']['bCodeMessage'][0]['code'],
                "message": dict_data['status']['bCodeMessage'][0]['errorMessage']
            }
        return price

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