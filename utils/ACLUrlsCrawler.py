import pymongo
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

import utils.LevelUrls as lu


def log(str):
    with open("../url.text", "a") as f:
        f.write(str)


class ACLUrlsCrawler:
    def __init__(self):
        self.baseUrl = "https://www.aclweb.org"
        '''
        约定 https://www.aclweb.org/anthology/ 为顶层
             https://www.aclweb.org/anthology/venues/anlp/ 为2级
             https://www.aclweb.org/anthology/events/anlp-2000/ 为1级
             https://www.aclweb.org/anthology/A00-1000/ 为0级
        '''
        self.database = "ACLAnthology"  # 爬取的url将要保存的数据库名

        self.collection = "Urls"  # 爬取的url将要保存的表名
        self.finishflag = "finish" #爬取url结束后保存的表名，有内容表明可以直接从数据库中读，否则爬取url
        self.client = pymongo.MongoClient("mongodb://localhost:27017/")

    def getACLUrls(self):
        ACLUlrs = []
        if self.checkIfhasScrawl():
            # 已经爬取过，从数据库中获取未爬取过的url
            ACLUlrs +=  self.getUnvisitedUrls()
        else:
            # 爬取所有论文的url并保存在数据库中
            print("start to crawl paper urls...")
            ACLUlrs += self.getUrlsfromTopLevel(self.baseUrl + "/anthology/")
        print("urls downloading done")
        return ACLUlrs

    def get_content(self, url):
        try:
            user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.109 " \
                         "Safari/537.36 "
            response = requests.get(url, headers={'User-Agent': user_agent})
            response.raise_for_status()  # 如果返回的状态码不是200， 则抛出异常;
            response.encoding = response.apparent_encoding  # 判断网页的编码格式， 便于respons.text知道如何解码;
        except Exception as e:
            print("爬取错误")
        else:
            # print(response.url)
            return response.content

    def getUrlsfromFirstLevel(self, firstlevel: str):
        '''
        :param firstlevel: 1级url ttps://www.aclweb.org/anthology/events/anlp-2000/
        :return: 返回0级url
        '''
        try:
            content = self.get_content(firstlevel)
            soup = BeautifulSoup(content, 'lxml')
            papers = soup.find_all(name="p", attrs={"class": "align-items-stretch"})
            paperUrls = []
            for paper in papers:
                paperUrl = paper.find(name="strong").find("a")["href"]
                paperUrls.append(self.baseUrl + paperUrl)
            return paperUrls
        except Exception as e:
            lu.ErrorUrlManeger(firstlevel,e)
            return []

    def getUrlsfromSecondLevel(self, secondlevel: str):
        '''
        :param secondlevel: 2级url https://www.aclweb.org/anthology/venues/anlp/
        :return:
        '''
        try:
            content = self.get_content(secondlevel)
            soup = BeautifulSoup(content, 'lxml')
            paperAccordingToYear = soup.find_all(name="div", attrs={"class": "row"})
            FirstLevelUrls = []
            for paper in paperAccordingToYear:
                yearUrl = paper.find(name="h4").find(name="a")['href']
                FirstLevelUrls.append(self.baseUrl + yearUrl)

            paperUrls = []
            pbar = tqdm(FirstLevelUrls)
            for FirstLevelUrl in pbar:
                pbar.set_description("Crawling %s" % FirstLevelUrl)
                partUrls = self.getUrlsfromFirstLevel(FirstLevelUrl)
                log("\t"+FirstLevelUrl + ":" + str(len(partUrls))+"\n")
                paperUrls += partUrls
            # print(paperUrls)
            return paperUrls
        except Exception as e:
            lu.ErrorUrlManeger(secondlevel,e)
            return []

    def getUrlsfromTopLevel(self, toplevel: str):
        '''
        :param toplevel: 网站入口 https://www.aclweb.org/anthology/
        :return:
        '''
        secondLevelManager = lu.SecondLevelManager()
        SecondLevelUrls = []
        if secondLevelManager.getSecondLevelUrls() == None:
            content = self.get_content(toplevel)
            print(content)
            soup = BeautifulSoup(content, 'lxml')
            tbodies = soup.find_all(name="tbody")
            for tbody in tbodies:
                for venue in tbody.find_all(name="th"):
                    try:
                        # print(venue.find(name="a")['href'])
                        SecondLevelUrls.append(self.baseUrl + venue.find(name="a")['href'])
                    except Exception as e:
                        pass
            secondLevelManager.saveSecondLevelUrls(SecondLevelUrls)
        else:
            SecondLevelUrls +=secondLevelManager.getSecondLevelUrls()
        paperUrls = []

        pbar = tqdm(SecondLevelUrls)
        for secondLevelUrl in pbar:
            pbar.set_description("Crawling %s" % secondLevelUrl)
            log("From " + secondLevelUrl + ":\n")
            partUrls = self.getUrlsfromSecondLevel(secondLevelUrl)
            if(len(partUrls) ==0):
                continue
            self.saveUrls(partUrls)
            log("total paper :{length}\n".format(length = len(partUrls)))
            secondLevelManager.updateSecondLevelUrls(secondLevelUrl)
            paperUrls += partUrls

        log("total paper in site:{length}\n".format(length=len(self.getACLUrls())))
        self.finishFlag()
        # print("total:{}".foramt(len(paperUrls)))
        return paperUrls

    def saveUrls(self, urls):
        '''
        保存爬取的url
        :param urls:
        :return:
        '''

        db = self.client[self.database]
        col = db[self.collection]
        urlsInDB = col.find({}, {"url": 1})
        urlsInDB = [urls['url'] for urls in urlsInDB]

        Urls = []
        for url in urls:
            if(url in urlsInDB):
                # 去重
                continue
            else:
                Urls.append({"url": url, "visit": False})
        if (len(Urls) == 0):
            return
        col.insert_many(Urls)

    def checkIfhasScrawl(self):
        '''
        检查是否已经爬取过url
        :return:
        '''
        db = self.client[self.database]
        col = db[self.finishflag]
        if (col.find_one() !=None):
            return True
        else:
            return False

    def getUnvisitedUrls(self):
        '''
        获取数据库中已保存且未爬取的url
        :return:
        '''
        db = self.client[self.database]
        col = db[self.collection]
        urls = col.find({"visit": False}, {"url": 1})
        urls = [url['url'] for url in urls]
        return urls

    def getAllUrls(self):
        '''
            获取数据库中所有的url
            :return:
        '''
        db = self.client[self.database]
        col = db[self.collection]
        urls = col.find({}, {"url": 1})
        urls = [url['url'] for url in urls]
        return urls

    def finishFlag(self):
        db = self.client[self.database]
        col = db[self.finishflag]
        col.insert_one({"finish": True})

    def updateUrl(self, url):
        '''
            已经爬过的url更新数据库的visit标记
        :param url:
        :return:
        '''
        db = self.client[self.database]
        col = db[self.collection]
        col.update_one({"url": url}, {"$set": {"visit": True}})

# if __name__ == '__main__':
#     aclscrawler = ACLUrlsCrawler()
#     print(aclscrawler.getACLUrls())