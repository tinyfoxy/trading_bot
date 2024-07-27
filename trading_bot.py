import ccxt
from web3 import Web3
import time
import threading

# Initialize exchange and contracts
okx = ccxt.okx({
    'apiKey': 'YOUR_OKX_API_KEY',
    'secret': 'YOUR_OKX_SECRET_KEY',
    'password': 'YOUR_OKX_API_PASSPHRASE',
})

w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/YOUR_INFURA_PROJECT_ID'))
dex_router_address = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'  # Uniswap V2 Router
dex_abi = [...]  # DEX Router ABI
dex_contract = w3.eth.contract(address=dex_router_address, abi=dex_abi)

# Global variables
PROFIT_RATE = 0.01  # 1% profit rate
AMOUNT = 1  # Trading amount
SYMBOL = 'ETH/USDT'
TOKEN_A = dex_contract.functions.WETH().call()
TOKEN_B = dex_contract.functions.USDT().call()

def get_dex_price(from_token, to_token, amount):
    amounts_out = dex_contract.functions.getAmountsOut(
        Web3.toWei(amount, 'ether'),
        [from_token, to_token]
    ).call()
    return amounts_out[1] / 1e6  # Assuming USDT has 6 decimal places

def create_cex_order(side, amount, price):
    return okx.create_limit_order(SYMBOL, side, amount, price)

def execute_dex_trade(from_token, to_token, amount):
    # Implement actual DEX trading logic here
    pass

def handle_partial_fill(order_id, symbol):
    order = okx.fetch_order(order_id, symbol)
    filled_amount = order['filled']
    remaining_amount = order['remaining']
    
    if filled_amount > 0:
        # Execute corresponding trade on DEX
        execute_dex_trade(TOKEN_A, TOKEN_B, filled_amount)
        print(f"Executed hedge trade of {filled_amount} on DEX")
    
    if remaining_amount > 0:
        # Decide how to handle remaining order
        current_price = okx.fetch_ticker(symbol)['last']
        if abs(current_price - order['price']) / order['price'] > 0.01:  # If price deviation exceeds 1%
            okx.cancel_order(order_id, symbol)
            print(f"Cancelled remaining order, amount: {remaining_amount}")
            # Option to place a new order or reassess market
        else:
            print(f"Keeping remaining order, amount: {remaining_amount}")
    
    return filled_amount, remaining_amount

def monitor_cex_sell_eth():
    while True:
        try:
            # Get DEX price (ETH to USDT)
            dex_eth_to_usdt_price = get_dex_price(TOKEN_A, TOKEN_B, AMOUNT)
            
            # CEX sell ETH strategy
            cex_sell_price = dex_eth_to_usdt_price * (1 + PROFIT_RATE)
            cex_sell_order = create_cex_order('sell', AMOUNT, cex_sell_price)
            
            order_active = True
            while order_active:
                current_dex_eth_to_usdt_price = get_dex_price(TOKEN_A, TOKEN_B, AMOUNT)
                
                if current_dex_eth_to_usdt_price * (1 + PROFIT_RATE/2) < cex_sell_price:
                    okx.cancel_order(cex_sell_order['id'], SYMBOL)
                    order_active = False
                    print("Sell order cancelled, price gap narrowed")
                else:
                    sell_order = okx.fetch_order(cex_sell_order['id'], SYMBOL)
                    if sell_order['status'] == 'closed':
                        execute_dex_trade(TOKEN_A, TOKEN_B, AMOUNT)
                        order_active = False
                        print("OKX sell order executed, buy trade executed on DEX")
                    elif sell_order['status'] == 'open' and sell_order['filled'] > 0:
                        filled, remaining = handle_partial_fill(sell_order['id'], SYMBOL)
                        if remaining == 0:
                            order_active = False
                
                time.sleep(5)  # Check every 5 seconds
            
            time.sleep(10)  # Wait before starting a new cycle
        
        except Exception as e:
            print(f"Error in sell ETH monitoring: {e}")
            time.sleep(60)  # Wait for 1 minute before continuing if an error occurs

def monitor_cex_buy_eth():
    while True:
        try:
            # Get DEX price (USDT to ETH)
            dex_usdt_to_eth_price = 1 / get_dex_price(TOKEN_B, TOKEN_A, AMOUNT * get_dex_price(TOKEN_A, TOKEN_B, AMOUNT))
            
            # CEX buy ETH strategy
            cex_buy_price = dex_usdt_to_eth_price * (1 - PROFIT_RATE)
            cex_buy_order = create_cex_order('buy', AMOUNT, cex_buy_price)
            
            order_active = True
            while order_active:
                current_dex_usdt_to_eth_price = 1 / get_dex_price(TOKEN_B, TOKEN_A, AMOUNT * get_dex_price(TOKEN_A, TOKEN_B, AMOUNT))
                
                if current_dex_usdt_to_eth_price * (1 - PROFIT_RATE/2) > cex_buy_price:
                    okx.cancel_order(cex_buy_order['id'], SYMBOL)
                    order_active = False
                    print("Buy order cancelled, price gap narrowed")
                else:
                    buy_order = okx.fetch_order(cex_buy_order['id'], SYMBOL)
                    if buy_order['status'] == 'closed':
                        execute_dex_trade(TOKEN_B, TOKEN_A, AMOUNT * cex_buy_price)
                        order_active = False
                        print("OKX buy order executed, sell trade executed on DEX")
                    elif buy_order['status'] == 'open' and buy_order['filled'] > 0:
                        filled, remaining = handle_partial_fill(buy_order['id'], SYMBOL)
                        if remaining == 0:
                            order_active = False
                
                time.sleep(5)  # Check every 5 seconds
            
            time.sleep(10)  # Wait before starting a new cycle
        
        except Exception as e:
            print(f"Error in buy ETH monitoring: {e}")
            time.sleep(60)  # Wait for 1 minute before continuing if an error occurs

def main():
    sell_thread = threading.Thread(target=monitor_cex_sell_eth)
    buy_thread = threading.Thread(target=monitor_cex_buy_eth)
    
    sell_thread.start()
    buy_thread.start()
    
    sell_thread.join()
    buy_thread.join()

if __name__ == "__main__":
    main()