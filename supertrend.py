from Connect import XTSConnect
import json

def fetch_banknifty_ltp():
    MARKET_DATA_API_KEY = "e07d7541fc005710991935"
    MARKET_DATA_API_SECRET = "Uwpd306$Lf"
    source = "WEBAPI"

    xt_marketdata = XTSConnect(MARKET_DATA_API_KEY, MARKET_DATA_API_SECRET, source)
    response_marketdata = xt_marketdata.marketdata_login()

    instruments = [{'exchangeSegment': 1, 'exchangeInstrumentID': 26001}]

    # Get Quote Request
    response = xt_marketdata.get_quote(
        Instruments=instruments,
        xtsMessageCode=1501,
        publishFormat='JSON'
    )

    if response and "result" in response and "listQuotes" in response["result"]:
        list_quotes = response["result"]["listQuotes"]

        if list_quotes:
            quote_data = json.loads(list_quotes[0])
            banknifty_price = quote_data["LastTradedPrice"]
            return banknifty_price

    return None

# Loop to fetch live data
while True:
    ltp = fetch_banknifty_ltp()
    if ltp is not None:
        print("Bank Nifty LTP:", ltp)
    else:
        print("Failed to fetch Bank Nifty LTP.")
    
    # Add a delay or sleep if needed
    # time.sleep(1)  # Uncomment this line if you want to add a delay between each fetch
