import asyncio
import datetime
import random

import aiohttp
from aiohttp_socks import ProxyType, ProxyConnector, ChainProxyConnector
from tenacity import retry, stop_after_attempt, stop_after_delay

from inputs.config import MOBILE_PROXY_CHANGE_IP_LINK, MOBILE_PROXY
from .utils import Web3Utils, logger
from .utils.file_manager import str_to_file


class Web3Go:
    def __init__(self, key: str, proxy: str = None):
        self.web3_utils = Web3Utils(key=key)
        # self.proxy = f'http://{proxy}' if proxy else None

        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'uk-UA,uk;q=0.9',
            'Connection': 'keep-alive',
            'Origin': 'https://reiki.web3go.xyz',
            'Referer': 'https://reiki.web3go.xyz/taskboard',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-App-Channel': 'DIN',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }

        self.session = None
        self.proxy = proxy

    async def define_proxy(self, proxy: str):
        if MOBILE_PROXY:
            await Web3Go.change_ip()
            self.proxy = MOBILE_PROXY

        if proxy is not None:
            self.proxy = proxy

        connector = self.proxy and ProxyConnector.from_url(f'http://{self.proxy}')
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            trust_env=True,
            connector=connector
        )

    @staticmethod
    async def change_ip():
        async with aiohttp.ClientSession() as session:
            await session.get(MOBILE_PROXY_CHANGE_IP_LINK)

    @retry(stop=stop_after_attempt(20))
    async def login(self):
        url = 'https://reiki.web3go.xyz/api/account/web3/web3_challenge'
        params = await self.get_login_params()
        address = params["address"]
        nonce = params["nonce"]
        msg = f"reiki.web3go.xyz wants you to sign in with your Ethereum account:\n{address}\n\n{params['challenge']}\n\nURI: https://reiki.web3go.xyz\nVersion: 1\nChain ID: 56\nNonce: {nonce}\nIssued At: {Web3Go.get_utc_timestamp()}"

        json_data = {
            'address': address,
            'nonce': nonce,
            'challenge': '{"msg":"' + msg.replace('\n', '\\n') + '"}',
            'signature': self.web3_utils.get_signed_code(msg),
        }

        response = await self.session.post(url, json=json_data)

        res_json = await response.json()
        auth_token = res_json.get("extra", {}).get("token")

        if auth_token:
            self.upd_login_token(auth_token)

        return bool(auth_token)

    @retry(stop=stop_after_attempt(20))
    async def get_login_params(self):
        url = 'https://reiki.web3go.xyz/api/account/web3/web3_nonce'

        json_data = {
            'address': self.web3_utils.acct.address,
        }

        response = await self.session.post(url, json=json_data, ssl=False)

        return await response.json()

    def upd_login_token(self, token: str):
        self.session.headers["Authorization"] = f"Bearer {token}"

    @retry(stop=stop_after_attempt(20))
    async def claim(self):
        url = 'https://reiki.web3go.xyz/api/checkin'

        params = {
            'day': self.get_current_date(),
        }

        response = await self.session.put(url, params=params)

        assert await response.text() == "true"
        return True

    async def roll_up_lottery(self, lottery_step: int = 2000):
        leafs = await self.get_leaf_amount()

        if leafs < lottery_step:
            logger.info(f"{self.web3_utils} | Not enough leafs to spin: {leafs} leafs")
            return

        while leafs >= lottery_step:
            await asyncio.sleep(random.uniform(3, 5))
            prize = await self.spin_lottery()
            leafs -= lottery_step
            logger.info(f"{self.web3_utils} | Prize: {prize} | Leafs left: {leafs}")

    @retry(stop=stop_after_attempt(5))
    async def get_lottery_result(self):
        url = 'https://reiki.web3go.xyz/api/lottery/offchain'

        response = await self.session.get(url)

        return await response.json()

    async def get_leaf_amount(self):
        resp_json = await self.get_lottery_result()
        return resp_json["userGoldLeafCount"]

    @retry(stop=stop_after_attempt(5))
    async def spin_lottery(self):
        url = "https://reiki.web3go.xyz/api/lottery/try"

        response = await self.session.post(url)
        resp_json = await response.json()

        return resp_json["prize"]

    async def logout(self):
        await self.session.close()

    @staticmethod
    def get_current_date():
        return datetime.datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def get_utc_timestamp():
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def logs(self, file_name: str, msg_result: str = ""):
        address = self.web3_utils.acct.address
        file_msg = f"{address}|{self.proxy}"
        str_to_file(f"./logs/{file_name}.txt", file_msg)
        msg_result = msg_result and " | " + str(msg_result)

        if file_name == "success":
            logger.success(f"{address}{msg_result}")
        else:
            logger.error(f"{address}{msg_result}")