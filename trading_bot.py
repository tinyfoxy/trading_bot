import ccxt
import time
import threading
from web3 import Web3

# Configuration parameters
SYMBOL = 'ETH/USDT'
AMOUNT = 1  # Trading amount (ETH)
PROFIT_RATE = 0.01  # Expected profit rate
TOKEN_A = '0x...'  # ETH contract address
TOKEN_B = '0x...'  # USDT contract address

# Initialize exchange and Web3 connection
okx = ccxt.okx({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET',
    'password': 'YOUR_PASSWORD',
})

w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/YOUR_INFURA_PROJECT_ID'))
dex_contract = w3.eth.contract(address='DEX_CONTRACT_ADDRESS', abi=DEX_ABI)

def get_dex_price(token_in, token_out, amount):
    """Get the price from DEX for a given token pair and amount."""
    amount_in = Web3.toWei(amount, 'ether')
    amounts_out = dex_contract.functions.getAmountsOut(amount_in, [token_in, token_out]).call()
    return Web3.fromWei(amounts_out[1], 'ether')

def execute_dex_trade(from_token, to_token, amount):
    """Execute a trade on DEX."""
    deadline = int(time.time()) + 600  # 10 minutes from now
    path = [from_token, to_token]
    amount_in = Web3.toWei(amount, 'ether')
    
    amounts_out = dex_contract.functions.getAmountsOut(amount_in, path).call()
    min_amount_out = int(amounts_out[-1] * 0.99)  # 1% slippage tolerance
    
    transaction = dex_contract.functions.swapExactTokensForTokens(
        amount_in,
        min_amount_out,
        path,
        w3.eth.default_account,
        deadline
    ).buildTransaction({
        'from': w3.eth.default_account,
        'gas': 200000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(w3.eth.default_account),
    })
    
    signed_txn = w3.eth.account.sign_transaction(transaction, private_key='YOUR_PRIVATE_KEY')
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return tx_receipt

def create_cex_order(side, amount, price):
    """Create an order on the centralized exchange."""
    return okx.create_order(SYMBOL, 'limit', side, amount, price)

def get_cex_current_price(symbol):
    """Get the current market price from the centralized exchange."""
    ticker = okx.fetch_ticker(symbol)
    return ticker['last']

def calculate_final_buy_price(theoretical_buy_price, symbol):
    """Calculate the final buy price considering the current market price."""
    current_market_price = get_cex_current_price(symbol)
    return min(theoretical_buy_price, current_market_price)

def calculate_final_sell_price(theoretical_sell_price, symbol):
    """Calculate the final sell price considering the current market price."""
    current_market_price = get_cex_current_price(symbol)
    return max(theoretical_sell_price, current_market_price)

def monitor_order_and_price_difference(order_id, symbol, is_buy_order):
    """Monitor an order and cancel it if the price difference becomes unfavorable."""
    while True:
        try:
            order = okx.fetch_order(order_id, symbol)
            if order['status'] not in ['open', 'partial']:
                break
            
            if is_buy_order:
                dex_price = get_dex_price(TOKEN_B, TOKEN_A, AMOUNT)
            else:
                dex_price = get_dex_price(TOKEN_A, TOKEN_B, AMOUNT)
            
            price_difference = abs(order['price'] - dex_price) / dex_price
            
            if price_difference < PROFIT_RATE:
                okx.cancel_order(order_id, symbol)
                print(f"Order {order_id} cancelled due to insufficient price difference")
                break
            
            time.sleep(5)
        except Exception as e:
            print(f"Error in monitoring order {order_id}: {e}")
            time.sleep(60)

def handle_partial_fill(order, filled_amount):
    """Handle partial fill of an order by executing a corresponding trade on DEX."""
    try:
        if order['side'] == 'buy':
            dex_trade_result = execute_dex_trade(TOKEN_A, TOKEN_B, filled_amount)
        else:
            dex_trade_result = execute_dex_trade(TOKEN_B, TOKEN_A, filled_amount)
        print(f"Executed hedge trade of {filled_amount} on DEX. Transaction hash: {dex_trade_result['transactionHash'].hex()}")
    except Exception as e:
        print(f"Error executing DEX trade for partial fill: {e}")

def monitor_cex_buy_eth():
    """Monitor and execute buy orders on CEX and corresponding sell orders on DEX."""
    while True:
        try:
            dex_usdt_to_eth_price = get_dex_price(TOKEN_B, TOKEN_A, AMOUNT)
            theoretical_buy_price = dex_usdt_to_eth_price * (1 - PROFIT_RATE)
            final_buy_price = calculate_final_buy_price(theoretical_buy_price, SYMBOL)
            
            cex_buy_order = create_cex_order('buy', AMOUNT, final_buy_price)
            
            threading.Thread(target=monitor_order_and_price_difference, 
                             args=(cex_buy_order['id'], SYMBOL, True)).start()
            
            order_active = True
            while order_active:
                buy_order = okx.fetch_order(cex_buy_order['id'], SYMBOL)
                if buy_order['status'] == 'closed':
                    try:
                        dex_trade_result = execute_dex_trade(TOKEN_B, TOKEN_A, AMOUNT * final_buy_price)
                        print(f"OKX buy order executed, sell trade executed on DEX. Transaction hash: {dex_trade_result['transactionHash'].hex()}")
                    except Exception as e:
                        print(f"Error executing DEX trade: {e}")
                    order_active = False
                elif buy_order['status'] == 'canceled':
                    print("Buy order was canceled")
                    order_active = False
                elif buy_order['status'] == 'partial':
                    filled_amount = buy_order['filled']
                    handle_partial_fill(buy_order, filled_amount)
                
                time.sleep(5)
        except Exception as e:
            print(f"Error in buy monitoring: {e}")
            time.sleep(60)

def monitor_cex_sell_eth():
    """Monitor and execute sell orders on CEX and corresponding buy orders on DEX."""
    while True:
        try:
            dex_eth_to_usdt_price = get_dex_price(TOKEN_A, TOKEN_B, AMOUNT)
            theoretical_sell_price = dex_eth_to_usdt_price * (1 + PROFIT_RATE)
            final_sell_price = calculate_final_sell_price(theoretical_sell_price, SYMBOL)
            
            cex_sell_order = create_cex_order('sell', AMOUNT, final_sell_price)
            
            threading.Thread(target=monitor_order_and_price_difference, 
                             args=(cex_sell_order['id'], SYMBOL, False)).start()
            
            order_active = True
            while order_active:
                sell_order = okx.fetch_order(cex_sell_order['id'], SYMBOL)
                if sell_order['status'] == 'closed':
                    try:
                        dex_trade_result = execute_dex_trade(TOKEN_B, TOKEN_A, AMOUNT * final_sell_price)
                        print(f"OKX sell order executed, buy trade executed on DEX. Transaction hash: {dex_trade_result['transactionHash'].hex()}")
                    except Exception as e:
                        print(f"Error executing DEX trade: {e}")
                    order_active = False
                elif sell_order['status'] == 'canceled':
                    print("Sell order was canceled")
                    order_active = False
                elif sell_order['status'] == 'partial':
                    filled_amount = sell_order['filled']
                    handle_partial_fill(sell_order, filled_amount)
                
                time.sleep(5)
        except Exception as e:
            print(f"Error in sell monitoring: {e}")
            time.sleep(60)

# Start monitoring threads
threading.Thread(target=monitor_cex_buy_eth).start()
threading.Thread(target=monitor_cex_sell_eth).start()

# Main loop to keep the program running
while True:
    time.sleep(1)