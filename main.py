from database.db import DbConnection
from web_driver.wd import WebDriver

db_conn = DbConnection()
market = db_conn.get_market()
url = market.marketplace_info.link

webdriver = WebDriver(market, db_conn)

webdriver.load_url(url)
webdriver.bidder()
# webdriver.quit()
