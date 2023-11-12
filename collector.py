from get_quote import GetQuote
import multiprocessing
import atexit
import time

my_symbols = [
    'AAPL'
]


def run_quote(symbol, file, interval=2, duration=300):
    with open(file, 'w') as f:
        quote = GetQuote(symbol)
        elapsed_time = 0
        f.write("time,epoch,price,isup,volume,isRealTime,bidPrice,askPrice,bidSize,askSize\n")
        while elapsed_time < duration:
            price = quote.get_quote()
            if quote.price == 0:
                break
            f.write(f"{quote.time.replace(',','')},{quote.epoch},{quote.price},{quote.isUp},{quote.volume},{quote.isReal},{quote.bidPrice},{quote.askPrice},{quote.bidSize},{quote.askSize}\n")
            time.sleep(interval)
            elapsed_time += interval

def close_files():
    for symbol in my_symbols:
        ## close the files
        pass


atexit.register(close_files)

jobs = {}
data_dir = "./data"
for symbol in my_symbols:
    file = f"{data_dir}/{symbol.lower()}.csv"
    run_quote(symbol, file)
