from datetime import datetime
from Connect import XTSConnect
import json
import pandas as pd
import requests
import os
import pickle
import math

INTERACTIVE_API_KEY = "********************"
INTERACTIVE_API_SECRET = "**********"
MARKET_DATA_API_KEY = "***********"
MARKET_DATA_API_SECRET = "***************"
source = "WEBAPI"


class TradingStrategy:
    def __init__(self):
        self.xt_interactive = XTSConnect(
            INTERACTIVE_API_KEY, INTERACTIVE_API_SECRET, source
        )
        self.xt_marketdata = XTSConnect(
            MARKET_DATA_API_KEY, MARKET_DATA_API_SECRET, source
        )
        self.xt_interactive.interactive_login()
        self.xt_marketdata.marketdata_login()
        print("Login Success with MarketData")
        self.positionList = []
        self.instruments_file = "instruments.csv"
        self.instrument_df = self.load_instruments()

    def load_position_list(self, pickle_file):
        try:
            with open(pickle_file, "rb") as file:
                self.position_list = pickle.load(file)
            return self.position_list
        except FileNotFoundError:
            print("Position list pickle file not found.")
            return []
        except Exception as e:
            print("Error occurred while loading the position list:", str(e))
            return []

    def load_instruments(self):
        # Check if the instruments file was created today
        if os.path.exists(self.instruments_file):
            creation_time = os.path.getctime(self.instruments_file)
            creation_date = datetime.fromtimestamp(creation_time).date()
            today_date = datetime.now().date()

            if creation_date == today_date:
                print("Reading existing instruments file.")
                instrument_df = pd.read_csv(self.instruments_file)
                instrument_df.set_index("symbol", inplace=True)
                return instrument_df

        # Delete old file and create a new one
        if os.path.exists(self.instruments_file):
            os.remove(self.instruments_file)
        print("Generating Instrument file.")
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        request = requests.get(url=url, verify=False)
        data = request.json()
        instrument_df = pd.DataFrame(data)
        instrument_df.to_csv(self.instruments_file)
        instrument_df.set_index("symbol", inplace=True)
        return instrument_df

    def fetch_atm_strike(self):
        xts_market_data = XTSConnect(
            MARKET_DATA_API_KEY, MARKET_DATA_API_SECRET, source
        )
        xts_market_data.marketdata_login()
        response = xts_market_data.get_quote(
            Instruments=[{"exchangeSegment": 1, "exchangeInstrumentID": 26001}],
            xtsMessageCode=1512,
            publishFormat="JSON",
        )
        quote_data = response.get("result", {}).get("listQuotes", [])
        if quote_data:
            quote_dict = json.loads(quote_data[0])
            banknifty_price = float(quote_dict["LastTradedPrice"])
            atm_strike = round(banknifty_price / 100) * 100
        else:
            atm_strike = None

        return atm_strike

    def get_token_and_exchange(self, name):
        symbol_token = self.instrument_df.loc[name]["token"]
        return symbol_token

    def place_order(self, token, strike_price, option_type, order_side="SELL"):
        exchange_segment = self.xt_interactive.EXCHANGE_NSEFO
        order_type = self.xt_interactive.ORDER_TYPE_MARKET
        validity = self.xt_interactive.VALIDITY_DAY
        try:
            response = self.xt_interactive.place_order(
                exchangeSegment=exchange_segment,
                exchangeInstrumentID=token,
                productType=self.xt_interactive.PRODUCT_NRML,
                orderType=order_type,
                orderSide=order_side,
                timeInForce=validity,
                orderQuantity=25,
                disclosedQuantity=0,
                limitPrice=0,
                stopPrice=0,
                orderUniqueIdentifier="temp1",
                clientID="*****",
            )
            xts_orderid = response["result"]["AppOrderID"]
            print(f"XTS order placed successfully: {xts_orderid}")
        except Exception as e:
            print("Error in order placement:", str(e))
            print("Response:", response)

    def get_option_ltp(self, token):
        xts_market_data = XTSConnect(
            MARKET_DATA_API_KEY, MARKET_DATA_API_SECRET, source
        )
        xts_market_data.marketdata_login()
        response = xts_market_data.get_quote(
            Instruments=[{"exchangeSegment": 2, "exchangeInstrumentID": token}],
            xtsMessageCode=1501,
            publishFormat="JSON",
        )
        quote_data = response.get("result", {}).get("listQuotes", [])
        if quote_data:
            quote_dict = json.loads(quote_data[0])
            ltp = quote_dict["LastTradedPrice"]
            return float(ltp)
        return None

    def create_short_straddle(self, atm_strike):
        if len(self.positionList) > 0:
            print("Position already running")
            return
        call_strike_price = atm_strike
        put_strike_price = atm_strike
        call_option_name = "BANKNIFTY06JUL23" + str(call_strike_price) + "CE"
        put_option_name = "BANKNIFTY06JUL23" + str(put_strike_price) + "PE"
        call_token = self.get_token_and_exchange(call_option_name)
        put_token = self.get_token_and_exchange(put_option_name)
        try:
            self.place_order(call_token, call_strike_price, "CE")
            self.place_order(put_token, put_strike_price, "PE")
            print("Short Straddle Created")
        except Exception as e:
            print(e)
        # Add trade information to positionList
        CE_Strike_LTP = self.get_option_ltp(call_token)
        PE_Strike_LTP = self.get_option_ltp(put_token)

        self.positionList.append(
            {
                "Strike": call_option_name,
                "EntryPrice": CE_Strike_LTP,
                "type": "Position",
            }
        )
        self.positionList.append(
            {"Strike": put_option_name, "EntryPrice": PE_Strike_LTP, "type": "Position"}
        )

        pickle_file = "positionList.pickle"

        with open(pickle_file, "wb") as file:
            pickle.dump(self.positionList, file)
        print(self.positionList)

    def CalculateMTM(self, atm_strike):
        call_strike_price = atm_strike
        put_strike_price = atm_strike
        call_option_name = "BANKNIFTY06JUL23" + str(call_strike_price) + "CE"
        put_option_name = "BANKNIFTY06JUL23" + str(put_strike_price) + "PE"
        call_token = self.get_token_and_exchange(call_option_name)
        put_token = self.get_token_and_exchange(put_option_name)
        call_ltp = self.get_option_ltp(call_token)
        put_ltp = self.get_option_ltp(put_token)
        if os.path.exists("M2M.pickle"):
            with open("M2M.pickle", "rb") as file:
                real_time_pnl = pickle.load(file)
        else:
            real_time_pnl = 0
        print(call_ltp, " CE LTP")
        print(put_ltp, " PE LTP")

        for i, position in enumerate(self.positionList):
            if i % 2 == 0:
                # Subtract call_ltp in even iterations
                real_time_pnl += (position["EntryPrice"] - call_ltp) * 25
            else:
                # Subtract put_ltp in odd iterations
                real_time_pnl += (position["EntryPrice"] - put_ltp) * 25
        return real_time_pnl

    def square_positions(self):
        for position in self.positionList:
            token = self.get_token_and_exchange(position["Strike"])
            exchange_segment = self.xt_interactive.EXCHANGE_NSEFO
            order_type = self.xt_interactive.ORDER_TYPE_MARKET
            order_side = "BUY" if position["type"] == "Position" else "SELL"
            validity = self.xt_interactive.VALIDITY_DAY
            try:
                self.xt_interactive.place_order(
                    exchangeSegment=exchange_segment,
                    exchangeInstrumentID=token,
                    productType=self.xt_interactive.PRODUCT_NRML,
                    orderType=order_type,
                    orderSide=order_side,
                    timeInForce=validity,
                    orderQuantity=25,
                    disclosedQuantity=0,
                    limitPrice=0,
                    stopPrice=0,
                    orderUniqueIdentifier="temp1",
                    clientID="*****",
                )
                print(f"XTS order placed successfully: {position['Strike']}")
            except Exception as e:
                print("Error in order placement:", str(e))

        if os.path.exists("positionList.pickle"):
            os.remove("positionList.pickle")
            print(f"Pickle file  deleted.")
        else:
            print(f"Pickle file  not found.")

    def take_Insurance(self, atm_strike):
        print(len(self.positionList), "Leangth")
        if len(self.positionList) < 2:
            print("Running previous insurance")
            return
        call_option_name = "BANKNIFTY06JUL23" + str(atm_strike) + "CE"
        put_option_name = "BANKNIFTY06JUL23" + str(atm_strike) + "PE"
        call_token = self.get_token_and_exchange(call_option_name)
        put_token = self.get_token_and_exchange(put_option_name)
        a = int(self.get_option_ltp(call_token))
        b = int(self.get_option_ltp(put_token))
        call_strike_price = atm_strike + round((a + b) * 2 / 100) * 100
        put_strike_price = atm_strike - round((a + b) * 2 / 100) * 100

        print(call_strike_price, "CE")
        print(put_strike_price, "PE")
        CE_Insurance_Token = self.get_token_and_exchange(
            "BANKNIFTY06JUL23" + str(call_strike_price) + "CE"
        )
        PE_Insurance_Token = self.get_token_and_exchange(
            "BANKNIFTY06JUL23" + str(put_strike_price) + "PE"
        )
        self.place_order(CE_Insurance_Token, call_strike_price, "CE", "BUY")
        self.place_order(PE_Insurance_Token, put_strike_price, "PE", "BUY")

    def run_strategy(self):
        pickle_file = "positionList.pickle"
        self.positionList = self.load_position_list(pickle_file)
        atm_strike = self.fetch_atm_strike()
        self.create_short_straddle(atm_strike)
        self.take_Insurance(atm_strike)
        call_strike_price = atm_strike
        put_strike_price = atm_strike
        call_option_name = "BANKNIFTY06JUL23" + str(call_strike_price) + "CE"
        put_option_name = "BANKNIFTY06JUL23" + str(put_strike_price) + "PE"
        call_token = self.get_token_and_exchange(call_option_name)
        put_token = self.get_token_and_exchange(put_option_name)

        while True:
            CE_Price = self.get_option_ltp(call_token)
            PE_Price = self.get_option_ltp(put_token)

            if (int(CE_Price) / int(PE_Price)) >= 2 or (
                int(PE_Price) / int(CE_Price)
            ) >= 2:
                with open("M2M.pickle", "wb") as file:
                    pickle.dump(self.CalculateMTM(atm_strike), file)
                self.square_positions()
                atm_strike_New = self.fetch_atm_strike()
                self.create_short_straddle(atm_strike_New)
                print("New Position Created")

            pnl = self.CalculateMTM(atm_strike)
            print("M2M ", pnl)

            if pnl <= -1500:
                # Square all positions
                self.square_positions()
                print("Position Sqared off")
                break


strr = TradingStrategy()
strr.run_strategy()
