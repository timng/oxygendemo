#!/usr/bin/env python
# -*- coding: utf-8 -*-
import scrapy
from scrapy.http import Request, FormRequest
from scrapy.spiders import CrawlSpider
from oxygendemo.items import *

from scrapy.conf import settings
import re
from pyquery import PyQuery as pq

class OxygenSpider(CrawlSpider):
    """ Spider for site : http://oxygenboutique.com
    """
    name = "oxygenboutique.com"

    allowed_domains = ['oxygenboutique.com']

    # Set header for request, to make it look like real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:43.0) Gecko/20100101 Firefox/43.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive'
    }

    start_url = 'http://www.oxygenboutique.com/'
    base_url  = 'http://www.oxygenboutique.com/'
    base_url2 = 'http://www.oxygenboutique.com'
    sitemap_url = 'http://www.oxygenboutique.com/sitemap.xml'

    url_set_currency = 'http://www.oxygenboutique.com/Currency.aspx'

    currencies = ['USD', 'GBP', 'EUR']

    # product_type mapping table, from category to product_type
    # All product list in category A will have product_type = type_map['A']
    type_map = {
        'clothing' : 'A',     # apparel
        'shoes' : 'S',        # shoes
        'accessories' : 'R',  # accessories
        'ring': 'J',          # jewelry
        'necklace': 'J',
        'bracelet' : 'J',
        'tattoos': 'J'
    }

    def __init__(self):
        # Setting scrapy params
        settings.set('RETRY_HTTP_CODES', [503, 504, 400, 408, 404] )
        settings.set('RETRY_TIMES', 5)
        settings.set('REDIRECT_ENABLED', True)
        settings.set('METAREFRESH_ENABLED', True)

        # Excluded categories
        self.EXCLUDE_CATEGORY_LEVEL_1 = [
            # 'designers',
            'look book'
        ]

    def start_requests(self):
        """ Function for: Start parsing - Called after __init__
            spider start from here
        """
        # We start 3 sessions for 3 curreny options.
        # session No.0 -> USD
        # session No.1 -> GBP
        # session No.2 -> EUR
        session_id=0
        for currency in self.currencies:
            yield Request(
                url=self.url_set_currency,
                callback=self.parse_set_currency,
                headers=self.headers,
                meta={'cookiejar': session_id, 'currency': currency},
                dont_filter=True
            )
            session_id+=1

    def parse_set_currency(self, response):
        """  Parse response from url_set_currency
        """
        page = pq(response.body)
        page.remove_namespaces()  # Remove namespace in hmtl document

        # Find data key of currency in POST form
        currency = response.meta['currency']
        currency_form_value = page("#ddlCurrency > option:contains('(%s)')" % currency).eq(0).attr['value']
 
        formdata  = {
            '__EVENTTARGET':'lnkCurrency',
            '__EVENTARGUMENT':'',
            '__VIEWSTATE':'',
            '__VIEWSTATEGENERATOR':'',
            'ddlCountry1':'United Kingdom',
            'ddlCurrency':'%s' % currency_form_value
        }

        # Find __VIEWSTATE and __EVENTARGUMENT
        inputs = page('input[type=hidden]')
        for i in range(0, len(inputs)):
            node = inputs.eq(i)
            name  = node.attr['name']
            value = node.attr['value']
            if name in formdata and value != '':
                formdata[name] = value

        # Make POST request to submit set currency form
        yield FormRequest(
            url = self.url_set_currency,
            formdata=formdata,
            callback= self.parse_start_url,
            meta={'cookiejar': response.meta['cookiejar'], 'currency': response.meta['currency']},
            headers= self.headers,
            dont_filter=True
        )      

    def parse_start_url(self, response):
        """ Parse response from POST request which sent to url_set_currency
        """
        if response.meta['currency'] == 'USD':
            # In USD session, load home page to scrape products
            yield Request(
                url = self.start_url,
                callback= self.parse_category,
                headers= self.headers,
                meta={'cookiejar': response.meta['cookiejar']},
                dont_filter=True
            )
        else:
            # In GBP, EUR session, do nothing
            print 'Set currency successful for: %s' % response.meta['currency']

    def parse_category(self, response):
        """ Parse all categories & subcategory
        """
        page = pq(response.body)
        page.remove_namespaces()

        # Contains list of (category_url, category)
        requests = []

        # Find all category level 1
        tags = page('ul.topnav > li')
        for i in range(0, len(tags)):
            # Get category's name
            cat1 = tags.eq(i).find('a').eq(0).text().lower()
            
            # Check if cat1 in exclude list or not
            if cat1 not in self.EXCLUDE_CATEGORY_LEVEL_1:
                # Find all subcategory (category_level_2)
                tagAs = tags.eq(i).find('a')
                for k in range(0, len(tagAs)):
                    # Get subcategory's name
                    cat2 = tagAs.eq(k).text().lower()
                    if cat2 == 'all' or cat2 == 'new in':
                        continue

                    href = self.base_url + tagAs.eq(k).attr['href']

                    # Find product type for all product in category_level_2
                    if cat2 not in self.type_map and cat1 in self.type_map:
                        # set product_type of subcategory to it's parent's product_type
                        self.type_map[cat2] = self.type_map[cat1]

                    requests.append([href, cat2])

        for req in requests:
            href = req[0]
            cat2 = req[1]

            if cat2 in self.type_map:
                product_type = self.type_map[cat2]
            else:
                product_type = ''

            yield Request(
                url = href,
                callback= self.parse_item_list,
                headers= self.headers,
                meta={'cookiejar': response.meta['cookiejar'], 'product_type': product_type},
                dont_filter=True,
                priority=1
            )


        # # Some product avaible in sitemap but not display in categories
        # yield Request(
        #     url = self.sitemap_url,
        #     callback= self.parse_sitemap,
        #     headers= self.headers,
        #     meta={'cookiejar': response.meta['cookiejar']},
        #     dont_filter=True,
        #     priority=1
        # )

    def parse_item_list(self, response):
        """ Parse products in category page
        """
        page = pq(response.body)
        page.remove_namespaces()

        # Find all product category page 
        tags = page('div.itm > div > a:nth-child(2)')
        for i in range(0, len(tags)):
            href = self.base_url + tags.eq(i).attr['href']
            yield Request(
                url = href,
                callback= self.parse_item,
                headers= self.headers,
                meta={'cookiejar': response.meta['cookiejar'], 'product_type': response.meta['product_type']},
                priority=3           # higher priority 
            )

        # Next page
        tags  = page('a.NextPage')
        if len(tags) > 0:
            href = self.base_url2 + tags.eq(0).attr['href']
            yield Request(
                url = href,
                callback= self.parse_item_list,
                headers= self.headers,
                meta={'cookiejar': response.meta['cookiejar'], 'product_type': response.meta['product_type']},
                dont_filter=True,
                priority=2
            )

    # def parse_sitemap(self, response):
    #     for url in re.findall(r'<loc>([^<]+)', response.body.replace(u'\x00', '')):
    #         url = url.strip()
    #         # yield Request(
    #         #     url = href,
    #         #     callback= self.parse_item,
    #         #     headers= self.headers,
    #         #     meta={'cookiejar': response.meta['cookiejar'], 'product_type': ''
    #         #     },
    #         #     priority=2
    #         # )
            
    def parse_item(self, response):
        """ Function for: Parse product information
        """
        page = pq(response.body)
        page.remove_namespaces()

        item = OxygendemoItem()

        item['type'] = response.meta['product_type']

        item['gender'] = 'F'                          # This website contain product for women
        item['designer'] = page('#ctl00_ContentPlaceHolder1_AnchorDesigner').text()

        # http://www.oxygenboutique.com/Geena-Jumpsuit.aspx -> geena-jumpsuit
        item['code'] = response.request.url.split('.aspx', 1)[0].split('/')[-1].lower()

        item['name'] = page('#container > div.right > h2').text()

        # Get desciption
        item['description'] = page('#accordion > div:nth-child(2)').text()

        # Get sizing and details
        item['description'] += '. ' + page('#accordion > div:nth-child(4) > div').text()

        # This website doesn't present color of product
        # Product Name: Mason Long Sleeve Wrap Dress in Cranberry -> color: Cranberry
        if ' in ' in item['name']:
            item['raw_color'] = item['name'].split(' in ', 1)[1].strip()
        else:
            item['raw_color'] = None

        item['image_urls'] = []
        images = page('#thumbnails-container img')
        for i in range(0, len(images)):
            item['image_urls'].append( self.base_url2 + images.eq(i).attr['src'] )

        # Get origin price in USD
        item['usd_price'] = self.getPrice(page).replace('$', '')

        # Get sale price in USD
        item['sale_discount']  = page('#container > div.right > span > span:not(.mark)').text().replace('$', '')

        # Calc discount percen 
        if item['sale_discount'] == '':
            item['sale_discount'] = 0
        else:
            item['sale_discount'] = float(item['sale_discount']) * 100 / float(item['usd_price'])
            item['sale_discount'] = float("%.2f" % item['sale_discount'])


        stock_status = {}

        # Get list of sizes
        tags = page('#ctl00_ContentPlaceHolder1_ddlSize > option')
        for i in range(1, len(tags)):
            txt = tags.eq(i).text()
            size = txt.split('-', 1)[0].strip()
            if 'Sold Out' in txt:
                stock_status[size] = 1  # out of stock
            else:
                stock_status[size] = 3  # in stock

        item['stock_status'] = stock_status

        item['link'] = response.request.url


        item['eur_price'] = ''
        item['gbp_price'] = ''


        # Guess product_type by it's name & designer
        if item['type'] == '':
            item['type'] = None
            name = ' %s %s ' % (item['name'], item['designer'])
            name = name.lower()
            for cat in self.type_map:
                product_type = self.type_map[cat]
                cat = ' %s ' % cat
                if cat in name:
                    item['type'] = product_type
                    break
        
        # Load url of this product in session of GBP to get GBP price
        yield Request(
            url = response.request.url,
            callback= self.parse_gbp_price,
            headers= self.headers,
            meta={'cookiejar': 1, 'item': item },     # Cookiejar of GBP is 1
            priority=4,
            dont_filter=True
        )


    def parse_gbp_price(self, response):
        """ Parse GBP price
        """
        item = response.meta['item']
        page = pq(response.body)
        page.remove_namespaces()

        item['gbp_price'] =  self.getPrice(page).replace(u'\xa3', '')

        # Load url of this product in session of EUR to get EUR price
        yield Request(
            url = response.request.url,
            callback= self.parse_eur_price,
            headers= self.headers,
            meta={'cookiejar': 2, 'item': item },     # Cookiejar of EUR is 2
            priority=5,                               # Set this as highest priority, so it will reduce requests, item in Queue
            dont_filter=True
        )

    def parse_eur_price(self, response):
        """ Parse EUR price
        """
        item = response.meta['item']
        page = pq(response.body)
        page.remove_namespaces()

        item['eur_price'] = self.getPrice(page).replace(u'\u20ac', '')

        return item

    def getPrice(self, page):
        """  get product origin price
             Return as string, includeed currency sign
        """
        # Get Original price  of product which has sale price - http://www.oxygenboutique.com/Evie-Blouse.aspx
        price = page('#container > div.right > span > span.mark').text()
        if price != '':
            return price
        else:
            # Product has only 1 price, Regular price - http://www.oxygenboutique.com/Stripe-Crochet-Poncho-by-Mira%20Mikati.aspx
            return page('#container > div.right > span').text()


