# This is a utility file to support the scraping and cleaning of Newegg data
import pandas as pd
import numpy as np
import requests
import bs4
import re
from collections import OrderedDict
import time
import random

def get_product_html(url, soup=False):
    # Returns raw HTML of passed url
    r = requests.get(url)
    if soup == True:
        return bs4.BeautifulSoup(r.text, 'lxml')
    else:
        return r.text

def get_components(html):
    '''Grabs all available PC components from Newegg webpage. 
       ====Parameters====
       soup: BeautifulSoup object (use get_soup() function)
       ====Returns====
       this_computer: OrderedDict mapping this computer's variables to values
    '''
    soup = bs4.BeautifulSoup(html, 'lxml')
    new_link = None
    # Grab link from product page
    for s in soup.find_all('link', href=True):
        if s['rel'][0] == 'canonical':
            new_link = s['href']
            break

    new_link = new_link + '&ignorebbr=1'

    #new_link = f'https://www.newegg.com/Product/Product.aspx?Item={item_no}&ignorebbr=1'
    # Narrow down to specifications part of page
    specs = soup.find('div', class_='plinks')

    if specs == None:
        return None
    # All categories of technical specifications in dt tags
    categories = specs.find_all('dt')
    # All details of technical specifications in dd tags
    details = specs.find_all('dd')
    
    this_computer = OrderedDict()

    this_computer['link'] = new_link
    
    for cat, det in zip(categories, details):
        # raw detail is always located here
        try:
            raw_det = det.contents[0]
        except:
            continue
        
        # in some cases, have to go one tag deeper to get category name
        if type(cat.contents[0]) == bs4.element.Tag:
                raw_cat = cat.contents[0].contents[0]
        else:
            raw_cat = cat.contents[0]
            
        this_computer[raw_cat] = raw_det
    return this_computer

def get_prices_and_links(html):
    # Grabs all 96 prices from the product array page
    soup = bs4.BeautifulSoup(html, 'lxml')
    price_link = []
    
    product_array = soup.find_all('div', class_='item-container')

    for prod in product_array:
        price_span = prod.find('span', class_='price-current-label')

        try:
            price = price_span.findNextSibling().contents[0]

        except AttributeError:
            price = np.nan
    
        link = prod.find('a', href=True)['href']

        price_link.append((price, link))

    return price_link

def get_links(product_array):    
    # Returns a list of 96 product links on a product list page
    prod_links = []

    for prod in product_array:
        prod_links.append(prod.find('a', href=True)['href'])
        
    return prod_links

def one_page_scrape(url):
    '''
       Scrapes one product array page as well as each product on that page. 96 products plus
       one set of prices for each of these products is returned in the HTML of dataframes.
       ====Parameters====
       url: url of product array page to be scraped
    '''
    prices_df = pd.DataFrame(columns=['price_html'])
    products_df = pd.DataFrame(columns=['component_html'])
    
    r = requests.get(url)
    
    array_page_html = pd.DataFrame(data = [r.text], columns=['price_html'])
    prices_df = prices_df.append(array_page_html)
    
    soup = bs4.BeautifulSoup(r.text, 'lxml')
    
    # Grab array holding all 96 products
    product_array = soup.find_all('div', class_='item-container')
    # Get links for each of those products
    prod_links = get_links(product_array)
    
    # Scrape the html of each of those products
    counter = 0
    for prod_url in prod_links:
        counter += 1
        print(f'About to scrape page {counter}')
        time.sleep(5 + 5*random.random())
        html = get_product_html(prod_url)
        current_page_html = pd.DataFrame(data = [html], columns=['component_html'])
        products_df = products_df.append(current_page_html)
        
    return prices_df, products_df

def scrape_all(url_list, master_prices, master_components, up_to):
    # Scrapes all pages in url_list
    for url in url_list[:up_to]:
        products, prices = one_page_scrape(url)
        
        master_prices.append(prices)
        master_components.append(products)
        
        master_prices.to_csv('master_price_html.csv')
        master_components.to_csv('master_component_html.csv')
        
    return master_prices, master_components

