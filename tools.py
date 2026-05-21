import json
import requests,re,time
from markdownify import markdownify as md
import constants

class Client:
    def __init__(self):
        self.__session = requests.Session()
        self.__username = constants.USERNAME
        self.__password = constants.PASSWORD
        self.__logged_in = False

    @property
    def session(self)->requests.Session:
        return self.__session
    @property
    def username(self)->str:
        return self.__username
    @property
    def password(self)->str:
        return self.__password
    @property
    def logged_in(self)->bool:
        return self.__logged_in

    @username.setter
    def username(self, username):
        self.__username = username
    @password.setter
    def password(self, password):
        self.__password = password
    @session.setter
    def session(self, session):
        self.__session = session
    @logged_in.setter
    def logged_in(self, logged_in):
        if type(logged_in) == bool:
            self.__logged_in = logged_in

client = Client()

def login():
    loginPage=client.session.get(constants.BASE_URL+"/inteyvat/").text
    result=re.search(r"<input type=\"hidden\" id=\"jstokenCSRF\" name=\"tokenCSRF\" value=\"(.+)\">",loginPage)
    token = result.group(1) if result else None
    if not result:
        return False

    status=client.session.post(constants.BASE_URL+"/inteyvat/",data={
        "tokenCSRF": token,
        "username": client.username,
        "password": client.password,
        "remember": "true"})

    if "logout" in status.text:
        client.logged_in = True
        return True
    return False

def fetch_article_list():
    articleListPage=client.session.get(constants.BASE_URL+"/").text
    pattern=r"<h2 class=\"title\" itemprop=\"headline\">\n.+<a class=\"text-dark\" href=\"(.+)\" itemprop=\"url\">(.+)</a>"
    result=re.findall(pattern,articleListPage)
    results=[]
    for i in range(len(result)):
        results.append({
            "url": result[i][0],
            "title": result[i][1]
        })
    return results

def fetch_article_content(url):
    url=json.loads(url)
    articlePage=client.session.get(url).text
    titlePattern=r"<h1 class=\"title\" itemprop=\"headline\">(.+)</h1>"
    title=re.search(titlePattern,articlePage).group(1)
    contentPattern=r"<div class=\"page-content\" itemprop=\"articleBody\">([\s\S]+?)</div>"
    result=re.search(contentPattern,articlePage).group(1)
    return {"title": title, "content": md(result), "url": url}

def post_article(params):
    if client.logged_in==False:
        return "ERROR, NOT LOGGED IN"

    params=json.loads(params)
    title=params["title"]
    content=params["content"]
    slug = params["slug"]
    page=client.session.get(constants.BASE_URL+"/inteyvat/new-content").text
    csrf = re.search(r"<input type=\"hidden\" id=\"jstokenCSRF\" name=\"tokenCSRF\" value=\"(.+?)\">", page).group(1)
    uuid = re.search(r"<input type=\"hidden\" id=\"jsuuid\" name=\"uuid\" value=\"(.+?)\">",page).group(1)
    if csrf=="" or uuid=="":
        return "ERROR, FAILED TO GET CSRF TOKEN OR UUID"
    now=time.localtime(time.time())
    response = client.session.post(constants.BASE_URL+"/inteyvat/new-content",data={"tokenCSRF":csrf,"uuid":uuid,"slug":slug,"title":title,"content":content,"date":f"{now[0]}-{now[1]:02}-{now[2]:02} {now[3]:02}:{now[4]:02}:{now[5]:02}","typeSelector":"published","type":"published"})
    return True

TOOLLIST=[login,fetch_article_list, fetch_article_content, post_article]

if __name__ == "__main__":
    print(login())
    #print(fetch_article_list())
    # print(client.session.get(constants.BASE_URL+"/inteyvat").text)
    post_article("{\"title\": \"My New Post\",\"content\": \"# This is the content of my new post\\n\\nThis is a sample blog post content in markdown format.\",\"slug\":\"test\"}")
    #print(fetch_article_content(constants.BASE_URL+"/%E8%AD%A6%E6%83%95%E3%83%AF%E3%83%BC%E3%83%AB%E3%83%89%E3%82%A4%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%B3-world-is-mine"))