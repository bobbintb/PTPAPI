from bs4 import BeautifulSoup as bs4

def raise_for_cloudflare(text):
    """Raises an exception if a CloudFlare error page is detected

    :param text: a raw html string"""
    soup = bs4(text, "html.parser")
    if soup.find(class_="cf-error-overview") is not None:
        msg = '-'.join(soup.find(class_="cf-error-overview").get_text().splitlines())
        raise PTPAPIException("Encountered Cloudflare error page: ", msg)

def snarf_cover_view_data(text):
    """Grab cover view data directly from an html source
    and parse out any relevant infomation we can

    :param text: a raw html string
    :rtype: a dictionary of movie data"""
    data = []
    for json_data in re.finditer(r'coverViewJsonData\[\s*\d+\s*\]\s*=\s*({.*});', text):
        data.extend(json.loads(json_data.group(1))['Movies'])
        for movie in data:
            movie['Title'] = HTMLParser.HTMLParser().unescape(movie['Title'])
            movie['Torrents'] = []
            for group in movie['GroupingQualities']:
                for torrent in group['Torrents']:
                    soup = bs4(torrent['Title'], "html.parser")
                    torrent['Codec'], torrent['Container'], torrent['Source'], torrent['Resolution'] = [item.strip() for item in soup.a.text.split('/')[0:4]]
                    torrent['GoldenPopcorn'] = (soup.contents[0].string.strip(' ') == u'\u10047') # 10047 = Unicode GP symbol pylint: disable=line-too-long
                    torrent['ReleaseName'] = soup.a['title'].split('\n')[-1]
                    match = re.search(r'torrents.php\?id=(\d+)&torrentid=(\d+)', soup.a['href'])
                    torrent['Id'] = match.group(2)
                    movie['Torrents'].append(torrent)
    return data

def creds_from_conf(filename):
    """Pull user, password, and passkey information from a file

    :param filename: an absolute filename
    :rtype: a diction of the username, password and passkey"""
    config_file = configparser.ConfigParser()
    config_file.read(filename)
    return {'username': config_file.get('PTP', 'username'),
            'password': config_file.get('PTP', 'password'),
            'passkey': config_file.get('PTP', 'passkey')}