def extract_load(components, prices):
    '''
        Parses HTML of two dataframes and merges them in to a single dataframe.
        ====Parameters====
        components: html of individual computer pages
        prices: html of product array page with 96 products
        ====Returns====
        merged: dataframe with prices corresponding to components
    '''

    
    # Some dataframes have Unnamed: 0 column
    try:
        prices.drop(labels=['Unnamed: 0.1', 'Unnamed: 0', 'component_html'], axis=1, inplace=True)
        components.drop(labels=['Unnamed: 0.1', 'Unnamed: 0', 'price_html'], axis=1, inplace=True)

    # Some don't
    except (KeyError, ValueError):
        prices.drop(labels=['component_html'], axis=1, inplace=True)
        components.drop(labels=['price_html'], axis=1, inplace=True)
    
    components = components.apply(lambda x: get_components(x[0]), axis=1)

    prices = prices.apply(lambda x: get_prices_and_links(x[0]), axis=1)

    concat_prices = list()
    
    for price in prices:
        concat_prices.extend(price)
    
    components = components.dropna()
    
    components = pd.DataFrame.from_records(components.values)    
    
    # Concatenate all rows in to one list of prices and links
    
                
    prices = pd.DataFrame(concat_prices)
    prices.columns = ['price', 'link']
    
    merged = prices.merge(components, on='link', how='outer')
    
    return merged

# ============Cleaning functions===========

def processor_brand(processor):
    # Return the first word in the processor description (usually the brand)
    return processor.split(' ')[0]

def num_cores(processor):
    # Returns the number of cores in a processor
    processor = processor.upper()
    
    if ('6-CORE' in processor) or ('6 CORE' in processor) or ('I7' in processor):
        return 6
    elif ('4-CORE' in processor) or ('4 CORE' in processor) or ('QUAD' in processor) or ('I5' in processor):
        return 4
    elif ('2-CORE' in processor) or ('2 CORE' in processor) or ('DUAL' in processor) or ('DUO' in processor) or ('I3' in processor):
        return 2
    elif ('SINGLE' in processor) or ('PENTIUM' in processor):
        return 1
    else:
        return np.nan

def ram_cap(memory):
    # Returns RAM capacity
    memory = memory.upper()

    mem_list = memory.split(' ')

    try:
        gb_ind = mem_list.index('GB')
        
        return mem_list[gb_ind - 1]
    except:
        return np.nan

def ram_type(memory):
    # Returns type of RAM (DDR2, DDR3, or DDR4)
    memory = memory.upper()
    if 'DDR2' in memory:
        return 'ddr2'
    elif 'DDR3' in memory:
        return 'ddr3'
    elif 'DDR4' in memory:
        return 'ddr4'
    else:
        return np.nan

def disk_cap(storage):
    # Returns the disk capacity of a hard disk (will also grab first letter of storage unit GB or TB)
    storage = storage.upper()
    stor_split = storage.split('B')
    return stor_split[0]

def ssd_or_hdd(ssd):
    # Check contents of storage for keywords indicating disk type
    ssd = ssd.upper()
    
    if ('GB' in ssd) or ('TB' in ssd):
        return 'ssd'
    else:
        return 'hdd'

def storage_cap(storage):
    cap = 0

    storage = storage.split(' ')
    try:
        num = int(storage[0])
    except ValueError:
        return np.nan
    units = storage[1]

    if units.upper() == 'GB':
        cap += num
    elif units.upper() == 'TB':
        cap += 1024*num

    return cap

def storage_cap2(storage):
    units = re.findall(r'(GB|TB)', storage)
    

def get_brand(brand):
    brand = brand.upper()

    if ('LENOVO' in brand) or ('THINKCENTRE' in brand):
        return 'LENOVO'
    elif ('HP' in brand) or ('HEWLETT-PACKARD' in brand):
        return 'HP'
    elif 'DELL' in brand:
        return 'DELL'
    else:
        return np.nan

def clean_store_cap(cap):
    
    pat = re.compile(r'\d*')

    try:
        num = re.findall(pat, cap)[0]
        num = int(num)
    except:
        return np.nan

    if 'TB' in cap:
        return num*1024
    elif 'GB' in cap:
        return num

def graphics_type(graphics):
    # Decides if graphics is AMD, Nvidia, or integrated based on keywords
    graphics = graphics.upper()

    if ('INTEL' in graphics) or ('INTEGRATED' in graphics):
        return 'INTEGRATED'
    elif 'NVIDIA' in graphics:
        return 'NVIDIA'
    elif 'AMD' in graphics:
        return 'AMD'
    else:
        return np.nan
    
def form_factor(form):
    form = form.upper()

    if ('TOWER' in form) or ('DESKTOP' in form):
        return 'TOWER'
    elif 'NAN' in form:
        return np.nan
    else:
        return 'SMALL'
